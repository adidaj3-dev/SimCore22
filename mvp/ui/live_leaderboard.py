# mvp/ui/live_leaderboard.py

import json
import os
import time

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

STATE_FILE = "state/leaderboard.json"
console = Console()


def render_leaderboard(data):
    console.clear()

    header = f"{data['league_name']} • Week {data['week']}"
    sub = f"Course: {data['course_name']}   Format: {data['format']}"

    table = Table(
        title="SIMCORE22 LIVE LEADERBOARD",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
        padding=(0, 1),
    )

    table.add_column("Pos", justify="right", style="bold white", overflow="fold")
    table.add_column("Player", style="bold", overflow="fold")
    table.add_column("Thru", justify="center", overflow="fold")
    table.add_column("Gross", justify="right", overflow="fold")
    table.add_column("Net", justify="right", overflow="fold")
    table.add_column("Vs Par", justify="right", overflow="fold")
    table.add_column("Pts", justify="right", style="green", overflow="fold")
    table.add_column("Need", justify="right", style="yellow", overflow="fold")

    players = sorted(data["players"], key=lambda p: (p["net"], p["thru"]))

    for i, p in enumerate(players, start=1):
        vs_par = p.get("vs_par", 0)
        vs_par_str = f"{vs_par:+d}" if isinstance(vs_par, int) else str(vs_par)
        table.add_row(
            str(i),
            p["name"],
            str(p["thru"]),
            str(p["gross"]),
            str(p["net"]),
            vs_par_str,
            str(p["points"]),
            str(p["points_needed"]),
        )

    me = next((p for p in players if p["name"].lower() == "jeff"), None)
    footer_text = ""
    if me:
        footer_text = (
            f"[bold]SimCore Index:[/bold] {me['simcore_index']}   "
            f"[bold]Outdoor HCP:[/bold] {me['outdoor_hcp']}   "
            f"[bold]Points:[/bold] {me['points']} / "
            f"{me['points'] + me['points_needed']}"
        )

    panel = Panel(
        table,
        title=header,
        subtitle=sub + ("\n" + footer_text if footer_text else ""),
        border_style="cyan",
        expand=True,
    )

    console.print(panel)


def main():
    last_mtime = None
    while True:
        if os.path.exists(STATE_FILE):
            mtime = os.path.getmtime(STATE_FILE)
            if mtime != last_mtime:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                render_leaderboard(data)
                last_mtime = mtime
        time.sleep(0.5)


if __name__ == "__main__":
    main()
