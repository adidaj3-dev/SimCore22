# simcore22/tools/bay_check.py
"""
Run this ON THE BAY PC (with GSPro / FSX open) to find out why capture or data
isn't working. It never changes anything - it only looks.

    python -m simcore22.tools.bay_check            # 5 second countdown, then check
    python -m simcore22.tools.bay_check --delay 0

It reports, and saves to captures/<timestamp>/ :
  1. Your monitors and a screenshot of each, and whether each one is BLACK
  2. Which GSPro / Foresight / launch-monitor programs are running and their
     windows (borderless or with a title bar)
  3. Which network ports those programs are listening on / connected to
     (e.g. GSPro Connect should be LISTENING on 127.0.0.1:921)
  4. The CAPTURE TARGET: the GSPro window the engine will crop to, saved as
     game_window.png (should be just the game picture - no title bar, borders
     or other windows). If GSPro's title isn't found, it lists candidates.
  5. A verdict. Black capture = exclusive fullscreen; switch to borderless.

Zip up the captures/<timestamp>/ folder and send it back for calibration.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import cv2
import mss
import numpy as np

from simcore22.engine import config
from simcore22.engine.ocr.window_capture import (
    _NOT_THE_GAME,
    find_window,
    grab_window,
    list_windows,
    looks_black,
    make_dpi_aware,
)

GSPRO_CONNECT_PORT = 921

# A keyword only counts at the start of a word, so "e6" matches "E6Connect.exe"
# but not the "e6" inside "RtkAudUService64.exe".
_WATCH = re.compile(
    r"(?<![a-z0-9])(?:gspro|gs pro|fsx|foresight|falcon|hawk|gcquad|gc3|"
    r"trackman|skytrak|uneekor|e6|tgc|openconnect)"
)


# ---------------------------------------------------------------- Windows bits

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


def check_capture_target(out_dir: Path) -> Dict:
    """
    What the engine will actually capture: the configured window's drawable
    area. Saves it as game_window.png so you can confirm it's just the game.
    """
    title = config.CAPTURE_WINDOW_TITLE
    result: Dict = {"title_setting": title, "found": False}
    windows = list_windows()
    win = find_window(title, windows)

    if win is None:
        # Help pick the right title: every window big enough to be a game.
        result["candidates"] = sorted(
            {w.title for w in windows
             if w.client_width >= 200 and w.client_height >= 150 and not w.minimized
             and w.exe.lower() not in _NOT_THE_GAME},
        )
        return result

    frame = grab_window(win)
    path = out_dir / "game_window.png"
    cv2.imwrite(str(path), frame)
    result.update({
        "found": True,
        "title": win.title,
        "exe": win.exe,
        "outer_size": f"{win.width}x{win.height}",
        "picture_size": f"{win.client_width}x{win.client_height}",
        "picture_position": f"({win.client_left},{win.client_top})",
        "has_title_bar": win.has_title_bar,
        "borderless": win.frame_thickness == 0,
        "cropped_off": f"{win.width - win.client_width}x{win.height - win.client_height}",
        "looks_black": looks_black(frame),
        "file": path.name,
    })
    return result


def check_programs() -> Dict:
    names = _process_names()
    windows = [asdict(w) for w in list_windows()]
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

    make_dpi_aware()
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
    target = check_capture_target(out_dir)

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

    print(f"\n4) CAPTURE TARGET  (window title contains '{target['title_setting']}')")
    if target["found"]:
        frame_note = ("borderless - picture fills the window" if target["borderless"]
                      else f"title bar/borders cropped off ({target['cropped_off']} px, wide x tall)")
        print(f"   FOUND  '{target['title'][:50]}' ({target['exe']})")
        print(f"          window {target['outer_size']}, picture {target['picture_size']} "
              f"at {target['picture_position']}; {frame_note}")
        print(f"          what the OCR will see -> {target['file']}")
    else:
        print("   NOT FOUND. If GSPro is open, its title doesn't contain that text.")
        print("   Windows that could be it (set SIMCORE_WINDOW_TITLE to part of the right one):")
        for title in target.get("candidates", []):
            print(f"     - {title[:70]}")

    print("\n5) VERDICT")
    black_monitors = [m for m in monitors[1:] if m["looks_black"]]
    if target["found"] and target["looks_black"]:
        print("   The GSPro window is capturing as BLACK.")
        print("   Cause: exclusive fullscreen. Switch GSPro to 'Windowed' / 'Borderless")
        print("   windowed' in its display settings, then re-run.")
    elif target["found"]:
        print("   Window capture works. Open game_window.png: it should be only the game")
        print("   picture. If so, capture is ready and OCR calibration is the next step.")
    elif black_monitors:
        print("   GSPro window not found, and monitor capture is BLACK for monitor(s) "
              f"{', '.join(str(m['index']) for m in black_monitors)}.")
        print("   Open GSPro (windowed/borderless, not minimized) and re-run.")
    else:
        print("   Screen capture returns real pixels, but the GSPro window wasn't found.")
        print("   Open GSPro (not minimized) and re-run, or fix the window title above.")

    (out_dir / "report.json").write_text(
        json.dumps({"monitors": monitors, "programs": programs, "capture_target": target}, indent=2),
        encoding="utf-8")
    print(f"\nSaved everything to: {out_dir.resolve()}")
    print("Send that whole folder back for calibration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
