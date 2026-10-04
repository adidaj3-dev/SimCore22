"""
Regenerate the screenshots in docs/images/ from the built-in DEMO venue (fictional players only).

    python -m simcore22.tools.ui_screenshots              # all of them, into docs/images/
    python -m simcore22.tools.ui_screenshots --out some/folder

Needs Playwright and an installed Microsoft Edge - a dev-only tool, not in requirements.txt:
    pip install playwright
"""
import argparse
import socket
import threading
import time
from pathlib import Path

import uvicorn

from simcore22.league.demo_seed import DEMO_ADMIN_EMAIL, DEMO_PASSWORD
from simcore22.web.app import create_app

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "images"
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
ALEX = "alex.rivera@demo.simcore22.test"


def _serve():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(demo=True), host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}"


def _login(page, base, email):
    page.goto(f"{base}/login")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", DEMO_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/admin**" if email == DEMO_ADMIN_EMAIL else "**/app**")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    server, base = _serve()
    shots = []

    def snap(page, name, wait_for, *, full=False):
        page.wait_for_selector(wait_for, timeout=10000)
        page.wait_for_timeout(900)                      # let charts and rows finish animating
        path = args.out / f"{name}.png"
        page.screenshot(path=str(path), full_page=full)
        shots.append(path.name)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")

        def fresh(size, scheme="dark"):
            context = browser.new_context(viewport=size, color_scheme=scheme, device_scale_factor=1)
            return context.new_page()

        page = fresh(DESKTOP)
        page.goto(f"{base}/live")
        snap(page, "live-leaderboard", ".row")
        page.goto(f"{base}/login")
        snap(page, "login", "text=Try it without signing up")

        _login(page, base, DEMO_ADMIN_EMAIL)
        for name, route, wait in (
            ("admin-overview", "#/overview", "text=Live now"),
            ("admin-league", "#/leagues/1", "text=Standings"),
            ("admin-players", "#/players", "text=Last played"),
            ("admin-capture", "#/capture", "text=Round by round"),
            ("admin-round", "#/round/5", "text=Correct a score"),
        ):
            page.goto(f"{base}/admin{route}")
            snap(page, name, wait)

        page = fresh(DESKTOP)
        _login(page, base, ALEX)
        page.wait_for_selector("text=Hi, Alex")
        snap(page, "player-home", "text=Recent rounds")
        page.goto(f"{base}/app#/handicap")
        snap(page, "player-handicap", "text=How it works")

        phone = fresh(PHONE)
        _login(phone, base, ALEX)
        phone.goto(f"{base}/app#/play")
        phone.wait_for_selector("text=Start a round")
        phone.fill("input[name=bay]", "Bay 3")
        phone.click("button:has-text('Start round')")
        for hole in range(1, 5):
            phone.wait_for_selector(f".hole-title h2:has-text('Hole {hole}')")
            if hole in (2, 4):
                phone.click("button[aria-label='One more stroke']")
            phone.click("button:has-text('Save')")
        phone.wait_for_selector(".hole-title h2:has-text('Hole 5')")
        snap(phone, "player-play-phone", ".hole-card")
        browser.close()

    server.should_exit = True
    print(f"Saved {len(shots)} screenshots to {args.out}: " + ", ".join(shots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
