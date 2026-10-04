# simcore22/web/league_api.py
"""
The account / league / hand-entered-round API (everything under /api that needs the database).

Who may do what:
  anyone         sign up, log in, see the public league list and a league's live board (bay TVs)
  a player       their own profile, rounds and leagues; join a league with its code
  a venue admin  everything, including entering or correcting any player's round
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

from simcore22.league import accounts, accuracy, leagues, rounds, standings
from simcore22.league.db import audit
from simcore22.league.demo_seed import demo_accounts
from simcore22.league.errors import Forbidden, NotFound
from simcore22.web import auth, data


# ------------------------------------------------------------------ request bodies

class SignupBody(BaseModel):
    email: str
    password: str
    display_name: str
    outdoor_index: Optional[str] = None
    ghin_number: Optional[str] = None
    gspro_name: Optional[str] = None
    join_code: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


class SetupBody(BaseModel):
    email: str
    password: str
    display_name: str


class ProfileBody(BaseModel):
    display_name: Optional[str] = None
    outdoor_index: Optional[str] = None
    ghin_number: Optional[str] = None
    gspro_name: Optional[str] = None


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


class StartRoundBody(BaseModel):
    league_id: Optional[int] = None
    user_id: Optional[int] = None
    holes: Optional[int] = None
    bay: Optional[str] = None
    course_name: Optional[str] = None
    pars: Optional[List[int]] = None


class HoleBody(BaseModel):
    strokes: int
    par: Optional[int] = None


class LeagueBody(BaseModel):
    name: Optional[str] = None
    season: Optional[str] = None
    holes: Optional[int] = None
    ranking: Optional[str] = None
    course_name: Optional[str] = None
    pars: Optional[List[int]] = None
    archived: Optional[bool] = None


class JoinBody(BaseModel):
    code: str


class MemberBody(BaseModel):
    user_id: int


class TeamBody(BaseModel):
    team: Optional[str] = None


class RoleBody(BaseModel):
    role: str


class DisabledBody(BaseModel):
    disabled: bool


def _fields(body: BaseModel) -> Dict[str, Any]:
    return {k: getattr(body, k) for k in body.model_fields_set}


def build_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(auth.check_csrf)])

    def db(request: Request):
        return request.app.state.db

    def sync_demo(request: Request) -> None:
        demo = request.app.state.demo_venue
        if demo is not None:
            demo.sync()

    # =================================================================== session

    @router.get("/api/session", tags=["accounts"])
    def session(request: Request):
        """Who is logged in, whether first-time setup is needed, and (in demo mode) the demo accounts."""
        user = auth.current_user(request)
        with db(request).connect() as conn:
            needs_setup = not accounts.has_admin(conn)
        demo = request.app.state.demo_venue
        return {"user": user, "needs_setup": needs_setup and demo is None, "can_setup": auth.is_local(request),
                "demo": demo_accounts() if demo is not None else None}

    @router.post("/api/auth/setup", tags=["accounts"])
    def setup(body: SetupBody, request: Request, response: Response):
        """Create the first venue admin. Only possible while there is no admin, and only from this PC."""
        if not auth.is_local(request):
            raise Forbidden("First-time setup has to be done on the venue PC itself.")
        with db(request).connect() as conn:
            if accounts.has_admin(conn):
                raise Forbidden("This venue already has an admin.")
            user = accounts.create_user(conn, email=body.email, password=body.password, display_name=body.display_name, role="admin")
            token, _ = accounts.login(conn, body.email, body.password, auth.client_ip(request))
        auth.set_session_cookie(request, response, token)
        return {"user": user}

    @router.post("/api/auth/signup", tags=["accounts"])
    def signup(body: SignupBody, request: Request, response: Response):
        """Make a player account (outdoor handicap ID and index are self-reported). A league join code is optional."""
        with db(request).connect() as conn:
            code = (body.join_code or "").strip()
            if code and conn.execute("SELECT 1 FROM leagues WHERE join_code = ? AND archived = 0", (code.upper(),)).fetchone() is None:
                raise NotFound("That join code doesn't match a league. Check it, or leave it blank and join later.")
            user = accounts.create_user(conn, email=body.email, password=body.password, display_name=body.display_name,
                                        outdoor_index=body.outdoor_index, ghin_number=body.ghin_number, gspro_name=body.gspro_name)
            if code:
                leagues.join(conn, user["id"], code)
            token, _ = accounts.login(conn, body.email, body.password, auth.client_ip(request))
        auth.set_session_cookie(request, response, token)
        return {"user": user}

    @router.post("/api/auth/login", tags=["accounts"])
    def login(body: LoginBody, request: Request, response: Response):
        with db(request).connect() as conn:
            token, user = accounts.login(conn, body.email, body.password, auth.client_ip(request))
        auth.set_session_cookie(request, response, token)
        return {"user": user}

    @router.post("/api/auth/logout", tags=["accounts"])
    def logout(request: Request, response: Response):
        with db(request).connect() as conn:
            accounts.logout(conn, request.cookies.get(auth.COOKIE))
        auth.clear_session_cookie(response)
        return {"ok": True}

    # ========================================================================= me

    @router.patch("/api/me", tags=["accounts"])
    def update_me(body: ProfileBody, request: Request):
        me = auth.require_user(request)
        with db(request).connect() as conn:
            user = accounts.update_profile(conn, me["id"], fields=set(body.model_fields_set), **_fields(body))
            rounds.recompute_handicap(conn, me["id"])        # the outdoor index feeds a new player's number
            return {"user": accounts.get_user(conn, user["id"])}

    @router.post("/api/me/password", tags=["accounts"])
    def change_password(body: PasswordBody, request: Request):
        me = auth.require_user(request)
        with db(request).connect() as conn:
            accounts.change_password(conn, me["id"], body.current_password, body.new_password)
        return {"ok": True}

    @router.get("/api/me/home", tags=["accounts"])
    def home(request: Request):
        """Everything the player's home screen needs in one go."""
        me = auth.require_user(request)
        sync_demo(request)
        with db(request).connect() as conn:
            profile = standings.player_profile(conn, me["id"])
            return {**profile, "leagues": leagues.for_user(conn, me["id"])}

    # ===================================================================== rounds

    def _round_for(conn, request: Request, round_id: int) -> Dict[str, Any]:
        me = auth.require_user(request)
        row = rounds.get_row(conn, round_id)
        if row["user_id"] != me["id"] and me["role"] != "admin":
            raise Forbidden("That's another player's round.")
        return me

    @router.post("/api/play/rounds", tags=["rounds"])
    def start_round(body: StartRoundBody, request: Request):
        me = auth.require_user(request)
        with db(request).connect() as conn:
            return rounds.start(conn, me, user_id=body.user_id, league_id=body.league_id, bay=body.bay,
                                holes=body.holes, course_name=body.course_name, pars=body.pars)

    @router.get("/api/play/rounds/{round_id}", tags=["rounds"])
    def get_round(round_id: int, request: Request):
        with db(request).connect() as conn:
            _round_for(conn, request, round_id)
            return rounds.view(conn, rounds.get_row(conn, round_id), with_user=True)

    @router.put("/api/play/rounds/{round_id}/holes/{hole}", tags=["rounds"])
    def save_hole(round_id: int, hole: int, body: HoleBody, request: Request):
        """Enter (or correct) one hole. The live leaderboard updates the moment this returns."""
        with db(request).connect() as conn:
            me = _round_for(conn, request, round_id)
            return rounds.save_hole(conn, me, round_id, hole, body.strokes, body.par)

    @router.delete("/api/play/rounds/{round_id}/holes/{hole}", tags=["rounds"])
    def clear_hole(round_id: int, hole: int, request: Request):
        with db(request).connect() as conn:
            me = _round_for(conn, request, round_id)
            return rounds.clear_hole(conn, me, round_id, hole)

    @router.post("/api/play/rounds/{round_id}/finish", tags=["rounds"])
    def finish_round(round_id: int, request: Request):
        """End a round now. Holes already entered are kept (and count toward the handicap once 9 are in)."""
        with db(request).connect() as conn:
            me = _round_for(conn, request, round_id)
            return rounds.finish(conn, me, round_id)

    @router.delete("/api/play/rounds/{round_id}", tags=["rounds"])
    def delete_round(round_id: int, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            rounds.delete(conn, me, round_id)
        return {"ok": True}

    # ==================================================================== leagues

    @router.get("/api/leagues/public", tags=["leagues"])
    def public_leagues(request: Request):
        """League names for the bay-screen picker. No login: it is just names."""
        with db(request).connect() as conn:
            return {"leagues": [{k: lg[k] for k in ("id", "name", "season", "holes", "ranking", "course_name")}
                                for lg in leagues.list_all(conn)]}

    @router.get("/api/leagues", tags=["leagues"])
    def list_leagues(request: Request):
        me = auth.require_user(request)
        with db(request).connect() as conn:
            if me["role"] == "admin":
                return {"leagues": leagues.list_all(conn, include_archived=True)}
            return {"leagues": leagues.for_user(conn, me["id"])}

    @router.post("/api/leagues", tags=["leagues"])
    def create_league(body: LeagueBody, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            return leagues.create(conn, me["id"], name=body.name, season=body.season, holes=body.holes or 9,
                                  ranking=body.ranking or "net", course_name=body.course_name, pars=body.pars)

    @router.patch("/api/leagues/{league_id}", tags=["leagues"])
    def update_league(league_id: int, body: LeagueBody, request: Request):
        me = auth.require_admin(request)
        changes = _fields(body)
        changes.pop("holes", None)             # a league's length is fixed once players have rounds against it
        with db(request).connect() as conn:
            return leagues.update(conn, me["id"], league_id, **changes)

    @router.post("/api/leagues/join", tags=["leagues"])
    def join_league(body: JoinBody, request: Request):
        me = auth.require_user(request)
        with db(request).connect() as conn:
            return leagues.join(conn, me["id"], body.code)

    def _members_only(conn, request: Request, league_id: int) -> Dict[str, Any]:
        me = auth.require_user(request)
        leagues.get_row(conn, league_id)
        if me["role"] != "admin" and not leagues.is_member(conn, league_id, me["id"]):
            raise Forbidden("Join this league to see its table.")
        return me

    @router.get("/api/leagues/{league_id}/board", tags=["leagues"])
    def league_board(league_id: int, request: Request):
        """Tonight's live leaderboard (what the bay screens show). Public, like the screens themselves."""
        sync_demo(request)
        with db(request).connect() as conn:
            board = standings.live_board(conn, league_id)
        return {**board, "players": data.rank_players(board["players"])}

    @router.get("/api/leagues/{league_id}/table", tags=["leagues"])
    def league_table(league_id: int, request: Request):
        sync_demo(request)
        with db(request).connect() as conn:
            _members_only(conn, request, league_id)
            return standings.league_table(conn, league_id)

    @router.get("/api/leagues/{league_id}/rounds", tags=["leagues"])
    def league_rounds(league_id: int, request: Request):
        auth.require_admin(request)
        sync_demo(request)
        with db(request).connect() as conn:
            leagues.get_row(conn, league_id)
            return {"rounds": rounds.list_for_league(conn, league_id)}

    @router.get("/api/leagues/{league_id}/members", tags=["leagues"])
    def league_members(league_id: int, request: Request):
        auth.require_admin(request)
        with db(request).connect() as conn:
            leagues.get_row(conn, league_id)
            rows = conn.execute(
                "SELECT u.*, m.team FROM league_members m JOIN users u ON u.id = m.user_id WHERE m.league_id = ?"
                " ORDER BY u.display_name COLLATE NOCASE", (league_id,)).fetchall()
            return {"members": [{**accounts.public(r), "team": r["team"]} for r in rows]}

    @router.post("/api/leagues/{league_id}/members", tags=["leagues"])
    def add_member(league_id: int, body: MemberBody, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            leagues.add_member(conn, me["id"], league_id, body.user_id)
        return {"ok": True}

    @router.delete("/api/leagues/{league_id}/members/{user_id}", tags=["leagues"])
    def remove_member(league_id: int, user_id: int, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            leagues.remove_member(conn, me["id"], league_id, user_id)
        return {"ok": True}

    @router.put("/api/leagues/{league_id}/members/{user_id}/team", tags=["leagues"])
    def set_team(league_id: int, user_id: int, body: TeamBody, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            leagues.set_team(conn, me["id"], league_id, user_id, body.team)
        return {"ok": True}

    # ====================================================================== admin

    @router.get("/api/admin/overview", tags=["admin"])
    def overview(request: Request):
        auth.require_admin(request)
        sync_demo(request)
        with db(request).connect() as conn:
            return standings.venue_overview(conn)

    @router.get("/api/admin/players", tags=["admin"])
    def admin_players(request: Request):
        auth.require_admin(request)
        sync_demo(request)
        with db(request).connect() as conn:
            out = []
            for u in accounts.list_users(conn):
                stats = conn.execute(
                    "SELECT COUNT(*) AS n, MAX(started_at) AS last FROM rounds WHERE user_id = ? AND status IN ('completed','ended_early')",
                    (u["id"],)).fetchone()
                names = [r["name"] for r in conn.execute(
                    "SELECT l.name FROM leagues l JOIN league_members m ON m.league_id = l.id WHERE m.user_id = ? ORDER BY l.name", (u["id"],))]
                out.append({**u, "rounds": stats["n"], "last_played": stats["last"], "leagues": names})
            return {"players": out}

    @router.get("/api/admin/players/{user_id}", tags=["admin"])
    def admin_player(user_id: int, request: Request):
        auth.require_admin(request)
        with db(request).connect() as conn:
            return {**standings.player_profile(conn, user_id), "leagues": leagues.for_user(conn, user_id)}

    @router.patch("/api/admin/players/{user_id}", tags=["admin"])
    def admin_edit_player(user_id: int, body: ProfileBody, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            accounts.update_profile(conn, user_id, fields=set(body.model_fields_set), **_fields(body))
            rounds.recompute_handicap(conn, user_id)
            audit(conn, me["id"], "profile_edited", f"user {user_id}: {sorted(body.model_fields_set)}")
            return {"user": accounts.get_user(conn, user_id)}

    @router.post("/api/admin/players/{user_id}/reset-password", tags=["admin"])
    def reset_password(user_id: int, request: Request):
        """Issue a temporary password to hand to the player (there is no email reset yet)."""
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            return {"temporary_password": accounts.admin_reset_password(conn, me["id"], user_id)}

    @router.post("/api/admin/players/{user_id}/role", tags=["admin"])
    def set_role(user_id: int, body: RoleBody, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            return {"user": accounts.set_role(conn, me["id"], user_id, body.role)}

    @router.post("/api/admin/players/{user_id}/disabled", tags=["admin"])
    def set_disabled(user_id: int, body: DisabledBody, request: Request):
        me = auth.require_admin(request)
        with db(request).connect() as conn:
            return {"user": accounts.set_disabled(conn, me["id"], user_id, body.disabled)}

    @router.get("/api/admin/accuracy", tags=["admin"])
    def capture_accuracy(request: Request, league_id: Optional[int] = Query(None), days: int = Query(30, ge=1, le=365)):
        """Screen capture vs hand entry: how often the engine's scores match what players typed in."""
        auth.require_admin(request)
        sync_demo(request)
        since = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
        with db(request).connect() as conn:
            if league_id:
                leagues.get_row(conn, league_id)
            return accuracy.check(conn, request.app.state.source.rounds(), league_id=league_id, since=since)

    return router
