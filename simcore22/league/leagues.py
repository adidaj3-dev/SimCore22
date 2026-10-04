# simcore22/league/leagues.py
"""Leagues and who is in them."""
from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any, Dict, List, Optional

from simcore22.league.db import audit, bump_revision, now_iso
from simcore22.league.errors import Conflict, Forbidden, Invalid, NotFound

DEFAULT_PARS_9 = [4, 4, 3, 5, 4, 4, 3, 4, 5]
DEFAULT_PARS_18 = DEFAULT_PARS_9 + [4, 4, 3, 5, 4, 4, 3, 4, 5]
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def clean_pars(value: Any, holes: int) -> List[int]:
    if value in (None, "", []):
        return (DEFAULT_PARS_18 if holes == 18 else DEFAULT_PARS_9)[:holes]
    try:
        pars = [int(p) for p in value]
    except (TypeError, ValueError):
        raise Invalid("Pars must be a list of numbers.") from None
    if len(pars) != holes or any(p not in (3, 4, 5, 6) for p in pars):
        raise Invalid(f"Give one par (3-6) for each of the {holes} holes.")
    return pars


def pars_of(row) -> List[int]:
    holes = row["holes"]
    raw = row["default_pars"] if "default_pars" in row.keys() else row["planned_pars"]
    try:
        pars = json.loads(raw) if raw else None
    except ValueError:
        pars = None
    return pars if pars and len(pars) == holes else (DEFAULT_PARS_18 if holes == 18 else DEFAULT_PARS_9)[:holes]


def _new_code(conn) -> str:
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if not conn.execute("SELECT 1 FROM leagues WHERE join_code = ?", (code,)).fetchone():
            return code


def view(conn, row: sqlite3.Row, *, with_code: bool = False) -> Dict[str, Any]:
    members = conn.execute("SELECT COUNT(*) FROM league_members WHERE league_id = ?", (row["id"],)).fetchone()[0]
    out = {
        "id": row["id"], "name": row["name"], "season": row["season"], "holes": row["holes"], "ranking": row["ranking"],
        "course_name": row["course_name"], "pars": pars_of(row), "members": members, "archived": bool(row["archived"]),
        "created_at": row["created_at"],
    }
    if with_code:
        out["join_code"] = row["join_code"]
    return out


def get_row(conn, league_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    if row is None:
        raise NotFound("No such league.")
    return row


def create(conn, admin_id: int, *, name, season=None, holes=9, ranking="net", course_name=None, pars=None) -> Dict[str, Any]:
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 80:
        raise Invalid("Give the league a name (2-80 characters).")
    holes = int(holes) if str(holes) in ("9", "18") else None
    if holes is None:
        raise Invalid("A league plays 9 or 18 holes.")
    if ranking not in ("net", "gross"):
        raise Invalid("Rank by net or gross.")
    cur = conn.execute(
        "INSERT INTO leagues(name, season, holes, ranking, course_name, default_pars, join_code, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, (str(season).strip() or None) if season else None, holes, ranking,
         (str(course_name).strip() or None) if course_name else None, json.dumps(clean_pars(pars, holes)),
         _new_code(conn), now_iso()),
    )
    audit(conn, admin_id, "league_created", name)
    bump_revision(conn)
    return view(conn, get_row(conn, cur.lastrowid), with_code=True)


def update(conn, admin_id: int, league_id: int, **changes) -> Dict[str, Any]:
    row = get_row(conn, league_id)
    holes = row["holes"]
    new = {
        "name": row["name"], "season": row["season"], "ranking": row["ranking"], "course_name": row["course_name"],
        "archived": row["archived"], "default_pars": row["default_pars"],
    }
    if "name" in changes:
        name = " ".join(str(changes["name"] or "").split())
        if not 2 <= len(name) <= 80:
            raise Invalid("Give the league a name (2-80 characters).")
        new["name"] = name
    if "season" in changes:
        new["season"] = (str(changes["season"]).strip() or None) if changes["season"] else None
    if "course_name" in changes:
        new["course_name"] = (str(changes["course_name"]).strip() or None) if changes["course_name"] else None
    if "ranking" in changes:
        if changes["ranking"] not in ("net", "gross"):
            raise Invalid("Rank by net or gross.")
        new["ranking"] = changes["ranking"]
    if "pars" in changes:
        new["default_pars"] = json.dumps(clean_pars(changes["pars"], holes))
    if "archived" in changes:
        new["archived"] = 1 if changes["archived"] else 0
    conn.execute(
        "UPDATE leagues SET name=?, season=?, ranking=?, course_name=?, archived=?, default_pars=? WHERE id=?",
        (new["name"], new["season"], new["ranking"], new["course_name"], new["archived"], new["default_pars"], league_id),
    )
    audit(conn, admin_id, "league_updated", f"{league_id}: {sorted(changes)}")
    bump_revision(conn)
    return view(conn, get_row(conn, league_id), with_code=True)


def list_all(conn, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM leagues" + ("" if include_archived else " WHERE archived = 0") + " ORDER BY archived, created_at DESC"
    return [view(conn, r, with_code=True) for r in conn.execute(sql)]


def for_user(conn, user_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT l.* FROM leagues l JOIN league_members m ON m.league_id = l.id WHERE m.user_id = ? AND l.archived = 0"
        " ORDER BY l.created_at DESC", (user_id,)).fetchall()
    return [view(conn, r) for r in rows]


def is_member(conn, league_id: int, user_id: int) -> bool:
    return conn.execute("SELECT 1 FROM league_members WHERE league_id=? AND user_id=?", (league_id, user_id)).fetchone() is not None


def join(conn, user_id: int, code: str) -> Dict[str, Any]:
    code = str(code or "").strip().upper()
    row = conn.execute("SELECT * FROM leagues WHERE join_code = ?", (code,)).fetchone()
    if row is None:
        raise NotFound("That join code doesn't match a league.")
    if row["archived"]:
        raise Forbidden("That league has ended.")
    if is_member(conn, row["id"], user_id):
        raise Conflict("You're already in that league.")
    conn.execute("INSERT INTO league_members(league_id, user_id, joined_at) VALUES (?, ?, ?)", (row["id"], user_id, now_iso()))
    bump_revision(conn)
    return view(conn, row)


def add_member(conn, admin_id: int, league_id: int, user_id: int) -> None:
    get_row(conn, league_id)
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        raise NotFound("No such player.")
    if not is_member(conn, league_id, user_id):
        conn.execute("INSERT INTO league_members(league_id, user_id, joined_at) VALUES (?, ?, ?)", (league_id, user_id, now_iso()))
        audit(conn, admin_id, "member_added", f"league {league_id} user {user_id}")
        bump_revision(conn)


def remove_member(conn, admin_id: int, league_id: int, user_id: int) -> None:
    conn.execute("DELETE FROM league_members WHERE league_id=? AND user_id=?", (league_id, user_id))
    audit(conn, admin_id, "member_removed", f"league {league_id} user {user_id}")
    bump_revision(conn)


def set_team(conn, admin_id: int, league_id: int, user_id: int, team: Optional[str]) -> None:
    team = " ".join(str(team or "").split()) or None
    if team and len(team) > 40:
        raise Invalid("Team names are at most 40 characters.")
    conn.execute("UPDATE league_members SET team = ? WHERE league_id=? AND user_id=?", (team, league_id, user_id))
    audit(conn, admin_id, "team_set", f"league {league_id} user {user_id} -> {team}")
    bump_revision(conn)
