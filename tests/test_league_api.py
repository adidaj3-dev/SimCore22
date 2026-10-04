"""The account / league / hand-entry API, driven the way the pages drive it."""
import json

import pytest
from fastapi.testclient import TestClient
from web_helpers import CSRF, PASSWORD, add_user, admin_client, login, make_client

from simcore22.league.demo_seed import DEMO_ADMIN_EMAIL, DEMO_PASSWORD
from simcore22.web.app import create_app

PARS = [4, 4, 3, 5, 4, 4, 3, 4, 5]


@pytest.fixture
def app(sandbox):
    return create_app(rounds_path=sandbox / "data" / "rounds.jsonl", leaderboard_path=sandbox / "state" / "leaderboard.json",
                      engine_status_path=sandbox / "state" / "engine_status.json", scorecards_dir=sandbox / "data" / "scorecards",
                      local_hosts=frozenset({"testclient"}))


@pytest.fixture
def admin(app):
    return admin_client(app)


@pytest.fixture
def league(admin):
    response = admin.post("/api/leagues", json={"name": "Tuesday Night", "holes": 9, "ranking": "net", "course_name": "Pebble"})
    assert response.status_code == 200, response.text
    return response.json()


def signup(app, name, code=None, **extra):
    client = make_client(app)
    body = {"email": f"{name.split()[0].lower()}@example.com", "password": PASSWORD, "display_name": name, **extra}
    if code:
        body["join_code"] = code
    response = client.post("/api/auth/signup", json=body)
    assert response.status_code == 200, response.text
    return client, response.json()["user"]


def play_hole(client, round_id, hole, strokes):
    response = client.put(f"/api/play/rounds/{round_id}/holes/{hole}", json={"strokes": strokes})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------- first-time setup

def test_first_admin_can_only_be_created_from_the_venue_pc_and_only_once(sandbox):
    body = {"email": "boss@example.com", "password": PASSWORD, "display_name": "Venue Boss"}
    remote = create_app(rounds_path=sandbox / "a" / "r.jsonl")                      # test client is not "localhost" here
    client = make_client(remote)
    assert client.get("/api/session").json() == {"user": None, "needs_setup": True, "can_setup": False, "demo": None}
    assert client.post("/api/auth/setup", json=body).status_code == 403

    local = create_app(rounds_path=sandbox / "b" / "r.jsonl", local_hosts=frozenset({"testclient"}))
    client = make_client(local)
    assert client.get("/api/session").json()["can_setup"] is True
    done = client.post("/api/auth/setup", json=body)
    assert done.status_code == 200 and done.json()["user"]["role"] == "admin"
    assert client.get("/api/session").json()["user"]["email"] == "boss@example.com"
    assert make_client(local).post("/api/auth/setup", json={**body, "email": "second@example.com"}).status_code == 403


# ------------------------------------------------------------------------ safety

def test_state_changing_requests_need_the_anti_forgery_header(app):
    plain = TestClient(app)                                                          # no header
    response = plain.post("/api/auth/login", json={"email": "a@b.co", "password": "whatever1"})
    assert response.status_code == 403 and "header" in response.json()["detail"]
    assert plain.get("/api/session").status_code == 200                              # reading needs nothing


def test_the_session_cookie_is_httponly_samesite_and_marked_secure_on_https(app):
    add_user(app, "ann@example.com", "Ann Player")
    client = make_client(app)
    cookie = client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    secure = make_client(app, base_url="https://testserver")
    cookie = secure.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).headers["set-cookie"].lower()
    assert "secure" in cookie


def test_engine_log_admin_endpoints_are_not_public(app):
    anonymous = make_client(app)
    for path in ("/api/rounds", "/api/players", "/api/summary", "/api/scorecards/x.png", "/api/admin/players", "/api/admin/overview"):
        assert anonymous.get(path).status_code == 401, path
    player, _ = signup(app, "Ann Player")
    for path in ("/api/rounds", "/api/admin/players", "/api/admin/accuracy"):
        assert player.get(path).status_code == 403, path
    assert anonymous.get("/api/leaderboard").status_code == 200                      # the bay screens stay open
    assert anonymous.get("/api/leagues/public").status_code == 200


def test_passwords_never_leave_the_server(app):
    _, user = signup(app, "Ann Player")
    assert "password" not in json.dumps(user).lower()
    admin = admin_client(app)
    assert "password_hash" not in admin.get("/api/admin/players").text


# ----------------------------------------------------------------- sign up / log in

def test_sign_up_with_ghin_and_outdoor_index_logs_you_in_and_seeds_the_handicap(app):
    client, user = signup(app, "Ann Player", outdoor_index="14.2", ghin_number="1234567", gspro_name="AnnP")
    assert user["indoor_index"] == 14.2 and user["ghin_number"] == "1234567" and user["gspro_name"] == "AnnP"
    assert client.get("/api/session").json()["user"]["id"] == user["id"]
    home = client.get("/api/me/home").json()
    assert home["handicap"]["index"] == 14.2 and home["active_round"] is None and home["leagues"] == []


def test_a_bad_join_code_stops_sign_up_without_creating_an_account(app):
    client = make_client(app)
    body = {"email": "ann@example.com", "password": PASSWORD, "display_name": "Ann Player", "join_code": "NOPE00"}
    assert client.post("/api/auth/signup", json=body).status_code == 404
    assert client.post("/api/auth/signup", json={**body, "join_code": ""}).status_code == 200   # the email wasn't burned


def test_signup_validation_messages_are_readable(app):
    client = make_client(app)
    bad = client.post("/api/auth/signup", json={"email": "nope", "password": PASSWORD, "display_name": "Ann"})
    assert bad.status_code == 400 and "email" in bad.json()["detail"].lower()
    short = client.post("/api/auth/signup", json={"email": "a@b.co", "password": "short", "display_name": "Ann"})
    assert short.status_code == 400 and "8" in short.json()["detail"]


def test_login_logout_and_wrong_password(app):
    add_user(app, "ann@example.com", "Ann Player")
    client = make_client(app)
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong"}).status_code == 401
    login(client, "ann@example.com")
    assert client.get("/api/me/home").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/me/home").status_code == 401


def test_repeated_wrong_passwords_lock_the_account_for_a_while(app):
    add_user(app, "ann@example.com", "Ann Player")
    client = make_client(app)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).status_code == 429


def test_profile_update_and_password_change(app):
    client, _ = signup(app, "Ann Player", outdoor_index="20")
    updated = client.patch("/api/me", json={"outdoor_index": "12.0", "ghin_number": ""}).json()["user"]
    assert updated["outdoor_index"] == 12.0 and updated["ghin_number"] is None and updated["indoor_index"] == 12.0
    assert client.patch("/api/me", json={"ghin_number": "12"}).status_code == 400
    assert client.post("/api/me/password", json={"current_password": "nope", "new_password": "another long one"}).status_code == 400
    assert client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "another long one"}).status_code == 200
    login(make_client(app), "ann@example.com", "another long one")


# --------------------------------------------------- a league night, hole by hole

def test_a_league_night_updates_the_live_board_hole_by_hole_and_builds_the_admin_tables(app, admin, league):
    ann, ann_user = signup(app, "Ann Player", league["join_code"], outdoor_index="0")
    bob, _ = signup(app, "Bob Player", league["join_code"], outdoor_index="18")
    bay_tv = make_client(app)                                          # not logged in: it's a screen on the wall
    board = lambda: bay_tv.get(f"/api/leagues/{league['id']}/board").json()   # noqa: E731

    assert board()["players"] == []
    ra = ann.post("/api/play/rounds", json={"league_id": league["id"], "bay": "Bay 2"}).json()
    rb = bob.post("/api/play/rounds", json={"league_id": league["id"], "bay": "Bay 5"}).json()
    assert ra["holes_total"] == 9 and ra["bay"] == "Bay 2"

    play_hole(ann, ra["id"], 1, 4)
    play_hole(bob, rb["id"], 1, 6)                                     # bogey+1 gross, but net par... almost: +2 gross, 1 stroke
    live = {p["name"]: p for p in board()["players"]}
    assert live["Ann Player"]["thru"] == 1 and live["Ann Player"]["rank"] == 1
    assert live["Bob Player"]["gross_vs_par"] == 2 and live["Bob Player"]["vs_par"] == 1     # net to par
    assert board()["ranking"] == "net" and board()["round_complete"] is False

    for hole in range(2, 10):
        ann_round = play_hole(ann, ra["id"], hole, PARS[hole - 1])
        play_hole(bob, rb["id"], hole, PARS[hole - 1] + 1)
    assert ann_round["status"] == "completed"
    assert board()["round_complete"] is True

    table = admin.get(f"/api/leagues/{league['id']}/table").json()
    names = [p["name"] for p in table["players"]]
    assert names == ["Ann Player", "Bob Player"] and table["players"][0]["rounds"] == 1
    assert admin.get(f"/api/leagues/{league['id']}/rounds").json()["rounds"][0]["player"] in names
    # Bob's handicap came out of the rounds he typed in, not a number somebody entered
    bob_profile = bob.get("/api/me/home").json()
    assert bob_profile["handicap"]["history"][-1]["method"] == "simcore-index-v1"
    assert admin.get("/api/admin/overview").json()["total_rounds"] == 2
    assert ann.get(f"/api/leagues/{league['id']}/table").status_code == 200
    assert ann_user["id"] in [p["user_id"] for p in table["players"]]


def test_players_cannot_see_other_players_rounds_or_leagues_they_are_not_in(app, league):
    ann, _ = signup(app, "Ann Player", league["join_code"])
    bob, _ = signup(app, "Bob Player")
    ra = ann.post("/api/play/rounds", json={"league_id": league["id"]}).json()
    assert bob.get(f"/api/play/rounds/{ra['id']}").status_code == 403
    assert bob.put(f"/api/play/rounds/{ra['id']}/holes/1", json={"strokes": 4}).status_code == 403
    assert bob.get(f"/api/leagues/{league['id']}/table").status_code == 403
    assert bob.post("/api/play/rounds", json={"league_id": league["id"]}).status_code == 403    # not a member
    assert bob.delete(f"/api/play/rounds/{ra['id']}").status_code == 403


def test_end_a_round_early_and_the_data_is_kept(app):
    ann, _ = signup(app, "Ann Player")
    r = ann.post("/api/play/rounds", json={"holes": 18}).json()
    for hole in range(1, 11):
        play_hole(ann, r["id"], hole, 5)
    done = ann.post(f"/api/play/rounds/{r['id']}/finish").json()
    assert done["status"] == "ended_early" and done["thru"] == 10 and done["counts"]
    assert ann.post(f"/api/play/rounds/{r['id']}/finish").status_code == 409
    assert ann.get("/api/me/home").json()["handicap"]["index"] is not None


def test_entry_mistakes_are_refused_with_a_reason(app):
    ann, _ = signup(app, "Ann Player")
    r = ann.post("/api/play/rounds", json={"holes": 9}).json()
    assert ann.post("/api/play/rounds", json={"holes": 9}).status_code == 409
    for hole, strokes in ((0, 4), (10, 4), (1, 0), (1, 16)):
        assert ann.put(f"/api/play/rounds/{r['id']}/holes/{hole}", json={"strokes": strokes}).status_code == 400
    assert ann.post("/api/play/rounds", json={"holes": 7}).status_code in (400, 409)


def test_admin_can_enter_for_a_player_correct_it_and_reset_a_password(app, admin):
    ann, ann_user = signup(app, "Ann Player")
    r = admin.post("/api/play/rounds", json={"user_id": ann_user["id"], "holes": 9}).json()
    assert r["user_id"] == ann_user["id"]
    for hole in range(1, 10):
        done = play_hole(admin, r["id"], hole, 8)
    bad_index = ann.get("/api/me/home").json()["handicap"]["index"]
    play_hole(admin, r["id"], 1, 4)
    assert ann.get("/api/me/home").json()["handicap"]["index"] < bad_index and done["status"] == "completed"

    temp = admin.post(f"/api/admin/players/{ann_user['id']}/reset-password").json()["temporary_password"]
    assert ann.get("/api/me/home").status_code == 401                              # her old session ended
    login(make_client(app), "ann@example.com", temp)
    assert admin.post(f"/api/admin/players/{ann_user['id']}/disabled", json={"disabled": True}).json()["user"]["disabled"] is True
    assert make_client(app).post("/api/auth/login", json={"email": "ann@example.com", "password": temp}).status_code == 403
    assert admin.delete(f"/api/play/rounds/{r['id']}").status_code == 200
    assert admin.get("/api/admin/overview").json()["total_rounds"] == 0


def test_league_rules_and_membership_admin(app, admin, league):
    assert admin.post("/api/leagues", json={"name": "x"}).status_code == 400
    assert admin.post("/api/leagues", json={"name": "Bad pars", "pars": [4, 4]}).status_code == 400
    assert make_client(app).post("/api/leagues", json={"name": "Nope League"}).status_code == 401
    ann, ann_user = signup(app, "Ann Player")
    assert ann.post("/api/leagues/join", json={"code": "zzzzzz"}).status_code == 404
    assert ann.post("/api/leagues/join", json={"code": league["join_code"].lower()}).status_code == 200
    assert ann.post("/api/leagues/join", json={"code": league["join_code"]}).status_code == 409
    assert admin.put(f"/api/leagues/{league['id']}/members/{ann_user['id']}/team", json={"team": "Eagles"}).status_code == 200
    members = admin.get(f"/api/leagues/{league['id']}/members").json()["members"]
    assert members[0]["team"] == "Eagles"
    changed = admin.patch(f"/api/leagues/{league['id']}", json={"ranking": "gross", "holes": 18}).json()
    assert changed["ranking"] == "gross" and changed["holes"] == 9                  # length can't change under players
    assert admin.delete(f"/api/leagues/{league['id']}/members/{ann_user['id']}").status_code == 200
    assert ann.get("/api/leagues").json()["leagues"] == []


def test_the_live_stream_can_follow_one_league_and_unknown_leagues_404(app, league):
    ann, _ = signup(app, "Ann Player", league["join_code"])
    r = ann.post("/api/play/rounds", json={"league_id": league["id"]}).json()
    play_hole(ann, r["id"], 1, 5)
    anonymous = make_client(app)
    response = anonymous.get(f"/api/stream?league={league['id']}&max_events=1")
    assert response.status_code == 200 and response.text.startswith("event: update")
    payload = json.loads(response.text.split("data: ", 1)[1])
    assert payload["leaderboard"]["league_name"] == "Tuesday Night" and payload["leaderboard"]["players"][0]["name"] == "Ann Player"
    assert anonymous.get("/api/stream?league=999&max_events=1").status_code == 404


# -------------------------------------------------------------- capture accuracy

def test_accuracy_endpoint_compares_hand_entry_with_what_the_engine_logged(app, admin, sandbox):
    from datetime import datetime

    ann, _ = signup(app, "Ann Player", gspro_name="AnnP")
    r = ann.post("/api/play/rounds", json={"holes": 9}).json()
    for hole in range(1, 10):
        play_hole(ann, r["id"], hole, PARS[hole - 1])
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    captured = [{"round_id": "abc", "player": "AnnP", "finished_at": now, "round_status": "completed", "score_source": "scorecard_ocr_verified",
                 "stats": {"gross_score": 36}, "hole_scores": [{"hole": i + 1, "par": p, "score_used": p + (1 if i == 2 else 0)} for i, p in enumerate(PARS)]}]
    path = sandbox / "data" / "rounds.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(c) + "\n" for c in captured), encoding="utf-8")

    result = admin.get("/api/admin/accuracy").json()
    assert result["summary"]["pairs"] == 1 and result["summary"]["holes_compared"] == 9 and result["summary"]["holes_matching"] == 8
    assert [h["hole"] for h in result["pairs"][0]["holes"] if h["match"] is False] == [3]
    assert admin.get("/api/admin/accuracy?league_id=999").status_code == 404


# ------------------------------------------------------------------------- demo

def test_demo_venue_has_accounts_a_live_board_history_and_capture_accuracy():
    demo_app = create_app(demo=True)
    anonymous = make_client(demo_app)
    session = anonymous.get("/api/session").json()
    assert session["demo"]["password"] == DEMO_PASSWORD and session["needs_setup"] is False
    league = anonymous.get("/api/leagues/public").json()["leagues"][0]
    board = anonymous.get(f"/api/leagues/{league['id']}/board").json()
    assert len(board["players"]) >= 8 and board["league_name"] == "Tuesday Night League"

    admin = make_client(demo_app)
    login(admin, DEMO_ADMIN_EMAIL, DEMO_PASSWORD)
    table = admin.get(f"/api/leagues/{league['id']}/table").json()
    assert len(table["players"]) == 16 and all(p["rounds"] >= 4 for p in table["players"])
    assert all(p["index"] is not None for p in table["players"])
    accuracy = admin.get("/api/admin/accuracy?days=365").json()["summary"]
    assert accuracy["pairs"] > 50 and 0.9 < accuracy["hole_accuracy"] < 1.0           # a few deliberate slips

    player = make_client(demo_app)
    login(player, "alex.rivera@demo.simcore22.test", DEMO_PASSWORD)
    assert player.get("/api/me/home").json()["user"]["display_name"] == "Alex Rivera"


def test_demo_tonight_advances_through_the_same_entry_code_and_never_touches_real_files(sandbox):
    demo_app = create_app(demo=True)
    venue = demo_app.state.demo_venue
    venue.engine.clock = lambda: venue.engine._epoch + 0.5            # the start of the night
    anonymous = make_client(demo_app)
    league_id = venue.league_id
    first = sum(p["thru"] for p in anonymous.get(f"/api/leagues/{league_id}/board").json()["players"])
    venue.engine.clock = lambda: venue.engine._epoch + 60
    later = sum(p["thru"] for p in anonymous.get(f"/api/leagues/{league_id}/board").json()["players"])
    assert later > first
    venue.engine.clock = lambda: venue.engine._epoch + venue.engine._cycle + 0.5     # the night loops: starts over, nothing piles up
    assert sum(p["thru"] for p in anonymous.get(f"/api/leagues/{league_id}/board").json()["players"]) == first
    assert not (sandbox / "data").exists()


def test_csrf_constant_is_the_one_the_pages_send():
    assert CSRF == {"x-requested-with": "SimCore22"}
    from simcore22.web.app import STATIC_DIR
    assert "SimCore22" in (STATIC_DIR / "js" / "api.js").read_text(encoding="utf-8")
