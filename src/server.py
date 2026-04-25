import socket as sc
from threading import Thread
import json
from command import COMMAND
from struct import pack, unpack
import time
import zipfile, io
import os
from pathlib import Path
import subprocess

# Kullanıcının kendi ana dizininde gizli bir klasör kullanmak en güvenlisidir
SBCS_DATA_PATH = os.path.join(Path.home(), ".local/share/sbcs")
JSON_FILE = os.path.join(SBCS_DATA_PATH, "info.json")

def initialize_json():

    if not os.path.exists(SBCS_DATA_PATH):
        try:
            os.makedirs(SBCS_DATA_PATH, exist_ok=True)
        except PermissionError:

            print("Sistem dizinine erişim yok, yerel dizin kullanılıyor.")
            return "info.json"
    
    if not os.path.exists(JSON_FILE):
        default_data = {"id": sc.gethostname()} # Varsayılan olarak makine adını ver
        try:
            with open(JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4)
            print(f"Yeni yapılandırma dosyası oluşturuldu: {JSON_FILE}")
        except Exception as e:
            print(f"Dosya oluşturma hatası: {e}")
    
    return JSON_FILE


def get_unique_filename(base_path, filename):
    path = Path(base_path) / filename
    name = path.stem # dosya adı
    suffix = path.suffix # .txt, .jpg vb.
    counter = 1
    
    while path.exists():
        path = Path(base_path) / f"{name}_{counter}{suffix}"
        counter += 1
        
    return path

def get_downloads_path():
    home = Path.home()
    config_file = home / ".config" / "user-dirs.dirs"

    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                for line in f:
                    if "XDG_DOWNLOAD_DIR" in line:
                        path = line.split('=')[1].strip().strip('"')
                        path = path.replace("$HOME", str(home))
                        return Path(path)
        except Exception as e:
            print(f"XDG okunamadı: {e}")

    return home / "Downloads"


class Server:
    def __init__(self, udp_port=5000, tcp_port=5001, id="Server"):
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.id = id
        self.udp = None
        self.tcp = None

    def recv_fixed_length(self, sock, length):
        data = b''
        while len(data) < length:
            packet = sock.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return data

    def get_data(self, sock) -> bytes:
        data_length = self.recv_fixed_length(sock, 8)
        if not data_length:
            return b""
        data_length = unpack('!Q', data_length)[0]
        data = self.recv_fixed_length(sock, data_length)
        if not data:
            return b""
        return data

    def show_message(self, sender, msg):
        try:
            subprocess.Popen(
                [
                    "notify-send",
                    "-u",
                    "normal",  # low, normal, critical
                    "-t",
                    "5000",  # ms
                    sender,
                    msg,
                ]
            )
        except Exception as e:
            print(f"notify-send hatası: {e}")

    def udp_server(self):
        self.udp = sc.socket(sc.AF_INET, sc.SOCK_DGRAM)
        self.udp.bind(('', self.udp_port))
        print(f"UDP server started on port {self.udp_port}")
        while True:
            data, addr = self.udp.recvfrom(1)
            if not data:
                continue

            match unpack('!B', data)[0]:
                case COMMAND.DISCOVER:
                    response = pack("!B", COMMAND.ACTIVE.value)
                    response += pack("!Q", len(self.id))
                    response += self.id.encode()
                    self.udp.sendto(response, addr)
                case _:
                    print(f"Unknown UDP command from {addr}: {data}")
                    pass # Gelen diğer komutları umursama

    def handle_tcp_client(self, sock):
        try:
            while True:
                data = self.recv_fixed_length(sock, 1)
                if not data:
                    break

                match unpack('!B', data)[0]:
                    case COMMAND.MESSAGE:
                        #   Göndericinin adını oku
                        name = self.get_data(sock).decode("utf-8")
                        if not name:
                            break

                        #   Mesaj içeriğini oku
                        message = self.get_data(sock).decode("utf-8")
                        if not message:
                            break

                        print(f"Message from {name}: {message}")
                        self.show_message(name, message)

                    case COMMAND.FILE:
                        # Göndericinin adını oku
                        name = self.get_data(sock).decode('utf-8')
                        if not name:
                            break

                        # Dosya adını oku
                        filename = self.get_data(sock).decode('utf-8')
                        if not filename:
                            break

                        # Dosya içeriğini oku
                        file_content = self.get_data(sock)
                        if not file_content:
                            break
                        file_path = get_unique_filename(get_downloads_path(), filename)
                        file_path.write_bytes(file_content)
                        self.show_message(name, f"Dosya geldi: {file_path.name}\n")
                    case COMMAND.FOLDER:
                        sender_name = self.get_data(sock).decode('utf-8')
                        folder_name = self.get_data(sock).decode('utf-8')
                        zip_data = self.get_data(sock)

                        if all([sender_name, folder_name, zip_data]):
                            # İndirilenler klasöründe benzersiz bir isim bul (Klasör için)
                            base_path = get_downloads_path() / folder_name
                            # get_unique_filename fonksiyonunu klasör için modifiye edebilirsin
                            # veya doğrudan klasörü oluşturabilirsin
                            if base_path.exists():
                                base_path = Path(str(base_path) + "_" + str(int(time.time())))

                            base_path.mkdir(parents=True, exist_ok=True)

                            # Zip içeriğini aç
                            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                                z.extractall(base_path)

                            self.show_message(sender_name, f"Klasör geldi: {folder_name}\nKonum: {base_path}")
                    case _:
                        pass # Gelen diğer komutları umursama
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            sock.close()

    def tcp_server(self):
        self.tcp = sc.socket(sc.AF_INET, sc.SOCK_STREAM)
        self.tcp.bind(('', self.tcp_port))
        self.tcp.listen(5)
        print(f"TCP server started on port {self.tcp_port}")
        while True:
            conn, addr = self.tcp.accept()
            Thread(target=self.handle_tcp_client, args=(conn,), daemon=True).start()

    def start(self):
        udp_thread = Thread(target=self.udp_server, daemon=True)
        tcp_thread = Thread(target=self.tcp_server, daemon=True)

        udp_thread.start()
        tcp_thread.start()

        udp_thread.join()
        tcp_thread.join()


if __name__ == "__main__":
    current_json_path = initialize_json()
    try:
        with open(current_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            id = config.get("id", "Bilinmeyen_Cihaz")
    except Exception as e:
        try:
            print(f"Yapılandırma okunamadı: {e}. Yeni bir yapılandırma dosyası oluşturuluyor.")
            id = sc.gethostname() # Varsayılan olarak makine adını ver
            with open(current_json_path, "w", encoding="utf-8") as f:
                json.dump({"id": id}, f, indent=4)
            print(f"Yeni yapılandırma dosyası oluşturuldu: {current_json_path}")
        except Exception as e:
            print(f"Yapılandırma dosyası oluşturulamadı: {e}. Varsayılan ID kullanılacak.")
            id = "Bilinmeyen_Cihaz"
    server = Server(id=id)
    server.start()
