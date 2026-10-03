import socket

import pytest

from simcore22.web.__main__ import pick_port


def _busy_port():
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    return held, held.getsockname()[1]


def test_a_free_port_is_used_as_asked():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free = probe.getsockname()[1]
    probe.close()
    assert pick_port("127.0.0.1", free) == free


def test_a_busy_port_falls_through_to_the_next_free_one():
    held, port = _busy_port()
    try:
        chosen = pick_port("127.0.0.1", port)
        assert port < chosen <= port + 9
    finally:
        held.close()


def test_giving_up_is_an_error_not_a_hang():
    held, first = _busy_port()
    sockets = [held]
    try:
        for offset in (1, 2):  # occupy the next two ports as well
            neighbour = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(neighbour)
            try:
                neighbour.bind(("127.0.0.1", first + offset))
                neighbour.listen(1)
            except OSError:
                pytest.skip("couldn't occupy the neighbouring ports on this machine")
        with pytest.raises(OSError):
            pick_port("127.0.0.1", first, tries=3)
    finally:
        for s in sockets:
            s.close()
