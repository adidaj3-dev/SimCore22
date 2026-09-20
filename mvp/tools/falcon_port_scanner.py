import socket
import time

COMMON_PORTS = [15000, 15001, 20000, 20800, 30000, 50000]

def scan_port(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.bind(("0.0.0.0", port))
        data, addr = s.recvfrom(2048)
        if data:
            print(f"[FOUND] Foresight LM stream on port {port}")
            return True
    except:
        pass
    return False

def main():
    print("Scanning for Falcon LM stream...")
    for port in COMMON_PORTS:
        print(f"Checking port {port}...")
        if scan_port(port):
            print("✔ Use this port in your EngineConfig.")
            return
    print("❌ No LM stream found on common ports. Try auto-detect tool next.")

if __name__ == "__main__":
    main()
