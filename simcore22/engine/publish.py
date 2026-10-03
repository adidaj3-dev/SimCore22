# simcore22/engine/publish.py
"""Turns the live session into the standings that screens show."""
import logging

from simcore22.engine import config, engine
from simcore22.engine.dashboard.live_dashboard import display_live_dashboard
from simcore22.engine.leaderboard.leaderboard import Leaderboard
from simcore22.engine.state_writer import write_leaderboard_state

logger = logging.getLogger(__name__)


class LeaderboardPublisher:
    """
    Recomputes standings from the current session and pushes them out: the
    console table and state/leaderboard.json (what the on-screen leaderboard
    reads). Called after every shot AND every confirmed score, so the last hole
    of a round shows the official score rather than a stale shot count.
    """

    def __init__(self) -> None:
        self.leaderboard = Leaderboard()

    def refresh(self) -> None:
        self.leaderboard.update_from_session(engine.get_session_state())
        standings = self.leaderboard.get_standings()
        display_live_dashboard(standings)

        write_leaderboard_state(
            course_name="Unknown",
            league_name=config.LEAGUE_NAME,   # None until the venue sets one
            week=None,                        # no league calendar yet
            format_name="Stroke Play",
            players=[
                {
                    "name": row.player_name,
                    "team": row.team_name,
                    "thru": row.thru,
                    "gross": row.gross_score,
                    "net": row.net_score,
                    "vs_par": row.vs_par,
                    "points": 0,
                    "points_needed": 36,
                    "simcore_index": row.handicap_index,
                    "outdoor_hcp": row.handicap_index,
                }
                for row in standings
            ],
        )
