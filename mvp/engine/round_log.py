# mvp/engine/round_log.py
"""
Append-only log of every finished round: data/rounds.jsonl, one JSON object per
line, one line per player per round.

This is deliberately NOT a database. It exists so that bay-test rounds survive
restarts (state/*.json is overwritten by the next round) and so the real
fields we capture can drive the schema when a database is built later.

Rules the file keeps:
  * Lines are only ever appended, never rewritten.
  * Each line is complete JSON, so a crash can at worst leave one truncated
    LAST line; read_rounds() skips it and keeps everything before it.
  * `schema_version` is on every line so old lines stay interpretable if the
    fields change.
Treat it as private: it holds player names and scores (data/ is git-ignored).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "rounds.jsonl"


def _json_default(obj: Any) -> Any:
    """Make dataclasses, datetimes, bytes and odd types serializable."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=str)
    if hasattr(obj, "item"):  # numpy scalar
        return obj.item()
    return str(obj)


def append_round(record: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Append one round record as a single line. Returns the file written."""
    target = Path(path) if path is not None else DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "schema_version": SCHEMA_VERSION,
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **record,
    }
    line = json.dumps(entry, default=_json_default, separators=(",", ":"))

    # One write of the whole line, flushed to disk, so a power cut can't
    # leave a half-line in the middle of the file.
    with open(target, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return target


def read_rounds(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """All readable round records, oldest first. Skips (and reports) bad lines."""
    source = Path(path) if path is not None else DEFAULT_PATH
    if not source.exists():
        return []

    rounds: List[Dict[str, Any]] = []
    with open(source, "r", encoding="utf-8") as f:
        for number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rounds.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping unreadable line %d in %s (truncated write?)", number, source)
    return rounds
