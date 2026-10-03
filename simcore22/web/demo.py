# simcore22/web/demo.py
"""
Built-in demo data, so the whole product can be shown without a bay.

A fictional league (made-up players, courses and teams): six weeks of finished
rounds plus a "tonight" leaderboard that plays itself out on a loop. It lives
only in memory - it never touches data/ or state/ - and every screen labels it
DEMO. The records use exactly the same shape the engine writes, so the UI code
path is identical for real and demo data.
"""
from __future__ import annotations

import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Tuple

from simcore22 import __version__

LEAGUE_NAME = "Tuesday Night League"
TONIGHT_COURSE = "Harbor Links"
TONIGHT_WEEK = 7
HOLES = 9

# name, team, handicap index (all fictional)
PLAYERS: List[Tuple[str, str, int]] = [
    ("Alex Rivera", "Eagles", 6), ("Sam Okafor", "Eagles", 11), ("Jordan Lee", "Eagles", 17), ("Taylor Brooks", "Eagles", 23),
    ("Morgan Diaz", "Birdies", 4), ("Casey Nguyen", "Birdies", 9), ("Riley Patel", "Birdies", 14), ("Jamie Fox", "Birdies", 20),
    ("Quinn Murphy", "Mulligans", 8), ("Avery Kim", "Mulligans", 12), ("Drew Santos", "Mulligans", 18), ("Parker Hale", "Mulligans", 26),
    ("Reese Coleman", "Albatross", 5), ("Skyler Wong", "Albatross", 10), ("Devon Price", "Albatross", 15), ("Emerson Blake", "Albatross", 22),
]

# Par for each hole of the three (fictional) courses; 9-hole layouts, par 36
COURSES: Dict[str, List[int]] = {
    "Harbor Links": [4, 5, 3, 4, 4, 3, 5, 4, 4],
    "Cedar Ridge": [4, 4, 5, 3, 4, 5, 3, 4, 4],
    "Stonebridge National": [5, 4, 3, 4, 4, 3, 4, 5, 4],
}


def _hole_scores(rng: random.Random, pars: List[int], handicap: int) -> List[int]:
    """Plausible hole-by-hole scores for a player of this handicap."""
    scores = []
    for par in pars:
        expected = par + handicap / 20 * (1.1 if par == 3 else 1.0)
        score = round(expected + rng.gauss(0, 0.85))
        scores.append(max(1, min(par + 4, max(par - 2, score))))
    return scores


def _stats(scores: List[int], pars: List[int], handicap: int) -> Dict[str, Any]:
    diffs = [s - p for s, p in zip(scores, pars, strict=True)]
    gross = sum(scores)
    return {
        "gross_score": gross,
        "gross_vs_par": gross - sum(pars),
        "net_score": gross - handicap,
        "birdies": sum(d == -1 for d in diffs),
        "pars": sum(d == 0 for d in diffs),
        "bogeys": sum(d == 1 for d in diffs),
        "doubles": sum(d >= 2 for d in diffs),
        "stableford_points": sum(max(0, 2 - d) for d in diffs),
    }


def _shots(rng: random.Random, pars: List[int], scores: List[int], when: datetime) -> List[Dict[str, Any]]:
    shots = []
    for par, score in zip(pars, scores, strict=True):
        full_swings = max(1, score - 2)  # the rest are putts
        for n in range(full_swings):
            tee = n == 0 and par > 3
            shots.append({
                "source_device": "Demo",
                "timestamp": when.isoformat(timespec="seconds"),
                "ball_speed": round(rng.gauss(150 if tee else 118, 6), 1),
                "carry_distance": round(rng.gauss(230 if tee else 140, 22), 1),
            })
    return shots


def _record(
    rng: random.Random, *, player: str, handicap: int, when: datetime, course: str, pars: List[int],
    status: str = "completed", round_type: str = "league", verified: bool = True, round_id: str = "",
) -> Dict[str, Any]:
    scores = _hole_scores(rng, pars, handicap)
    played = len(scores) if status == "completed" else max(2, int(len(scores) * rng.uniform(0.3, 0.75)))
    scores, pars_played = scores[:played], pars[:played]
    stats = _stats(scores, pars_played, handicap)
    after = handicap + (rng.choice([-1, 0, 0, 1]) if status == "completed" and round_type == "league" else 0)
    reason = {"completed": "scorecard", "ended_early": "manual_end", "abandoned": "idle_timeout"}[status]
    return {
        "schema_version": 1,
        "demo": True,
        "round_id": round_id or uuid.UUID(int=rng.getrandbits(128)).hex,
        "finished_at": when.isoformat(timespec="seconds"),
        "round_status": status,
        "finalize_reason": reason,
        "round_type": round_type,
        "player": player,
        "course": course,
        "holes_played": played,
        "score_source": "scorecard_ocr_verified" if verified else "shot_tally",
        "handicap_index_used": handicap,
        "handicap_was_default": False,
        "handicap_index_after": after if status == "completed" else None,
        "hole_scores": [
            {"hole": i + 1, "par": p, "par_assumed": False, "score_used": s, "gross_score": s if verified else None,
             "shot_tally": max(1, s + rng.choice([0, 0, 0, -1, 1])) if not verified else s, "counted": True}
            for i, (s, p) in enumerate(zip(scores, pars_played, strict=True))
        ],
        "stats": stats,
        "shot_devices": ["Demo"],
        "shots": _shots(rng, pars_played, scores, when),
        "scorecard_ocr": {"image_file": None},
    }


class DemoLeague:
    """The fictional league: history for the admin portal, a looping live night for the board."""

    PER_HOLE_SECONDS = (11, 22)   # how long a player "takes" per hole, in demo time
    START_OFFSET = 80             # each loop starts this far in, so the board is never empty
    FINAL_SECONDS = 25            # the finished board stays up this long before the next night starts

    def __init__(self, seed: int = 22, clock: Callable[[], float] = time.time):
        self.seed = seed
        self.clock = clock
        self._epoch = clock()
        now = datetime.fromtimestamp(self._epoch).astimezone()

        self._records = self._history(now)
        self._tonight = self._plan_tonight()
        last_finish = max(end[-1] for _, _, _, end in self._tonight.values())
        self._cycle = last_finish - self.START_OFFSET + self.FINAL_SECONDS

    # -------------------------------------------------------------- history

    def _history(self, now: datetime) -> List[Dict[str, Any]]:
        rng = random.Random(self.seed)
        course_names = list(COURSES)
        records: List[Dict[str, Any]] = []
        handicaps = {name: hcp for name, _, hcp in PLAYERS}

        # Six league nights, one a week, ending last week
        for week in range(1, TONIGHT_WEEK):
            night = (now - timedelta(days=7 * (TONIGHT_WEEK - week))).replace(hour=19, minute=30, second=0, microsecond=0)
            course = course_names[week % len(course_names)]
            round_id = uuid.UUID(int=rng.getrandbits(128)).hex
            for i, (name, _, _) in enumerate(PLAYERS):
                handicaps[name] = max(0, handicaps[name] + rng.choice([-1, 0, 0, 1]))
                status = "completed" if rng.random() > 0.05 else "ended_early"
                record = _record(
                    rng, player=name, handicap=handicaps[name], when=night + timedelta(minutes=70 + i * 2),
                    course=course, pars=COURSES[course], status=status, verified=rng.random() > 0.1, round_id=round_id,
                )
                records.append(record)

        # Walk-in and practice rounds on other days, some 18-hole
        for days_ago in range(1, 28):
            day = now - timedelta(days=days_ago)
            for _ in range(rng.choice([0, 1, 2, 2, 3, 4])):
                name, _, hcp = rng.choice(PLAYERS)
                course = rng.choice(course_names)
                pars = COURSES[course] * (2 if rng.random() < 0.3 else 1)
                when = day.replace(hour=rng.randint(10, 21), minute=rng.randint(0, 59), second=0, microsecond=0)
                status = rng.choices(["completed", "ended_early", "abandoned"], weights=[88, 8, 4])[0]
                records.append(_record(
                    rng, player=name, handicap=hcp, when=when, course=course, pars=pars, status=status,
                    round_type=rng.choice(["practice", "one_off"]), verified=rng.random() > 0.1,
                ))

        records.sort(key=lambda r: r["finished_at"])
        return records

    # --------------------------------------------------------- tonight's board

    def _plan_tonight(self) -> Dict[str, Tuple[str, int, List[int], List[float]]]:
        """name -> (team, handicap, hole scores, cumulative seconds at which each hole is finished)."""
        pars = COURSES[TONIGHT_COURSE]
        plan = {}
        for i, (name, team, hcp) in enumerate(PLAYERS):
            rng = random.Random(f"{self.seed}:tonight:{name}")
            scores = _hole_scores(rng, pars, hcp)
            clock, ends = 6.0 + i * 3.1, []
            for _ in scores:
                clock += rng.uniform(*self.PER_HOLE_SECONDS)
                ends.append(clock)
            plan[name] = (team, hcp, scores, ends)
        return plan

    def _position(self) -> float:
        return (self.clock() - self._epoch) % self._cycle + self.START_OFFSET

    # ----------------------------------------------------------- the interface

    def rounds(self) -> List[Dict[str, Any]]:
        return self._records

    def leaderboard(self) -> Dict[str, Any]:
        position, pars = self._position(), COURSES[TONIGHT_COURSE]
        rows = []
        for name, (team, hcp, scores, ends) in self._tonight.items():
            thru = sum(1 for end in ends if end <= position)
            if thru == 0:
                continue
            gross = sum(scores[:thru])
            rows.append({
                "name": name, "team": team, "thru": thru, "gross": gross,
                "net": gross - round(hcp * thru / HOLES), "vs_par": gross - sum(pars[:thru]),
                "points": 0, "points_needed": 36, "simcore_index": hcp, "outdoor_hcp": hcp,
            })
        done = bool(rows) and all(r["thru"] == HOLES for r in rows) and len(rows) == len(self._tonight)
        return {
            "demo": True,
            "course_name": TONIGHT_COURSE,
            "format": f"Stroke Play · {HOLES} holes",
            "league_name": LEAGUE_NAME,
            "week": TONIGHT_WEEK,
            "holes_total": HOLES,
            "round_complete": done,
            "players": rows,
            "updated_at": datetime.fromtimestamp(self.clock()).astimezone().isoformat(timespec="seconds"),
        }

    def engine_status(self) -> Dict[str, Any]:
        now = datetime.fromtimestamp(self.clock()).astimezone()
        board = self.leaderboard()
        playing = [
            {"name": r["name"], "holes": r["thru"], "current_hole": min(HOLES, r["thru"] + 1)}
            for r in board["players"] if r["thru"] < HOLES
        ]
        return {
            "demo": True,
            "running": True,
            "pid": 0,
            "version": __version__,
            "started_at": (now - timedelta(hours=3, minutes=12)).isoformat(timespec="seconds"),
            "updated_at": now.isoformat(timespec="seconds"),
            "capture": {"mode": "window", "target": "GSPro", "state": "capturing",
                        "last_frame_at": now.isoformat(timespec="seconds")},
            "feed": {"configured": False, "host": None, "port": None},
            "round": {"in_progress": bool(playing), "players": playing, "shots": 0,
                      "idle_seconds": 2, "idle_timeout_minutes": 20},
        }

    def signature(self) -> Tuple[int, ...]:
        return (int(self._position()),)  # changes every second, so the live board keeps moving
