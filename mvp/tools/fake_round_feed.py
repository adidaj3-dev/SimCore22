# mvp/tools/fake_round_feed.py

import time
from datetime import datetime
from typing import List, Dict, Any

from mvp.engine.models.events import ShotEvent, ScoreEvent
from mvp.engine.analyzer.analyzer import analyze_round
from mvp.engine.state_writer import (
    write_leaderboard_state,
    write_round_summary_state,
    write_admin_snapshot_state,
)


# ---------------------------------------------------------
# Build a simple 9-hole scorecard for the fake round
# ---------------------------------------------------------
def build_fake_scorecard() -> List[Dict[str, Any]]:
    scorecard: List[Dict[str, Any]] = []
    for hole in range(1, 10):
        scorecard.append(
            {
                "hole_number": hole,
                "par": 4,
                "score": 4,
                "putts": 2,
                "fairway_hit": True if hole % 2 == 0 else False,
                "green_in_reg": True if hole % 3 != 0 else False,
                "proximity": 20.0 + hole,
                "sand": False,
                "up_and_down_attempt": False,
                "up_and_down_success": False,
            }
        )
    return scorecard


# ---------------------------------------------------------
# Main fake round driver
# ---------------------------------------------------------
def run_fake_round() -> None:
    player_name = "Jeff"
    course_name = "Test Course"
    league_name = "Winter Sim League"
    week = 1
    format_name = "Net Stroke Play"

    shots: List[ShotEvent] = []
    score_events: List[ScoreEvent] = []

    print("Starting fake round feed...")

    # -----------------------------------------------------
    # Simulate 9 holes, 3 shots per hole
    # -----------------------------------------------------
    for hole in range(1, 10):
        for shot_num in range(3):
            ts = datetime.now()

            # Values for this shot
            carry_val = 200 + hole * 2 + shot_num
            spin_val = 2500 + hole * 10

            # Create ShotEvent using your real model fields
            shot = ShotEvent(
                source_device="FAKE",
                timestamp=ts,
                ball_speed=140 + hole + shot_num,
                launch_angle=12 + shot_num,
                azimuth=(-5 + shot_num * 2),
                spin_rate=spin_val,
                spin_axis=0.0,
                club_speed=95 + shot_num,
                carry_distance=carry_val,
                total_distance=210 + hole * 2 + shot_num,
                metadata={
                    "carry": carry_val,
                    "spin": spin_val,
                    "quality": 1.0,
                },
            )

            # -------------------------------------------------
            # Normalize fields so your analyzer works perfectly
            # -------------------------------------------------
            shot.carry = carry_val
            shot.spin = spin_val
            shot.quality = 1.0

            shots.append(shot)
            time.sleep(0.1)

        # -----------------------------------------------------
        # End of hole → ScoreEvent
        # -----------------------------------------------------
        se = ScoreEvent(
            timestamp=datetime.now(),
            player_name=player_name,
            hole_number=hole,
            gross_score=4,
            par=4,
        )
        score_events.append(se)

        # -----------------------------------------------------
        # Build leaderboard JSON for this hole
        # -----------------------------------------------------
        holes_played = hole
        gross_total = holes_played * 4
        simcore_index = 10.0
        net_score = gross_total - simcore_index
        vs_par = gross_total - (holes_played * 4)

        players_lb = [
            {
                "name": player_name,
                "thru": holes_played,
                "gross": gross_total,
                "net": int(net_score),
                "vs_par": int(vs_par),
                "points": hole * 2,          # simple fake points
                "points_needed": 36 - hole * 2,
                "simcore_index": simcore_index,
                "outdoor_hcp": 12.0,
            }
        ]

        write_leaderboard_state(
            course_name=course_name,
            league_name=league_name,
            week=week,
            format_name=format_name,
            players=players_lb,
        )

        print(f"Hole {hole} complete → leaderboard updated.")
        time.sleep(0.2)

    # ---------------------------------------------------------
    # After 9 holes → full round summary + admin snapshot
    # ---------------------------------------------------------
    scorecard = build_fake_scorecard()

    round_stats = analyze_round(
        shots=shots,
        scorecard=scorecard,
        simcore_index_before=10.0,
        outdoor_handicap_start=12.0,
        round_notes="Fake round for UI test.",
    )

    # ---------------------------------------------------------
    # Build summary JSON payload
    # ---------------------------------------------------------
    summary_payload: Dict[str, Any] = {
        "player": player_name,
        "course": course_name,
        "holes": len(scorecard),
        "gross": round_stats["gross_score"],
        "score_vs_par": round_stats["gross_vs_par"],
        "net": round_stats["net_score"],
        "simcore_index": round_stats["simcore_index_before"],
        "ball_flight": {
            "avg_bs": round_stats["avg_ball_speed"],
            "max_bs": round_stats["max_ball_speed"],
            "avg_carry": round_stats["avg_carry"],
        },
        "scoring": {
            "birdies": round_stats["birdies"],
            "pars": round_stats["pars"],
            "bogeys": round_stats["bogeys"],
        },
        "league": {
            "stableford": round_stats["stableford_points"],
            "quota": round_stats["quota_points"],
            "points_target": 36,
        },
        "raw": round_stats,
    }

    write_round_summary_state(summary_payload)
    print("Round summary written.")

    # ---------------------------------------------------------
    # Admin snapshot JSON
    # ---------------------------------------------------------
    players_admin = [
        {
            "name": player_name,
            "outdoor_ghin": round_stats["outdoor_handicap_start"],
            "simcore_index_start": round_stats["simcore_index_before"],
            "simcore_index_current": round_stats["simcore_index_after"],
            "practice_score": None,
            "week_scores": [round_stats["gross_score"]] + [None] * 8,
            "total_individual_points": round_stats["points_earned"],
            "points_per_round": [round_stats["points_earned"]],
            "team_points": 10,
        }
    ]

    teams = [
        {"name": "Team A", "points": 10},
        {"name": "Team B", "points": 8},
    ]

    write_admin_snapshot_state(
        league_name=league_name,
        week=week,
        players=players_admin,
        teams=teams,
    )

    print("Admin snapshot written.")
    print("Fake round complete. All JSON state written.")


if __name__ == "__main__":
    run_fake_round()
