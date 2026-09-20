import socket
import time

COMMON_PORTS = [15000, 15001, 20000, 20800, 30000, 50000]

def try_port(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.bind(("0.0.0.0", port))
        print(f"Listening on port {port}...")
        data, addr = s.recvfrom(4096)
        if data:
            print(f"✔ Falcon LM stream detected on port {port}")
            print(f"Raw packet: {data[:64]}")
            return True
    except:
        pass
    return False

def main():
    print("Auto-detecting Falcon LM stream...")
    for port in COMMON_PORTS:
        if try_port(port):
            return
    print("❌ Could not auto-detect. Try port scanner or Resource Monitor.")

if __name__ == "__main__":
    main()
