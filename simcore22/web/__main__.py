# simcore22/web/__main__.py
"""
Start the web UI.

    python -m simcore22.web              # your real rounds (what the engine has recorded)
    python -m simcore22.web --demo       # a fictional league, for showing the product
    python -m simcore22.web --open       # also open the admin portal in your browser

    player app:        http://localhost:8080/app      (players sign up and log in here)
    live leaderboard:  http://localhost:8080/live     (the bay screens)
    admin portal:      http://localhost:8080/admin    (the first visit asks you to create the admin account)
    API reference:     http://localhost:8080/docs

If port 8080 is busy (another program on the bay PC) the next free one is used and printed.
"""
import argparse
import socket
import threading
import webbrowser
from typing import Optional

import uvicorn

from simcore22.engine.logging_config import setup_logging
from simcore22.web.app import create_app

DEFAULT_PORT = 8080


def pick_port(host: str, preferred: int, tries: int = 10) -> int:
    """`preferred` if it is free, otherwise the next free port after it."""
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port between {preferred} and {preferred + tries - 1}.")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="SimCore22 web UI")
    parser.add_argument("--demo", action="store_true", help="serve the built-in fictional league instead of real data")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on (default: this PC only; 0.0.0.0 = the whole network)")
    parser.add_argument("--port", type=int, help=f"port to use (default {DEFAULT_PORT}, or the next free one)")
    parser.add_argument("--open", action="store_true", help="open the web UI in a browser")
    args = parser.parse_args(argv)

    setup_logging()
    try:
        port = args.port if args.port else pick_port(args.host, DEFAULT_PORT)
    except OSError as exc:
        print(f"Couldn't find a port to listen on: {exc}")
        return 1
    if args.port is None and port != DEFAULT_PORT:
        print(f"\n  (port {DEFAULT_PORT} is in use by another program, so port {port} is being used instead)")

    base = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{port}"
    print(f"\n  SimCore22 {'DEMO ' if args.demo else ''}web UI")
    print(f"    player app        {base}/app")
    print(f"    live leaderboard  {base}/live")
    print(f"    admin portal      {base}/admin")
    print(f"    API reference     {base}/docs")
    if args.demo:
        print("\n  Demo accounts are on the log-in page (password: demo-password). Nothing here is saved.")
    if args.host not in ("127.0.0.1", "localhost"):
        print("\n  NOTE: this is reachable from the network. Players and admins log in, but the connection is not "
              "encrypted (http). Use a trusted venue network, and put https in front of it before exposing it beyond that.")
    print()

    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(f"{base}/app")).start()

    try:
        uvicorn.run(create_app(demo=args.demo), host=args.host, port=port, log_level="warning")
    except OSError as exc:
        print(f"Couldn't start the web UI on port {port}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
