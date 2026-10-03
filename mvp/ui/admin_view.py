# mvp/ui/admin_view.py

import os
import time

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from mvp.engine.state_writer import ADMIN_SNAPSHOT_FILE as STATE_FILE, read_state

console = Console()


def render_admin(d):
    console.clear()

    header = f"{d['league_name']} • Week {d['week']}"

    table = Table(
        title="SIMCORE22 LEAGUE ADMIN VIEW",
        box=box.SIMPLE_HEAVY,
        header_style="bold magenta",
        show_lines=False,
        expand=True,
        padding=(0, 1),
    )

    cols = [
        "Player",
        "Outdoor\nGHIN",
        "SimCore\nIndex Start",
        "SimCore\nIndex Current",
        "Practice\nScore",
        "RD 1",
        "RD 2",
        "SimCore\nAdj 1",
        "RD 3",
        "RD 4",
        "SimCore\nAdj 2",
        "RD 5",
        "RD 6",
        "SimCore\nAdj 3",
        "Playoff\nRD",
        "Champ\nRD",
        "Ind\nPoints",
        "Team\nPoints",
    ]

    for c in cols:
        table.add_column(c, justify="center", no_wrap=False, overflow="fold")

    for p in d["players"]:
        weeks = p.get("week_scores", [])
        weeks = (weeks + [None] * 9)[:9]

        rd1 = weeks[0]
        rd2 = weeks[1]
        rd3 = weeks[2]
        rd4 = weeks[3]
        rd5 = weeks[4]
        rd6 = weeks[5]
        playoff = weeks[6]
        champ = weeks[7]

        row = [
            p["name"],
            str(p.get("outdoor_ghin", "")),
            str(p.get("simcore_index_start", "")),
            str(p.get("simcore_index_current", "")),
            str(p.get("practice_score", "")),
            "" if rd1 is None else str(rd1),
            "" if rd2 is None else str(rd2),
            "",
            "" if rd3 is None else str(rd3),
            "" if rd4 is None else str(rd4),
            "",
            "" if rd5 is None else str(rd5),
            "" if rd6 is None else str(rd6),
            "",
            "" if playoff is None else str(playoff),
            "" if champ is None else str(champ),
            str(p.get("total_individual_points", "")),
            str(p.get("team_points", "")),
        ]

        table.add_row(*row)

    teams_table = Table(
        title="Team Standings",
        box=box.SIMPLE,
        header_style="bold green",
        show_lines=False,
        expand=True,
        padding=(0, 1),
    )
    teams_table.add_column("Team / Player", justify="left", overflow="fold")
    teams_table.add_column("Points", justify="right", overflow="fold")

    players_by_team = {}
    for p in d.get("players", []):
        team_name = p.get("team_name", "")
        if team_name:
            players_by_team.setdefault(team_name, []).append(p["name"])

    for t in d.get("teams", []):
        team_name = t["name"]
        teams_table.add_row(team_name, str(t["points"]))
        for player in players_by_team.get(team_name, []):
            teams_table.add_row(f"  {player}", "")

    outer = Table.grid(expand=True)
    outer.add_row(table)
    outer.add_row(teams_table)

    panel = Panel(
        outer,
        title=f"[bold magenta]{header}[/bold magenta]",
        border_style="magenta",
        expand=True,
    )

    console.print(panel)


def main():
    last_mtime = None
    while True:
        if os.path.exists(STATE_FILE):
            mtime = os.path.getmtime(STATE_FILE)
            if mtime != last_mtime:
                d = read_state(STATE_FILE)
                if d is not None:  # None = being rewritten right now; retry next poll
                    render_admin(d)
                    last_mtime = mtime
        time.sleep(1.0)


if __name__ == "__main__":
    main()
