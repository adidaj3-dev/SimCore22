"""The player-account side: handicap math, accounts, hand-entered rounds, standings, capture accuracy."""
from datetime import datetime, timedelta

import pytest

from simcore22.league import accounts, accuracy, handicap, leagues, rounds, security, standings
from simcore22.league.db import Database
from simcore22.league.errors import Conflict, Forbidden, Invalid, NotAuthenticated, TooManyAttempts


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def conn(db):
    with db.connect() as c:
        yield c


def make_user(conn, name="Ann Player", email=None, **kw):
    email = email or f"{name.split()[0].lower()}@example.com"
    return accounts.create_user(conn, email=email, password="correct horse", display_name=name, **kw)


def admin_of(conn):
    return accounts.create_user(conn, email="boss@example.com", password="correct horse", display_name="Venue Boss", role="admin")


def play(conn, actor, strokes, **start_kw):
    if not start_kw.get("league_id"):
        start_kw.setdefault("holes", len(strokes))
    r = rounds.start(conn, actor, **start_kw)
    for hole, s in enumerate(strokes, start=1):
        r = rounds.save_hole(conn, actor, r["id"], hole, s)
    return r


# ---------------------------------------------------------------- handicap math

def test_strokes_on_hole_spreads_extra_strokes_to_early_holes():
    assert [handicap.strokes_on_hole(11, n, 9) for n in range(1, 10)] == [2, 2, 1, 1, 1, 1, 1, 1, 1]
    assert handicap.strokes_on_hole(0, 1, 9) == 0


def test_course_handicap_scales_with_holes():
    assert handicap.course_handicap(18.0, 9) == 9
    assert handicap.course_handicap(None, 9) == 0


def test_differential_caps_blow_up_holes_and_scales_to_18():
    scores = [(n, 4, 4) for n in range(1, 9)] + [(9, 4, 12)]       # one 12 on a par 4
    assert handicap.differential(scores, None, 9) == 4.0           # capped at 6 -> +2 over, x2 for 18 holes
    assert handicap.differential([], None, 9) is None


def test_index_uses_best_of_recent_and_blends_outdoor_for_new_players():
    assert handicap.index_from([], None) is None
    assert handicap.index_from([], 12.0) == 12.0
    assert handicap.index_from([6.0], 12.0) == 10.0                # 1/3 sim + 2/3 outdoor
    assert handicap.index_from([8.0, 6.0, 10.0]) == 6.0            # 3 rounds -> lowest 1
    assert handicap.index_from([float(n) for n in range(30, 10, -1)]) == 14.5   # last 20, best 8 -> mean(11..18)
    assert handicap.index_from([90.0]) == 54.0


# ------------------------------------------------------------------- security

def test_password_hash_roundtrip_and_uniqueness():
    a, b = security.hash_password("hunter22!"), security.hash_password("hunter22!")
    assert a != b and security.verify_password("hunter22!", a)
    assert not security.verify_password("wrong", a) and not security.verify_password("x", "garbage")


# -------------------------------------------------------------------- accounts

def test_sign_up_validates_and_seeds_indoor_index_from_outdoor(conn):
    u = make_user(conn, outdoor_index="14.2", ghin_number="12 345-678")
    assert u["indoor_index"] == 14.2 and u["ghin_number"] == "12345678" and u["role"] == "player"
    assert "password_hash" not in u
    assert make_user(conn, "Plus Golfer", outdoor_index="+2.1")["indoor_index"] == -2.1
    for bad in ({"email": "nope"}, {"password": "short"}, {"display_name": "A"}, {"ghin_number": "12"}, {"outdoor_index": "99"}, {"outdoor_index": "abc"}):
        args = {"email": "x@example.com", "password": "longenough", "display_name": "Xavier"} | bad
        with pytest.raises(Invalid):
            accounts.create_user(conn, **args)


def test_duplicate_email_is_refused_case_insensitively(conn):
    make_user(conn, email="ann@example.com")
    with pytest.raises(Conflict):
        make_user(conn, "Other Ann", email="ANN@Example.com")


def test_login_session_logout(conn):
    make_user(conn)
    token, user = accounts.login(conn, "ANN@example.com", "correct horse")
    assert accounts.user_for_token(conn, token)["id"] == user["id"]
    assert accounts.user_for_token(conn, "bogus") is None
    accounts.logout(conn, token)
    assert accounts.user_for_token(conn, token) is None


def test_bad_login_is_throttled_and_remembered(db):
    with db.connect() as c:
        make_user(c)
    for _ in range(accounts.MAX_FAILS_PER_EMAIL):
        with db.connect() as c, pytest.raises(NotAuthenticated):
            accounts.login(c, "ann@example.com", "wrong")
    with db.connect() as c, pytest.raises(TooManyAttempts):
        accounts.login(c, "ann@example.com", "correct horse")      # even the right password waits


def test_expired_and_disabled_sessions_stop_working(conn):
    make_user(conn)
    admin = admin_of(conn)
    token, user = accounts.login(conn, "ann@example.com", "correct horse")
    conn.execute("UPDATE sessions SET expires_at = ?", ((datetime.now().astimezone() - timedelta(days=1)).isoformat(),))
    assert accounts.user_for_token(conn, token) is None
    token, _ = accounts.login(conn, "ann@example.com", "correct horse")
    accounts.set_disabled(conn, admin["id"], user["id"], True)
    assert accounts.user_for_token(conn, token) is None
    with pytest.raises(Forbidden):
        accounts.login(conn, "ann@example.com", "correct horse")


def test_admin_reset_password_kills_sessions_and_cannot_demote_self(conn):
    ann, admin = make_user(conn), admin_of(conn)
    token, _ = accounts.login(conn, "ann@example.com", "correct horse")
    temp = accounts.admin_reset_password(conn, admin["id"], ann["id"])
    assert accounts.user_for_token(conn, token) is None
    accounts.login(conn, "ann@example.com", temp)
    with pytest.raises(Invalid):
        accounts.set_role(conn, admin["id"], admin["id"], "player")


# ---------------------------------------------------------------------- rounds

def test_round_lifecycle_and_auto_complete(conn):
    ann = make_user(conn, outdoor_index=18)
    r = rounds.start(conn, ann, holes=9)
    assert r["status"] == "in_progress" and r["thru"] == 0
    with pytest.raises(Conflict):
        rounds.start(conn, ann, holes=9)
    r = rounds.save_hole(conn, ann, r["id"], 1, 5)
    assert (r["thru"], r["gross"], r["vs_par"]) == (1, 5, 1)
    for hole in range(2, 10):
        r = rounds.save_hole(conn, ann, r["id"], hole, 5)
    assert r["status"] == "completed" and r["finished_at"] and r["thru"] == 9
    assert accounts.get_user(conn, ann["id"])["indoor_index"] is not None


def test_net_uses_the_index_at_the_start_of_the_round(conn):
    ann = make_user(conn, outdoor_index=18)                      # course handicap 9 over 9 holes
    r = play(conn, ann, [5] * 9)
    assert r["course_handicap"] == 9 and r["gross"] == 45 and r["net"] == 36
    assert r["vs_par"] == 45 - 36 and r["net_vs_par"] == 0


def test_save_hole_validation(conn):
    ann = make_user(conn)
    r = rounds.start(conn, ann, holes=9)
    for hole, strokes in ((0, 4), (10, 4), (1, 0), (1, 16), ("x", 4)):
        with pytest.raises(Invalid):
            rounds.save_hole(conn, ann, r["id"], hole, strokes)
    with pytest.raises(Invalid):
        rounds.save_hole(conn, ann, r["id"], 1, 4, par=7)


def test_editing_a_hole_replaces_it_and_clear_hole_works_only_in_progress(conn):
    ann = make_user(conn)
    r = rounds.start(conn, ann, holes=9)
    rounds.save_hole(conn, ann, r["id"], 1, 5)
    r = rounds.save_hole(conn, ann, r["id"], 1, 4)
    assert r["thru"] == 1 and r["gross"] == 4
    assert rounds.clear_hole(conn, ann, r["id"], 1)["thru"] == 0


def test_ending_early_saves_data_and_empty_round_is_abandoned(conn):
    ann = make_user(conn)
    r = rounds.start(conn, ann, holes=18)
    assert rounds.finish(conn, ann, r["id"])["status"] == "abandoned"
    r = rounds.start(conn, ann, holes=18)
    for hole in range(1, 13):
        rounds.save_hole(conn, ann, r["id"], hole, 5)
    done = rounds.finish(conn, ann, r["id"])
    assert done["status"] == "ended_early" and done["thru"] == 12 and done["counts"]     # 12 holes >= 9: counts
    r = rounds.start(conn, ann, holes=18)
    for hole in range(1, 6):
        rounds.save_hole(conn, ann, r["id"], hole, 5)
    short = rounds.finish(conn, ann, r["id"])
    assert short["status"] == "ended_early" and not short["counts"]                       # 5 holes: kept, but no handicap


def test_players_cannot_touch_each_others_rounds_but_admins_can(conn):
    ann, bob, admin = make_user(conn), make_user(conn, "Bob Player"), admin_of(conn)
    r = rounds.start(conn, ann, holes=9)
    with pytest.raises(Forbidden):
        rounds.save_hole(conn, bob, r["id"], 1, 4)
    assert rounds.save_hole(conn, admin, r["id"], 1, 4)["thru"] == 1
    with pytest.raises(Forbidden):
        rounds.start(conn, bob, user_id=ann["id"], holes=9)
    assert rounds.start(conn, admin, user_id=bob["id"], holes=9)["user_id"] == bob["id"]


def test_old_finished_rounds_need_an_admin_to_edit(conn):
    ann, admin = make_user(conn), admin_of(conn)
    r = play(conn, ann, [4] * 9)
    conn.execute("UPDATE rounds SET finished_at = ? WHERE id = ?", ((datetime.now().astimezone() - timedelta(days=3)).isoformat(), r["id"]))
    with pytest.raises(Forbidden):
        rounds.save_hole(conn, ann, r["id"], 1, 5)
    assert rounds.save_hole(conn, admin, r["id"], 1, 5)["gross"] == 37


def test_editing_a_score_recomputes_the_handicap_and_deleting_a_round_too(conn):
    ann, admin = make_user(conn), admin_of(conn)
    bad = play(conn, ann, [8] * 9)                              # a typo-ridden round
    index_bad = accounts.get_user(conn, ann["id"])["indoor_index"]
    rounds.save_hole(conn, ann, bad["id"], 1, 4)
    for hole in range(2, 10):
        rounds.save_hole(conn, ann, bad["id"], hole, 4)
    index_fixed = accounts.get_user(conn, ann["id"])["indoor_index"]
    assert index_fixed < index_bad
    history = rounds.handicap_history(conn, ann["id"])
    assert history[-1]["index"] == index_fixed and history[-1]["method"] == handicap.METHOD
    rounds.delete(conn, admin, bad["id"])
    assert accounts.get_user(conn, ann["id"])["indoor_index"] is None


def test_handicap_follows_rounds_in_order(conn):
    ann = make_user(conn, outdoor_index=20)
    play(conn, ann, [4, 4, 3, 5, 4, 4, 3, 4, 5])                # level par
    assert accounts.get_user(conn, ann["id"])["indoor_index"] == pytest.approx(13.3, abs=0.1)   # 1/3 * 0 + 2/3 * 20
    play(conn, ann, [4, 4, 3, 5, 4, 4, 3, 4, 5])
    play(conn, ann, [4, 4, 3, 5, 4, 4, 3, 4, 5])
    assert accounts.get_user(conn, ann["id"])["indoor_index"] == 0.0     # 3 rounds: outdoor no longer counts


def test_stale_rounds_are_closed(conn):
    ann = make_user(conn)
    r = rounds.start(conn, ann, holes=9)
    rounds.save_hole(conn, ann, r["id"], 1, 4)
    conn.execute("UPDATE rounds SET updated_at = ?", ((datetime.now().astimezone() - timedelta(hours=20)).isoformat(),))
    assert rounds.abandon_stale(conn) == 1
    assert rounds.get_row(conn, r["id"])["status"] == "ended_early"


# --------------------------------------------------------------- leagues / board

def setup_league(conn, ranking="net"):
    admin = admin_of(conn)
    league = leagues.create(conn, admin["id"], name="Tuesday Night League", holes=9, ranking=ranking, course_name="Pebble Beach")
    return admin, league


def test_joining_by_code_and_league_rounds_use_league_settings(conn):
    admin, league = setup_league(conn)
    ann = make_user(conn)
    with pytest.raises(Forbidden):
        rounds.start(conn, ann, league_id=league["id"])             # not a member yet
    leagues.join(conn, ann["id"], league["join_code"].lower())
    with pytest.raises(Conflict):
        leagues.join(conn, ann["id"], league["join_code"])
    r = rounds.start(conn, ann, league_id=league["id"], bay="Bay 3")
    assert r["holes_total"] == 9 and r["course_name"] == "Pebble Beach" and r["bay"] == "Bay 3"
    with pytest.raises(Invalid):
        leagues.create(conn, admin["id"], name="X")
    with pytest.raises(Invalid):
        leagues.create(conn, admin["id"], name="Bad pars", pars=[4, 4])


def test_live_board_updates_after_every_hole_and_ranks_by_the_league_basis(conn):
    admin, league = setup_league(conn, ranking="net")
    low, high = make_user(conn, "Low Index", outdoor_index=0), make_user(conn, "High Index", outdoor_index=18)
    for u in (low, high):
        leagues.join(conn, u["id"], league["join_code"])
    ra, rb = rounds.start(conn, low, league_id=league["id"]), rounds.start(conn, high, league_id=league["id"])
    assert standings.live_board(conn, league["id"])["players"] == []      # nobody has entered a hole
    rounds.save_hole(conn, low, ra["id"], 1, 4)
    rounds.save_hole(conn, high, rb["id"], 1, 5)                          # gross +1 but gets 1 stroke: net par
    board = standings.live_board(conn, league["id"])
    assert board["league_name"] == "Tuesday Night League" and board["holes_total"] == 9 and not board["round_complete"]
    by_name = {p["name"]: p for p in board["players"]}
    assert by_name["Low Index"]["vs_par"] == 0 and by_name["High Index"]["vs_par"] == 0     # net to par
    assert by_name["High Index"]["gross_vs_par"] == 1 and by_name["High Index"]["thru"] == 1
    rounds.save_hole(conn, low, ra["id"], 2, 7)
    assert {p["name"]: p["vs_par"] for p in standings.live_board(conn, league["id"])["players"]}["Low Index"] == 3


def test_gross_league_ranks_on_gross(conn):
    admin, league = setup_league(conn, ranking="gross")
    ann = make_user(conn, outdoor_index=18)
    leagues.join(conn, ann["id"], league["join_code"])
    r = rounds.start(conn, ann, league_id=league["id"])
    rounds.save_hole(conn, ann, r["id"], 1, 6)
    assert standings.live_board(conn, league["id"])["players"][0]["vs_par"] == 2


def test_league_table_ranks_by_average_to_par(conn):
    admin, league = setup_league(conn, ranking="gross")
    ann, bob, cat = make_user(conn, "Ann Player"), make_user(conn, "Bob Player"), make_user(conn, "Cat Player")
    for u in (ann, bob, cat):
        leagues.join(conn, u["id"], league["join_code"])
    par = [4, 4, 3, 5, 4, 4, 3, 4, 5]
    play(conn, ann, [p + 1 for p in par], league_id=league["id"])
    play(conn, bob, par, league_id=league["id"])
    play(conn, bob, [p + 2 for p in par], league_id=league["id"])
    table = standings.league_table(conn, league["id"])
    rows = {p["name"]: p for p in table["players"]}
    assert rows["Ann Player"]["avg_vs_par"] == 9.0 and rows["Bob Player"]["avg_vs_par"] == 9.0
    assert rows["Cat Player"]["avg_vs_par"] is None and rows["Cat Player"]["rank"] == 3
    assert rows["Ann Player"]["rank"] == 2 and rows["Bob Player"]["rank"] == 1          # same average, Bob's best round wins the tie-break
    assert not rows["Ann Player"]["tied"]


def test_player_profile(conn):
    ann = make_user(conn, outdoor_index=10)
    play(conn, ann, [4, 4, 3, 5, 4, 4, 3, 4, 5])
    profile = standings.player_profile(conn, ann["id"])
    assert profile["stats"]["rounds"] == 1 and profile["active_round"] is None
    assert profile["handicap"]["history"] and profile["handicap"]["outdoor_index"] == 10


# --------------------------------------------------------------------- accuracy

def engine_record(name, finished_at, scores, source="scorecard_ocr_verified", round_id="r1"):
    return {"round_id": round_id, "player": name, "finished_at": finished_at, "round_status": "completed", "score_source": source,
            "stats": {"gross_score": sum(scores)},
            "hole_scores": [{"hole": i, "par": 4, "score_used": s} for i, s in enumerate(scores, start=1)]}


def test_accuracy_pairs_manual_rounds_with_captured_ones(conn):
    ann = make_user(conn, gspro_name="AnnP")
    manual = play(conn, ann, [4, 5, 4, 6, 4, 4, 3, 4, 5])
    soon = datetime.now().astimezone().isoformat()
    records = [engine_record("annp", soon, [4, 5, 4, 5, 4, 4, 3, 4, 5], round_id="a"),                  # one hole differs
               engine_record("Somebody Else", soon, [4] * 9, round_id="b")]
    result = accuracy.check(conn, records)
    summary = result["summary"]
    assert summary["pairs"] == 1 and summary["holes_compared"] == 9 and summary["holes_matching"] == 8
    assert summary["hole_accuracy"] == pytest.approx(0.889, abs=0.001) and summary["unmatched_capture"] == 1
    pair = result["pairs"][0]
    assert pair["manual_round_id"] == manual["id"] and not pair["gross_matches"]
    assert [h["hole"] for h in pair["holes"] if h["match"] is False] == [4]
    assert summary["verified"]["accuracy"] == pytest.approx(0.889, abs=0.001)


def test_accuracy_reports_unmatched_rounds_instead_of_guessing(conn):
    ann = make_user(conn)
    play(conn, ann, [4] * 9)
    old = (datetime.now().astimezone() - timedelta(days=2)).isoformat()
    result = accuracy.check(conn, [engine_record("Ann Player", old, [4] * 9)])
    assert result["summary"]["pairs"] == 0 and result["summary"]["unmatched_manual"] == 1 and result["summary"]["hole_accuracy"] is None


def test_accuracy_counts_holes_the_capture_missed(conn):
    ann = make_user(conn)
    play(conn, ann, [4] * 9)
    rec = engine_record("Ann Player", datetime.now().astimezone().isoformat(), [4] * 9)
    rec["hole_scores"] = rec["hole_scores"][:7]
    pair = accuracy.check(conn, [rec])["pairs"][0]
    assert pair["holes_compared"] == 7 and pair["holes_missing_from_capture"] == 2 and pair["hole_accuracy"] == 1.0
