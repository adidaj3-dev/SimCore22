# simcore22/web/auth.py
"""
Who is making this request? Cookie handling and the dependencies the API routes use.

* The session cookie is HttpOnly (page scripts can't read it), SameSite=Lax, and Secure whenever
  the request came in over https.
* Every state-changing request must carry `X-Requested-With: SimCore22`. A web page on another
  site can't add that header without our permission, which is what stops cross-site request
  forgery on top of SameSite.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request, Response

from simcore22.league import accounts
from simcore22.league.accounts import SESSION_DAYS
from simcore22.league.errors import Forbidden, NotAuthenticated

COOKIE = "sc22_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "SimCore22"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def is_local(request: Request) -> bool:
    hosts = getattr(request.app.state, "local_hosts", LOOPBACK)
    return client_ip(request) in hosts


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def check_csrf(request: Request) -> None:
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise Forbidden("Missing request header - reload the page and try again.")


def current_user(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with request.app.state.db.connect() as conn:
        return accounts.user_for_token(conn, token)


def require_user(request: Request) -> Dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise NotAuthenticated("Log in to continue.")
    return user


def require_admin(request: Request) -> Dict[str, Any]:
    user = require_user(request)
    if user["role"] != "admin":
        raise Forbidden("That needs a venue admin.")
    return user
