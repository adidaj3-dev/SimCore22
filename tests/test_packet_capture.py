import socket
import threading
import time

import pytest

from simcore22.tools.packet_capture import capture, hexdump

PAYLOAD = b"SHOT ball_speed=150.5\x00\xff"


def _free_port(kind=socket.SOCK_DGRAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_capture(mode, port, out, seconds=3.0):
    result = {}

    def go():
        result["count"] = capture(mode, "127.0.0.1", port, seconds, out)

    thread = threading.Thread(target=go)
    thread.start()
    return thread, result


def _check_log(out, expected_hex="53 48 4f 54"):
    text = out.read_text(encoding="utf-8")
    assert expected_hex in text           # the bytes are written as hex
    # ...and as readable text beside them (a dump wraps every 16 bytes)
    assert "SHOT ball_speed=" in text and "150.5" in text
    assert f"{len(PAYLOAD)} bytes" in text
    assert "packet(s) captured" in text


def test_hexdump_shows_offsets_hex_and_ascii():
    dump = hexdump(b"ABC\x00" + bytes(range(16)))
    first, second = dump.splitlines()
    assert first.startswith("  0000  41 42 43 00 00 01 02 03")
    assert first.endswith("ABC.............")
    assert second.startswith("  0010  0c 0d 0e 0f")


def test_udp_datagrams_are_recorded(tmp_path):
    port, out = _free_port(), tmp_path / "udp.log"
    thread, result = _run_capture("udp", port, out)
    time.sleep(0.5)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(PAYLOAD, ("127.0.0.1", port))
    thread.join()

    assert result["count"] == 1
    _check_log(out)


def test_tcp_connect_records_what_the_server_sends(tmp_path):
    out = tmp_path / "tcp.log"
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve():
        conn, _ = server.accept()
        conn.sendall(PAYLOAD)
        time.sleep(0.3)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    thread, result = _run_capture("tcp-connect", port, out)
    thread.join()
    server.close()

    assert result["count"] == 1
    _check_log(out)


def test_tcp_listen_records_what_the_client_sends(tmp_path):
    port, out = _free_port(socket.SOCK_STREAM), tmp_path / "listen.log"
    thread, result = _run_capture("tcp-listen", port, out)
    time.sleep(0.5)
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.sendall(PAYLOAD)
        time.sleep(0.3)
    thread.join()

    assert result["count"] == 1
    _check_log(out)


def test_silence_is_reported_as_zero_packets_not_an_error(tmp_path):
    out = tmp_path / "quiet.log"
    assert capture("udp", "127.0.0.1", _free_port(), 0.6, out) == 0
    assert "0 packet(s) captured" in out.read_text(encoding="utf-8")


def test_connecting_to_nothing_raises_a_clear_os_error(tmp_path):
    with pytest.raises(OSError):
        capture("tcp-connect", "127.0.0.1", _free_port(socket.SOCK_STREAM), 1.0, tmp_path / "x.log")
