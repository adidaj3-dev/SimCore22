# simcore22/engine/console.py
"""Typed commands for whoever is at the engine window (and, later, an admin portal)."""
import asyncio
import logging
import sys
import threading
from typing import Awaitable, Callable

from simcore22.engine import engine
from simcore22.engine.rounds import RoundManager

logger = logging.getLogger(__name__)

CONSOLE_HELP = """\
Engine commands (type one, press Enter):
  end     finish the round now and save it (use when a player quits early)
  save    checkpoint the round so far; play continues
  status  show who is playing and how far along they are
  help    show this list"""


def _who(results: list) -> str:
    return ", ".join(f"{name} ({holes} holes)" for name, holes in results)


async def run_command(rounds: RoundManager, command: str) -> str:
    """Run one command; returns the text to show the person who typed it."""
    cmd = command.strip().lower()

    if cmd in ("end", "e"):
        if not rounds.has_data():
            return "No round in progress - nothing to end."
        results = rounds.finalize(reason="manual_end")
        return f"Round ended and saved: {_who(results) or 'nothing to save'}."

    if cmd in ("save", "s"):
        saved = rounds.snapshot()
        if not saved:
            return "No round in progress - nothing to save."
        return f"Checkpoint saved: {_who(saved)}. The round continues."

    if cmd == "status":
        players = [
            f"{name}: {sum(1 for h in rs.holes.values() if h.gross_score is not None or h.strokes > 0)} holes"
            for name, rs in engine.get_session_state().players.items() if rounds.player_has_data(rs)
        ]
        if not players:
            return "No round in progress."
        idle_min = int(rounds.idle_for().total_seconds() // 60)
        return f"Round in progress - {'; '.join(players)}. {len(rounds.shots)} shots. Idle {idle_min} min."

    if cmd in ("help", "?"):
        return CONSOLE_HELP
    return f"Unknown command '{command}'. Type help."


def start_console_thread(run: Callable[[str], Awaitable[str]], loop: asyncio.AbstractEventLoop) -> bool:
    """
    Read commands from the console in a background thread and run them on the
    engine's event loop. Does nothing (returns False) if no console is attached,
    e.g. when started as a service.
    """
    if not sys.stdin or not sys.stdin.isatty():
        return False

    def worker() -> None:
        print(CONSOLE_HELP)
        for line in sys.stdin:
            command = line.strip()
            if not command:
                continue
            future = asyncio.run_coroutine_threadsafe(run(command), loop)
            try:
                print(future.result(timeout=60))
            except Exception as exc:
                print(f"Command failed: {exc}")

    threading.Thread(target=worker, name="simcore-console", daemon=True).start()
    return True
