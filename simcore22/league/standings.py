# simcore22/league/standings.py
"""
What the screens read, built from the hand-entered rounds: the live leaderboard for tonight's
play, the season table for a league, and a player's profile.

`live_board` deliberately returns the same shape the engine writes to state/leaderboard.json,
so the bay-TV page can show either without caring where the numbers came from.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Dict, Optional

from simcore22.league import handicap, leagues, rounds
from simcore22.league.db import now_iso

LIVE_WINDOW_HOURS = 12      # a league round counts as "tonight's play" for this long after it starts


def _basis(r: Dict[str, Any], ranking: str) -> Optional[int]:
    return r["net_vs_par"] if ranking == "net" else r["vs_par"]


def live_board(conn, league_id: int, *, hours: float = LIVE_WINDOW_HOURS) -> Dict[str, Any]:
    league = leagues.get_row(conn, league_id)
    since = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT r.*, u.display_name, m.team FROM rounds r JOIN users u ON u.id = r.user_id"
        " LEFT JOIN league_members m ON m.league_id = r.league_id AND m.user_id = r.user_id"
        " WHERE r.league_id = ? AND r.started_at >= ? AND r.status != 'abandoned' ORDER BY r.started_at, r.id",
        (league_id, since)).fetchall()
    latest: Dict[int, Any] = {}
    for row in rows:                       # one line per player: their most recent round
        latest[row["user_id"]] = row
    players, open_rounds = [], 0
    for row in latest.values():
        r = rounds.view(conn, row)
        if r["thru"] == 0:
            continue                       # opened a round but hasn't entered a hole yet
        open_rounds += r["status"] == "in_progress"
        players.append({
            "name": row["display_name"], "team": row["team"], "simcore_index": r["index_at_start"],
            "bay": r["bay"], "thru": r["thru"], "vs_par": _basis(r, league["ranking"]),
            "gross_vs_par": r["vs_par"], "gross": r["gross"], "net": r["net"], "playing": r["status"] == "in_progress",
            "updated_at": row["updated_at"],
        })
    return {
        "league_id": league_id, "league_name": league["name"], "course_name": league["course_name"], "week": None,
        "format": f"{league['ranking'].title()} · {league['holes']} holes", "ranking": league["ranking"],
        "holes_total": league["holes"], "round_complete": bool(players) and open_rounds == 0, "players": players,
        "updated_at": now_iso(), "source": "manual",
    }


def league_table(conn, league_id: int) -> Dict[str, Any]:
    """Season standings: every member, ranked by average score to par over their finished league rounds."""
    league = leagues.get_row(conn, league_id)
    ranking = league["ranking"]
    members = conn.execute(
        "SELECT u.*, m.team FROM league_members m JOIN users u ON u.id = m.user_id WHERE m.league_id = ?", (league_id,)).fetchall()
    out = []
    for u in members:
        finished = [rounds.view(conn, r) for r in conn.execute(
            "SELECT * FROM rounds WHERE league_id = ? AND user_id = ? AND status IN ('completed','ended_early') ORDER BY started_at",
            (league_id, u["id"]))]
        full = [r for r in finished if r["status"] == "completed"]
        basis = [_basis(r, ranking) for r in full if _basis(r, ranking) is not None]
        out.append({
            "user_id": u["id"], "name": u["display_name"], "team": u["team"], "index": u["indoor_index"],
            "rounds": len(full), "avg_vs_par": round(mean(basis), 1) if basis else None,
            "best_vs_par": min(basis) if basis else None, "total_vs_par": sum(basis) if basis else None,
            "avg_gross": round(mean(r["gross"] for r in full), 1) if full else None,
            "last_played": finished[-1]["finished_at"] if finished else None,
            "trend": [_basis(r, ranking) for r in full[-8:]],
        })
    out.sort(key=lambda p: (p["avg_vs_par"] is None, p["avg_vs_par"] if p["avg_vs_par"] is not None else 0,
                            p["best_vs_par"] if p["best_vs_par"] is not None else 0, p["name"].lower()))
    rank, last_key, last_rank = 0, None, 0
    for p in out:
        rank += 1
        key = (p["avg_vs_par"], p["best_vs_par"])
        p["rank"] = last_rank if key == last_key and p["avg_vs_par"] is not None else rank
        p["tied"] = False
        last_key, last_rank = key, p["rank"]
    for p in out:
        p["tied"] = p["avg_vs_par"] is not None and sum(1 for q in out if q["rank"] == p["rank"]) > 1
    return {"league": leagues.view(conn, league), "ranking": ranking, "players": out}


def venue_overview(conn, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Headline numbers for the admin overview, from the hand-entered rounds."""
    now = now or datetime.now().astimezone()

    def started(row) -> datetime:
        return datetime.fromisoformat(row["started_at"])

    rows = conn.execute("SELECT * FROM rounds WHERE status != 'abandoned' ORDER BY started_at").fetchall()
    real = [r for r in rows if conn.execute("SELECT 1 FROM hole_scores WHERE round_id = ? LIMIT 1", (r["id"],)).fetchone()]
    last7 = [r for r in real if started(r) >= now - timedelta(days=7)]
    prev7 = [r for r in real if now - timedelta(days=14) <= started(r) < now - timedelta(days=7)]

    to_par = []
    for r in real:
        if r["status"] == "completed" and started(r) >= now - timedelta(days=30):
            s = conn.execute("SELECT SUM(strokes) - SUM(par) FROM hole_scores WHERE round_id = ?", (r["id"],)).fetchone()[0]
            to_par.append(s)

    mix = dict.fromkeys(("eagle_or_better", "birdie", "par", "bogey", "double_or_worse"), 0)
    since = (now - timedelta(days=30)).isoformat(timespec="seconds")
    for h in conn.execute("SELECT h.strokes - h.par AS d FROM hole_scores h JOIN rounds r ON r.id = h.round_id WHERE r.started_at >= ?", (since,)):
        d = h["d"]
        mix["eagle_or_better" if d <= -2 else {-1: "birdie", 0: "par", 1: "bogey"}.get(d, "double_or_worse")] += 1

    by_day = []
    for offset in range(13, -1, -1):
        day = (now - timedelta(days=offset)).date()
        by_day.append({"date": day.isoformat(), "rounds": sum(1 for r in real if started(r).astimezone().date() == day)})

    return {
        "total_rounds": len(real), "rounds_7d": len(last7), "rounds_prev_7d": len(prev7),
        "players": conn.execute("SELECT COUNT(*) FROM users WHERE role = 'player' AND disabled = 0").fetchone()[0],
        "players_7d": len({r["user_id"] for r in last7}),
        "leagues": conn.execute("SELECT COUNT(*) FROM leagues WHERE archived = 0").fetchone()[0],
        "playing_now": conn.execute("SELECT COUNT(*) FROM rounds WHERE status = 'in_progress'").fetchone()[0],
        "avg_vs_par_30d": round(mean(to_par), 1) if to_par else None,
        "rounds_by_day": by_day, "scoring_mix": mix,
    }


def player_profile(conn, user_id: int) -> Dict[str, Any]:
    from simcore22.league import accounts
    user = accounts.get_user(conn, user_id)
    mine = rounds.list_for_user(conn, user_id, limit=200)
    done = [r for r in mine if r["status"] in ("completed", "ended_early")]
    to_par = [r["vs_par"] for r in done if r["status"] == "completed" and r["vs_par"] is not None]
    return {
        "user": user,
        "rounds": mine,
        "stats": {
            "rounds": len(done), "avg_vs_par": round(mean(to_par), 1) if to_par else None,
            "best_vs_par": min(to_par) if to_par else None,
            "avg_gross": round(mean(r["gross"] for r in done if r["gross"] is not None), 1) if done else None,
        },
        "handicap": {"index": user["indoor_index"], "outdoor_index": user["outdoor_index"],
                     "history": rounds.handicap_history(conn, user_id), "method": handicap.METHOD,
                     "counted_best_of": handicap.best_k(min(len([r for r in done if r["counts"]]), handicap.RECENT_ROUNDS))},
        "active_round": next((r for r in mine if r["status"] == "in_progress"), None),
    }
