"""Tests for league_app.engine.league_standings — pure functions, no DB."""

from uuid import uuid4

from league_app.engine.league_standings import (
    TournamentPlacement,
    compute_elo_ratings,
    compute_placement_standings,
    compute_win_loss_standings,
)
from league_app.engine.standings import GameResult, MatchResult

P1, P2, P3 = uuid4(), uuid4(), uuid4()


def _match(a, b, sa, sb):
    return MatchResult(
        participant_a_id=a,
        participant_b_id=b,
        games=[GameResult(score_a=sa, score_b=sb)],
    )


class TestPlacementPoints:
    def test_single_tournament(self):
        placements = [
            [
                TournamentPlacement(P1, 1),
                TournamentPlacement(P2, 2),
                TournamentPlacement(P3, 3),
            ]
        ]
        rows = compute_placement_standings(placements)
        assert rows[0].participant_id == P1
        assert rows[0].score == 10
        assert rows[1].score == 7
        assert rows[2].score == 5

    def test_two_tournaments(self):
        placements = [
            [TournamentPlacement(P1, 1), TournamentPlacement(P2, 2)],
            [TournamentPlacement(P2, 1), TournamentPlacement(P1, 3)],
        ]
        rows = compute_placement_standings(placements)
        # P1: 10 + 5 = 15, P2: 7 + 10 = 17
        assert rows[0].participant_id == P2
        assert rows[0].score == 17
        assert rows[1].participant_id == P1
        assert rows[1].score == 15

    def test_custom_config(self):
        config = {"1": 5, "2": 3, "default": 1}
        placements = [[TournamentPlacement(P1, 1), TournamentPlacement(P2, 5)]]
        rows = compute_placement_standings(placements, config)
        assert rows[0].score == 5
        assert rows[1].score == 1  # "default"

    def test_empty(self):
        assert compute_placement_standings([]) == []


class TestElo:
    def test_basic_game(self):
        results = [_match(P1, P2, 6, 3)]
        rows = compute_elo_ratings(results)
        assert rows[0].participant_id == P1
        assert rows[0].score > 1000
        assert rows[1].score < 1000

    def test_symmetric_after_split(self):
        results = [_match(P1, P2, 6, 3), _match(P2, P1, 6, 3)]
        rows = compute_elo_ratings(results)
        # Ratings should be close to initial after 1-1
        for r in rows:
            assert abs(r.score - 1000) < 5

    def test_empty(self):
        assert compute_elo_ratings([]) == []


class TestWinLoss:
    def test_basic(self):
        results = [_match(P1, P2, 6, 3), _match(P1, P3, 6, 4)]
        rows = compute_win_loss_standings(results)
        assert rows[0].participant_id == P1
        assert rows[0].score == 6  # 2 wins * 3pts
        assert rows[0].wins == 2

    def test_draw(self):
        results = [_match(P1, P2, 5, 5)]
        rows = compute_win_loss_standings(results)
        assert rows[0].score == 1
        assert rows[0].draws == 1

    def test_custom_config(self):
        config = {"points_for_win": 2, "points_for_draw": 1, "points_for_loss": -1}
        results = [_match(P1, P2, 6, 3)]
        rows = compute_win_loss_standings(results, config)
        assert rows[0].score == 2
        assert rows[1].score == -1

    def test_empty(self):
        assert compute_win_loss_standings([]) == []



class TestErosion:
    def test_placement_erosion_reduces_older(self):
        placements = [
            [TournamentPlacement(P1, 1), TournamentPlacement(P2, 2)],  # old
            [TournamentPlacement(P1, 1), TournamentPlacement(P2, 2)],  # new
        ]
        # Without erosion
        rows_no = compute_placement_standings(placements, {"1": 10, "2": 5})
        # With erosion
        rows_e = compute_placement_standings(
            placements, {"1": 10, "2": 5, "erosion_factor": 0.5}
        )
        # With erosion, older tournament worth less → total lower
        assert rows_e[0].score < rows_no[0].score
        assert rows_e[0].score > 0

    def test_placement_no_erosion_default(self):
        placements = [
            [TournamentPlacement(P1, 1)],
            [TournamentPlacement(P1, 1)],
        ]
        rows = compute_placement_standings(placements)
        assert rows[0].score == 20  # 10 + 10, no erosion

    def test_win_loss_erosion(self):
        results = [_match(P1, P2, 6, 3), _match(P1, P2, 6, 3)]
        # Without erosion: 2 * 3 = 6
        rows_no = compute_win_loss_standings(results)
        assert rows_no[0].score == 6
        # With erosion: older match worth less
        rows_e = compute_win_loss_standings(
            results, {"points_for_win": 3, "erosion_factor": 0.5}
        )
        assert rows_e[0].score < 6
        assert rows_e[0].score > 3  # at least one full win

    def test_single_match_erosion_no_effect(self):
        results = [_match(P1, P2, 6, 3)]
        rows = compute_win_loss_standings(
            results, {"points_for_win": 3, "erosion_factor": 0.5}
        )
        assert rows[0].score == 3  # single match → weight=1.0