import sys
import time

import numpy as np
import pytest

from mvp.engine.ocr.window_capture import (
    GameWindowNotFound,
    WindowInfo,
    capture_window_frame,
    clip_box,
    find_window,
    looks_black,
    make_dpi_aware,
)

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows capture")


def _win(title, w=1280, h=720, exe="gspro.exe", minimized=False):
    return WindowInfo(
        hwnd=1, title=title, pid=1, exe=exe,
        left=0, top=0, width=w, height=h,
        client_left=0, client_top=0, client_width=w, client_height=h,
        has_title_bar=False, minimized=minimized,
    )


# ------------------------------------------------------------ pure logic

def test_clip_box_inside_is_unchanged():
    assert clip_box((10, 10, 100, 50), (0, 0, 1920, 1080)) == (10, 10, 100, 50)


def test_clip_box_trims_the_part_off_screen():
    assert clip_box((1800, 1000, 300, 200), (0, 0, 1920, 1080)) == (1800, 1000, 120, 80)
    assert clip_box((-50, -20, 200, 100), (0, 0, 1920, 1080)) == (0, 0, 150, 80)


def test_clip_box_fully_off_screen_is_none():
    assert clip_box((3000, 0, 100, 100), (0, 0, 1920, 1080)) is None


def test_find_window_prefers_the_biggest_match():
    small, big = _win("GSPro - side panel", 400, 300), _win("GSPro", 1920, 1080)
    assert find_window("gspro", [small, big]) is big


def test_find_window_ignores_terminals_explorer_minimized_and_tiny_windows():
    wins = [
        _win("C:\\GSPro", exe="explorer.exe"),
        _win("GSPro log", exe="WindowsTerminal.exe"),
        _win("GSPro", minimized=True),
        _win("GSPro tooltip", 120, 80),
    ]
    assert find_window("gspro", wins) is None


def test_find_window_empty_title_means_no_window_capture():
    assert find_window("", [_win("GSPro")]) is None


def test_looks_black():
    assert looks_black(np.zeros((100, 100, 3), np.uint8))
    assert not looks_black(np.full((100, 100, 3), 120, np.uint8))
    half = np.zeros((100, 100, 3), np.uint8)
    half[:, :50] = 200
    assert not looks_black(half)


# ------------------------------------------------- real window on this PC

@windows_only
def test_missing_window_raises_not_found():
    with pytest.raises(GameWindowNotFound):
        capture_window_frame("zzz-no-such-window-98765")


@windows_only
@pytest.mark.parametrize(
    "position, canvas_w, canvas_h",
    [("+140+90", 640, 400), ("+700+260", 800, 500)],  # different spot AND size: same result
)
def test_capture_returns_only_the_picture_not_title_bar_or_borders(live_desktop, position, canvas_w, canvas_h):
    """
    Open a real window (title bar + borders) painted red on the left and blue
    on the right. The capture must be pure red/blue right to its edges - if
    the title bar or border leaked in, an edge pixel would be grey/white - and
    must be exactly the painted size wherever the window sits.
    """
    tk = pytest.importorskip("tkinter")
    make_dpi_aware()
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")

    title = "SimCoreCaptureTest-7731"
    try:
        root.title(title)
        root.geometry(position)
        root.attributes("-topmost", True)
        canvas = tk.Canvas(root, width=canvas_w, height=canvas_h, highlightthickness=0, bd=0)
        canvas.pack()
        half = canvas_w // 2
        canvas.create_rectangle(0, 0, half, canvas_h, fill="#ff0000", width=0)         # left: red
        canvas.create_rectangle(half, 0, canvas_w, canvas_h, fill="#0000ff", width=0)  # right: blue
        for _ in range(8):
            root.update()
            time.sleep(0.1)

        window = find_window(title)
        assert window is not None, "capture couldn't find the test window by title"
        assert window.has_title_bar
        assert window.frame_thickness > 0  # there ARE borders/title bar to crop away

        frame = capture_window_frame(title)

        assert frame.shape[:2] == (window.client_height, window.client_width)
        assert frame.shape[:2] == (canvas_h, canvas_w)  # exactly the painted area
        assert frame.shape[0] < window.height           # smaller than the outer window
        red_bgr, blue_bgr = (0, 0, 255), (255, 0, 0)
        h, w = frame.shape[:2]
        # Just inside each corner the frame is pure paint: no title bar or
        # border leaked in. (Inset a little: Windows 11 rounds the bottom
        # corners of a window, blending the last few pixels into the desktop.)
        inset = 14
        assert tuple(frame[0, 0]) == red_bgr          # top edge = first row of picture
        assert tuple(frame[0, w - 1]) == blue_bgr
        assert tuple(frame[h - inset, inset]) == red_bgr
        assert tuple(frame[h - inset, w - inset]) == blue_bgr
        assert tuple(frame[h // 2, 5]) == red_bgr     # left edge
        assert tuple(frame[h // 2, w - 6]) == blue_bgr  # right edge
        # and it really is a two-colour image, not a screenshot of something else
        assert {tuple(p) for p in frame[h // 2, :: max(1, w // 40)]} == {red_bgr, blue_bgr}
    finally:
        root.destroy()
