# simcore22/engine/engine_loop.py
"""
The running engine: connects the event sources to the live session and the
round lifecycle.

    sources                       event bus           handlers
    -------                       ---------           --------
    launch-monitor feed (opt-in)  EventDispatcher --> engine (session state)
    GSPro screen: HUD OCR                         --> publisher (leaderboard)
    GSPro screen: end-of-round card --------------> rounds (finish / save / reset)

Where things live:
    rounds.py          when a round ends, what is saved, what carries over
    scorecard_watch.py spotting GSPro's end-of-round scorecard on screen
    console.py         typed commands (end / save / status)
    publish.py         standings -> console + state/leaderboard.json
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from simcore22 import __version__
from simcore22.engine import config, console, engine
from simcore22.engine.ingestion.dispatcher import EventDispatcher
from simcore22.engine.ingestion.foresight.listener import ForesightLiveListener
from simcore22.engine.logging_config import setup_logging
from simcore22.engine.models.events import (
    HoleEvent, PlayerEvent, RoundEndEvent, ScoreEvent, ShotEvent,
)
from simcore22.engine.ocr.ocr_listener import OCRHudListener
from simcore22.engine.publish import LeaderboardPublisher
from simcore22.engine.rounds import RoundManager
from simcore22.engine.scorecard_watch import ScorecardWatcher
from simcore22.engine.state_writer import write_engine_status

logger = logging.getLogger(__name__)

STATUS_INTERVAL_S = 3.0


class EngineRuntime:
    def __init__(
        self,
        *,
        feed_host: Optional[str] = None,
        feed_port: Optional[int] = None,
        ocr_enabled: bool = True,
        window_title: str = config.CAPTURE_WINDOW_TITLE,
        monitor_index: int = config.CAPTURE_MONITOR_INDEX,
        ocr_poll_interval: float = 1.0,
        idle_timeout_minutes: float = config.ROUND_IDLE_TIMEOUT_MINUTES,
        console_commands: bool = True,
    ):
        if feed_port == config.GSPRO_CONNECT_PORT:
            raise ValueError(
                f"Port {feed_port} is GSPro Connect's own port: GSPro listens there for the "
                "launch-monitor software, and accepts only one client. Connecting to it would "
                "take FSX's place and break the bay. Use the launch monitor's own port instead "
                "(find it with `python -m simcore22.tools.packet_capture`)."
            )

        self.dispatcher = EventDispatcher()

        # Optional launch-monitor feed. NOTE: its wire protocol is still a
        # placeholder (ingestion/foresight/parser.py) - nothing has decoded a real
        # Falcon/Hawk packet yet - so it is only started when explicitly configured.
        self.foresight_listener: Optional[ForesightLiveListener] = None
        self.feed_host = feed_host or config.FEED_HOST
        self.feed_port = feed_port
        if feed_port:
            self.foresight_listener = ForesightLiveListener(self.feed_host, feed_port, self.dispatcher)
        else:
            logger.info("[FEED] No launch-monitor feed configured (set SIMCORE_FEED_PORT to enable); "
                        "rounds are tracked from the GSPro screen.")

        self.window_title = window_title
        self.monitor_index = monitor_index
        self.ocr_poll_interval = ocr_poll_interval
        self.ocr_listener: Optional[OCRHudListener] = None
        if ocr_enabled:
            self.ocr_listener = OCRHudListener(
                emit_callback=self.dispatcher.emit,
                poll_interval=ocr_poll_interval,
            )
        else:
            logger.info("[OCR] Disabled")

        self.publisher = LeaderboardPublisher()
        self.rounds = RoundManager(self.publisher)
        self.scorecard_watcher = ScorecardWatcher(self._on_final_card)

        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self.console_commands = console_commands
        self.started_at = datetime.now()
        self.capture_state = {
            "mode": "window" if window_title else "monitor",
            "target": window_title or str(monitor_index),
            "state": "starting" if ocr_enabled else "disabled",
            "last_frame_at": None,
        }

    # ------------------------------------------------------------------ running

    async def start(self) -> None:
        logger.info("Starting SimCore22 Engine Runtime...")

        tasks = [
            asyncio.create_task(self._engine_loop()),
            asyncio.create_task(self._status_loop()),
        ]
        if self.foresight_listener:
            tasks.append(asyncio.create_task(self.foresight_listener.start()))
        if self.ocr_listener:
            tasks.append(asyncio.create_task(self._ocr_capture_loop()))

        if self.console_commands:
            console.start_console_thread(self.handle_command, asyncio.get_running_loop())
        await asyncio.gather(*tasks)

    def shutdown(self) -> None:
        """
        The engine is being stopped (Ctrl+C, window closed): save any round in
        progress rather than losing it, and mark the engine as stopped.
        """
        try:
            self.rounds.finalize(reason="engine_stopped")
        finally:
            self._write_status(running=False)

    async def handle_command(self, command: str) -> str:
        """Run one console command and return the text to show. Also the hook for an admin portal."""
        return await console.run_command(self.rounds, command)

    # ---------------------------------------------------------- status heartbeat

    def status_snapshot(self, running: bool = True) -> dict:
        session = engine.get_session_state()
        players = [
            {
                "name": name,
                "holes": sum(1 for h in rs.holes.values() if h.gross_score is not None or h.strokes > 0),
                "current_hole": rs.current_hole,
            }
            for name, rs in session.players.items() if self.rounds.player_has_data(rs)
        ]
        return {
            "running": running,
            "pid": os.getpid(),
            "version": __version__,
            "started_at": self.started_at.astimezone().isoformat(timespec="seconds"),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "capture": dict(self.capture_state),
            "feed": {"configured": self.foresight_listener is not None,
                     "host": self.feed_host, "port": self.feed_port},
            "round": {
                "in_progress": bool(players),
                "players": players,
                "shots": len(self.rounds.shots),
                "idle_seconds": int(self.rounds.idle_for().total_seconds()),
                "idle_timeout_minutes": self.idle_timeout.total_seconds() / 60,
            },
        }

    def _write_status(self, running: bool = True) -> None:
        try:
            write_engine_status(self.status_snapshot(running))
        except Exception:
            logger.exception("Couldn't write the engine status file.")

    async def _status_loop(self) -> None:
        while True:
            self._write_status()
            await asyncio.sleep(STATUS_INTERVAL_S)

    # ------------------------------------------------------------ screen capture

    async def _ocr_capture_loop(self) -> None:
        """
        Owns screen capture and feeds frames to the OCR listener.

        - GSPro not open / minimized: wait quietly (one log line per streak).
        - Frames come back all black: GSPro is almost certainly in exclusive
          fullscreen. Log it once with the fix, and skip OCR on those frames.
        - Any other failure is logged and retried; it never kills the engine.
          `python -m simcore22.tools.bay_check` diagnoses all of the above.
        - Every good frame is also checked for the end-of-round scorecard.
        """
        # Imported here so this module still imports on non-Windows machines.
        from simcore22.engine.ocr.capture_windows import capture_game_frame
        from simcore22.engine.ocr.window_capture import GameWindowNotFound, looks_black

        target = f"window '{self.window_title}'" if self.window_title else f"monitor {self.monitor_index}"
        logger.info(f"Starting OCR capture loop on {target}")

        def set_state(state: str) -> None:
            self.capture_state["state"] = state

        waiting_logged = False
        black_logged = False
        while True:
            try:
                frame = capture_game_frame(self.window_title, self.monitor_index)
                self.capture_state["last_frame_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                if waiting_logged:
                    logger.info(f"[OCR] Found {target}; capturing.")
                    waiting_logged = False

                if looks_black(frame):
                    set_state("black_frames")
                    if not black_logged:
                        logger.warning(
                            "[OCR] Captured frames are black. GSPro is likely in exclusive "
                            "fullscreen - switch it to Windowed or Borderless in its display "
                            "settings. OCR is paused until real pixels arrive."
                        )
                        black_logged = True
                else:
                    black_logged = False
                    set_state("capturing")
                    await self.ocr_listener.process_frame(frame)
                    await self.scorecard_watcher.check(frame)
            except GameWindowNotFound as exc:
                set_state("waiting_for_window")
                if not waiting_logged:
                    logger.warning(f"[OCR] Waiting for {target}: {exc}")
                    waiting_logged = True
            except Exception:
                set_state("error")
                logger.exception("OCR capture loop iteration failed")
            await asyncio.sleep(self.ocr_poll_interval)

    async def _on_final_card(self, card: dict, frame) -> None:
        """GSPro's end-of-round scorecard appeared: keep the screenshot, finish the round."""
        card["image_file"] = self.rounds.save_scorecard_image(frame)
        self.rounds.finalize(reason="scorecard", card=card)

    # ----------------------------------------------------------------- event bus

    async def _engine_loop(self) -> None:
        logger.info("Engine loop running...")

        while True:
            event = await self.dispatcher.next_event(timeout=1.0)

            if event is None:
                # A quiet second: has the round been abandoned?
                if self.rounds.has_data() and self.rounds.idle_for() > self.idle_timeout:
                    self.rounds.finalize(reason="idle_timeout")
                continue

            self.rounds.touch()

            # One bad event must never take down a bay that runs all day.
            try:
                await self._route_event(event)
            except Exception:
                logger.exception("Failed to handle %s; continuing.", type(event).__name__)

    async def _route_event(self, event) -> None:
        if isinstance(event, ShotEvent):
            await self._handle_shot_event(event)

        elif isinstance(event, PlayerEvent):
            engine.handle_player_event(event)

        elif isinstance(event, HoleEvent):
            engine.handle_hole_event(event)

        elif isinstance(event, ScoreEvent):
            engine.handle_score_event(event)
            self.publisher.refresh()  # push the confirmed score, not just the last shot tally

        elif isinstance(event, RoundEndEvent):
            # "completed" = the source says the round finished; anything
            # else (e.g. "manual_end") is a stop before the end.
            reason = "round_end_event" if event.reason == "completed" else event.reason
            self.rounds.finalize(reason=reason)

    async def _handle_shot_event(self, shot: ShotEvent) -> None:
        try:
            engine.handle_shot_event(shot)
        except Exception as e:
            logger.error(f"Engine ingestion failed: {e}")
            return

        self.rounds.record_shot(shot)
        self.publisher.refresh()


def main() -> None:
    setup_logging()
    logger.info("=== SimCore22: Engine Runtime ===")

    runtime = EngineRuntime(feed_host=config.FEED_HOST, feed_port=config.FEED_PORT, ocr_enabled=True)
    try:
        asyncio.run(runtime.start())
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
