# simcore22/web/data.py
"""
Read-side view of the engine's round log: turns data/rounds.jsonl lines into what
the screens show (round lists, scorecards, player profiles, venue numbers).

The log can hold several lines for one player's round (a `save` checkpoint, then
the final record); the LATEST line wins. Everything here is pure functions over
plain dicts so it works the same for real data and the built-in demo data.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

VERIFIED = "scorecard_ocr_verified"
SNAPSHOT = "snapshot"

# Scoring-mix buckets, by strokes relative to par
MIX_ORDER = ("eagle_or_better", "birdie", "par", "bogey", "double_or_worse")


def parse_time(value: Optional[str]) -> datetime:
    """An aware datetime from an ISO string; unparseable / missing sorts as very old."""
    try:
        parsed = datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        return datetime.min.astimezone()
    return parsed if parsed.tzinfo else parsed.astimezone()


def collapse(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record per (round, player), the latest line winning; newest round first."""
    latest: Dict[tuple, Dict[str, Any]] = {}
    for record in records:  # file order is chronological
        key = (record.get("round_id"), str(record.get("player", "")).strip().lower())
        latest[key] = record
    return sorted(
        latest.values(),
        key=lambda r: parse_time(r.get("finished_at") or r.get("logged_at")),
        reverse=True,
    )


def finals(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Records that are a real result (not a still-open checkpoint)."""
    return [r for r in records if r.get("round_status") != SNAPSHOT]


# ------------------------------------------------------------------- rounds

def summarize(record: Dict[str, Any]) -> Dict[str, Any]:
    stats = record.get("stats") or {}
    image = (record.get("scorecard_ocr") or {}).get("image_file")
    after = record.get("handicap_index_after")
    return {
        "round_id": record.get("round_id"),
        "player": record.get("player"),
        "finished_at": record.get("finished_at"),
        "course": record.get("course") or "Unknown",
        "round_status": record.get("round_status"),
        "finalize_reason": record.get("finalize_reason"),
        "round_type": record.get("round_type"),
        "holes_played": record.get("holes_played", 0),
        "gross": stats.get("gross_score"),
        "vs_par": stats.get("gross_vs_par"),
        "net": stats.get("net_score"),
        "score_source": record.get("score_source"),
        "verified": record.get("score_source") == VERIFIED,
        "handicap": after if after is not None else record.get("handicap_index_used"),
        "image": Path(image).name if image else None,
        "demo": bool(record.get("demo")),
    }


_DETAIL_STATS = (
    "birdies", "pars", "bogeys", "doubles", "fir", "gir", "avg_putts", "avg_carry", "max_carry",
    "avg_ball_speed", "max_ball_speed", "stableford_points", "par3_avg", "par4_avg", "par5_avg",
    "best_hole", "worst_hole",
)


def detail(record: Dict[str, Any]) -> Dict[str, Any]:
    stats = record.get("stats") or {}
    shots = record.get("shots") or []
    speeds = [s["ball_speed"] for s in shots if s.get("ball_speed") is not None]
    carries = [s["carry_distance"] for s in shots if s.get("carry_distance") is not None]

    out = summarize(record)
    out["holes"] = [
        {
            "hole": h.get("hole"),
            "par": h.get("par"),
            "par_assumed": bool(h.get("par_assumed")),
            "score": h.get("score_used"),
            "shot_tally": h.get("shot_tally"),
            "counted": h.get("counted", True),
        }
        for h in record.get("hole_scores") or []
    ]
    out["stats"] = {k: stats[k] for k in _DETAIL_STATS if stats.get(k) is not None}
    out["shots"] = {
        "count": len(shots),
        "devices": record.get("shot_devices") or [],
        "avg_ball_speed": round(mean(speeds), 1) if speeds else None,
        "max_ball_speed": round(max(speeds), 1) if speeds else None,
        "avg_carry": round(mean(carries), 1) if carries else None,
    }
    out["handicap_was_default"] = bool(record.get("handicap_was_default"))
    out["handicap_after"] = record.get("handicap_index_after")
    return out


def filter_rounds(
    records: List[Dict[str, Any]],
    *,
    status: Optional[str] = None,
    player: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Summaries of `records`, optionally filtered by status, exact player, or free text."""
    needle = (query or "").strip().lower()
    out = []
    for record in records:
        if status and record.get("round_status") != status:
            continue
        if player and str(record.get("player", "")).lower() != player.lower():
            continue
        if needle:
            haystack = f"{record.get('player', '')} {record.get('course', '')} {record.get('round_status', '')}"
            if needle not in haystack.lower():
                continue
        out.append(summarize(record))
    return out


# ------------------------------------------------------------------ players

def players(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One profile per player, best average first."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in finals(records):
        groups.setdefault(str(record.get("player", "")).strip().lower(), []).append(record)

    profiles = []
    for rounds in groups.values():
        rounds = sorted(rounds, key=lambda r: parse_time(r.get("finished_at")))  # oldest first
        completed = [r for r in rounds if r.get("round_status") == "completed"]
        to_par = [r["stats"]["gross_vs_par"] for r in completed if (r.get("stats") or {}).get("gross_vs_par") is not None]
        latest = rounds[-1]
        after = latest.get("handicap_index_after")
        profiles.append({
            "player": latest.get("player"),
            "rounds": len(rounds),
            "completed_rounds": len(completed),
            "avg_vs_par": round(mean(to_par), 1) if to_par else None,
            "best_vs_par": min(to_par) if to_par else None,
            "handicap": after if after is not None else latest.get("handicap_index_used"),
            "last_played": latest.get("finished_at"),
            "last_course": latest.get("course"),
            "verified_rate": round(sum(r.get("score_source") == VERIFIED for r in rounds) / len(rounds), 2),
            "trend": [r["stats"]["gross_vs_par"] for r in rounds[-10:] if (r.get("stats") or {}).get("gross_vs_par") is not None],
            "demo": any(r.get("demo") for r in rounds),
        })
    profiles.sort(key=lambda p: (p["avg_vs_par"] is None, p["avg_vs_par"] if p["avg_vs_par"] is not None else 0, p["player"] or ""))
    return profiles


# -------------------------------------------------------------------- venue

def _mix_bucket(diff: int) -> str:
    if diff <= -2:
        return "eagle_or_better"
    return {-1: "birdie", 0: "par", 1: "bogey"}.get(diff, "double_or_worse")


def venue_summary(records: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    """The headline numbers for the admin overview."""
    now = now or datetime.now().astimezone()
    rows = finals(records)
    week = now - timedelta(days=7)
    prev_week = now - timedelta(days=14)

    def when(r):
        return parse_time(r.get("finished_at"))

    last7 = [r for r in rows if when(r) >= week]
    prev7 = [r for r in rows if prev_week <= when(r) < week]
    last30 = [r for r in rows if when(r) >= now - timedelta(days=30)]

    completed30 = [r for r in last30 if r.get("round_status") == "completed"]
    to_par = [r["stats"]["gross_vs_par"] for r in completed30 if (r.get("stats") or {}).get("gross_vs_par") is not None]

    mix = dict.fromkeys(MIX_ORDER, 0)
    for r in last30:
        for h in r.get("hole_scores") or []:
            if not h.get("counted", True) or h.get("par_assumed") or h.get("par") is None or h.get("score_used") is None:
                continue
            mix[_mix_bucket(h["score_used"] - h["par"])] += 1

    by_day = []
    for offset in range(13, -1, -1):
        day = (now - timedelta(days=offset)).date()
        by_day.append({"date": day.isoformat(), "rounds": sum(1 for r in rows if when(r).astimezone().date() == day)})

    return {
        "total_rounds": len(rows),
        "total_players": len({str(r.get("player", "")).strip().lower() for r in rows}),
        "rounds_7d": len(last7),
        "rounds_prev_7d": len(prev7),
        "players_7d": len({str(r.get("player", "")).strip().lower() for r in last7}),
        "avg_vs_par_30d": round(mean(to_par), 1) if to_par else None,
        "verified_rate_30d": round(sum(r.get("score_source") == VERIFIED for r in last30) / len(last30), 3) if last30 else None,
        "rounds_by_day": by_day,
        "scoring_mix": mix,
    }


# -------------------------------------------------------------- leaderboard

def rank_players(players_json: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Leaderboard rows ranked by score to par (ties share a rank), with `rank` and `tied` added."""
    ordered = sorted(
        players_json,
        key=lambda p: (p.get("vs_par", 0), -p.get("thru", 0), p.get("gross", 0), str(p.get("name", ""))),
    )
    ranked, last_key, last_rank = [], None, 0
    for index, player in enumerate(ordered, start=1):
        key = (player.get("vs_par", 0), player.get("thru", 0))
        rank = last_rank if key == last_key else index
        ranked.append({**player, "rank": rank})
        last_key, last_rank = key, rank
    counts: Dict[int, int] = {}
    for p in ranked:
        counts[p["rank"]] = counts.get(p["rank"], 0) + 1
    return [{**p, "tied": counts[p["rank"]] > 1} for p in ranked]
