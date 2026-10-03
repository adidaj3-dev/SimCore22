# mvp/engine/ocr/window_capture.py
"""
Capture the GSPro window itself instead of a whole monitor.

Why: the OCR layouts (layouts/*.json) are fractions of the game picture. If
GSPro runs windowed - title bar, borders, not filling the display, parked on
the second monitor - a full-monitor frame puts every fraction in the wrong
place. Cropping to the window's *client area* (the drawable part, no title bar
or borders) makes the frame the same no matter where or how big the window is.

Limits worth knowing:
  * The grab reads screen pixels, so another window covering part of GSPro
    appears in the frame. Keep GSPro on top of its monitor.
  * A minimized window can't be captured; we report it as not found.
  * If the game window itself comes back black, the game is probably in
    exclusive fullscreen - switch it to windowed / borderless (see bay_check).
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import mss
import numpy as np

logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]  # left, top, width, height (screen pixels)

# A window whose title matches but is really one of these is not the game:
# a terminal or Explorer folder both happily have "GSPro" in their title.
_NOT_THE_GAME = {
    "explorer.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe",
    "windowsterminal.exe", "code.exe", "notepad.exe", "chrome.exe", "msedge.exe",
    "firefox.exe", "claude.exe",
}
_MIN_CLIENT_SIZE = (200, 150)  # ignore tiny tool windows

_dpi_done = False


class GameWindowNotFound(RuntimeError):
    """No usable window matched the configured title."""


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    exe: str
    # Outer rectangle (includes title bar and borders)
    left: int
    top: int
    width: int
    height: int
    # Client rectangle: just the drawable area, in screen coordinates
    client_left: int
    client_top: int
    client_width: int
    client_height: int
    has_title_bar: bool
    minimized: bool

    @property
    def client_box(self) -> Box:
        return (self.client_left, self.client_top, self.client_width, self.client_height)

    @property
    def frame_thickness(self) -> int:
        """Pixels of title bar + borders around the picture (0 = borderless)."""
        return (self.width * self.height) - (self.client_width * self.client_height)


# ------------------------------------------------------------------ win32 bits

def make_dpi_aware() -> None:
    """
    Without this, Windows reports window sizes in scaled units on 125%/150%
    displays and the crop lands in the wrong spot. Safe to call repeatedly.
    """
    global _dpi_done
    if _dpi_done or sys.platform != "win32":
        return
    _dpi_done = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            logger.debug("Could not set DPI awareness", exc_info=True)


def _exe_name(pid: int) -> str:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value.rsplit("\\", 1)[-1] if ok else ""
    finally:
        kernel32.CloseHandle(handle)


def list_windows() -> List[WindowInfo]:
    """Visible, titled, top-level windows."""
    make_dpi_aware()
    user32 = ctypes.windll.user32
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]

    found: List[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)

        outer, client = wintypes.RECT(), wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(outer))
        user32.GetClientRect(hwnd, ctypes.byref(client))
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE

        found.append(WindowInfo(
            hwnd=int(hwnd or 0), title=title.value, pid=pid.value, exe=_exe_name(pid.value),
            left=outer.left, top=outer.top,
            width=outer.right - outer.left, height=outer.bottom - outer.top,
            client_left=origin.x, client_top=origin.y,
            client_width=client.right - client.left, client_height=client.bottom - client.top,
            has_title_bar=bool(style & 0x00C00000),  # WS_CAPTION
            minimized=bool(user32.IsIconic(hwnd)),
        ))
        return True

    user32.EnumWindows(visit, 0)
    return found


# --------------------------------------------------------------------- finding

def find_window(
    title_contains: str, windows: Optional[Sequence[WindowInfo]] = None
) -> Optional[WindowInfo]:
    """
    Best window whose title contains `title_contains` (case-insensitive):
    visible, not minimized, big enough to be a game, not a terminal/Explorer.
    If several match, the one with the largest drawable area wins.
    """
    if not title_contains:
        return None
    needle = title_contains.lower()
    wins = list_windows() if windows is None else windows
    candidates = [
        w for w in wins
        if needle in w.title.lower()
        and not w.minimized
        and w.client_width >= _MIN_CLIENT_SIZE[0]
        and w.client_height >= _MIN_CLIENT_SIZE[1]
        and w.exe.lower() not in _NOT_THE_GAME
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda w: w.client_width * w.client_height)


# ------------------------------------------------------------------- capturing

def clip_box(box: Box, area: Box) -> Optional[Box]:
    """Intersection of two (left, top, width, height) boxes, or None if empty."""
    l1, t1, w1, h1 = box
    l2, t2, w2, h2 = area
    left, top = max(l1, l2), max(t1, t2)
    right, bottom = min(l1 + w1, l2 + w2), min(t1 + h1, t2 + h2)
    if right <= left or bottom <= top:
        return None
    return (left, top, right - left, bottom - top)


def grab_box(box: Box) -> np.ndarray:
    """Grab a screen rectangle (any monitor) as a BGR array."""
    make_dpi_aware()
    with mss.MSS() as sct:
        virtual = sct.monitors[0]  # all monitors combined
        area = (virtual["left"], virtual["top"], virtual["width"], virtual["height"])
        clipped = clip_box(box, area)
        if clipped is None:
            raise GameWindowNotFound("Game window is entirely off-screen.")
        if clipped != box:
            logger.warning("Game window extends past the screen; capturing the visible part only.")
        left, top, width, height = clipped
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)


def grab_window(window: WindowInfo) -> np.ndarray:
    """The window's drawable area only - no title bar, no borders."""
    return grab_box(window.client_box)


def capture_window_frame(title_contains: str) -> np.ndarray:
    """Find the window by title and return its drawable area as a BGR array."""
    window = find_window(title_contains)
    if window is None:
        raise GameWindowNotFound(
            f"No visible window with '{title_contains}' in its title "
            "(is it open and not minimized?). Run: python -m mvp.tools.bay_check"
        )
    return grab_window(window)


def looks_black(frame: np.ndarray, threshold: float = 0.98) -> bool:
    """True when (almost) every pixel is black - the exclusive-fullscreen symptom."""
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float((gray < 8).mean()) > threshold
