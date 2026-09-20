from typing import List, Dict, Any, Optional

from mvp.engine.models.events import ShotEvent


def analyze_live_shot(shots: List[ShotEvent]) -> Dict[str, Any]:
    """
    Lightweight real-time shot analysis for the live dashboard.
    Does NOT replace the full round analyzer.
    """

    if not shots:
        return {"error": "No shots yet"}

    last = shots[-1]

    def _safe(val: Optional[float]) -> float:
        return float(val) if val is not None else 0.0

    analysis = {
        "total_shots": len(shots),
        "last_ball_speed": _safe(last.ball_speed),
        "last_launch_angle": _safe(last.launch_angle),
        "last_spin": _safe(last.spin),
        "last_spin_axis": _safe(last.spin_axis),
        "last_shape": getattr(last, "shape", None),
        "last_carry": _safe(last.carry),
        "last_quality": _safe(getattr(last, "quality", None)),
        "avg_ball_speed": sum(_safe(s.ball_speed) for s in shots) / len(shots),
        "avg_carry": sum(_safe(s.carry) for s in shots) / len(shots),
        "avg_quality": sum(_safe(getattr(s, "quality", None)) for s in shots) / len(shots),
    }

    return analysis


def analyze_round(
    shots: List[ShotEvent],
    scorecard: List[Dict[str, Any]],
    simcore_index_before: float = 10.0,
    outdoor_handicap_start: float = 12.0,
    round_notes: str | None = None,
) -> Dict[str, Any]:
    """
    Full SimCore22 analytics engine (shot-based).
    - shots: list of normalized ShotEvent objects
    - scorecard: list of hole dicts containing scoring + FIR/GIR + putts + proximity
    """

    stats = {
        # --- Shot Analytics ---
        "total_shots": len(shots),
        "avg_ball_speed": None,
        "max_ball_speed": None,
        "avg_carry": None,
        "max_carry": None,
        "min_carry": None,
        "offline_avg": None,
        "offline_max": None,
        "left_miss_pct": None,
        "right_miss_pct": None,
        "penalties": 0,

        # --- Hole Analytics ---
        "total_score": 0,
        "score_relative_to_par": 0,
        "birdies": 0,
        "pars": 0,
        "bogeys": 0,
        "doubles": 0,
        "fir": 0,
        "gir": 0,
        "scrambling": None,
        "up_and_down": None,
        "sand_saves": None,
        "total_putts": 0,
        "avg_putts": None,
        "avg_proximity": None,
        "three_putt_avoidance": None,
        "birdie_conversion": None,
        "par_save_rate": None,

        # --- Round Analytics ---
        "par3_avg": None,
        "par4_avg": None,
        "par5_avg": None,
        "best_hole": None,
        "worst_hole": None,
        "consistency": None,
        "round_quality_score": None,

        # --- League / Points ---
        "gross_score": None,
        "gross_vs_par": None,
        "net_score": None,
        "net_vs_par": None,
        "stableford_points": None,
        "quota_points": None,
        "points_earned": None,
        "points_needed": None,

        # --- Handicap Placeholders ---
        "simcore_index_before": simcore_index_before,
        "simcore_index_after": simcore_index_before,
        "simcore_index_delta": 0.0,
        "outdoor_handicap_start": outdoor_handicap_start,
        "outdoor_vs_simcore": None,

        # --- Notes ---
        "round_notes": round_notes or "No notes provided.",
    }

    carries: list[float] = []
    ball_speeds: list[float] = []
    offlines: list[float] = []

    for shot in shots:
        if shot.carry is not None:
            carries.append(float(shot.carry))
        if shot.ball_speed is not None:
            ball_speeds.append(float(shot.ball_speed))
        if getattr(shot, "azimuth", None) is not None:
            offlines.append(float(shot.azimuth))
        if getattr(shot, "raw_payload", {}).get("penalty", False):
            stats["penalties"] += 1

    if ball_speeds:
        stats["avg_ball_speed"] = sum(ball_speeds) / len(ball_speeds)
        stats["max_ball_speed"] = max(ball_speeds)

    if carries:
        stats["avg_carry"] = sum(carries) / len(carries)
        stats["max_carry"] = max(carries)
        stats["min_carry"] = min(carries)
        stats["consistency"] = max(carries) - min(carries)

    if offlines:
        stats["offline_avg"] = sum(abs(x) for x in offlines) / len(offlines)
        stats["offline_max"] = max(abs(x) for x in offlines)
        stats["left_miss_pct"] = len([x for x in offlines if x < 0]) / len(offlines)
        stats["right_miss_pct"] = len([x for x in offlines if x > 0]) / len(offlines)

    proximities: list[float] = []
    par3_scores: list[int] = []
    par4_scores: list[int] = []
    par5_scores: list[int] = []

    scrambling_attempts = scrambling_success = 0
    updown_attempts = updown_success = 0
    sand_attempts = sand_success = 0
    three_putt_holes = 0
    birdie_putt_chances = birdie_putt_made = 0
    par_save_chances = par_saves = 0

    for hole in scorecard:
        par = hole.get("par", 4)
        score = hole.get("score", 0)
        putts = hole.get("putts", 0)
        fairway = hole.get("fairway_hit", False)
        green = hole.get("green_in_reg", False)
        proximity = hole.get("proximity")
        sand = hole.get("sand", False)
        updown_attempt = hole.get("up_and_down_attempt", False)
        updown_success_flag = hole.get("up_and_down_success", False)

        stats["total_score"] += score
        stats["score_relative_to_par"] += (score - par)

        diff = score - par
        if diff == -1:
            stats["birdies"] += 1
        elif diff == 0:
            stats["pars"] += 1
        elif diff == 1:
            stats["bogeys"] += 1
        elif diff >= 2:
            stats["doubles"] += 1

        if fairway:
            stats["fir"] += 1
        if green:
            stats["gir"] += 1

        stats["total_putts"] += putts
        if putts >= 3:
            three_putt_holes += 1

        if proximity is not None:
            proximities.append(float(proximity))

        if green:
            birdie_putt_chances += 1
            if diff == -1:
                birdie_putt_made += 1

        if diff == 0:
            par_save_chances += 1
            par_saves += 1

        if not green:
            scrambling_attempts += 1
            if score <= par:
                scrambling_success += 1

        if updown_attempt:
            updown_attempts += 1
            if updown_success_flag:
                updown_success += 1

        if sand:
            sand_attempts += 1
            if score <= par:
                sand_success += 1

        if par == 3:
            par3_scores.append(score)
        elif par == 4:
            par4_scores.append(score)
        elif par == 5:
            par5_scores.append(score)

    num_holes = len(scorecard)
    if num_holes > 0:
        stats["avg_putts"] = stats["total_putts"] / num_holes
        stats["fir"] = stats["fir"] / num_holes
        stats["gir"] = stats["gir"] / num_holes
        stats["three_putt_avoidance"] = 1 - (three_putt_holes / num_holes)

    if proximities:
        stats["avg_proximity"] = sum(proximities) / len(proximities)

    if scrambling_attempts > 0:
        stats["scrambling"] = scrambling_success / scrambling_attempts

    if updown_attempts > 0:
        stats["up_and_down"] = updown_success / updown_attempts

    if sand_attempts > 0:
        stats["sand_saves"] = sand_success / sand_attempts

    if birdie_putt_chances > 0:
        stats["birdie_conversion"] = birdie_putt_made / birdie_putt_chances

    if par_save_chances > 0:
        stats["par_save_rate"] = par_saves / par_save_chances

    if par3_scores:
        stats["par3_avg"] = sum(par3_scores) / len(par3_scores)
    if par4_scores:
        stats["par4_avg"] = sum(par4_scores) / len(par4_scores)
    if par5_scores:
        stats["par5_avg"] = sum(par5_scores) / len(par5_scores)

    if scorecard:
        stats["best_hole"] = min(scorecard, key=lambda h: h.get("score", 99)).get("hole_number")
        stats["worst_hole"] = max(scorecard, key=lambda h: h.get("score", -99)).get("hole_number")

    if (
        stats["avg_carry"] is not None
        and stats["avg_ball_speed"] is not None
        and stats["offline_avg"] is not None
        and stats["avg_putts"] is not None
    ):
        stats["round_quality_score"] = (
            (stats["fir"] or 0) * 20 +
            (stats["gir"] or 0) * 20 +
            (1 - (stats["offline_avg"] or 0) / 50) * 20 +
            (1 - (stats["avg_putts"] or 2) / 3) * 20 +
            (1 - (stats["score_relative_to_par"] / 20)) * 20
        )

    stats["gross_score"] = stats["total_score"]
    stats["gross_vs_par"] = stats["score_relative_to_par"]
    stats["net_score"] = stats["gross_score"] - stats["simcore_index_before"]
    stats["net_vs_par"] = stats["gross_vs_par"] - stats["simcore_index_before"]

    stats["stableford_points"] = (
        stats["birdies"] * 3 +
        stats["pars"] * 2 +
        stats["bogeys"] * 1 +
        stats["doubles"] * 0
    )

    stats["quota_points"] = stats["stableford_points"]
    stats["points_earned"] = stats["stableford_points"]
    stats["points_needed"] = 36 - stats["stableford_points"]

    stats["simcore_index_after"] = stats["simcore_index_before"]
    stats["simcore_index_delta"] = 0.0
    stats["outdoor_vs_simcore"] = outdoor_handicap_start - stats["simcore_index_after"]

    return stats
