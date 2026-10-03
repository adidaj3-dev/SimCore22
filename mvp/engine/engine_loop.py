# mvp/engine/engine_loop.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from mvp.engine import config
from mvp.engine.logging_config import setup_logging
from mvp.engine.ingestion.dispatcher import EventDispatcher
from mvp.engine.ingestion.foresight.listener import ForesightLiveListener
from mvp.engine.ocr.ocr_listener import OCRHudListener
from mvp.engine.ocr.scorecard import read_scorecard_from_image

from mvp.engine.models.events import ShotEvent, PlayerEvent, HoleEvent, ScoreEvent
from mvp.engine import engine

from mvp.engine.analyzer.analyzer import analyze_round
from mvp.engine.leaderboard.leaderboard import Leaderboard
from mvp.engine.dashboard.live_dashboard import display_live_dashboard

from mvp.engine.handicap.handicap_engine import HandicapEngine
from mvp.engine.handicap.update_logic import should_update_handicap
from mvp.engine.models.league import LeagueConfig, LeagueState
from mvp.engine.models.schedule import ScheduleConfig
from mvp.engine.scheduling.classifier import classify_round_by_time

from mvp.engine.state_writer import (
    write_leaderboard_state,
    write_round_summary_state,
    write_admin_snapshot_state,
)

logger = logging.getLogger(__name__)

# Used only when a player has no handicap on record yet (first-ever round).
# Picked, not measured - tune once real league data exists.
DEFAULT_STARTING_INDEX = 18


class EngineRuntime:
    def __init__(
        self,
        foresight_host: str,
        foresight_port: int,
        ocr_enabled: bool = True,
        window_title: str = config.CAPTURE_WINDOW_TITLE,
        monitor_index: int = config.CAPTURE_MONITOR_INDEX,
        ocr_poll_interval: float = 1.0,
    ):
        self.dispatcher = EventDispatcher()

        # Ingestion
        # NOTE: the Foresight wire protocol here is still a placeholder (see
        # ingestion/foresight/parser.py) - nothing has decoded a real Falcon/Hawk
        # packet yet. Run mvp/tools/falcon_packet_decoder.py on the bay to
        # capture real packets, then fix the parser against them.
        self.foresight_listener = ForesightLiveListener(
            foresight_host, foresight_port, self.dispatcher
        )

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

        # Engine state
        self.leaderboard = Leaderboard()
        self.shots: list[ShotEvent] = []

        self.league_config = LeagueConfig(league_id="default_league")
        self.league_state = LeagueState(league_id="default_league")
        self.handicap_engine = HandicapEngine()
        self.schedule_config = ScheduleConfig()

        # Round completion tracking
        self.last_event_time = datetime.now()
        self.round_complete = False

    async def start(self) -> None:
        logger.info("Starting SimCore22 Engine Runtime...")

        tasks = [
            asyncio.create_task(self.foresight_listener.start()),
            asyncio.create_task(self._engine_loop()),
        ]

        if self.ocr_listener:
            tasks.append(asyncio.create_task(self._ocr_capture_loop()))

        await asyncio.gather(*tasks)

    async def _ocr_capture_loop(self) -> None:
        """
        Owns screen capture and feeds frames to the OCR listener.

        - GSPro not open / minimized: wait quietly (one log line per streak).
        - Frames come back all black: GSPro is almost certainly in exclusive
          fullscreen. Log it once with the fix, and skip OCR on those frames.
        - Any other failure is logged and retried; it never kills the engine.
          `python -m mvp.tools.bay_check` diagnoses all of the above.
        """
        # Imported here so this module still imports on non-Windows machines.
        from mvp.engine.ocr.capture_windows import capture_game_frame
        from mvp.engine.ocr.window_capture import GameWindowNotFound, looks_black

        target = f"window '{self.window_title}'" if self.window_title else f"monitor {self.monitor_index}"
        logger.info(f"Starting OCR capture loop on {target}")

        waiting_logged = False
        black_logged = False
        while True:
            try:
                frame = capture_game_frame(self.window_title, self.monitor_index)
                if waiting_logged:
                    logger.info(f"[OCR] Found {target}; capturing.")
                    waiting_logged = False

                if looks_black(frame):
                    if not black_logged:
                        logger.warning(
                            "[OCR] Captured frames are black. GSPro is likely in exclusive "
                            "fullscreen - switch it to Windowed or Borderless in its display "
                            "settings. OCR is paused until real pixels arrive."
                        )
                        black_logged = True
                else:
                    black_logged = False
                    await self.ocr_listener.process_frame(frame)
            except GameWindowNotFound as exc:
                if not waiting_logged:
                    logger.warning(f"[OCR] Waiting for {target}: {exc}")
                    waiting_logged = True
            except Exception:
                logger.exception("OCR capture loop iteration failed")
            await asyncio.sleep(self.ocr_poll_interval)

    async def _engine_loop(self) -> None:
        logger.info("Engine loop running...")

        while True:
            event = await self.dispatcher.next_event(timeout=1.0)

            # Check inactivity timeout
            if datetime.now() - self.last_event_time > timedelta(minutes=1):
                await self._finalize_round()
                continue

            if event is None:
                continue

            # Update last event time
            self.last_event_time = datetime.now()

            # Route event
            if isinstance(event, ShotEvent):
                await self._handle_shot_event(event)

            elif isinstance(event, PlayerEvent):
                engine.handle_player_event(event)

            elif isinstance(event, HoleEvent):
                engine.handle_hole_event(event)

            elif isinstance(event, ScoreEvent):
                engine.handle_score_event(event)
                self._refresh_leaderboard()  # push the confirmed score, not just the last shot tally
                await self._maybe_handle_round_completion(event)

    async def _handle_shot_event(self, shot: ShotEvent) -> None:
        try:
            engine.handle_shot_event(shot)
        except Exception as e:
            logger.error(f"Engine ingestion failed: {e}")
            return

        self.shots.append(shot)
        self._refresh_leaderboard()

    def _refresh_leaderboard(self) -> None:
        """
        Recompute standings from the current session state and push them out
        (console + state/leaderboard.json). Called after every shot AND after
        every confirmed score, so the last hole of a round shows the official
        score rather than a stale shot-count the instant it's recorded.
        """
        session_state = engine.get_session_state()
        self.leaderboard.update_from_session(session_state)

        standings = self.leaderboard.get_standings()
        display_live_dashboard(standings)

        players_json = []
        for row in standings:
            players_json.append({
                "name": row.player_name,
                "team": row.team_name,
                "thru": row.thru,
                "gross": row.gross_score,
                "net": row.net_score,
                "vs_par": row.gross_score - (row.thru * 4),  # assumes par 4; refine once course par is OCR'd live
                "points": 0,
                "points_needed": 36,
                "simcore_index": row.handicap_index,
                "outdoor_hcp": row.handicap_index,
            })

        write_leaderboard_state(
            course_name="Unknown",
            league_name="Default League",
            week=1,
            format_name="Stroke Play",
            players=players_json,
        )

    async def _maybe_handle_round_completion(self, score_event: ScoreEvent) -> None:
        player_name = score_event.player_name.strip()
        if not player_name:
            return

        # Check hole count
        session_state = engine.get_session_state()
        round_state = session_state.players.get(player_name)
        if not round_state:
            return

        holes_played = len(round_state.holes)

        if holes_played >= 9 or holes_played >= 18:
            await self._finalize_round()

        # Handicap update
        now = datetime.now()
        round_type = classify_round_by_time(now, self.schedule_config)

        if should_update_handicap(
            player_name,
            self.league_config,
            self.league_state,
            round_type,
        ):
            new_index = self.handicap_engine.update_player_handicap(
                player_name,
                session_state,
            )
            logger.info(f"[HANDICAP] Updated index for {player_name}: {new_index}")

    def _apply_scorecard_overrides(self, session_state) -> None:
        """
        At round end, OCR the GSPro scorecard screen and - only where it reads
        as internally consistent (see ScorecardData.verified) - use its printed
        scores in place of the live shot tally. The tally can drift (a missed
        or doubled shot detection); the printed scorecard is GSPro's own math.
        Safe to call even if no scorecard is on screen: it just logs and the
        shot-tallied scores stand.
        """
        try:
            from mvp.engine.ocr.capture_windows import capture_game_frame

            frame = capture_game_frame(self.window_title, self.monitor_index)
        except Exception:
            logger.info("[ROUND] Couldn't capture a frame for scorecard verification; using shot tally.")
            return

        card = read_scorecard_from_image(frame)
        if not card or not card.get("players"):
            logger.info("[ROUND] No scorecard on screen (or it didn't parse); using shot tally.")
            return

        for player_name, round_state in session_state.players.items():
            match = next(
                (p for p in card["players"] if p["name"].strip().lower() == player_name.strip().lower()),
                None,
            )
            if match is None or not match.get("verified"):
                logger.info(f"[ROUND] No verified scorecard row for {player_name}; using shot tally.")
                continue

            for hole_num, score in match["strokes"].items():
                hole_state = round_state.holes.setdefault(hole_num, engine.HoleState(hole_number=hole_num))
                hole_state.gross_score = score
                if hole_num in card.get("par", {}):
                    hole_state.par = card["par"][hole_num]

            logger.info(f"[ROUND] Applied verified scorecard for {player_name}: "
                        f"{len(match['strokes'])} holes, total {match['total']}")

    async def _finalize_round(self) -> None:
        if self.round_complete:
            return

        self.round_complete = True
        logger.info("[ROUND] Finalizing round...")

        session_state = engine.get_session_state()
        self._apply_scorecard_overrides(session_state)

        # Build scorecard + shots per player
        for player_name, round_state in session_state.players.items():
            scorecard = []
            for hole_num, hole in round_state.holes.items():
                scorecard.append({
                    "hole_number": hole_num,
                    "par": hole.par,
                    "score": hole.gross_score or hole.strokes,
                    "putts": hole.putts,
                    "fairway_hit": hole.fairway_hit,
                    "green_in_reg": hole.green_in_reg,
                    "proximity": hole.proximity,
                    "sand": hole.sand,
                    "up_and_down_attempt": hole.up_and_down_attempt,
                    "up_and_down_success": hole.up_and_down_success,
                })

            # Filter shots for this player (handle_shot_event stamps player_name, not "player")
            player_shots = [s for s in self.shots if s.metadata.get("player_name") == player_name]

            starting_index = round_state.handicap_index
            if starting_index is None:
                starting_index = DEFAULT_STARTING_INDEX
                logger.info(f"[ROUND] {player_name} has no handicap on record; "
                            f"using default starting index {DEFAULT_STARTING_INDEX}.")

            stats = analyze_round(
                shots=player_shots,
                scorecard=scorecard,
                simcore_index_before=starting_index,
                outdoor_handicap_start=starting_index,
                round_notes="Auto summary",
            )

            # Write summary JSON
            summary_payload = {
                "player": player_name,
                "course": "Unknown",
                "holes": len(scorecard),
                "gross": stats["gross_score"],
                "score_vs_par": stats["gross_vs_par"],
                "net": stats["net_score"],
                "simcore_index": stats["simcore_index_before"],
                "ball_flight": {
                    "avg_bs": stats["avg_ball_speed"],
                    "max_bs": stats["max_ball_speed"],
                    "avg_carry": stats["avg_carry"],
                },
                "scoring": {
                    "birdies": stats["birdies"],
                    "pars": stats["pars"],
                    "bogeys": stats["bogeys"],
                },
                "league": {
                    "stableford": stats["stableford_points"],
                    "quota": stats["quota_points"],
                    "points_target": 36,
                },
                "raw": stats,
            }

            write_round_summary_state(summary_payload)

            # Admin snapshot
            players_admin = [{
                "name": player_name,
                "outdoor_ghin": stats["outdoor_handicap_start"],
                "simcore_index_start": stats["simcore_index_before"],
                "simcore_index_current": stats["simcore_index_after"],
                "practice_score": None,
                "week_scores": [stats["gross_score"]],
                "total_individual_points": stats["points_earned"],
                "points_per_round": [stats["points_earned"]],
                "team_points": 0,
            }]

            teams = [{"name": "Team A", "points": 0}]

            write_admin_snapshot_state(
                league_name="Default League",
                week=1,
                players=players_admin,
                teams=teams,
            )

        logger.info("[ROUND] Summary + admin snapshot written.")
        logger.info("[ROUND] Ready for next round.")


def main() -> None:
    setup_logging()
    logger.info("=== SimCore22 MVP: Engine Runtime ===")

    runtime = EngineRuntime(
        foresight_host=config.GSPRO_TCP_HOST,
        foresight_port=config.GSPRO_TCP_PORT,
        ocr_enabled=True,
    )

    asyncio.run(runtime.start())


if __name__ == "__main__":
    main()
