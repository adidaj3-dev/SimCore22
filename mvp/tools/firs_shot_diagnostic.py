import socket

def main():
    port = int(input("Enter LM port: "))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    print(f"Listening for Falcon packets on {port}...")

    while True:
        data, addr = s.recvfrom(4096)
        print("\n=== RAW PACKET RECEIVED ===")
        print(data[:128])
        print("===========================")

if __name__ == "__main__":
    main()
