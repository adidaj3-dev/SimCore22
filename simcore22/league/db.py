# simcore22/league/db.py
"""
The venue's own data - accounts, leagues, rounds typed in by players - in one SQLite file
(data/simcore22.db). SQLite needs no server and no installation, one file is trivial to back up,
and everything here is plain SQL, so moving to a hosted database later is a migration, not a rewrite.

`Database.connect()` is one transaction: it commits when the block finishes and rolls back if it
raises. `Database(":memory:")` is a throwaway database (tests and the demo).
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Union

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name  TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'player' CHECK (role IN ('player', 'admin')),
  outdoor_index REAL,            -- what the player says their outdoor handicap index is (NOT verified)
  ghin_number   TEXT,            -- the outdoor handicap ID the player gave (any outdoor service); self-reported, never verified
  gspro_name    TEXT,            -- the name this player uses inside GSPro; links screen-captured rounds to them
  indoor_index  REAL,            -- the current SimCore indoor index; rebuilt from their rounds (handicap.py)
  created_at    TEXT NOT NULL,
  last_login_at TEXT,
  disabled      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY,   -- only a hash of the cookie value is stored
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE login_attempts (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL,
  ip    TEXT,
  at    TEXT NOT NULL,
  ok    INTEGER NOT NULL
);

CREATE TABLE leagues (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  season       TEXT,
  holes        INTEGER NOT NULL DEFAULT 9 CHECK (holes IN (9, 18)),
  ranking      TEXT NOT NULL DEFAULT 'net' CHECK (ranking IN ('net', 'gross')),
  course_name  TEXT,
  default_pars TEXT,             -- JSON list, one par per hole
  join_code    TEXT NOT NULL UNIQUE,
  created_at   TEXT NOT NULL,
  archived     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE league_members (
  league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  team      TEXT,
  joined_at TEXT NOT NULL,
  PRIMARY KEY (league_id, user_id)
);

CREATE TABLE rounds (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  league_id     INTEGER REFERENCES leagues(id) ON DELETE SET NULL,
  course_name   TEXT,
  holes         INTEGER NOT NULL CHECK (holes IN (9, 18)),
  bay           TEXT,
  planned_pars  TEXT,            -- JSON list, shown on the entry screen before a hole is saved
  status        TEXT NOT NULL DEFAULT 'in_progress'
                CHECK (status IN ('in_progress', 'completed', 'ended_early', 'abandoned')),
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  updated_at    TEXT NOT NULL,
  index_at_start REAL,           -- the handicap index net scores in this round are based on
  differential  REAL,            -- set when the round counts toward the index
  entered_by    INTEGER REFERENCES users(id)
);
CREATE INDEX idx_rounds_user ON rounds(user_id, started_at);
CREATE INDEX idx_rounds_league ON rounds(league_id, started_at);

CREATE TABLE hole_scores (
  round_id   INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  hole       INTEGER NOT NULL CHECK (hole BETWEEN 1 AND 18),
  par        INTEGER NOT NULL CHECK (par BETWEEN 3 AND 6),
  strokes    INTEGER NOT NULL CHECK (strokes BETWEEN 1 AND 15),
  entered_at TEXT NOT NULL,
  PRIMARY KEY (round_id, hole)
);

CREATE TABLE handicap_history (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  round_id       INTEGER REFERENCES rounds(id) ON DELETE SET NULL,
  effective_at   TEXT NOT NULL,
  index_value    REAL,
  rounds_counted INTEGER NOT NULL,
  method         TEXT NOT NULL,
  note           TEXT
);
CREATE INDEX idx_handicap_user ON handicap_history(user_id, id);

CREATE TABLE audit_log (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  at      TEXT NOT NULL,
  user_id INTEGER,
  event   TEXT NOT NULL,
  detail  TEXT
);
"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def migrate(conn: sqlite3.Connection) -> None:
    """Bring a database up to SCHEMA_VERSION. Add numbered steps here as the schema grows."""
    exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
    version = int(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]) if exists else 0
    if version < 1:
        conn.executescript(_SCHEMA_V1)
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '1'), ('rev', '0')")
    # if version < 2: conn.executescript(...); conn.execute("UPDATE meta SET value='2' WHERE key='schema_version'")


def bump_revision(conn: sqlite3.Connection) -> None:
    """Note that data changed, so live screens (which watch this number) refresh."""
    conn.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'rev'")


def audit(conn: sqlite3.Connection, user_id, event: str, detail: str = "") -> None:
    """A permanent record of an admin-level action (score edit, password reset, role change)."""
    conn.execute("INSERT INTO audit_log(at, user_id, event, detail) VALUES (?, ?, ?, ?)", (now_iso(), user_id, event, detail))


class Database:
    def __init__(self, path: Union[str, Path] = ":memory:"):
        self.path = str(path)
        self._memory = self.path == ":memory:"
        self._lock = threading.RLock()
        if self._memory:
            # one connection shared behind a lock: the simplest correct way to share an in-memory db
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            migrate(conn)

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")      # readers don't block the writer
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if self._memory:
            with self._lock:
                try:
                    yield self._conn
                    self._conn.commit()
                except BaseException:
                    self._conn.rollback()
                    raise
            return
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def revision(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT value FROM meta WHERE key='rev'").fetchone()[0])
