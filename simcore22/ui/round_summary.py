# simcore22/ui/round_summary.py

import os
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from simcore22.engine.state_writer import ROUND_SUMMARY_FILE as STATE_FILE, read_state

console = Console()


def render_summary(d):
    console.clear()

    header = f"{d['player']} • {d['course']} • {d['holes']} holes"
    sub = (
        f"Gross: {d['gross']}  "
        f"Vs Par: {d['score_vs_par']:+d}  "
        f"Net: {d['net']}  "
        f"SimCore Index: {d['simcore_index']}"
    )

    bf = d["ball_flight"]
    sc = d["scoring"]
    lg = d["league"]

    t1 = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 1))
    t1.add_row("Avg Ball Speed", f"{bf['avg_bs']:.1f} mph" if bf["avg_bs"] is not None else "N/A")
    t1.add_row("Max Ball Speed", f"{bf['max_bs']:.1f} mph" if bf["max_bs"] is not None else "N/A")
    t1.add_row("Avg Carry", f"{bf['avg_carry']:.1f} yds" if bf["avg_carry"] is not None else "N/A")

    t2 = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 1))
    t2.add_row("Birdies", str(sc["birdies"]))
    t2.add_row("Pars", str(sc["pars"]))
    t2.add_row("Bogeys", str(sc["bogeys"]))

    t3 = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 1))
    t3.add_row("Stableford", str(lg["stableford"]))
    t3.add_row("Quota", str(lg["quota"]))
    t3.add_row("Target", str(lg["points_target"]))

    outer = Table.grid(expand=True)
    outer.add_row(t1, t2, t3)

    panel = Panel(
        outer,
        title=f"[bold cyan]SIMCORE22 ROUND SUMMARY[/bold cyan]  {header}",
        subtitle=sub,
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
                d = read_state(STATE_FILE)
                if d is not None:  # None = being rewritten right now; retry next poll
                    render_summary(d)
                    last_mtime = mtime
        time.sleep(0.5)


if __name__ == "__main__":
    main()
