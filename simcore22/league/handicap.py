# simcore22/league/handicap.py
"""
The SimCore indoor handicap ("SimCore Index v1").

This is modelled on the World Handicap System but it is NOT an official handicap and is not
an outdoor-service handicap: it only counts rounds played and entered here, on simulators. The rules, in plain words:

* Each completed round gets a score *differential*: how far over par the round was, after
  capping each hole at net double bogey, scaled to 18 holes so 9- and 18-hole rounds mix.
* The index is the average of the best few of the player's most recent differentials
  (the WHS table: 3 rounds -> lowest 1, ..., 20 rounds -> best 8).
* Until a player has 3 rounds, their self-reported outdoor index is blended in, so a new
  player gets a sensible number instead of a wild swing from one round.
* Capped at 54.0. The whole history is recomputed from the rounds whenever one changes, so
  fixing a wrong score fixes the handicap too.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

METHOD = "simcore-index-v1"
MAX_INDEX = 54.0
FULL_WEIGHT_ROUNDS = 3         # from here on the outdoor index is ignored
RECENT_ROUNDS = 20

# WHS table: number of differentials available -> how many of the lowest to average
_BEST_K = {3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 4, 13: 4, 14: 4, 15: 5, 16: 5, 17: 6, 18: 6, 19: 7}


def best_k(count: int) -> int:
    if count <= 0:
        return 0
    if count < 3:
        return 1
    return _BEST_K.get(count, 8)


def course_handicap(index: Optional[float], holes: int) -> int:
    """Strokes a player of this index receives over `holes` holes (0 when there is no index)."""
    if index is None:
        return 0
    return round(index * holes / 18)


def strokes_on_hole(course_hcp: int, hole_number: int, holes: int) -> int:
    """Strokes received on one hole. Without stroke-index data the extra strokes go to the
    lowest-numbered holes first, which is fair enough for an indoor league and easy to explain."""
    if course_hcp <= 0:
        return 0
    base, extra = divmod(course_hcp, holes)
    return base + (1 if hole_number <= extra else 0)


def adjusted_gross(scores: Sequence[Tuple[int, int, int]], index: Optional[float], holes: int) -> int:
    """Total strokes with each hole capped at net double bogey (par + 2 + strokes received on it).
    `scores` is (hole, par, strokes) for each hole played."""
    chp = course_handicap(index if index is not None else 0.0, holes)
    total = 0
    for hole, par, strokes in scores:
        cap = par + 2 + strokes_on_hole(chp, hole, holes)
        total += min(strokes, cap)
    return total


def differential(scores: Sequence[Tuple[int, int, int]], index: Optional[float], holes: int) -> Optional[float]:
    """How far over par the round was, scaled to 18 holes. None if nothing was played."""
    if not scores:
        return None
    par = sum(p for _, p, _ in scores)
    adjusted = adjusted_gross(scores, index, holes)
    return round((adjusted - par) * 18 / len(scores), 1)


def index_from(differentials: Sequence[float], outdoor_index: Optional[float] = None) -> Optional[float]:
    """The index from differentials listed OLDEST first."""
    recent = list(differentials)[-RECENT_ROUNDS:]
    count = len(recent)
    if count == 0:
        return None if outdoor_index is None else round(min(outdoor_index, MAX_INDEX), 1)
    k = best_k(count)
    own = sum(sorted(recent)[:k]) / k
    if count < FULL_WEIGHT_ROUNDS and outdoor_index is not None:
        weight = count / FULL_WEIGHT_ROUNDS            # 1 round -> 1/3 simulator, 2/3 outdoor
        own = own * weight + outdoor_index * (1 - weight)
    return round(max(min(own, MAX_INDEX), -10.0), 1)


def rebuild(rounds: List[Tuple[int, float]], outdoor_index: Optional[float]) -> List[Tuple[int, Optional[float], int]]:
    """Index after each round, replaying history. `rounds` is [(round_id, differential)] oldest first;
    returns [(round_id, index_after, rounds_counted)]."""
    out, seen = [], []
    for round_id, diff in rounds:
        seen.append(diff)
        out.append((round_id, index_from(seen, outdoor_index), min(len(seen), RECENT_ROUNDS)))
    return out
