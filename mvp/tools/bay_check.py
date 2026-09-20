# mvp/tools/bay_check.py
"""
Run this ON THE BAY PC (with GSPro / FSX open) to find out why capture or data
isn't working. It never changes anything - it only looks.

    python -m mvp.tools.bay_check            # 5 second countdown, then check
    python -m mvp.tools.bay_check --delay 0

It reports, and saves to captures/<timestamp>/ :
  1. Your monitors and their resolution / DPI scaling
  2. A screenshot of every monitor, and whether each one is BLACK
     (black = the game is in exclusive fullscreen; switch it to borderless)
  3. Which GSPro / Foresight / launch-monitor programs are running, their
     windows, and whether each window is borderless-fullscreen
  4. Which network ports those programs are listening on / connected to
     (this is where a launch monitor's data path shows up - e.g. GSPro Connect
     should be LISTENING on 127.0.0.1:921)

Zip up the captures/<timestamp>/ folder and send it back for calibration.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import cv2
import mss
import numpy as np

GSPRO_CONNECT_PORT = 921

# A keyword only counts at the start of a word, so "e6" matches "E6Connect.exe"
# but not the "e6" inside "RtkAudUService64.exe".
_WATCH = re.compile(
    r"(?<![a-z0-9])(?:gspro|gs pro|fsx|foresight|falcon|hawk|gcquad|gc3|"
    r"trackman|skytrak|uneekor|e6|tgc|openconnect)"
)


# ---------------------------------------------------------------- Windows bits

def _make_dpi_aware() -> None:
    """Without this Windows lies about pixel sizes on scaled (125%/150%) displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _list_windows() -> List[Dict]:
    """Visible top-level windows: title, owning process id, rectangle, style."""
    user32 = ctypes.windll.user32
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    out: List[Dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        out.append({
            "title": buf.value,
            "pid": pid.value,
            "left": rect.left, "top": rect.top,
            "width": rect.right - rect.left, "height": rect.bottom - rect.top,
            "has_title_bar": bool(style & 0x00C00000),  # WS_CAPTION
        })
        return True

    user32.EnumWindows(visit, 0)
    return out


def _process_names() -> Dict[int, str]:
    """pid -> exe name, via tasklist (no extra dependencies)."""
    result = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, errors="replace")
    names: Dict[int, str] = {}
    for line in result.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            names[int(parts[1])] = parts[0].strip('"')
    return names


def _connections() -> List[Dict]:
    """TCP/UDP endpoints with owning pid, via netstat."""
    result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="replace")
    rows: List[Dict] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or parts[0] not in ("TCP", "UDP"):
            continue
        if parts[0] == "TCP" and len(parts) >= 5:
            rows.append({"proto": "TCP", "local": parts[1], "remote": parts[2],
                         "state": parts[3], "pid": int(parts[4])})
        elif parts[0] == "UDP" and len(parts) >= 4:
            rows.append({"proto": "UDP", "local": parts[1], "remote": parts[2],
                         "state": "", "pid": int(parts[3])})
    return rows


# ------------------------------------------------------------------- the check

def _is_watched(text: str) -> bool:
    return bool(_WATCH.search(text.lower()))


def check_monitors(out_dir: Path) -> List[Dict]:
    report: List[Dict] = []
    with mss.MSS() as sct:
        for idx, mon in enumerate(sct.monitors):
            label = "ALL monitors combined" if idx == 0 else f"monitor {idx}"
            shot = np.array(sct.grab(mon))[:, :, :3]
            gray = cv2.cvtColor(shot, cv2.COLOR_BGR2GRAY)
            black_fraction = float((gray < 8).mean())
            entry = {
                "index": idx, "label": label,
                "size": f"{mon['width']}x{mon['height']}",
                "position": f"({mon['left']},{mon['top']})",
                "mean_brightness": round(float(gray.mean()), 1),
                "black_fraction": round(black_fraction, 3),
                "looks_black": black_fraction > 0.98,
            }
            path = out_dir / f"monitor_{idx}.png"
            cv2.imwrite(str(path), shot)
            entry["file"] = path.name
            report.append(entry)
    return report


def check_programs() -> Dict:
    names = _process_names()
    windows = _list_windows()
    conns = _connections()

    watched_pids = {pid for pid, exe in names.items() if _is_watched(exe)}
    watched_pids |= {w["pid"] for w in windows if _is_watched(w["title"])}

    prog_windows = []
    for w in windows:
        if w["pid"] in watched_pids or _is_watched(w["title"]):
            prog_windows.append({**w, "exe": names.get(w["pid"], "?")})

    prog_conns = []
    for c in conns:
        if c["pid"] in watched_pids and (c["state"] in ("LISTENING", "ESTABLISHED", "")):
            prog_conns.append({**c, "exe": names.get(c["pid"], "?")})

    port_921 = [c for c in conns if c["local"].endswith(f":{GSPRO_CONNECT_PORT}") and c["state"] == "LISTENING"]

    return {
        "processes": sorted({names[p] for p in watched_pids if p in names}),
        "windows": prog_windows,
        "connections": prog_conns,
        "gspro_connect_listening": bool(port_921),
    }


def _monitor_containing(window: Dict, monitors: List[Dict]) -> str:
    for m in monitors[1:]:
        if m["size"] == f"{window['width']}x{window['height']}":
            return f"fills monitor {m['index']}"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="SimCore22 bay capture/data diagnostic")
    parser.add_argument("--delay", type=int, default=5,
                        help="seconds to wait so you can bring GSPro to the front (default 5)")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("bay_check is for the Windows bay PC.")
        return 1

    _make_dpi_aware()
    out_dir = Path("captures") / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print(" SimCore22 bay check")
    print("=" * 66)
    if args.delay:
        print(f"Bring GSPro / FSX to the front. Checking in {args.delay}s ...")
        for n in range(args.delay, 0, -1):
            print(f"  {n}...", end="\r", flush=True)
            time.sleep(1)

    monitors = check_monitors(out_dir)
    programs = check_programs()

    print("\n1) MONITORS + SCREENSHOTS")
    for m in monitors:
        flag = "  <-- BLACK FRAME" if m["looks_black"] else ""
        print(f"   {m['label']:24} {m['size']:>10} at {m['position']:<12} "
              f"brightness {m['mean_brightness']:>5}{flag}   -> {m['file']}")

    print("\n2) LAUNCH-MONITOR / SIM PROGRAMS")
    if not programs["processes"]:
        print("   None found. Are GSPro / FSX running on THIS computer?")
    for exe in programs["processes"]:
        print(f"   running: {exe}")
    for w in programs["windows"]:
        bord = "borderless" if not w["has_title_bar"] else "windowed (has title bar)"
        fills = _monitor_containing(w, monitors)
        print(f"   window : '{w['title'][:50]}' {w['width']}x{w['height']} {bord} {fills}")

    print("\n3) NETWORK (what those programs are listening on / talking to)")
    if programs["gspro_connect_listening"]:
        print(f"   OK   GSPro Connect is LISTENING on port {GSPRO_CONNECT_PORT}.")
    else:
        print(f"   NOTE nothing is listening on port {GSPRO_CONNECT_PORT}. "
              "GSPro Connect only listens once GSPro is open and Connect is enabled.")
    if not programs["connections"]:
        print("   (no open connections found for those programs)")
    for c in programs["connections"]:
        remote = c["remote"] if c["state"] != "LISTENING" else ""
        print(f"   {c['exe']:<22} {c['proto']} {c['state']:<12} {c['local']:<22} {remote}")

    print("\n4) VERDICT")
    black = [m for m in monitors[1:] if m["looks_black"]]
    if black:
        print("   Screen capture is returning BLACK for monitor(s) "
              f"{', '.join(str(m['index']) for m in black)}.")
        print("   Cause: the game is in exclusive fullscreen. Switch GSPro (and FSX)")
        print("   to 'Windowed' / 'Borderless windowed' in their display settings, then re-run.")
    else:
        print("   Screen capture is returning real pixels. Open the PNGs to confirm")
        print("   they show the GSPro screen, then run the OCR on them.")

    (out_dir / "report.json").write_text(
        json.dumps({"monitors": monitors, "programs": programs}, indent=2), encoding="utf-8")
    print(f"\nSaved everything to: {out_dir.resolve()}")
    print("Send that whole folder back for calibration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
