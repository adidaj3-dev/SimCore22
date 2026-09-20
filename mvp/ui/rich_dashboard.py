from __future__ import annotations

import time
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich import box

from mvp.engine.models.events import ShotEvent, ScoreEvent, HoleEvent, PlayerEvent

console = Console()

# Global dashboard state
_last_shot: Dict[str, Any] | None = None
_shot_history: List[Dict[str, Any]] = []
_scoreboard: Dict[str, Dict[str, Any]] = {}
_current_player: str | None = None
_current_hole: int | None = None


# ---------------------------------------------------------------------------
# Event Router
# ---------------------------------------------------------------------------

def update_dashboard(event: Any) -> None:
    """
    Called by bootstrap_windows.py whenever an event arrives.
    Updates internal dashboard state and re-renders the UI.
    """
    global _last_shot, _shot_history, _scoreboard, _current_player, _current_hole

    # PlayerEvent
    if isinstance(event, PlayerEvent):
        _current_player = event.player_name.strip()

    # HoleEvent
    elif isinstance(event, HoleEvent):
        _current_hole = event.hole_number

    # ShotEvent
    elif isinstance(event, ShotEvent):
        shot_info = {
            "player": event.metadata.get("player_name", _current_player),
            "hole": event.metadata.get("hole_number", _current_hole),
            "ball_speed": event.ball_speed,
            "carry": event.carry,
            "launch_angle": event.launch_angle,
            "spin": event.spin,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        _last_shot = shot_info
        _shot_history.append(shot_info)
        if len(_shot_history) > 10:
            _shot_history.pop(0)

    # ScoreEvent
    elif isinstance(event, ScoreEvent):
        player = event.player_name.strip()
        hole = event.hole_number
        gross = event.gross_score
        par = event.par

        if player not in _scoreboard:
            _scoreboard[player] = {"gross": 0, "holes": {}}

        _scoreboard[player]["holes"][hole] = {"gross": gross, "par": par}
        _scoreboard[player]["gross"] = sum(
            h["gross"] for h in _scoreboard[player]["holes"].values() if h["gross"] is not None
        )

    render_dashboard()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_dashboard() -> None:
    console.clear()
    layout = Layout()

    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3),
    )

    layout["body"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=1),
    )

    layout["left"].split(
        Layout(name="last_shot", ratio=1),
        Layout(name="shot_history", ratio=1),
    )

    layout["right"].split(
        Layout(name="scoreboard", ratio=1),
        Layout(name="mini_leaderboard", ratio=1),
    )

    layout["header"].update(render_header())
    layout["last_shot"].update(render_last_shot())
    layout["shot_history"].update(render_shot_history())
    layout["scoreboard"].update(render_scoreboard())
    layout["mini_leaderboard"].update(render_mini_leaderboard())
    layout["footer"].update(render_footer())

    console.print(layout)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

def render_header() -> Panel:
    txt = Text("SIMCORE22 LIVE DASHBOARD", style="bold cyan")
    return Panel(txt, border_style="cyan", padding=(0, 2))


def render_last_shot() -> Panel:
    if not _last_shot:
        return Panel("Waiting for first shot...", title="Last Shot", border_style="green")

    t = Table(box=box.SIMPLE, expand=True)
    t.add_column("Field")
    t.add_column("Value")

    for k, v in _last_shot.items():
        t.add_row(str(k), str(v))

    return Panel(t, title="Last Shot", border_style="green")


def render_shot_history() -> Panel:
    t = Table(box=box.SIMPLE, expand=True)
    t.add_column("Time")
    t.add_column("Player")
    t.add_column("Hole")
    t.add_column("BS")
    t.add_column("Carry")

    for s in reversed(_shot_history):
        t.add_row(
            s["timestamp"],
            str(s["player"]),
            str(s["hole"]),
            f"{s['ball_speed']}",
            f"{s['carry']}",
        )

    return Panel(t, title="Shot History (Last 10)", border_style="yellow")


def render_scoreboard() -> Panel:
    t = Table(box=box.SIMPLE_HEAVY, expand=True)
    t.add_column("Player")
    t.add_column("Gross")
    t.add_column("Holes")

    for player, data in _scoreboard.items():
        holes_str = ", ".join(
            f"{h}:{info['gross']}"
            for h, info in data["holes"].items()
        )
        t.add_row(player, str(data["gross"]), holes_str)

    return Panel(t, title="Scoreboard", border_style="cyan")


def render_mini_leaderboard() -> Panel:
    t = Table(box=box.SIMPLE, expand=True)
    t.add_column("Player")
    t.add_column("Gross")

    for player, data in sorted(_scoreboard.items(), key=lambda x: x[1]["gross"]):
        t.add_row(player, str(data["gross"]))

    return Panel(t, title="Mini Leaderboard", border_style="magenta")


def render_footer() -> Panel:
    txt = Text("SimCore22 MVP • Live Engine Active", style="bold blue")
    return Panel(txt, border_style="blue")


# ---------------------------------------------------------------------------
# Manual Run
# ---------------------------------------------------------------------------

def main():
    render_dashboard()


if __name__ == "__main__":
    main()
