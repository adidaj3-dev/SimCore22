# simcore22/league/rounds.py
"""
Rounds typed in by hand, hole by hole, and the handicap that grows out of them.

A round starts when a player (or an admin on their behalf) opens it, gains a hole each time
one is saved, and finishes by itself after the last hole - or earlier if the player ends it.
Statuses mirror the engine's own round log: in_progress | completed | ended_early | abandoned.
Every change recomputes that player's indoor handicap from their whole history, so correcting
a wrong score corrects the handicap too.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from simcore22.league import handicap, leagues
from simcore22.league.db import audit, bump_revision, now_iso
from simcore22.league.errors import Conflict, Forbidden, Invalid, NotFound

MIN_HOLES_TO_COUNT = 9          # an ended-early round feeds the handicap only if at least this many holes were played
PLAYER_EDIT_WINDOW = timedelta(hours=24)   # after this, only an admin can change a finished round
COUNTED_STATUSES = ("completed", "ended_early")


def _holes_rows(conn, round_id: int) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM hole_scores WHERE round_id = ? ORDER BY hole", (round_id,)).fetchall()


def get_row(conn, round_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    if row is None:
        raise NotFound("No such round.")
    return row


def counts_toward_handicap(row: sqlite3.Row, holes_played: int) -> bool:
    if row["status"] == "completed":
        return holes_played > 0
    return row["status"] == "ended_early" and holes_played >= MIN_HOLES_TO_COUNT


def view(conn, row: sqlite3.Row, *, with_user: bool = False) -> Dict[str, Any]:
    """A round with its scorecard and running totals (gross, to par, net to par)."""
    scores = _holes_rows(conn, row["id"])
    planned = leagues.pars_of(row)
    chp = handicap.course_handicap(row["index_at_start"], row["holes"])
    played = {s["hole"]: s for s in scores}
    holes = []
    for n in range(1, row["holes"] + 1):
        s = played.get(n)
        holes.append({"hole": n, "par": s["par"] if s else planned[n - 1], "strokes": s["strokes"] if s else None,
                      "received": handicap.strokes_on_hole(chp, n, row["holes"])})
    gross = sum(s["strokes"] for s in scores)
    par_played = sum(s["par"] for s in scores)
    received = sum(h["received"] for h in holes if h["strokes"] is not None)
    out = {
        "id": row["id"], "user_id": row["user_id"], "league_id": row["league_id"], "course_name": row["course_name"],
        "holes_total": row["holes"], "bay": row["bay"], "status": row["status"], "started_at": row["started_at"],
        "finished_at": row["finished_at"], "index_at_start": row["index_at_start"], "course_handicap": chp,
        "differential": row["differential"], "counts": counts_toward_handicap(row, len(scores)),
        "thru": len(scores), "gross": gross if scores else None, "par_played": par_played,
        "vs_par": gross - par_played if scores else None,
        "net_vs_par": gross - par_played - received if scores else None,
        "net": gross - received if scores else None,
        "holes": holes, "entered_by": row["entered_by"],
    }
    if with_user:
        u = conn.execute("SELECT display_name FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        out["player"] = u["display_name"] if u else None
    return out


# ------------------------------------------------------------------ authority

def _can_manage(conn, row: sqlite3.Row, actor: Dict[str, Any]) -> bool:
    if actor["role"] == "admin":
        return True
    if row["user_id"] != actor["id"]:
        return False
    if row["status"] == "in_progress" or not row["finished_at"]:
        return True
    return datetime.now().astimezone() - datetime.fromisoformat(row["finished_at"]) <= PLAYER_EDIT_WINDOW


def _require_manage(conn, row, actor) -> None:
    if not _can_manage(conn, row, actor):
        raise Forbidden("Only the player can change their round - and only within a day of finishing it. Ask the front desk.")


# --------------------------------------------------------------------- start

def active_round(conn, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM rounds WHERE user_id=? AND status='in_progress' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()


def start(conn, actor: Dict[str, Any], *, user_id: Optional[int] = None, league_id: Optional[int] = None, bay: Optional[str] = None,
          holes: Optional[int] = None, course_name: Optional[str] = None, pars: Any = None) -> Dict[str, Any]:
    user_id = user_id or actor["id"]
    if user_id != actor["id"] and actor["role"] != "admin":
        raise Forbidden("You can only start your own round.")
    player = conn.execute("SELECT * FROM users WHERE id = ? AND disabled = 0", (user_id,)).fetchone()
    if player is None:
        raise NotFound("No such player.")
    if active_round(conn, user_id):
        raise Conflict("There's already a round in progress. Finish or end it first.")
    league = None
    if league_id:
        league = leagues.get_row(conn, int(league_id))
        if league["archived"]:
            raise Forbidden("That league has ended.")
        if not leagues.is_member(conn, league["id"], user_id):
            raise Forbidden("Join the league before playing a league round.")
        holes, course_name, pars = league["holes"], course_name or league["course_name"], pars or leagues.pars_of(league)
    if str(holes) not in ("9", "18"):
        raise Invalid("Choose a 9 or 18 hole round.")
    holes = int(holes)
    pars = leagues.clean_pars(pars, holes)
    bay = " ".join(str(bay or "").split())[:20] or None
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO rounds(user_id, league_id, course_name, holes, bay, planned_pars, status, started_at, updated_at, index_at_start, entered_by)"
        " VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?, ?, ?, ?)",
        (user_id, league["id"] if league else None, (str(course_name).strip() or None) if course_name else None, holes, bay,
         json.dumps(pars), now, now, player["indoor_index"], actor["id"]),
    )
    bump_revision(conn)
    return view(conn, get_row(conn, cur.lastrowid))


# ---------------------------------------------------------------------- holes

def save_hole(conn, actor: Dict[str, Any], round_id: int, hole: Any, strokes: Any, par: Any = None) -> Dict[str, Any]:
    row = get_row(conn, round_id)
    _require_manage(conn, row, actor)
    if row["status"] == "abandoned":
        raise Conflict("That round was abandoned.")
    try:
        hole, strokes = int(hole), int(strokes)
    except (TypeError, ValueError):
        raise Invalid("Hole and strokes must be numbers.") from None
    if not 1 <= hole <= row["holes"]:
        raise Invalid(f"This round has holes 1-{row['holes']}.")
    if not 1 <= strokes <= 15:
        raise Invalid("Strokes must be between 1 and 15.")
    planned = leagues.pars_of(row)
    par = planned[hole - 1] if par in (None, "") else par
    try:
        par = int(par)
    except (TypeError, ValueError):
        raise Invalid("Par must be a number.") from None
    if par not in (3, 4, 5, 6):
        raise Invalid("Par must be 3, 4, 5 or 6.")
    conn.execute(
        "INSERT INTO hole_scores(round_id, hole, par, strokes, entered_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(round_id, hole) DO UPDATE SET par=excluded.par, strokes=excluded.strokes, entered_at=excluded.entered_at",
        (round_id, hole, par, strokes, now_iso()),
    )
    conn.execute("UPDATE rounds SET updated_at = ? WHERE id = ?", (now_iso(), round_id))
    row = get_row(conn, round_id)
    done = conn.execute("SELECT COUNT(*) FROM hole_scores WHERE round_id = ?", (round_id,)).fetchone()[0]
    if row["status"] == "in_progress" and done >= row["holes"]:
        _close(conn, row, "completed")
    elif row["status"] != "in_progress":
        if row["status"] == "ended_early" and done >= row["holes"]:
            conn.execute("UPDATE rounds SET status = 'completed' WHERE id = ?", (round_id,))
        recompute_handicap(conn, row["user_id"])      # an edit to a finished round
        audit(conn, actor["id"], "score_edited", f"round {round_id} hole {hole} -> {strokes}")
    bump_revision(conn)
    return view(conn, get_row(conn, round_id))


def clear_hole(conn, actor: Dict[str, Any], round_id: int, hole: int) -> Dict[str, Any]:
    """Un-enter a hole (only while the round is still open, so a finished round can't lose holes by accident)."""
    row = get_row(conn, round_id)
    _require_manage(conn, row, actor)
    if row["status"] != "in_progress":
        raise Conflict("Only a round in progress can lose a hole. Ask the front desk to correct a finished round.")
    conn.execute("DELETE FROM hole_scores WHERE round_id = ? AND hole = ?", (round_id, int(hole)))
    conn.execute("UPDATE rounds SET updated_at = ? WHERE id = ?", (now_iso(), round_id))
    bump_revision(conn)
    return view(conn, get_row(conn, round_id))


# --------------------------------------------------------------------- finish

def _close(conn, row, status: str) -> None:
    conn.execute("UPDATE rounds SET status = ?, finished_at = ?, updated_at = ? WHERE id = ?", (status, now_iso(), now_iso(), row["id"]))
    recompute_handicap(conn, row["user_id"])


def finish(conn, actor: Dict[str, Any], round_id: int) -> Dict[str, Any]:
    """End a round now: with no holes it is abandoned; otherwise it is saved as ended early (or completed if all holes are in)."""
    row = get_row(conn, round_id)
    _require_manage(conn, row, actor)
    if row["status"] != "in_progress":
        raise Conflict("That round is already finished.")
    played = conn.execute("SELECT COUNT(*) FROM hole_scores WHERE round_id = ?", (round_id,)).fetchone()[0]
    _close(conn, row, "abandoned" if played == 0 else "completed" if played >= row["holes"] else "ended_early")
    bump_revision(conn)
    return view(conn, get_row(conn, round_id))


def delete(conn, admin: Dict[str, Any], round_id: int) -> None:
    if admin["role"] != "admin":
        raise Forbidden("Only an admin can delete a round.")
    row = get_row(conn, round_id)
    conn.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
    audit(conn, admin["id"], "round_deleted", f"round {round_id} of user {row['user_id']}")
    recompute_handicap(conn, row["user_id"])
    bump_revision(conn)


def abandon_stale(conn, *, hours: float = 12.0) -> int:
    """Close rounds nobody has touched for a long time (a player who walked out): saved as ended early, or abandoned when empty."""
    cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
    stale = conn.execute("SELECT * FROM rounds WHERE status='in_progress' AND updated_at < ?", (cutoff,)).fetchall()
    for row in stale:
        played = conn.execute("SELECT COUNT(*) FROM hole_scores WHERE round_id = ?", (row["id"],)).fetchone()[0]
        _close(conn, row, "abandoned" if played == 0 else "ended_early")
    if stale:
        bump_revision(conn)
    return len(stale)


# -------------------------------------------------------------------- handicap

def recompute_handicap(conn, user_id: int) -> Optional[float]:
    """Replay the player's counted rounds oldest-first and rebuild their index, differentials and history."""
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return None
    outdoor = user["outdoor_index"]
    rounds = conn.execute(
        "SELECT * FROM rounds WHERE user_id = ? AND status IN ('completed','ended_early') ORDER BY started_at, id", (user_id,)).fetchall()

    conn.execute("DELETE FROM handicap_history WHERE user_id = ? AND method != 'outdoor-start'", (user_id,))
    conn.execute("UPDATE rounds SET differential = NULL WHERE user_id = ?", (user_id,))
    seen: List[float] = []
    index_now = handicap.index_from([], outdoor)
    for row in rounds:
        scores = [(s["hole"], s["par"], s["strokes"]) for s in _holes_rows(conn, row["id"])]
        if not counts_toward_handicap(row, len(scores)):
            continue
        diff = handicap.differential(scores, index_now, row["holes"])
        seen.append(diff)
        conn.execute("UPDATE rounds SET differential = ?, index_at_start = ? WHERE id = ?", (diff, index_now, row["id"]))
        index_now = handicap.index_from(seen, outdoor)
        conn.execute(
            "INSERT INTO handicap_history(user_id, round_id, effective_at, index_value, rounds_counted, method, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, row["id"], row["finished_at"] or row["updated_at"], index_now, min(len(seen), handicap.RECENT_ROUNDS),
             handicap.METHOD, f"differential {diff:+.1f}"),
        )
    conn.execute("UPDATE users SET indoor_index = ? WHERE id = ?", (index_now, user_id))
    return index_now


def handicap_history(conn, user_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM handicap_history WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
    return [{"round_id": r["round_id"], "at": r["effective_at"], "index": r["index_value"], "rounds_counted": r["rounds_counted"],
             "method": r["method"], "note": r["note"]} for r in rows]


# --------------------------------------------------------------------- listing

def list_for_user(conn, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM rounds WHERE user_id = ? ORDER BY started_at DESC, id DESC LIMIT ?", (user_id, limit)).fetchall()
    return [view(conn, r) for r in rows]


def list_for_league(conn, league_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM rounds WHERE league_id = ? ORDER BY started_at DESC, id DESC LIMIT ?", (league_id, limit)).fetchall()
    return [view(conn, r, with_user=True) for r in rows]
