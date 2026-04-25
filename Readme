# SBCS - SmartBoard Communication System

SBCS is a lightweight communication protocol designed for seamless discovery and data transfer between clients and SmartBoards within a local network.

---

##  How It Works

The system operates using two primary communication channels to balance speed and reliability:

###  1. Device Discovery (UDP)
* **Port:** `5000`
* **Process:** 1. The **Client** broadcasts a "discovery" packet to the entire network via UDP port 5000.
    2. The **Server (SmartBoard)** listens on this port and sends back a response packet to identify itself and its availability.

###  2. Data Transfer (TCP)
* **Port:** `5001`
* **Process:**
    1. Once the SmartBoard is discovered, the **Client** establishes a TCP connection to port 5001.
    2. This channel is used for sending text messages or file buffers reliably.
    3. Upon receiving a message, the **Server** triggers a system notification using `libnotify` (`notify-send`).

