# mvp/engine/ocr/bootstrap_windows.py
import cv2
import asyncio
import logging
from pathlib import Path

from mvp.engine.ingestion.dispatcher import EventDispatcher
from mvp.engine.ocr.round_start_ocr import RoundStartOCR
from mvp.engine.ocr.ocr_listener import OCRHudListener
from mvp.engine import config
from mvp.engine.ocr.capture_windows import capture_game_frame

# Attach Rich dashboard listener
from mvp.ui.rich_dashboard import update_dashboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimCore22.OCRBootstrap.Windows")


class WindowsOCROnlyBootstrap:
    """
    Windows-only OCR bootstrapper.
    - Captures HUD from a real monitor using MSS
    - Feeds frames into OCRHudListener
    - Uses the same event model and round lifecycle as Mac
    """

    def __init__(self, layout_dir: str, monitor_index: int = 1, poll_interval: float = 1.0):
        self.layout_dir = Path(layout_dir)
        self.monitor_index = monitor_index
        self.poll_interval = poll_interval

        # Event dispatcher
        self.dispatcher = EventDispatcher()

        # Attach Rich dashboard listener
        self.dispatcher.add_listener(update_dashboard)

        # Round lifecycle
        self.round = RoundStartOCR(
            layout_dir=self.layout_dir,
            emit_callback=self.dispatcher.emit,
        )

        # OCR HUD listener
        self.listener = OCRHudListener(
            emit_callback=self.dispatcher.emit,
            base_dir=self.layout_dir,
            poll_interval=self.poll_interval,
        )

        self._running = False

    async def _capture_loop(self):
        """
        Windows-only capture loop:
        - Grabs full monitor frame
        - Passes it to OCRHudListener.process_frame()
        """
        self._running = True
        logger.info(f"Starting Windows capture loop on monitor {self.monitor_index}")

        while self._running:
            try:
                frame = capture_game_frame(config.CAPTURE_WINDOW_TITLE, self.monitor_index)
            except Exception as exc:  # GSPro not open yet, etc. - keep waiting
                logger.warning(f"Capture not ready: {exc}")
                await asyncio.sleep(self.poll_interval)
                continue
            cv2.imwrite("hud_preview.png", frame)
            await self.listener.process_frame(frame)
            await asyncio.sleep(self.poll_interval)

    async def start(self, player_name: str = "Player 1"):
        logger.info("=== STARTING SIMCORE22 OCR-ONLY MODE (WINDOWS) ===")

        # Start round (emits RoundStartEvent, PlayerEvent, HoleEvent)
        await self.round.start_round(player_name=player_name)

        # Start dispatcher loop
        asyncio.create_task(self.dispatcher.run())

        # Start capture loop
        asyncio.create_task(self._capture_loop())

        logger.info("Windows OCR-only mode is now running.")

    async def stop(self):
        logger.info("=== STOPPING SIMCORE22 OCR-ONLY MODE (WINDOWS) ===")
        self._running = False
        await self.round.end_round()
        await self.dispatcher.stop()
        logger.info("Windows OCR-only mode stopped cleanly.")


async def main():
    layout_dir = str(Path(__file__).resolve().parent / "layouts")

    # Adjust monitor_index if GSPro is on a different display
    system = WindowsOCROnlyBootstrap(
        layout_dir=layout_dir,
        monitor_index=1,   # Change to 2 or 3 if GSPro HUD is on another monitor
        poll_interval=1.0,
    )

    await system.start(player_name="BAY_PLAYER")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await system.stop()


if __name__ == "__main__":
    asyncio.run(main())
