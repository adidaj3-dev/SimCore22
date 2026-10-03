from simcore22.engine.engine import HoleState, RoundState, SessionState
from simcore22.engine.leaderboard.leaderboard import Leaderboard


def _session(**players):
    """players: name -> list of HoleState"""
    session = SessionState()
    for name, holes in players.items():
        session.players[name] = RoundState(player_name=name, holes={h.hole_number: h for h in holes})
    return session


def _board(session):
    board = Leaderboard()
    board.update_from_session(session)
    return board


def test_to_par_uses_the_real_par_of_the_holes_played():
    # par 3, 4, 5 = 12; scored 3, 5, 4 = 12 -> even par (the old "par 4 every hole" math said -0 only by luck)
    board = _board(_session(Alex=[
        HoleState(1, par=3, gross_score=3), HoleState(2, par=4, gross_score=5), HoleState(3, par=5, gross_score=4),
    ]))
    (row,) = board.get_standings()
    assert (row.thru, row.gross_score, row.par_played, row.vs_par) == (3, 12, 12, 0)


def test_a_par_5_birdie_is_under_par_not_over():
    (row,) = _board(_session(Alex=[HoleState(1, par=5, gross_score=4)])).get_standings()
    assert row.vs_par == -1  # assuming par 4 for every hole would have said E


def test_unknown_par_is_assumed_to_be_4():
    (row,) = _board(_session(Alex=[HoleState(1, strokes=5)])).get_standings()
    assert (row.par_played, row.vs_par) == (4, 1)


def test_a_hole_with_no_shots_yet_is_not_counted_as_played():
    """The HUD shows hole 2 before anyone hits; it must not inflate 'thru'."""
    (row,) = _board(_session(Alex=[HoleState(1, par=4, gross_score=4), HoleState(2, par=4)])).get_standings()
    assert row.thru == 1


def test_a_player_with_nothing_played_is_not_listed():
    assert _board(_session(Alex=[HoleState(1)])).get_standings() == []


def test_standings_rank_by_score_to_par_and_expose_it():
    board = _board(_session(
        Sam=[HoleState(1, par=4, gross_score=6)],
        Alex=[HoleState(1, par=4, gross_score=3)],
    ))
    rows = board.to_dict()
    assert [r["player_name"] for r in rows] == ["Alex", "Sam"]
    assert [r["position"] for r in rows] == [1, 2]
    assert [r["vs_par"] for r in rows] == [-1, 2]


def test_a_player_through_fewer_holes_does_not_lead_just_for_having_a_lower_gross():
    """Gross after 1 hole (5) beats gross after 3 holes (12) - but 3 pars is better than a bogey."""
    board = _board(_session(
        Early=[HoleState(1, par=4, gross_score=5)],
        Steady=[HoleState(1, par=4, gross_score=4), HoleState(2, par=4, gross_score=4), HoleState(3, par=4, gross_score=4)],
    ))
    assert [r.player_name for r in board.get_standings()] == ["Steady", "Early"]


def test_equal_to_par_ranks_the_player_who_has_played_more_holes_first():
    board = _board(_session(
        Short=[HoleState(1, par=4, gross_score=4)],
        Long=[HoleState(1, par=4, gross_score=4), HoleState(2, par=4, gross_score=4)],
    ))
    assert [r.player_name for r in board.get_standings()] == ["Long", "Short"]
