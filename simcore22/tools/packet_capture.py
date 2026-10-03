# simcore22/tools/packet_capture.py
"""
Record what a launch monitor / simulator program really sends over the network,
as a hex dump file you can send back for decoding. Nothing is interpreted: this
only listens and writes down the bytes.

First run `python -m simcore22.tools.bay_check` with the sim software open - its
NETWORK section shows which ports FSX / GSPro use. Then, while shots are being
hit:

    python -m simcore22.tools.packet_capture --port 12345                  # UDP (default)
    python -m simcore22.tools.packet_capture --port 921 --mode tcp-connect # we connect to it
    python -m simcore22.tools.packet_capture --port 921 --mode tcp-listen  # it connects to us

Modes:
    udp          bind the port and record datagrams sent to it
    tcp-connect  connect out to host:port and record what it sends
    tcp-listen   wait for the other side to connect, then record

Output: captures/packets_<time>.log. Stop with Ctrl+C (or --seconds). If nothing
arrives: check the port with bay_check, try the other modes, and check that
Windows Firewall isn't blocking Python. A port can have only one UDP listener,
so close anything else that is bound to it first.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

MODES = ("udp", "tcp-connect", "tcp-listen")


def hexdump(data: bytes) -> str:
    """Classic 16-bytes-per-line dump: offset, hex, printable ASCII."""
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk).ljust(47)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {offset:04x}  {hex_part}  {text}")
    return "\n".join(lines)


def format_packet(when: datetime, source: str, data: bytes) -> str:
    return f"[{when:%H:%M:%S.%f}"[:-3] + f"] {source}  {len(data)} bytes\n{hexdump(data)}\n"


def _packets(mode: str, host: str, port: int, deadline: float):
    """Yield (source, bytes) until the deadline. Sockets are cleaned up on exit."""
    if mode == "udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.settimeout(0.5)
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                yield f"{addr[0]}:{addr[1]}", data
        return

    if mode == "tcp-connect":
        conn = socket.create_connection((host, port), timeout=5)
        source = f"{host}:{port}"
    else:  # tcp-listen
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(1)
        server.settimeout(0.5)
        conn, source = None, ""
        try:
            while conn is None and time.monotonic() < deadline:
                try:
                    conn, addr = server.accept()
                    source = f"{addr[0]}:{addr[1]}"
                except socket.timeout:
                    continue
        finally:
            server.close()
        if conn is None:
            return

    with conn:
        conn.settimeout(0.5)
        while time.monotonic() < deadline:
            try:
                data = conn.recv(65535)
            except socket.timeout:
                continue
            if not data:  # the other side closed the connection
                return
            yield source, data


def capture(
    mode: str,
    host: str,
    port: int,
    seconds: float,
    out_path: Path,
    on_packet: Optional[Callable[[str], None]] = None,
) -> int:
    """Record packets for `seconds` into out_path; returns how many arrived."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    deadline = time.monotonic() + seconds
    with open(out_path, "w", encoding="utf-8") as out:
        out.write(f"# packet_capture {datetime.now():%Y-%m-%d %H:%M:%S}  mode={mode} host={host} port={port}\n\n")
        try:
            for source, data in _packets(mode, host, port, deadline):
                count += 1
                out.write(format_packet(datetime.now(), source, data) + "\n")
                out.flush()
                if on_packet:
                    on_packet(f"#{count} from {source}: {len(data)} bytes  {data[:40]!r}")
        except KeyboardInterrupt:
            pass
        out.write(f"# {count} packet(s) captured\n")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Record raw launch-monitor / simulator network traffic.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--mode", choices=MODES, default="udp")
    parser.add_argument("--host", help="address (default: 0.0.0.0 to listen, 127.0.0.1 to connect)")
    parser.add_argument("--seconds", type=float, default=300, help="stop after this long (default 300)")
    parser.add_argument("--out", type=Path, help="output file (default captures/packets_<time>.log)")
    args = parser.parse_args()

    host = args.host or ("127.0.0.1" if args.mode == "tcp-connect" else "0.0.0.0")
    out_path = args.out or Path("captures") / f"packets_{datetime.now():%Y%m%d_%H%M%S}.log"

    print(f"Recording {args.mode} on {host}:{args.port} for up to {args.seconds:.0f}s - hit some shots. Ctrl+C to stop.")
    try:
        count = capture(args.mode, host, args.port, args.seconds, out_path, on_packet=print)
    except OSError as exc:
        print(f"Couldn't start: {exc}")
        if args.mode == "tcp-connect":
            print("Nothing is accepting connections there. Check the port with bay_check, or try --mode tcp-listen / udp.")
        else:
            print("Is something else already using that port? Close it, or pick the right port from bay_check.")
        return 1

    print(f"\n{count} packet(s) saved to {out_path.resolve()}")
    if count == 0:
        print("Nothing arrived. Check the port (bay_check), try the other modes, check Windows Firewall.")
    else:
        print("Send that file back so the packets can be decoded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
