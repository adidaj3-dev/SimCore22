import asyncio
import logging
import sys
import time
from contextlib import contextmanager

import pytest

from mvp.engine.engine_loop import EngineRuntime
from mvp.engine.ocr.window_capture import make_dpi_aware

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows capture")


class _RecordingListener:
    def __init__(self):
        self.frames = []

    async def process_frame(self, frame):
        self.frames.append(frame)


@contextmanager
def stand_in_window(title, color, width=480, height=300):
    tk = pytest.importorskip("tkinter")
    make_dpi_aware()
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    try:
        root.title(title)
        root.geometry("+160+110")
        root.attributes("-topmost", True)
        tk.Canvas(root, width=width, height=height, highlightthickness=0, bd=0, bg=color).pack()
        for _ in range(8):
            root.update()
            time.sleep(0.1)
        yield
    finally:
        root.destroy()


def _run_loop(title, seconds=0.8):
    """Run the engine's real capture loop for a moment against a stub OCR listener."""
    runtime = EngineRuntime("127.0.0.1", 921, ocr_enabled=True, window_title=title, ocr_poll_interval=0.1)
    runtime.ocr_listener = _RecordingListener()

    async def go():
        task = asyncio.create_task(runtime._ocr_capture_loop())
        await asyncio.sleep(seconds)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    return runtime.ocr_listener.frames


def test_loop_feeds_ocr_the_window_picture():
    title = "SimCoreLoopTest-OK"
    with stand_in_window(title, "#2a6f2a", 480, 300):
        frames = _run_loop(title)
    assert len(frames) >= 3
    assert frames[0].shape[:2] == (300, 480)  # the picture only, borders cropped


def test_loop_waits_quietly_when_the_game_isnt_open(caplog):
    with caplog.at_level(logging.INFO, logger="mvp.engine.engine_loop"):
        frames = _run_loop("zzz-no-such-window-55555")
    assert frames == []
    waiting = [r for r in caplog.records if "Waiting for" in r.getMessage()]
    assert len(waiting) == 1  # one line, not one per poll


def test_loop_warns_once_and_skips_ocr_on_black_frames(caplog):
    title = "SimCoreLoopTest-BLACK"
    with stand_in_window(title, "#000000"):
        with caplog.at_level(logging.INFO, logger="mvp.engine.engine_loop"):
            frames = _run_loop(title)
    assert frames == []  # never ran OCR on a black frame
    black = [r for r in caplog.records if "exclusive fullscreen" in r.getMessage()]
    assert len(black) == 1
