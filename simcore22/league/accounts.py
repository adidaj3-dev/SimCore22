# simcore22/league/accounts.py
"""Sign-up, log-in, sessions and profiles. Every function takes an open connection (see db.Database.connect)."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from simcore22.league import security
from simcore22.league.db import audit, bump_revision, now_iso
from simcore22.league.errors import Conflict, Forbidden, Invalid, NotAuthenticated, NotFound, TooManyAttempts

SESSION_DAYS = 14
MIN_PASSWORD = 8
MAX_PASSWORD = 200
LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILS_PER_EMAIL = 5
MAX_FAILS_PER_IP = 25
MIN_INDEX, MAX_INDEX = -8.0, 54.0

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GHIN = re.compile(r"^\d{7,8}$")
_DUMMY_HASH = security.hash_password("not-a-real-password")   # so an unknown email costs the same time as a wrong password


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def public(row: sqlite3.Row) -> Dict[str, Any]:
    """A user as the API shows them. The password hash never leaves this module."""
    return {
        "id": row["id"], "email": row["email"], "display_name": row["display_name"], "role": row["role"],
        "outdoor_index": row["outdoor_index"], "ghin_number": row["ghin_number"], "gspro_name": row["gspro_name"],
        "indoor_index": row["indoor_index"], "created_at": row["created_at"], "disabled": bool(row["disabled"]),
    }


# ----------------------------------------------------------------- validation

def clean_email(email: Any) -> str:
    email = str(email or "").strip().lower()
    if not _EMAIL.match(email) or len(email) > 200:
        raise Invalid("Enter a valid email address.")
    return email


def clean_name(name: Any) -> str:
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 60:
        raise Invalid("Enter your name (2-60 characters).")
    return name


def clean_password(password: Any) -> str:
    password = str(password or "")
    if len(password) < MIN_PASSWORD:
        raise Invalid(f"Use a password of at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise Invalid("That password is too long.")
    return password


def clean_ghin(ghin: Any) -> Optional[str]:
    digits = re.sub(r"[\s-]", "", str(ghin or ""))
    if not digits:
        return None
    if not _GHIN.match(digits):
        raise Invalid("A GHIN number is 7 or 8 digits. Leave it blank if you don't have one.")
    return digits


def clean_index(value: Any, label: str = "Handicap index") -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        # golfers write a better-than-scratch index as "+2.1"; internally that is -2.1
        number = -float(text[1:]) if text.startswith("+") else float(text)
    except (TypeError, ValueError):
        raise Invalid(f"{label} must be a number, like 14.2.") from None
    if not MIN_INDEX <= number <= MAX_INDEX:
        raise Invalid(f"{label} must be between {MIN_INDEX:g} and {MAX_INDEX:g}.")
    return round(number, 1)


def clean_gspro_name(value: Any) -> Optional[str]:
    value = " ".join(str(value or "").split())
    if len(value) > 60:
        raise Invalid("That GSPro name is too long.")
    return value or None


# ------------------------------------------------------------------- accounts

def count_users(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def has_admin(conn) -> bool:
    return conn.execute("SELECT 1 FROM users WHERE role='admin' AND disabled=0 LIMIT 1").fetchone() is not None


def create_user(conn, *, email, password, display_name, outdoor_index=None, ghin_number=None,
                gspro_name=None, role: str = "player") -> Dict[str, Any]:
    if role not in ("player", "admin"):
        raise Invalid("Unknown role.")
    email, name, password = clean_email(email), clean_name(display_name), clean_password(password)
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise Conflict("There is already an account with that email. Try logging in.")
    cur = conn.execute(
        "INSERT INTO users(email, display_name, password_hash, role, outdoor_index, ghin_number, gspro_name, indoor_index, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (email, name, security.hash_password(password), role, clean_index(outdoor_index, "Outdoor index"),
         clean_ghin(ghin_number), clean_gspro_name(gspro_name) or name, None, now_iso()),
    )
    user_id = cur.lastrowid
    # before any simulator rounds exist, the starting index is the player's own outdoor index
    row = get_row(conn, user_id)
    if row["outdoor_index"] is not None:
        conn.execute("UPDATE users SET indoor_index = outdoor_index WHERE id = ?", (user_id,))
        conn.execute(
            "INSERT INTO handicap_history(user_id, round_id, effective_at, index_value, rounds_counted, method, note)"
            " VALUES (?, NULL, ?, ?, 0, 'outdoor-start', 'Started from the outdoor index entered at sign-up')",
            (user_id, now_iso(), row["outdoor_index"]),
        )
    audit(conn, user_id, "account_created", f"role={role}")
    bump_revision(conn)
    return public(get_row(conn, user_id))


def get_row(conn, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFound("No such player.")
    return row


def get_user(conn, user_id: int) -> Dict[str, Any]:
    return public(get_row(conn, user_id))


def list_users(conn) -> list:
    return [public(r) for r in conn.execute("SELECT * FROM users ORDER BY display_name COLLATE NOCASE")]


def update_profile(conn, user_id: int, *, display_name=None, outdoor_index=None, ghin_number=None,
                   gspro_name=None, fields: Optional[set] = None) -> Dict[str, Any]:
    """Change only the fields named in `fields` (so a blank GHIN can mean 'remove it')."""
    row = get_row(conn, user_id)
    fields = fields or set()
    new = {
        "display_name": clean_name(display_name) if "display_name" in fields else row["display_name"],
        "outdoor_index": clean_index(outdoor_index, "Outdoor index") if "outdoor_index" in fields else row["outdoor_index"],
        "ghin_number": clean_ghin(ghin_number) if "ghin_number" in fields else row["ghin_number"],
        "gspro_name": clean_gspro_name(gspro_name) if "gspro_name" in fields else row["gspro_name"],
    }
    conn.execute(
        "UPDATE users SET display_name=?, outdoor_index=?, ghin_number=?, gspro_name=? WHERE id=?",
        (new["display_name"], new["outdoor_index"], new["ghin_number"], new["gspro_name"], user_id),
    )
    bump_revision(conn)
    return public(get_row(conn, user_id))


def change_password(conn, user_id: int, current: str, new: str) -> None:
    row = get_row(conn, user_id)
    if not security.verify_password(current or "", row["password_hash"]):
        raise Invalid("Your current password isn't right.")
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(clean_password(new)), user_id))
    audit(conn, user_id, "password_changed")


def admin_reset_password(conn, admin_id: int, user_id: int) -> str:
    """No email reset exists yet: an admin issues a temporary password in person. Ends the player's other sessions."""
    get_row(conn, user_id)
    temp = security.temporary_password()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(temp), user_id))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    audit(conn, admin_id, "password_reset", f"for user {user_id}")
    return temp


def set_role(conn, admin_id: int, user_id: int, role: str) -> Dict[str, Any]:
    if role not in ("player", "admin"):
        raise Invalid("Unknown role.")
    if user_id == admin_id and role != "admin":
        raise Invalid("You can't remove your own admin access.")
    get_row(conn, user_id)
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    audit(conn, admin_id, "role_changed", f"user {user_id} -> {role}")
    return get_user(conn, user_id)


def set_disabled(conn, admin_id: int, user_id: int, disabled: bool) -> Dict[str, Any]:
    if user_id == admin_id and disabled:
        raise Invalid("You can't disable your own account.")
    get_row(conn, user_id)
    conn.execute("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, user_id))
    if disabled:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    audit(conn, admin_id, "account_disabled" if disabled else "account_enabled", f"user {user_id}")
    bump_revision(conn)
    return get_user(conn, user_id)


# ------------------------------------------------------------------- sessions

def _recent_fails(conn, column: str, value: str) -> int:
    since = (datetime.now().astimezone() - LOGIN_WINDOW).isoformat(timespec="seconds")
    return conn.execute(
        f"SELECT COUNT(*) FROM login_attempts WHERE {column} = ? AND ok = 0 AND at >= ?", (value, since)
    ).fetchone()[0]


def login(conn, email: str, password: str, ip: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """(session token, user). Raises NotAuthenticated for a bad email/password and TooManyAttempts when throttled."""
    email = str(email or "").strip().lower()
    if _recent_fails(conn, "email", email) >= MAX_FAILS_PER_EMAIL or (ip and _recent_fails(conn, "ip", ip) >= MAX_FAILS_PER_IP):
        raise TooManyAttempts("Too many failed log-ins. Wait 15 minutes and try again, or ask the front desk to reset your password.")
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    ok = security.verify_password(str(password or ""), row["password_hash"] if row else _DUMMY_HASH)
    ok = bool(ok and row is not None)
    conn.execute("INSERT INTO login_attempts(email, ip, at, ok) VALUES (?, ?, ?, ?)", (email, ip, now_iso(), 1 if ok else 0))
    if not ok:
        conn.commit()      # a failed attempt must be remembered even though we're about to raise
        raise NotAuthenticated("That email and password don't match.")
    if row["disabled"]:
        raise Forbidden("This account has been disabled. Ask the front desk.")
    token, token_hash = security.new_session_token()
    now = datetime.now().astimezone()
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token_hash, row["id"], now.isoformat(timespec="seconds"), (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")),
    )
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso(), row["id"]))
    conn.execute("DELETE FROM login_attempts WHERE at < ?", ((now - timedelta(days=2)).isoformat(timespec="seconds"),))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(timespec="seconds"),))
    return token, public(row)


def user_for_token(conn, token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    row = conn.execute(
        "SELECT u.*, s.expires_at AS _expires FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (security.hash_token(token),),
    ).fetchone()
    if row is None or row["disabled"] or _parse(row["_expires"]) < datetime.now().astimezone():
        return None
    return public(row)


def logout(conn, token: Optional[str]) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.hash_token(token),))
