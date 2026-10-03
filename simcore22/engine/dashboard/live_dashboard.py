# simcore22/engine/dashboard/live_dashboard.py

from __future__ import annotations

from typing import Iterable

from simcore22.engine.leaderboard.leaderboard import PlayerLeaderboardRow


def display_live_dashboard(rows: Iterable[PlayerLeaderboardRow]) -> None:
    """
    Plain console leaderboard, reprinted whenever standings change.

    The on-screen bay leaderboards will read state/leaderboard.json instead.
    """

    rows = list(rows)
    if not rows:
        return

    header = (
        f"{'Pos':>3}  "
        f"{'Player':<18} "
        f"{'Team':<12} "
        f"{'Thru':>4}  "
        f"{'Gross':>5}  "
        f"{'Net':>5}  "
        f"{'HCP':>3}"
    )
    print("\n" + header)
    print("-" * len(header))

    for idx, row in enumerate(rows, start=1):
        line = (
            f"{idx:>3}  "
            f"{row.player_name:<18.18} "
            f"{row.team_name:<12.12} "
            f"{row.thru:>4}  "
            f"{row.gross_score:>5}  "
            f"{row.net_score:>5}  "
            f"{row.handicap_index:>3}"
        )
        print(line)

    print()
