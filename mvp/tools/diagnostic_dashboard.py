# mvp/tools/diagnostic_dashboard.py

import os
import time
import socket
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich import box

console = Console()


def check_lm_port(host: str, port: int, timeout: float = 0.3) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.bind((host, port))
        s.recvfrom(2048)
        return True
    except Exception:
        return False
    finally:
        s.close()


def file_status(path: str):
    if not os.path.exists(path):
        return "missing", "-"
    mtime = os.path.getmtime(path)
    age = time.time() - mtime
    return "ok", f"{int(age)}s ago"


def build_dashboard(host: str, port: int):
    lm_ok = check_lm_port(host, port)

    lb_status, lb_age = file_status("state/leaderboard.json")
    rs_status, rs_age = file_status("state/round_summary.json")
    ad_status, ad_age = file_status("state/admin_snapshot.json")

    t = Table(box=box.SIMPLE_HEAVY, expand=True)
    t.add_column("Component", style="bold")
    t.add_column("Status")
    t.add_column("Detail")

    t.add_row(
        "Launch Monitor Stream",
        "[green]OK[/green]" if lm_ok else "[red]NO DATA[/red]",
        f"{host}:{port}",
    )
    t.add_row(
        "Leaderboard JSON",
        "[green]OK[/green]" if lb_status == "ok" else "[red]MISSING[/red]",
        lb_age,
    )
    t.add_row(
        "Round Summary JSON",
        "[green]OK[/green]" if rs_status == "ok" else "[red]MISSING[/red]",
        rs_age,
    )
    t.add_row(
        "Admin Snapshot JSON",
        "[green]OK[/green]" if ad_status == "ok" else "[red]MISSING[/red]",
        ad_age,
    )

    panel = Panel(
        t,
        title=f"[bold cyan]SimCore22 Diagnostic Dashboard[/bold cyan]",
        subtitle=f"Updated: {datetime.now().strftime('%H:%M:%S')}",
        border_style="cyan",
        expand=True,
    )
    return panel


def main():
    host = "0.0.0.0"
    port = int(input("Enter LM port to monitor (e.g. 15000): "))

    with Live(refresh_per_second=1, console=console):
        while True:
            console.print(build_dashboard(host, port))
            time.sleep(1)
            console.clear()


if __name__ == "__main__":
    main()
