"""Tests for league_app.engine.standings — pure function, no DB needed."""

from uuid import uuid4

import pytest

from league_app.engine.standings import (
    GameResult,
    MatchResult,
    StandingRow,
    compute_standings,
)

P1, P2, P3, P4 = uuid4(), uuid4(), uuid4(), uuid4()


def _match(a, b, *game_scores):
    """Shortcut: _match(P1, P2, (6, 3), (4, 6)) -> MatchResult with 2 games."""
    return MatchResult(
        participant_a_id=a,
        participant_b_id=b,
        games=[GameResult(score_a=s[0], score_b=s[1]) for s in game_scores],
    )


class TestBasicStandings:
    def test_single_match_win(self):
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(results)
        assert len(standings) == 2
        assert standings[0].participant_id == P1
        assert standings[0].wins == 1
        assert standings[0].losses == 0
        assert standings[0].points == 3
        assert standings[1].participant_id == P2
        assert standings[1].wins == 0
        assert standings[1].losses == 1
        assert standings[1].points == 0

    def test_draw(self):
        results = [_match(P1, P2, (5, 5))]
        standings = compute_standings(results)
        assert standings[0].draws == 1
        assert standings[1].draws == 1
        assert standings[0].points == 1
        assert standings[1].points == 1

    def test_goal_difference_tiebreak(self):
        # P1 beats P3 6-0, P2 beats P4 6-5 → same points, P1 has better GD
        results = [
            _match(P1, P3, (6, 0)),
            _match(P2, P4, (6, 5)),
        ]
        standings = compute_standings(results)
        assert standings[0].participant_id == P1
        assert standings[1].participant_id == P2


class TestMultipleRounds:
    def test_three_rounds_four_players(self):
        results = [
            _match(P1, P2, (6, 3)),
            _match(P3, P4, (6, 4)),
            _match(P1, P3, (5, 5)),  # draw
            _match(P2, P4, (6, 2)),
            _match(P1, P4, (6, 1)),
            _match(P2, P3, (3, 6)),
        ]
        standings = compute_standings(results)
        # P1: 2W 1D 0L = 7pts, P3: 2W 1D 0L = 7pts (worse GD), P2: 1W 0D 2L = 3pts, P4: 0W 0D 3L = 0pts
        assert standings[0].points == 7
        assert standings[1].points == 7
        assert standings[2].points == 3
        assert standings[3].points == 0
        # P1 has better GD (23-9=14) vs P3 (17-12=5)
        assert standings[0].participant_id == P1
        assert standings[1].participant_id == P3


class TestBestOfN:
    def test_best_of_3_match(self):
        # P1 wins 2-1 in games → 1 match win
        results = [_match(P1, P2, (6, 3), (2, 6), (6, 4))]
        standings = compute_standings(results)
        assert standings[0].participant_id == P1
        assert standings[0].wins == 1
        assert standings[0].goals_for == 14
        assert standings[0].goals_against == 13


class TestCustomScoring:
    def test_custom_points(self):
        rules = {"points_for_win": 2, "points_for_draw": 1, "points_for_loss": 0}
        results = [
            _match(P1, P2, (6, 3)),
            _match(P1, P3, (5, 5)),
        ]
        standings = compute_standings(results, rules=rules)
        assert standings[0].participant_id == P1
        assert standings[0].points == 3  # 2 + 1

    def test_loss_points(self):
        rules = {"points_for_win": 3, "points_for_draw": 1, "points_for_loss": -1}
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(results, rules=rules)
        assert standings[1].points == -1


class TestEdgeCases:
    def test_empty(self):
        assert compute_standings([]) == []

    def test_single_player_appears_only_once(self):
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(results)
        ids = [r.participant_id for r in standings]
        assert len(ids) == len(set(ids))
