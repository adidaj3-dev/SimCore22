# mvp/engine/ocr/bootstrap_ocr_only.py
import asyncio
import logging
from pathlib import Path

from mvp.engine.ingestion.dispatcher import EventDispatcher
from .round_start_ocr import RoundStartOCR

logger = logging.getLogger("SimCore22.OCRBootstrap")
logging.basicConfig(level=logging.INFO)


class OCROnlyBootstrap:
    """
    Top-level orchestrator for OCR-only mode.
    """

    def __init__(self, layout_dir: str):
        self.layout_dir = Path(layout_dir)
        self.dispatcher = EventDispatcher()
        self.round = RoundStartOCR(
            layout_dir=self.layout_dir,
            emit_callback=self.dispatcher.emit,
        )

    async def start(self, player_name: str = "Player 1"):
        logger.info("=== STARTING SIMCORE22 OCR-ONLY MODE ===")
        await self.round.start_round(player_name=player_name)
        asyncio.create_task(self.dispatcher.run())
        logger.info("OCR-only mode is now running.")

    async def stop(self):
        logger.info("=== STOPPING SIMCORE22 OCR-ONLY MODE ===")
        await self.round.end_round()
        await self.dispatcher.stop()
        logger.info("OCR-only mode stopped cleanly.")


async def main():
    layout_dir = str(Path(__file__).resolve().parent / "layouts")
    system = OCROnlyBootstrap(layout_dir=layout_dir)
    await system.start(player_name="FAKE_PLAYER")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await system.stop()


if __name__ == "__main__":
    asyncio.run(main())
