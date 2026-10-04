# simcore22/league/security.py
"""Password hashing and session tokens - standard library only, no extra dependencies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Tuple

# scrypt: deliberately slow and memory-hungry, so a stolen database can't be cracked cheaply.
_N, _R, _P, _LEN = 2 ** 14, 8, 1, 32


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_LEN, maxmem=64 * 1024 * 1024)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected), maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)   # constant time


def new_session_token() -> Tuple[str, str]:
    """(token to give the browser, hash to store). Only the hash is kept, so a leaked database can't be used to log in."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def temporary_password() -> str:
    """Easy to read out loud at a front desk: two words-ish chunks and digits, no look-alike characters."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(secrets.choice("23456789") for _ in range(2))
