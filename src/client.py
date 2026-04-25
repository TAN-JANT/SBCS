import os
from tkinter import filedialog, messagebox,simpledialog
from struct import pack, unpack
from command import COMMAND 
import tkinter as tk
import socket as sc
import time
import json
import zipfile ,io
from threading import Thread
from pathlib import Path

UDP_PORT = 5000
TCP_PORT = 5001 # Server'ın dinlediği TCP portu

SBCS_DATA_PATH = os.path.join(Path.home(), ".local/share/sbcs")
JSON_FILE = os.path.join(SBCS_DATA_PATH, "info.json")


def initialize_json():
    # 1. Klasör yoksa oluştur (Masaüstünde test ederken hata almamak için)
    if not os.path.exists(SBCS_DATA_PATH):
        try:
            os.makedirs(SBCS_DATA_PATH, exist_ok=True)
        except PermissionError:
            # Eğer /usr/share altına yazamazsa (local test) mevcut dizine dön
            print("Sistem dizinine erişim yok, yerel dizin kullanılıyor.")
            return "info.json"
    
    # 2. Dosya yoksa varsayılan verilerle oluştur
    if not os.path.exists(JSON_FILE):
        default_data = {"id": sc.gethostname()} # Varsayılan olarak makine adını ver
        try:
            with open(JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4)
            print(f"Yeni yapılandırma dosyası oluşturuldu: {JSON_FILE}")
        except Exception as e:
            print(f"Dosya oluşturma hatası: {e}")
    
    return JSON_FILE

class Client:
    def __init__(self,id="Client"):
        self.id = id

    def recv_fixed_length(self, sock, length):
        data = b''
        while len(data) < length:
            packet = sock.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return data

    def get_data(self, sock):
        data_length = self.recv_fixed_length(sock, 8)
        if not data_length:
            return None
        data_length = unpack('!Q', data_length)[0]
        data = self.recv_fixed_length(sock, data_length)
        if not data:
            return None
        return data.decode()

    def discover(self):
        udp = sc.socket(sc.AF_INET, sc.SOCK_DGRAM)
        udp.setsockopt(sc.SOL_SOCKET, sc.SO_BROADCAST, 1)
        udp.settimeout(1.5)

        udp.sendto(pack('!B', COMMAND.DISCOVER.value), ("255.255.255.255", UDP_PORT))

        devices = []
        start = time.time()
        while time.time() - start < 5:
            try:
                # 1 yerine geniş bir buffer okuyoruz
                data, addr = udp.recvfrom(1024) 
                if len(data) < 9: continue # En az CMD(1) + SIZE(8) olmalı

                cmd = unpack('!B', data[:1])[0]
                if cmd == COMMAND.ACTIVE.value:
                    name_len = unpack('!Q', data[1:9])[0]
                    # Kalan veriden ismi çekiyoruz
                    name = data[9:9+name_len].decode()
                    # Server'ın gerçek TCP portunu burada kullanmalısın
                    devices.append((name, addr[0], 5001)) 
            except sc.timeout:
                break # Zaman aşımı olunca döngüden çık
            except Exception as e:
                print(f"UDP Error: {e}")
        return devices

    def _send_packet(self, ip, cmd, payloads):
        """
        Generic paket gönderici. 
        payloads: List of bytes (Her biri length-prefixed olarak gönderilecek)
        """
        try:
            s = sc.socket(sc.AF_INET, sc.SOCK_STREAM)
            s.settimeout(10)
            s.connect((ip, TCP_PORT))

            # 1. Komutu gönder
            s.sendall(pack('!B', cmd.value))

            # 2. Her bir payload parçasını gönder (Boyut + Veri)
            for p in payloads:
                if isinstance(p, str):
                    p = p.encode()
                s.sendall(pack('!Q', len(p))) # 8 byte size
                s.sendall(p)                 # asıl veri

            s.close()
        except Exception as e:
            print(f"Bağlantı hatası: {e}")

    def send_message(self, ip, msg):
        # Protokol: [CMD] [NAME_SIZE][NAME] [MSG_SIZE][MSG]
        self._send_packet(ip, COMMAND.MESSAGE, [self.id, msg])

    def send_file(self, ip, filepath):
        import os
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            file_data = f.read()

        # Protokol: [CMD] [NAME_SIZE][NAME] [FILE_NAME_SIZE][FILE_NAME] [DATA_SIZE][DATA]
        self._send_packet(ip, COMMAND.FILE, [self.id, filename, file_data])
    
    def send_folder(self, ip, folder_path):
        # zipfile.Path DEĞİL, pathlib.Path kullanıyoruz
        base_path = Path(folder_path) 
        zip_buffer = io.BytesIO()

        # Klasörü bellekte zipleyelim
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # rglob("*") ile tüm alt dosya ve klasörleri geziyoruz
            for file in base_path.rglob("*"):
                if file.is_file(): # Sadece dosyaları ekle (klasörler otomatik oluşur)
                    # write(fiziksel_yol, zip_icindeki_yol)
                    zip_file.write(file, file.relative_to(base_path))

        folder_zip_data = zip_buffer.getvalue()
        folder_name = base_path.name

        # Protokol: [CMD] [ID] [FOLDER_NAME] [ZIP_DATA]
        self._send_packet(ip, COMMAND.FOLDER, [self.id, folder_name, folder_zip_data])

# --- UI KISMI ---
# --- UI KISMI ---
class App(tk.Tk):
    def __init__(self, id="Client"):
        super().__init__()
        self.id = id
        self.client = Client(id=id)
        self.title(f"SBCS Panel - {self.id}")

        screen_width = self.winfo_screenwidth()
        self.scale = max(1.0, screen_width / 1920) 
        
        base_font_size = int(12 * self.scale)
        self.option_add("*Font", f"Arial {base_font_size}")

        window_w = int(450 * self.scale)
        window_h = int(600 * self.scale)
        self.geometry(f"{window_w}x{window_h}")
        
        self.devices = []
        
        pad_x = int(10 * self.scale)
        pad_y = int(10 * self.scale)
        btn_pad_y = int(5 * self.scale)

        self.listbox = tk.Listbox(self, width=int(50))
        self.listbox.pack(pady=pad_y, padx=pad_x, fill=tk.BOTH, expand=True)
        
        
        tk.Button(self, text="Mesaj Gönder", command=self.send_msg).pack(pady=btn_pad_y, fill=tk.X, padx=pad_x)
        tk.Button(self, text="Dosya Gönder", command=self.send_file_btn).pack(pady=btn_pad_y, fill=tk.X, padx=pad_x)
        tk.Button(self, text="Klasör Gönder", command=self.send_folder_btn).pack(pady=btn_pad_y, fill=tk.X, padx=pad_x)
        tk.Button(self, text="Cihazları Yenile", command=self.refresh_devices).pack(pady=btn_pad_y, fill=tk.X, padx=pad_x)
        tk.Button(self, text="Sınıf Adını (ID) Değiştir", command=self.change_id, fg="blue").pack(pady=btn_pad_y, fill=tk.X, padx=pad_x)
        
        self.refresh_devices()
    def change_id(self):
        new_id = simpledialog.askstring("ID Değiştir", "Yeni Sınıf/Cihaz Adı Giriniz:", initialvalue=self.id)
        
        if new_id and new_id.strip():
            new_id = new_id.strip()
            try:
                current_json_path = initialize_json()
                with open(current_json_path, "w", encoding="utf-8") as f:
                    json.dump({"id": new_id}, f, indent=4)
                
                self.id = new_id
                self.client.id = new_id 
                self.title(f"SBCS Panel - {self.id}")
                
                messagebox.showinfo("Başarılı", f"Cihaz adı '{new_id}' olarak güncellendi.\nDeğişikliğin ağda görünmesi için arkaplan servisinin yeniden başlaması gerekebilir.")
            except Exception as e:
                messagebox.showerror("Hata", f"Dosya yazılamadı: {e}")
    
    def refresh_devices(self):
        self.devices = self.client.discover()
        self.listbox.delete(0, tk.END)
        for dev in self.devices:
            self.listbox.insert(tk.END, f"{dev[0]} ({dev[1]})")
    
    def custom_ask_message(self, target_name):
        dialog = tk.Toplevel(self)
        dialog.title(f"Mesaj Gönderiliyor: {target_name}")

        # Ölçeklendirme
        scale = self.scale
        w = int(500 * scale)
        h = int(300 * scale)

        # Ekranın ortasına konumlandır
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        dialog.transient(self)
        dialog.grab_set()

        result = {"msg": ""}

        # Tasarım
        font_main = ("Arial", int(14 * scale))
        
        tk.Label(dialog, text=f"{target_name} için mesajınız:", font=font_main).pack(pady=10)
        
        # Çok satırlı metin girişi (Öğretmenler rahat yazsın)
        text_area = tk.Text(dialog, font=font_main, height=5, width=40)
        text_area.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)
        text_area.focus_set()

        def on_confirm():
            result["msg"] = text_area.get("1.0", tk.END).strip()
            dialog.destroy()

        # Butonlar
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=15, fill=tk.X)
        
        tk.Button(btn_frame, text="GÖNDER", font=font_main, bg="#4CAF50", fg="white", 
                  command=on_confirm).pack(side=tk.RIGHT, padx=20, ipadx=20)
        
        tk.Button(btn_frame, text="İPTAL", font=font_main, 
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        self.wait_window(dialog)
        return result["msg"]

    def send_msg(self):
        selected = self.listbox.curselection()
        if not selected: 
            messagebox.showwarning("Uyarı", "Lütfen bir cihaz seçin.")
            return
        target_name = self.devices[selected[0]][0]
        ip = self.devices[selected[0]][1]
        msg = self.custom_ask_message(target_name)
        if msg:
            self.client.send_message(ip, msg)

    def send_file_btn(self):
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen bir cihaz seçin.")
            return

        
        ip = self.devices[selected[0]][1]
        filepath = filedialog.askopenfilename()
        if filepath:
            self.client.send_file(ip, filepath)
            messagebox.showinfo("Başarılı", "Dosya gönderildi.")
    
    # App sınıfına eklenecek buton fonksiyonu
    def send_folder_btn(self):
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen bir cihaz seçin.")
            return

        ip = self.devices[selected[0]][1]
        folderpath = filedialog.askdirectory() # Dosya değil klasör seçtirir
        if folderpath:
            # Thread kullanarak UI'ın donmasını engellemek iyi olur
            Thread(target=self.client.send_folder, args=(ip, folderpath), daemon=True).start()
            messagebox.showinfo("Başarılı", "Klasör sıkıştırılıyor ve gönderiliyor...")

if __name__ == "__main__":
    current_json_path = initialize_json()
    try:
        with open(current_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            id = config.get("id", "Bilinmeyen_Cihaz")
    except Exception as e:
        id = "Yedek_Cihaz"
        print(f"Okuma hatası: {e}")
    
    app = App(id=id)

    app.mainloop()
