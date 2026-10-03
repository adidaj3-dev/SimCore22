from datetime import datetime, timedelta

from simcore22.web import data

NOW = datetime(2026, 10, 14, 20, 0).astimezone()


def _rec(player="Alex", round_id="r1", when=NOW, status="completed", gross=40, vs_par=4, source="scorecard_ocr_verified",
         holes=None, **extra):
    record = {
        "round_id": round_id, "player": player, "finished_at": when.isoformat(timespec="seconds"),
        "round_status": status, "course": "Harbor Links", "holes_played": 9, "score_source": source,
        "handicap_index_used": 12, "stats": {"gross_score": gross, "gross_vs_par": vs_par, "net_score": gross - 12},
        "hole_scores": holes or [], "scorecard_ocr": {"image_file": None},
    }
    record.update(extra)
    return record


def _hole(n, par, score, **kw):
    return {"hole": n, "par": par, "score_used": score, "par_assumed": False, "counted": True, **kw}


# ---------------------------------------------------------------- collapsing

def test_a_checkpoint_is_replaced_by_the_final_record_of_the_same_round():
    snapshot = _rec(status="snapshot", gross=20, when=NOW - timedelta(minutes=30))
    final = _rec(status="ended_early", gross=31)
    (only,) = data.collapse([snapshot, final])  # file order: oldest first
    assert only["round_status"] == "ended_early" and only["stats"]["gross_score"] == 31


def test_the_same_player_in_different_rounds_is_not_merged_and_newest_comes_first():
    old = _rec(round_id="old", when=NOW - timedelta(days=3))
    new = _rec(round_id="new", when=NOW)
    assert [r["round_id"] for r in data.collapse([old, new])] == ["new", "old"]


def test_player_names_match_ignoring_case_when_collapsing():
    (only,) = data.collapse([_rec(player="Alex", status="snapshot"), _rec(player="ALEX")])
    assert only["player"] == "ALEX"


def test_an_open_checkpoint_is_not_a_result():
    assert data.finals([_rec(status="snapshot"), _rec(status="completed")]) == [_rec(status="completed")]


# ----------------------------------------------------------------- summaries

def test_summary_exposes_the_numbers_the_screens_show():
    s = data.summarize(_rec(handicap_index_after=11, scorecard_ocr={"image_file": r"C:\x\data\scorecards\card.png"}))
    assert (s["gross"], s["vs_par"], s["net"]) == (40, 4, 28)
    assert s["verified"] is True and s["handicap"] == 11
    assert s["image"] == "card.png"  # a file name only, never the machine's folder layout


def test_unverified_rounds_say_so_and_fall_back_to_the_handicap_used():
    s = data.summarize(_rec(source="shot_tally"))
    assert s["verified"] is False and s["handicap"] == 12


def test_detail_includes_holes_shots_and_only_the_stats_that_exist():
    record = _rec(
        holes=[_hole(1, 4, 4, shot_tally=4), _hole(2, 3, 5, shot_tally=5, counted=False)],
        shots=[{"ball_speed": 140.0, "carry_distance": 200.0}, {"ball_speed": 150.0, "carry_distance": 220.0}],
        shot_devices=["Falcon"],
    )
    record["stats"].update(birdies=0, pars=1, fir=None)
    d = data.detail(record)

    assert [(h["hole"], h["par"], h["score"], h["counted"]) for h in d["holes"]] == [(1, 4, 4, True), (2, 3, 5, False)]
    assert d["shots"] == {"count": 2, "devices": ["Falcon"], "avg_ball_speed": 145.0, "max_ball_speed": 150.0, "avg_carry": 210.0}
    assert d["stats"] == {"birdies": 0, "pars": 1}  # fir=None is left out, not shown as a blank


# ------------------------------------------------------------------- filters

def test_filtering_rounds_by_status_player_and_text():
    records = [
        _rec(player="Alex", round_id="a"), _rec(player="Sam", round_id="b", status="abandoned"),
        _rec(player="Sam", round_id="c", course="Cedar Ridge"),
    ]
    assert [r["round_id"] for r in data.filter_rounds(records, status="abandoned")] == ["b"]
    assert [r["round_id"] for r in data.filter_rounds(records, player="sam")] == ["b", "c"]
    assert [r["round_id"] for r in data.filter_rounds(records, query="cedar")] == ["c"]
    assert len(data.filter_rounds(records)) == 3


# ------------------------------------------------------------------- players

def test_player_profiles_average_only_completed_rounds_and_use_the_latest_handicap():
    records = [
        _rec(round_id="1", when=NOW - timedelta(days=14), vs_par=6, handicap_index_after=12),
        _rec(round_id="2", when=NOW - timedelta(days=7), vs_par=2, handicap_index_after=11),
        _rec(round_id="3", when=NOW, vs_par=-9, status="ended_early"),   # quit early: not in the average
        _rec(round_id="4", when=NOW, vs_par=0, status="snapshot"),       # open checkpoint: ignored
    ]
    (profile,) = data.players(records)
    assert profile["rounds"] == 3 and profile["completed_rounds"] == 2
    assert profile["avg_vs_par"] == 4.0 and profile["best_vs_par"] == 2
    assert profile["trend"] == [6, 2, -9]  # oldest first, what a sparkline wants


def test_players_are_listed_best_average_first():
    records = [_rec(player="Sam", vs_par=8), _rec(player="Alex", vs_par=1, round_id="x"), _rec(player="Quit", status="abandoned", round_id="y")]
    assert [p["player"] for p in data.players(records)] == ["Alex", "Sam", "Quit"]  # no completed rounds sorts last


# --------------------------------------------------------------------- venue

def test_venue_summary_windows_and_rates():
    records = [
        _rec(round_id="a", when=NOW - timedelta(days=1)),
        _rec(round_id="b", player="Sam", when=NOW - timedelta(days=2), source="shot_tally"),
        _rec(round_id="c", when=NOW - timedelta(days=9)),                       # previous week
        _rec(round_id="d", when=NOW - timedelta(days=60), source="shot_tally"),  # outside 30 days
    ]
    s = data.venue_summary(records, now=NOW)
    assert (s["rounds_7d"], s["rounds_prev_7d"], s["players_7d"], s["total_rounds"]) == (2, 1, 2, 4)
    assert s["verified_rate_30d"] == 0.667   # 2 of the 3 rounds in the last 30 days
    assert len(s["rounds_by_day"]) == 14 and s["rounds_by_day"][-1]["date"] == NOW.date().isoformat()


def test_scoring_mix_counts_only_holes_with_a_known_par_that_were_counted():
    holes = [
        _hole(1, 4, 3), _hole(2, 4, 4), _hole(3, 4, 5), _hole(4, 4, 7), _hole(5, 5, 3),
        {"hole": 6, "par": None, "score_used": 4, "par_assumed": True, "counted": True},   # par unknown
        _hole(7, 4, 9, counted=False),                                                      # quit mid-hole
    ]
    mix = data.venue_summary([_rec(holes=holes)], now=NOW)["scoring_mix"]
    assert mix == {"eagle_or_better": 1, "birdie": 1, "par": 1, "bogey": 1, "double_or_worse": 1}


# --------------------------------------------------------------- leaderboard

def test_ranking_is_by_score_to_par_with_ties_sharing_a_rank():
    rows = data.rank_players([
        {"name": "C", "vs_par": 2, "thru": 3, "gross": 14},
        {"name": "A", "vs_par": -1, "thru": 3, "gross": 11},
        {"name": "B", "vs_par": -1, "thru": 3, "gross": 11},
    ])
    assert [(r["name"], r["rank"], r["tied"]) for r in rows] == [("A", 1, True), ("B", 1, True), ("C", 3, False)]


def test_a_player_who_has_played_fewer_holes_does_not_lead_on_gross():
    rows = data.rank_players([
        {"name": "Early", "vs_par": 0, "thru": 1, "gross": 4},
        {"name": "Steady", "vs_par": 0, "thru": 3, "gross": 12},
    ])
    assert [r["name"] for r in rows] == ["Steady", "Early"]
