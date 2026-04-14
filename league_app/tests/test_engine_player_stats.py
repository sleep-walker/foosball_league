"""Tests for league_app.engine.player_stats — pure functions, no DB."""

from uuid import uuid4

from league_app.engine.player_stats import (
    compute_elo_progression,
    compute_player_stats,
)
from league_app.engine.standings import GameResult, MatchResult

P1, P2, P3 = uuid4(), uuid4(), uuid4()


def _match(a, b, sa, sb):
    return MatchResult(a, b, [GameResult(sa, sb)])


class TestPlayerStats:
    def test_basic(self):
        results = [_match(P1, P2, 6, 3), _match(P1, P3, 6, 4)]
        s = compute_player_stats(P1, results)
        assert s.matches_played == 2
        assert s.wins == 2
        assert s.losses == 0
        assert s.goals_for == 12
        assert s.goals_against == 7
        assert s.win_rate == 1.0

    def test_mixed_results(self):
        results = [_match(P1, P2, 6, 3), _match(P2, P1, 6, 4)]
        s = compute_player_stats(P1, results)
        assert s.wins == 1
        assert s.losses == 1
        assert s.win_rate == 0.5

    def test_head_to_head(self):
        results = [
            _match(P1, P2, 6, 3),
            _match(P1, P2, 3, 6),
            _match(P1, P2, 6, 4),
        ]
        s = compute_player_stats(P1, results)
        assert s.h2h[P2]["wins"] == 2
        assert s.h2h[P2]["losses"] == 1

    def test_opponents_sorted_by_frequency(self):
        results = [
            _match(P1, P2, 6, 3),
            _match(P1, P2, 6, 4),
            _match(P1, P3, 6, 5),
        ]
        s = compute_player_stats(P1, results)
        assert s.opponents[0] == (P2, 2)
        assert s.opponents[1] == (P3, 1)

    def test_irrelevant_matches_skipped(self):
        results = [_match(P2, P3, 6, 3)]
        s = compute_player_stats(P1, results)
        assert s.matches_played == 0
        assert s.win_rate == 0.0

    def test_draw(self):
        results = [MatchResult(P1, P2, [GameResult(5, 5)])]
        s = compute_player_stats(P1, results)
        assert s.draws == 1
        assert s.wins == 0
        assert s.win_rate == 0.0

    def test_empty(self):
        s = compute_player_stats(P1, [])
        assert s.matches_played == 0


class TestEloProgression:
    def test_basic_progression(self):
        results = [_match(P1, P2, 6, 3), _match(P1, P2, 6, 4)]
        snaps = compute_elo_progression(P1, results)
        assert len(snaps) == 2
        assert snaps[0].rating > 1000  # won → rating up
        assert snaps[1].rating > snaps[0].rating  # won again → higher

    def test_loss_decreases_rating(self):
        results = [_match(P1, P2, 3, 6)]
        snaps = compute_elo_progression(P1, results)
        assert snaps[0].rating < 1000

    def test_empty(self):
        assert compute_elo_progression(P1, []) == []
