# simcore22/league/demo_seed.py
"""
A fictional venue in an in-memory database, so the player app and admin portal can be shown
(and tried by hand) without a bay or real accounts.

It reuses the demo league the engine-side screens already show: the same sixteen made-up
players, six past league nights entered "by hand" (a few holes deliberately differ from what the
fake screen capture read, so the accuracy page has something to say), and tonight's round,
which advances by itself as the demo clock moves - through the same code a real player's hole
entry uses.
"""
from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional

from simcore22.league import accounts, leagues, rounds
from simcore22.league.db import Database
from simcore22.league.errors import Conflict
from simcore22.web import demo as demo_data

DEMO_PASSWORD = "demo-password"
DEMO_ADMIN_EMAIL = "admin@demo.simcore22.test"
SLIP_RATE = 0.05          # share of past holes whose hand-entered score differs from the "captured" one


def player_email(name: str) -> str:
    return name.lower().replace(" ", ".") + "@demo.simcore22.test"


# The demo players you can log in as. Tonight's round plays itself out for everyone EXCEPT these,
# so whoever logs in as one of them enters their own holes without the demo writing over them.
LOGIN_PLAYERS = [name for name, _, _ in demo_data.PLAYERS[:4]]


def demo_accounts() -> Dict[str, object]:
    """What the demo log-in page offers (these are fictional accounts that exist only in the demo)."""
    return {"password": DEMO_PASSWORD, "admin": {"email": DEMO_ADMIN_EMAIL, "name": "Demo Manager"},
            "players": [{"email": player_email(n), "name": n} for n in LOGIN_PLAYERS]}


class DemoVenue:
    def __init__(self, engine_demo: Optional[demo_data.DemoLeague] = None):
        self.engine = engine_demo or demo_data.DemoLeague()
        self.db = Database(":memory:")
        self._lock = threading.Lock()
        self._tonight: Dict[str, int] = {}          # player name -> tonight's round id
        self._users: Dict[str, int] = {}
        self._admin: Dict[str, object] = {}
        self._league_id = 0
        with self.db.connect() as conn:
            self._seed(conn)

    # ------------------------------------------------------------------ seeding

    def _seed(self, conn) -> None:
        self._admin = accounts.create_user(conn, email=DEMO_ADMIN_EMAIL, password=DEMO_PASSWORD, display_name="Demo Manager", role="admin")
        pars = demo_data.COURSES[demo_data.TONIGHT_COURSE]
        league = leagues.create(conn, self._admin["id"], name=demo_data.LEAGUE_NAME, season="Fall", holes=demo_data.HOLES,
                                ranking="net", course_name=demo_data.TONIGHT_COURSE, pars=pars)
        self._league_id = league["id"]
        for name, team, hcp in demo_data.PLAYERS:
            user = accounts.create_user(conn, email=player_email(name), password=DEMO_PASSWORD, display_name=name,
                                        outdoor_index=hcp, gspro_name=name)
            self._users[name] = user["id"]
            leagues.add_member(conn, self._admin["id"], league["id"], user["id"])
            leagues.set_team(conn, self._admin["id"], league["id"], user["id"], team)

        rng = random.Random(22)
        nights = [r for r in self.engine.rounds() if r.get("round_type") == "league" and r.get("round_status") in ("completed", "ended_early")]
        # walk-in and practice rounds: most were typed in as casual rounds, some never were
        casual = [r for r in self.engine.rounds() if r.get("round_type") != "league" and r.get("round_status") == "completed"]
        everything = [(r, True) for r in nights] + [(r, False) for r in casual if rng.random() < 0.6]
        for record, in_league in sorted(everything, key=lambda item: item[0]["finished_at"]):
            if in_league and rng.random() < 0.03:
                continue                                # nobody typed this one in
            self._enter_past_round(conn, rng, record, in_league)

        # the accounts were "created" before the first round they typed in
        opened = (datetime.now().astimezone() - timedelta(days=60)).isoformat(timespec="seconds")
        conn.execute("UPDATE users SET created_at = ?", (opened,))
        conn.execute("UPDATE handicap_history SET effective_at = ? WHERE method = 'outdoor-start'", (opened,))
        for user_id in self._users.values():
            rounds.recompute_handicap(conn, user_id)

    def _enter_past_round(self, conn, rng: random.Random, record: dict, in_league: bool) -> None:
        user_id = self._users[record["player"]]
        admin = {"id": self._admin["id"], "role": "admin"}
        pars = [h["par"] for h in record["hole_scores"]]
        full_pars = demo_data.COURSES.get(record["course"], pars) if in_league else pars
        if in_league:
            r = rounds.start(conn, admin, user_id=user_id, league_id=self._league_id, course_name=record["course"], pars=full_pars)
        else:
            r = rounds.start(conn, admin, user_id=user_id, holes=len(full_pars), course_name=record["course"], pars=full_pars)
        for h in record["hole_scores"]:
            strokes = h["score_used"]
            if rng.random() < SLIP_RATE:
                strokes = max(1, strokes + rng.choice([-1, 1]))
            rounds.save_hole(conn, admin, r["id"], h["hole"], strokes)
        if record["round_status"] == "ended_early":
            rounds.finish(conn, admin, r["id"])
        finished = datetime.fromisoformat(record["finished_at"]) + timedelta(seconds=rng.randint(5, 90))
        conn.execute("UPDATE rounds SET started_at = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                     ((finished - timedelta(minutes=48)).isoformat(timespec="seconds"), finished.isoformat(timespec="seconds"),
                      finished.isoformat(timespec="seconds"), r["id"]))

    # ------------------------------------------------------------ tonight, live

    def sync(self) -> None:
        """Move tonight's rounds to where the demo clock says everyone is (and start over when the night loops)."""
        with self._lock, self.db.connect() as conn:
            admin = {"id": self._admin["id"], "role": "admin"}
            position = self.engine._position()
            changed = False
            for name, (_team, _hcp, scores, ends) in self.engine._tonight.items():
                if name in LOGIN_PLAYERS:
                    continue
                target = sum(1 for end in ends if end <= position)
                round_id = self._tonight.get(name)
                if round_id and conn.execute("SELECT 1 FROM rounds WHERE id = ?", (round_id,)).fetchone() is None:
                    self._tonight.pop(name)             # an admin deleted it while trying the demo
                    round_id = None
                have =conn.execute("SELECT COUNT(*) FROM hole_scores WHERE round_id = ?", (round_id,)).fetchone()[0] if round_id else 0
                if round_id and target < have:          # the demo night looped around
                    rounds.delete(conn, admin, round_id)
                    self._tonight.pop(name)
                    round_id, have, changed = None, 0, True
                if target == 0:
                    continue
                if round_id is None:
                    try:
                        started = rounds.start(conn, admin, user_id=self._users[name], league_id=self._league_id)
                    except Conflict:
                        continue                        # someone trying the demo is playing as this player: leave their round alone
                    round_id = self._tonight[name] = started["id"]
                for hole in range(have + 1, target + 1):
                    rounds.save_hole(conn, admin, round_id, hole, scores[hole - 1])
                    changed = True
            if changed:
                conn.commit()

    @property
    def league_id(self) -> int:
        return self._league_id
