# mvp/tools/falcon_packet_decoder.py

import socket
from datetime import datetime


def main():
    port = int(input("Enter LM port to decode (e.g. 15000): "))

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    print(f"Listening for Falcon packets on port {port}...\n")

    while True:
        data, addr = s.recvfrom(4096)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] Packet from {addr[0]}:{addr[1]}  len={len(data)} bytes")
        print("Hex preview:", data[:32].hex(" "))
        print("-" * 60)


if __name__ == "__main__":
    main()
