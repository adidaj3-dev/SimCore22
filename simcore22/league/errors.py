# simcore22/league/errors.py
"""Errors the league services raise. Each carries the HTTP status the web layer should answer with."""


class LeagueError(Exception):
    status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class Invalid(LeagueError):
    """The request is wrong in some way the person can fix (bad email, score out of range, ...)."""
    status = 400


class NotAuthenticated(LeagueError):
    status = 401


class Forbidden(LeagueError):
    status = 403


class NotFound(LeagueError):
    status = 404


class Conflict(LeagueError):
    """Valid request, but it clashes with what exists (duplicate email, a round already in progress)."""
    status = 409


class TooManyAttempts(LeagueError):
    status = 429
