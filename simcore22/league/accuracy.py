# simcore22/league/accuracy.py
"""
How well does screen capture agree with what players typed in?

While capture is still being proven on a real bay, every round a player enters by hand is a
free answer key. This pairs each hand-entered round with the round the engine logged for the
same player at about the same time, and compares them hole by hole.

Pairing: the engine records the player's GSPro name (set on their profile); a pair is a manual
round and an engine round for that name whose finish times fall close together. Nothing is
guessed beyond that - rounds with no partner are reported as unmatched, not as errors.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from simcore22.league import rounds
from simcore22.web import data

MATCH_BEFORE = timedelta(minutes=10)    # an engine round may finish this long before the player started typing...
MATCH_AFTER = timedelta(minutes=90)     # ...or this long after the last hole was entered (people enter late)


def _norm(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def _manual_window(r: Dict[str, Any]):
    start = data.parse_time(r["started_at"])
    end = data.parse_time(r["finished_at"]) if r.get("finished_at") else datetime.now().astimezone()
    return start - MATCH_BEFORE, end + MATCH_AFTER


def compare(manual: Dict[str, Any], captured: Dict[str, Any]) -> Dict[str, Any]:
    """One manual round vs one engine record, hole by hole."""
    cap = {h.get("hole"): h for h in captured.get("hole_scores") or []}
    holes, same, differ = [], 0, 0
    for h in manual["holes"]:
        if h["strokes"] is None:
            continue
        c = cap.get(h["hole"])
        score = c.get("score_used") if c else None
        if score is None:
            holes.append({"hole": h["hole"], "manual": h["strokes"], "captured": None, "match": None})
            continue
        ok = score == h["strokes"]
        same += ok
        differ += not ok
        holes.append({"hole": h["hole"], "manual": h["strokes"], "captured": score, "match": ok})
    stats = captured.get("stats") or {}
    comparable = same + differ
    return {
        "manual_round_id": manual["id"], "player": manual.get("player"), "engine_round_id": captured.get("round_id"),
        "started_at": manual["started_at"], "finished_at": captured.get("finished_at"),
        "score_source": captured.get("score_source"), "verified": captured.get("score_source") == data.VERIFIED,
        "holes_compared": comparable, "holes_matching": same,
        "hole_accuracy": round(same / comparable, 3) if comparable else None,
        "gross_manual": manual["gross"], "gross_captured": stats.get("gross_score"),
        "gross_matches": manual["gross"] is not None and stats.get("gross_score") == manual["gross"],
        "holes_missing_from_capture": sum(1 for h in holes if h["match"] is None),
        "holes": holes,
    }


def check(conn, engine_records: Iterable[Dict[str, Any]], *, league_id: Optional[int] = None, since: Optional[str] = None) -> Dict[str, Any]:
    """Pair every counted manual round with an engine round and summarise the agreement."""
    finals = [r for r in data.finals(data.collapse(engine_records))]
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for rec in finals:
        by_name.setdefault(_norm(rec.get("player")), []).append(rec)

    sql = "SELECT r.*, u.gspro_name, u.display_name FROM rounds r JOIN users u ON u.id = r.user_id WHERE r.status != 'abandoned'"
    args: List[Any] = []
    if league_id:
        sql += " AND r.league_id = ?"
        args.append(league_id)
    if since:
        sql += " AND r.started_at >= ?"
        args.append(since)
    sql += " ORDER BY r.started_at"

    used, pairs, unmatched_manual = set(), [], []
    for row in conn.execute(sql, args).fetchall():
        manual = rounds.view(conn, row, with_user=True)
        if manual["thru"] == 0:
            continue
        lo, hi = _manual_window(manual)
        mid = lo + (hi - lo) / 2
        candidates = [
            rec for rec in by_name.get(_norm(row["gspro_name"] or row["display_name"]), [])
            if id(rec) not in used and lo <= data.parse_time(rec.get("finished_at") or rec.get("logged_at")) <= hi
        ]
        if not candidates:
            unmatched_manual.append({"manual_round_id": manual["id"], "player": manual["player"], "started_at": manual["started_at"],
                                     "thru": manual["thru"], "in_progress": manual["status"] == "in_progress"})
            continue
        best = min(candidates, key=lambda rec: abs(data.parse_time(rec.get("finished_at") or rec.get("logged_at")) - mid))
        used.add(id(best))
        pairs.append(compare(manual, best))

    known = {_norm(r["gspro_name"] or r["display_name"]) for r in conn.execute("SELECT gspro_name, display_name FROM users")}
    unmatched_capture = [
        {"engine_round_id": rec.get("round_id"), "player": rec.get("player"), "finished_at": rec.get("finished_at"),
         "gross": (rec.get("stats") or {}).get("gross_score"), "known_player": _norm(rec.get("player")) in known}
        for rec in finals if id(rec) not in used and (not since or data.parse_time(rec.get("finished_at")) >= data.parse_time(since))
    ]

    compared = sum(p["holes_compared"] for p in pairs)
    matching = sum(p["holes_matching"] for p in pairs)
    verified = [p for p in pairs if p["verified"]]
    tally = [p for p in pairs if not p["verified"]]

    def rate(group):
        c, m = sum(p["holes_compared"] for p in group), sum(p["holes_matching"] for p in group)
        return {"rounds": len(group), "holes": c, "accuracy": round(m / c, 3) if c else None}

    return {
        "summary": {
            "pairs": len(pairs), "holes_compared": compared, "holes_matching": matching,
            "hole_accuracy": round(matching / compared, 3) if compared else None,
            "rounds_exact": sum(1 for p in pairs if p["holes_compared"] and p["holes_matching"] == p["holes_compared"] and not p["holes_missing_from_capture"]),
            "unmatched_manual": len(unmatched_manual), "unmatched_capture": len(unmatched_capture),
            "verified": rate(verified), "counted_from_shots": rate(tally),
        },
        "pairs": sorted(pairs, key=lambda p: p["started_at"], reverse=True),
        "unmatched_manual": unmatched_manual,
        "unmatched_capture": unmatched_capture,
    }
