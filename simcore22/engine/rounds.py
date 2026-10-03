# simcore22/engine/rounds.py
"""
The life of a round: when it ends, what is saved, what carries into the next one.

How a round ends (each way saves the data and stats; they differ in status):

  completed    GSPro shows its end-of-round scorecard (it appears when the chosen
               number of holes - 9, 18, any - is finished; never mid-round).
               Scores come from that card where it reads as consistent.
  ended_early  Someone types `end` in the engine console (or any source emits a
               RoundEndEvent), or the engine is stopped: the player stopped.
               Everything played so far is kept; the hole in progress is not
               counted.
  abandoned    Nothing happened for ROUND_IDLE_TIMEOUT_MINUTES. Saved as-is.
  snapshot     `save` in the console: a checkpoint of the round so far. The round
               keeps going; the final record shares its round_id.

Only `completed` rounds can update a handicap. After any round ends the session
is reset (handicaps carried over) so the next round starts clean and is logged.

Everything here is synchronous: a round is finished start-to-finish without the
engine loop interleaving events halfway through its results.
"""
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2

from simcore22.engine import config, engine, round_log
from simcore22.engine.analyzer.analyzer import analyze_round
from simcore22.engine.handicap.handicap_engine import HandicapEngine
from simcore22.engine.handicap.update_logic import should_update_handicap
from simcore22.engine.models.league import LeagueConfig, LeagueState
from simcore22.engine.models.schedule import ScheduleConfig
from simcore22.engine.publish import LeaderboardPublisher
from simcore22.engine.scheduling.classifier import classify_round_by_time
from simcore22.engine.state_writer import write_admin_snapshot_state, write_round_summary_state

logger = logging.getLogger(__name__)

# Used only when a player has no handicap on record yet (first-ever round).
# Picked, not measured - tune once real league data exists.
DEFAULT_STARTING_INDEX = 18

# Why a round ended -> what to call it in the log.
STATUS_BY_REASON = {
    "scorecard": "completed",
    "round_end_event": "completed",
    "manual_end": "ended_early",
    "engine_stopped": "ended_early",
    "idle_timeout": "abandoned",
}


class RoundManager:
    def __init__(
        self,
        publisher: LeaderboardPublisher,
        *,
        schedule_config: Optional[ScheduleConfig] = None,
        league_config: Optional[LeagueConfig] = None,
        league_state: Optional[LeagueState] = None,
        handicap_engine: Optional[HandicapEngine] = None,
    ):
        self.publisher = publisher
        self.schedule_config = schedule_config or ScheduleConfig()
        self.league_config = league_config or LeagueConfig(league_id="default_league")
        self.league_state = league_state or LeagueState(league_id="default_league")
        self.handicap_engine = handicap_engine or HandicapEngine()

        self.shots: list = []
        self.last_activity = datetime.now()
        self._round_id: Optional[str] = None  # shared by snapshots and the final record

    # ------------------------------------------------------------------ state

    def touch(self) -> None:
        """Note that something happened (resets the idle clock)."""
        self.last_activity = datetime.now()

    def idle_for(self) -> timedelta:
        return datetime.now() - self.last_activity

    def record_shot(self, shot) -> None:
        self.shots.append(shot)

    @staticmethod
    def player_has_data(round_state) -> bool:
        return any(h.gross_score is not None or h.strokes > 0 for h in round_state.holes.values())

    def has_data(self) -> bool:
        return any(self.player_has_data(rs) for rs in engine.get_session_state().players.values())

    def current_round_id(self) -> str:
        if self._round_id is None:
            self._round_id = uuid.uuid4().hex
        return self._round_id

    def reset(self) -> None:
        """Start the next round clean (handicaps and the current player carry over)."""
        engine.reset_session()
        self.shots.clear()
        self._round_id = None
        self.touch()

    def save_scorecard_image(self, frame) -> Optional[str]:
        """Keep the screenshot so the logged round can be checked against it."""
        if not config.SAVE_SCORECARD_IMAGES:
            return None
        try:
            folder = Path(round_log.DEFAULT_PATH).parent / "scorecards"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"scorecard_{datetime.now():%Y%m%d_%H%M%S}_{self.current_round_id()[:6]}.png"
            path = folder / name
            cv2.imwrite(str(path), frame)
            return str(path)
        except Exception:
            logger.exception("Couldn't save the scorecard image.")
            return None

    # -------------------------------------------------------- finishing a round

    def finalize(self, reason: str = "unknown", card: Optional[dict] = None) -> list:
        """
        End the round: apply the scorecard (if given), compute stats, update
        handicaps (completed league rounds only), log, write the state files,
        then reset for the next round. Returns [(player, holes_counted)].
        """
        status = STATUS_BY_REASON.get(reason, "ended_early")
        card = card or {}
        session_state = engine.get_session_state()
        results: list = []

        try:
            applied = self._apply_scorecard(session_state, card) if card else {}

            if not self.has_data():
                logger.info(f"Round end ({reason}) but nothing was recorded; nothing to save.")
                return results

            logger.info(f"Finalizing round (trigger: {reason}, status: {status})...")
            self.publisher.refresh()  # final standings incl. the verified scorecard scores

            round_id = self.current_round_id()
            round_type = classify_round_by_time(datetime.now(), self.schedule_config)
            course_name = card.get("course_name") or "Unknown"
            admin_players = []

            for player_name, round_state in list(session_state.players.items()):
                if not self.player_has_data(round_state):
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
                    logger.exception(f"Couldn't finish {player_name}'s round.")

            if admin_players:
                write_admin_snapshot_state(
                    league_name="Default League",
                    week=1,
                    players=admin_players,
                    teams=[{"name": "Team A", "points": 0}],
                )
            logger.info(f"Saved {len(results)} player round(s). Ready for the next round.")
            return results
        finally:
            # Always reset - even if something above failed, a stuck round
            # would swallow every round after it.
            self.reset()

    def snapshot(self) -> list:
        """Checkpoint the round so far to the log. Play continues; nothing resets."""
        session_state = engine.get_session_state()
        round_id = self.current_round_id()
        round_type = classify_round_by_time(datetime.now(), self.schedule_config)
        saved: list = []
        for player_name, round_state in list(session_state.players.items()):
            if not self.player_has_data(round_state):
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
                logger.exception(f"Couldn't snapshot {player_name}.")
        return saved

    # --------------------------------------------------------------- internals

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
                logger.info(f"Scorecard row for {row['name']} didn't add up; not trusting it.")
                continue

            round_state = engine.find_player(row["name"]) or engine.get_or_create_round_state(row["name"])
            for hole_num, score in row["strokes"].items():
                hole_state = round_state.holes.setdefault(hole_num, engine.HoleState(hole_number=hole_num))
                hole_state.gross_score = score
                if hole_num in card.get("par", {}):
                    hole_state.par = card["par"][hole_num]

            applied[round_state.player_name] = row
            logger.info(f"Applied verified scorecard for {round_state.player_name}: "
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
            logger.info(f"{player_name} has no handicap on record; "
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
            logger.info(f"Handicap updated for {player_name}: {old} -> {new}")
            return new
        except Exception:
            logger.exception(f"Couldn't update the handicap for {player_name}.")
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
            logger.exception("Couldn't write round log entry (scoring unaffected).")
