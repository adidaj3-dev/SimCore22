"""
Real-browser smoke tests: load every screen of the demo in Edge and fail on any script error.

There is no JavaScript compiler in this project, so a missing bracket silently blanks a page. These
tests are the safety net. They need Playwright and an installed Microsoft Edge (a dev-only tool,
not in requirements.txt) and skip themselves when either is missing.
"""
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")

import uvicorn  # noqa: E402

from simcore22.league.demo_seed import DEMO_ADMIN_EMAIL, DEMO_PASSWORD  # noqa: E402
from simcore22.web.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def server():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(demo=True)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", app
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge")
        except Exception as exc:  # noqa: BLE001 - no Edge installed here
            pytest.skip(f"Microsoft Edge isn't available to Playwright: {exc}")
        yield b
        b.close()


def new_page(browser, width=1280, height=900):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    problems = []
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
    return page, problems


def log_in(page, base, email):
    page.goto(f"{base}/login")
    page.wait_for_selector("input[name=email]")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", DEMO_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/admin**" if email == DEMO_ADMIN_EMAIL else "**/app**")


def test_login_page_renders_and_shows_the_demo_accounts(browser, server):
    base, _ = server
    page, problems = new_page(browser)
    page.goto(f"{base}/login")
    page.wait_for_selector("text=Try it without signing up")
    page.click("text=Sign up")
    page.wait_for_selector("input[name=ghin_number]")
    assert not problems, problems


def test_unauthenticated_visitors_are_sent_to_the_login_page(browser, server):
    base, _ = server
    page, _problems = new_page(browser)
    page.goto(f"{base}/admin")
    page.wait_for_url("**/login**")
    page.goto(f"{base}/app")
    page.wait_for_url("**/login**")


@pytest.mark.parametrize("next_url", ["//evil.example/x", "/\\evil.example/x", "https://evil.example/x"])
def test_login_never_redirects_to_another_site(browser, server, next_url):
    from urllib.parse import quote
    base, _ = server
    page, _problems = new_page(browser)
    page.goto(f"{base}/login?next={quote(next_url, safe='')}")
    page.wait_for_selector("input[name=email]")
    page.fill("input[name=email]", "alex.rivera@demo.simcore22.test")
    page.fill("input[name=password]", DEMO_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(f"{base}/**")
    assert page.url.startswith(base)


def test_every_admin_screen_loads_without_errors(browser, server):
    base, app = server
    page, problems = new_page(browser)
    log_in(page, base, DEMO_ADMIN_EMAIL)
    checks = [
        ("#/overview", "Rounds this week"), ("#/leagues", "Tuesday Night League"), ("#/leagues/1", "Standings"),
        ("#/players", "Last played"), ("#/capture", "Hole accuracy"), ("#/captured", "Rounds the engine read"), ("#/system", "Screen capture"),
    ]
    for route, text in checks:
        page.goto(f"{base}/admin{route}")
        page.wait_for_selector(f"text={text}", timeout=8000)
    for route, text in (("#/players/3", "Reset password"), ("#/round/5", "Correct a score")):   # drawers
        page.goto(f"{base}/admin{route}")
        page.wait_for_selector(f"text={text}", timeout=8000)
    pair = page.evaluate("fetch('/api/admin/accuracy?days=365').then(r => r.json()).then(d => d.pairs[0].manual_round_id)")
    page.goto(f"{base}/admin#/capture/{pair}")
    page.wait_for_selector("text=Hole accuracy", timeout=8000)
    assert not problems, problems


def test_a_player_can_enter_a_round_hole_by_hole_and_see_the_result(browser, server):
    base, _ = server
    page, problems = new_page(browser)
    log_in(page, base, "alex.rivera@demo.simcore22.test")
    page.wait_for_selector("text=Hi, Alex")
    page.goto(f"{base}/app#/play")
    page.wait_for_selector("text=Start a round")
    page.fill("input[name=bay]", "Bay 4")
    page.click("button:has-text('Start round')")
    page.wait_for_selector("text=Hole 1")
    for hole in range(1, 10):
        page.wait_for_selector(f".hole-title h2:has-text('Hole {hole}')")
        page.click("button[aria-label='One more stroke']")
        page.click("button:has-text('Save')")
    page.wait_for_selector("text=Round complete")
    for route, text in (("#/home", "Recent rounds"), ("#/rounds", "Gross"), ("#/leagues/1", "Standings"), ("#/handicap", "How it works"), ("#/profile", "Your details")):
        page.goto(f"{base}/app{route}")
        page.wait_for_selector(f"text={text}", timeout=8000)
    assert not problems, problems


def test_the_live_board_shows_the_demo_league_and_a_phone_layout_does_not_overflow(browser, server):
    base, _ = server
    page, problems = new_page(browser, width=390, height=800)
    page.goto(f"{base}/live")
    page.wait_for_selector(".row", timeout=8000)
    log_in(page, base, "sam.okafor@demo.simcore22.test")
    page.wait_for_selector("text=Hi, Sam")
    for route in ("#/home", "#/play", "#/leagues/1", "#/handicap"):
        page.goto(f"{base}/app{route}")
        page.wait_for_timeout(600)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"{route} scrolls sideways on a phone"
    assert not problems, problems
