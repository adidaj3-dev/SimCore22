# simcore22/engine/engine_loop.py
"""
Wires ingestion -> engine -> outputs, and owns the life of a round.

How a round ends (each way saves the data and stats; they differ in status):

  completed    GSPro shows its end-of-round scorecard (it appears when the chosen
               number of holes - 9, 18, any - is finished; never mid-round).
               Scores come from that card where it reads as consistent.
  ended_early  Someone types `end` in the engine console (or any source emits a
               RoundEndEvent): the player stopped. Everything played so far is
               kept; the hole in progress is not counted.
  abandoned    Nothing happened for ROUND_IDLE_TIMEOUT_MINUTES. Saved as-is.
  snapshot     `save` in the console: a checkpoint of the round so far. The round
               keeps going; the final record shares its round_id.

Only `completed` rounds can update a handicap. After any round ends the session
is reset (handicaps carried over) so the next round starts clean and is logged.
"""
import asyncio
import logging
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2

from simcore22.engine import config, round_log
from simcore22.engine.logging_config import setup_logging
from simcore22.engine.ingestion.dispatcher import EventDispatcher
from simcore22.engine.ingestion.foresight.listener import ForesightLiveListener
from simcore22.engine.ocr.ocr_listener import OCRHudListener
from simcore22.engine.ocr.scorecard import read_scorecard_from_image
from simcore22.engine.ocr.scorecard_reader import looks_like_scorecard_panel

from simcore22.engine.models.events import (
    ShotEvent, PlayerEvent, HoleEvent, ScoreEvent, RoundEndEvent,
)
from simcore22.engine import engine

from simcore22.engine.analyzer.analyzer import analyze_round
from simcore22.engine.leaderboard.leaderboard import Leaderboard
from simcore22.engine.dashboard.live_dashboard import display_live_dashboard

from simcore22.engine.handicap.handicap_engine import HandicapEngine
from simcore22.engine.handicap.update_logic import should_update_handicap
from simcore22.engine.models.league import LeagueConfig, LeagueState
from simcore22.engine.models.schedule import ScheduleConfig
from simcore22.engine.scheduling.classifier import classify_round_by_time

from simcore22.engine.state_writer import (
    write_leaderboard_state,
    write_round_summary_state,
    write_admin_snapshot_state,
)

logger = logging.getLogger(__name__)

# Used only when a player has no handicap on record yet (first-ever round).
# Picked, not measured - tune once real league data exists.
DEFAULT_STARTING_INDEX = 18

# Why a round ended -> what to call it in the log.
_STATUS_BY_REASON = {
    "scorecard": "completed",
    "round_end_event": "completed",
    "manual_end": "ended_early",
    "idle_timeout": "abandoned",
}

CONSOLE_HELP = """\
Engine commands (type one, press Enter):
  end     finish the round now and save it (use when a player quits early)
  save    checkpoint the round so far; play continues
  status  show who is playing and how far along they are
  help    show this list"""


class EngineRuntime:
    def __init__(
        self,
        foresight_host: str,
        foresight_port: int,
        ocr_enabled: bool = True,
        window_title: str = config.CAPTURE_WINDOW_TITLE,
        monitor_index: int = config.CAPTURE_MONITOR_INDEX,
        ocr_poll_interval: float = 1.0,
        idle_timeout_minutes: float = config.ROUND_IDLE_TIMEOUT_MINUTES,
        console_commands: bool = True,
    ):
        self.dispatcher = EventDispatcher()

        # Ingestion
        # NOTE: the Foresight wire protocol here is still a placeholder (see
        # ingestion/foresight/parser.py) - nothing has decoded a real Falcon/Hawk
        # packet yet. Run simcore22/tools/falcon_packet_decoder.py on the bay to
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

        # Round tracking
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self.console_commands = console_commands
        self.last_event_time = datetime.now()
        self._round_id: Optional[str] = None  # shared by snapshots and the final record

        # End-of-round scorecard detection (see _check_for_scorecard)
        self._card_handled = False       # this on-screen card was already processed
        self._card_present_polls = 0     # consecutive polls with a card-like panel
        self._card_absent_polls = 0      # consecutive polls without one (after handling)
        self._card_retry_after = 0.0     # monotonic time before re-reading a non-card

    # ------------------------------------------------------------------ running

    async def start(self) -> None:
        logger.info("Starting SimCore22 Engine Runtime...")

        tasks = [
            asyncio.create_task(self.foresight_listener.start()),
            asyncio.create_task(self._engine_loop()),
        ]

        if self.ocr_listener:
            tasks.append(asyncio.create_task(self._ocr_capture_loop()))

        self._start_console_commands(asyncio.get_running_loop())
        await asyncio.gather(*tasks)

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
                    await self._check_for_scorecard(frame)
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

            if event is None:
                # A quiet second: has the round been abandoned?
                if self._session_has_data() and datetime.now() - self.last_event_time > self.idle_timeout:
                    await self._finalize_round(reason="idle_timeout")
                continue

            self.last_event_time = datetime.now()

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
            self._refresh_leaderboard()  # push the confirmed score, not just the last shot tally

        elif isinstance(event, RoundEndEvent):
            # "completed" = the source says the round finished; anything
            # else (e.g. "manual_end") is a stop before the end.
            reason = "round_end_event" if event.reason == "completed" else event.reason
            await self._finalize_round(reason=reason)

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

    # ------------------------------------------------- end-of-round detection

    async def _check_for_scorecard(self, frame) -> None:
        """
        Called with every good frame. When GSPro's end-of-round scorecard is on
        screen, read it once and finish the round.

        Cheap test first (looks_like_scorecard_panel, milliseconds): only a big
        light panel in the middle of the screen is worth the ~5s full read, and
        it must be there on two polls in a row (the card may animate in). A
        panel that turns out not to be a scorecard (bright sky) is not re-read
        for a few seconds. The read runs in a worker thread so the engine keeps
        processing events. A scorecard WITHOUT the PLAY AGAIN! button is a
        mid-round view and is ignored. After a card is handled it is not read
        again until it has left the screen.
        """
        present = looks_like_scorecard_panel(frame)

        if self._card_handled:
            self._card_absent_polls = 0 if present else self._card_absent_polls + 1
            if self._card_absent_polls >= 3:
                self._card_handled = False
                self._card_present_polls = 0
            return

        if not present:
            self._card_present_polls = 0
            return

        self._card_present_polls += 1
        if self._card_present_polls < 2 or time.monotonic() < self._card_retry_after:
            return

        card = await asyncio.to_thread(read_scorecard_from_image, frame)
        if not card or not card.get("players"):
            self._card_retry_after = time.monotonic() + 5.0
            return

        self._card_handled = True
        self._card_absent_polls = 0
        if not card.get("round_complete"):
            logger.info("[ROUND] A scorecard is on screen without PLAY AGAIN! - "
                        "treating it as a mid-round view and ignoring it.")
            return

        card["image_file"] = self._save_scorecard_image(frame)
        logger.info("[ROUND] End-of-round scorecard detected.")
        await self._finalize_round(reason="scorecard", card=card)

    def _save_scorecard_image(self, frame) -> Optional[str]:
        """Keep the screenshot so the logged round can be checked against it."""
        if not config.SAVE_SCORECARD_IMAGES:
            return None
        try:
            folder = Path(round_log.DEFAULT_PATH).parent / "scorecards"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"scorecard_{datetime.now():%Y%m%d_%H%M%S}_{self._current_round_id()[:6]}.png"
            path = folder / name
            cv2.imwrite(str(path), frame)
            return str(path)
        except Exception:
            logger.exception("[ROUND] Couldn't save the scorecard image.")
            return None

    # ------------------------------------------------------------ round state

    def _current_round_id(self) -> str:
        if self._round_id is None:
            self._round_id = uuid.uuid4().hex
        return self._round_id

    @staticmethod
    def _player_has_data(round_state) -> bool:
        return any(h.gross_score is not None or h.strokes > 0 for h in round_state.holes.values())

    def _session_has_data(self) -> bool:
        return any(self._player_has_data(rs) for rs in engine.get_session_state().players.values())

    def _reset_round(self) -> None:
        """Start the next round clean (handicaps and the current player carry over)."""
        engine.reset_session()
        self.shots.clear()
        self._round_id = None
        self.last_event_time = datetime.now()

    def _apply_scorecard(self, session_state, card: dict) -> dict:
        """
        Use the GSPro scorecard's printed scores - only for rows that read as
        internally consistent (ScorecardData.verified) - in place of the live
        shot tally, which can miss or double-count a shot. A verified player who
        isn't in the session yet (the HUD tracking missed them) is added from
        the card, so a round is still recorded if live tracking never worked.

        Returns {player_name: scorecard_row} for the players it applied.
        """
        applied: dict = {}
        for row in card.get("players", []):
            if not row.get("verified"):
                logger.info(f"[ROUND] Scorecard row for {row['name']} didn't add up; not trusting it.")
                continue

            round_state = engine.find_player(row["name"]) or engine.get_or_create_round_state(row["name"])
            for hole_num, score in row["strokes"].items():
                hole_state = round_state.holes.setdefault(hole_num, engine.HoleState(hole_number=hole_num))
                hole_state.gross_score = score
                if hole_num in card.get("par", {}):
                    hole_state.par = card["par"][hole_num]

            applied[round_state.player_name] = row
            logger.info(f"[ROUND] Applied verified scorecard for {round_state.player_name}: "
                        f"{len(row['strokes'])} holes, total {row['gross']}")
        return applied

    def _compute_player(self, player_name: str, round_state, status: str) -> dict:
        """Hole-by-hole record, shots and stats for one player, as of now."""
        holes, scorecard = [], []
        for hole_num, hole in sorted(round_state.holes.items()):
            if hole.gross_score is None and hole.strokes <= 0:
                continue  # seen on the HUD but nothing happened on it
            # Quitting mid-hole must not count that hole as a score
            in_progress = (
                hole.gross_score is None and status != "completed" and hole_num == round_state.current_hole
            )
            par_assumed = hole.par is None
            par = 4 if par_assumed else hole.par  # unknown par: assume 4 (flagged in the log)
            score = hole.gross_score if hole.gross_score is not None else hole.strokes
            holes.append({
                "hole": hole_num, "par": hole.par, "par_assumed": par_assumed,
                "score_used": score, "gross_score": hole.gross_score, "shot_tally": hole.strokes,
                "counted": not in_progress,
            })
            if not in_progress:
                scorecard.append({
                    "hole_number": hole_num, "par": par, "score": score,
                    "putts": hole.putts, "fairway_hit": hole.fairway_hit,
                    "green_in_reg": hole.green_in_reg, "proximity": hole.proximity,
                    "sand": hole.sand, "up_and_down_attempt": hole.up_and_down_attempt,
                    "up_and_down_success": hole.up_and_down_success,
                })

        # handle_shot_event stamps metadata["player_name"]
        player_shots = [s for s in self.shots if s.metadata.get("player_name") == player_name]

        starting_index = round_state.handicap_index
        was_default = starting_index is None
        if was_default:
            starting_index = DEFAULT_STARTING_INDEX
            logger.info(f"[ROUND] {player_name} has no handicap on record; "
                        f"using default starting index {DEFAULT_STARTING_INDEX}.")

        stats = analyze_round(
            shots=player_shots,
            scorecard=scorecard,
            simcore_index_before=starting_index,
            outdoor_handicap_start=starting_index,
            round_notes=f"Auto summary ({status})",
        )
        return {
            "holes": holes, "holes_counted": len(scorecard), "shots": player_shots,
            "starting_index": starting_index, "handicap_was_default": was_default, "stats": stats,
        }

    def _update_handicap(self, player_name: str, session_state, stats: dict) -> Optional[int]:
        """
        Count this league round and, if the league's schedule says it's time,
        recompute the player's handicap. Never raises - a handicap problem must
        not stop the round being saved.

        NOTE: nothing configures leagues yet (schedule windows, round numbers),
        so in practice this only runs once those are set up.
        """
        try:
            self.league_state.mark_round_completed(player_name)
            if not should_update_handicap(player_name, self.league_config, self.league_state, "league"):
                return None
            round_state = session_state.players[player_name]
            if round_state.handicap_index is None:  # first league round: start from the default
                round_state.handicap_index = DEFAULT_STARTING_INDEX
            old = round_state.handicap_index
            new = self.handicap_engine.update_player_handicap(player_name, session_state)
            stats["simcore_index_after"] = new
            stats["simcore_index_delta"] = float(new - old)
            logger.info(f"[HANDICAP] Updated index for {player_name}: {old} -> {new}")
            return new
        except Exception:
            logger.exception(f"[HANDICAP] Couldn't update the handicap for {player_name}.")
            return None

    def _log_round(
        self,
        *,
        round_id: str,
        reason: str,
        status: str,
        round_type: str,
        player_name: str,
        course_name: str,
        computed: dict,
        card: dict,
        card_row: Optional[dict],
        handicap_after: Optional[int],
    ) -> None:
        """Append this player's round to data/rounds.jsonl. Never raises."""
        try:
            round_log.append_round({
                "round_id": round_id,
                "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                # completed | ended_early | abandoned | snapshot. A snapshot is a
                # checkpoint: the final record for the round has the same round_id.
                "round_status": status,
                "finalize_reason": reason,
                "round_type": round_type,
                "player": player_name,
                "course": course_name,
                "holes_played": computed["holes_counted"],
                # Where the scores came from: GSPro's own verified scorecard, or
                # our count of shots (which can miss or double-count a shot).
                "score_source": "scorecard_ocr_verified" if card_row else "shot_tally",
                "handicap_index_used": computed["starting_index"],
                "handicap_was_default": computed["handicap_was_default"],
                "handicap_index_after": handicap_after,
                "hole_scores": computed["holes"],
                "stats": computed["stats"],
                "shot_devices": sorted({s.source_device for s in computed["shots"]}),
                "shots": computed["shots"],
                "scorecard_ocr": {
                    "image_file": card.get("image_file"),
                    "course_name": card.get("course_name"),
                    "holes_on_card": card.get("holes_on_card"),
                    "round_complete": card.get("round_complete"),
                    "par": card.get("par"),
                    "stroke_index": card.get("stroke_index"),
                    "players_on_card": [p["name"] for p in card.get("players", [])],
                    "matched_row": card_row,
                },
            })
        except Exception:
            logger.exception("[ROUND] Couldn't write round log entry (scoring unaffected).")

    # -------------------------------------------------------- finishing a round

    async def _finalize_round(self, reason: str = "unknown", card: Optional[dict] = None) -> list:
        """
        End the round: apply the scorecard (if given), compute stats, update
        handicaps (completed league rounds only), log, write the state files,
        then reset for the next round. Returns [(player, holes_counted)].

        Contains no `await`, so it runs start-to-finish without the engine loop
        interleaving events halfway through a round's results.
        """
        status = _STATUS_BY_REASON.get(reason, "ended_early")
        card = card or {}
        session_state = engine.get_session_state()
        results: list = []

        try:
            applied = self._apply_scorecard(session_state, card) if card else {}

            if not self._session_has_data():
                logger.info(f"[ROUND] Round end ({reason}) but nothing was recorded; nothing to save.")
                return results

            logger.info(f"[ROUND] Finalizing round (trigger: {reason}, status: {status})...")
            self._refresh_leaderboard()  # final standings incl. the verified scorecard scores

            round_id = self._current_round_id()
            round_type = classify_round_by_time(datetime.now(), self.schedule_config)
            course_name = card.get("course_name") or "Unknown"
            admin_players = []

            for player_name, round_state in list(session_state.players.items()):
                if not self._player_has_data(round_state):
                    continue
                try:
                    computed = self._compute_player(player_name, round_state, status)
                    stats = computed["stats"]

                    handicap_after = None
                    if status == "completed" and round_type == "league":
                        handicap_after = self._update_handicap(player_name, session_state, stats)

                    self._log_round(
                        round_id=round_id, reason=reason, status=status, round_type=round_type,
                        player_name=player_name, course_name=course_name, computed=computed,
                        card=card, card_row=applied.get(player_name), handicap_after=handicap_after,
                    )

                    write_round_summary_state({
                        "player": player_name,
                        "course": course_name,
                        "holes": computed["holes_counted"],
                        "gross": stats["gross_score"],
                        "score_vs_par": stats["gross_vs_par"],
                        "net": stats["net_score"],
                        "simcore_index": stats["simcore_index_before"],
                        "round_status": status,
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
                    })

                    admin_players.append({
                        "name": player_name,
                        "outdoor_ghin": stats["outdoor_handicap_start"],
                        "simcore_index_start": stats["simcore_index_before"],
                        "simcore_index_current": stats["simcore_index_after"],
                        "practice_score": None,
                        "week_scores": [stats["gross_score"]],
                        "total_individual_points": stats["points_earned"],
                        "points_per_round": [stats["points_earned"]],
                        "team_points": 0,
                    })
                    results.append((player_name, computed["holes_counted"]))
                except Exception:
                    logger.exception(f"[ROUND] Couldn't finish {player_name}'s round.")

            if admin_players:
                write_admin_snapshot_state(
                    league_name="Default League",
                    week=1,
                    players=admin_players,
                    teams=[{"name": "Team A", "points": 0}],
                )
            logger.info(f"[ROUND] Saved {len(results)} player round(s). Ready for the next round.")
            return results
        finally:
            # Always reset - even if something above failed, a stuck round
            # would swallow every round after it.
            self._reset_round()

    def _save_round_snapshot(self) -> list:
        """Checkpoint the round so far to the log. Play continues; nothing resets."""
        session_state = engine.get_session_state()
        round_id = self._current_round_id()
        round_type = classify_round_by_time(datetime.now(), self.schedule_config)
        saved: list = []
        for player_name, round_state in list(session_state.players.items()):
            if not self._player_has_data(round_state):
                continue
            try:
                computed = self._compute_player(player_name, round_state, "snapshot")
                self._log_round(
                    round_id=round_id, reason="manual_save", status="snapshot", round_type=round_type,
                    player_name=player_name, course_name="Unknown", computed=computed,
                    card={}, card_row=None, handicap_after=None,
                )
                saved.append((player_name, computed["holes_counted"]))
            except Exception:
                logger.exception(f"[ROUND] Couldn't snapshot {player_name}.")
        return saved

    # --------------------------------------------------------- console commands

    async def handle_command(self, command: str) -> str:
        """Run one console command; returns the text to show. (Also usable by a future admin portal.)"""
        cmd = command.strip().lower()

        if cmd in ("end", "e"):
            if not self._session_has_data():
                return "No round in progress - nothing to end."
            results = await self._finalize_round(reason="manual_end")
            who = ", ".join(f"{name} ({holes} holes)" for name, holes in results)
            return f"Round ended and saved: {who or 'nothing to save'}."

        if cmd in ("save", "s"):
            saved = self._save_round_snapshot()
            if not saved:
                return "No round in progress - nothing to save."
            who = ", ".join(f"{name} ({holes} holes)" for name, holes in saved)
            return f"Checkpoint saved: {who}. The round continues."

        if cmd == "status":
            session = engine.get_session_state()
            players = [
                f"{name}: {sum(1 for h in rs.holes.values() if h.gross_score is not None or h.strokes > 0)} holes"
                for name, rs in session.players.items() if self._player_has_data(rs)
            ]
            if not players:
                return "No round in progress."
            idle = int((datetime.now() - self.last_event_time).total_seconds() // 60)
            return f"Round in progress - {'; '.join(players)}. {len(self.shots)} shots. Idle {idle} min."

        if cmd in ("help", "?"):
            return CONSOLE_HELP
        return f"Unknown command '{command}'. Type help."

    def _start_console_commands(self, loop: asyncio.AbstractEventLoop) -> None:
        """Read commands from the console in a background thread (only if one is attached)."""
        if not self.console_commands or not sys.stdin or not sys.stdin.isatty():
            return

        def worker() -> None:
            print(CONSOLE_HELP)
            for line in sys.stdin:
                command = line.strip()
                if not command:
                    continue
                future = asyncio.run_coroutine_threadsafe(self.handle_command(command), loop)
                try:
                    print(future.result(timeout=60))
                except Exception as exc:
                    print(f"Command failed: {exc}")

        threading.Thread(target=worker, name="simcore-console", daemon=True).start()


def main() -> None:
    setup_logging()
    logger.info("=== SimCore22: Engine Runtime ===")

    runtime = EngineRuntime(
        foresight_host=config.GSPRO_TCP_HOST,
        foresight_port=config.GSPRO_TCP_PORT,
        ocr_enabled=True,
    )

    asyncio.run(runtime.start())


if __name__ == "__main__":
    main()
