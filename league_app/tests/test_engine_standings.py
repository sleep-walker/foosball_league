"""Tests for league_app.engine.standings — pure function, no DB needed."""

from uuid import uuid4


from league_app.engine.standings import (
    GameResult,
    MatchResult,
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
        assert standings[0].points == 2  # default: 2 pts/win (Kickertool style)
        assert standings[0].sets_won == 1
        assert standings[0].sets_lost == 0
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
        # P1: 2W 1D 0L = 5pts, P3: 2W 1D 0L = 5pts (worse GD), P2: 1W 0D 2L = 2pts, P4: 0W 0D 3L = 0pts
        assert standings[0].points == 5  # 2*2 + 1*1
        assert standings[1].points == 5
        assert standings[2].points == 2
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
        rules = {"points_for_win": 3, "points_for_draw": 1, "points_for_loss": 0}
        results = [
            _match(P1, P2, (6, 3)),
            _match(P1, P3, (5, 5)),
        ]
        standings = compute_standings(results, rules=rules)
        assert standings[0].participant_id == P1
        assert standings[0].points == 4  # 3 + 1

    def test_loss_points(self):
        rules = {"points_for_win": 3, "points_for_draw": 1, "points_for_loss": -1}
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(results, rules=rules)
        assert standings[1].points == -1

    def test_default_is_2_pts_per_win(self):
        """Default scoring matches Kickertool MonsterDYP: 2 pts/win."""
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(results)
        assert standings[0].points == 2


class TestSetsTracking:
    def test_best_of_3_sets(self):
        """In best-of-3, winner gets 2 sets won, loser gets 1."""
        results = [_match(P1, P2, (6, 3), (2, 6), (6, 4))]
        standings = compute_standings(results)
        assert standings[0].sets_won == 2
        assert standings[0].sets_lost == 1
        assert standings[0].sets_difference == 1
        assert standings[1].sets_won == 1
        assert standings[1].sets_lost == 2
        assert standings[1].sets_difference == -1

    def test_sets_tiebreaker(self):
        """When points are equal, sets_difference breaks the tie."""
        # P1 wins 2-0 in sets, P2 wins 2-1 in sets → same points, P1 better sets_diff
        results = [
            _match(P1, P3, (5, 3), (5, 2)),          # P1 wins 2-0
            _match(P2, P4, (5, 3), (3, 5), (5, 2)),  # P2 wins 2-1
        ]
        standings = compute_standings(results)
        assert standings[0].participant_id == P1  # better sets_diff (2-0=2 vs 2-1=1)
        assert standings[1].participant_id == P2


class TestRegisteredPlayers:
    def test_registered_without_matches_appear(self):
        """Players who are registered but haven't played appear with 0 stats."""
        P5 = uuid4()
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(
            results, registered_player_ids=[P1, P2, P5],
        )
        assert len(standings) == 3
        # P5 is last with 0 points
        p5_row = [r for r in standings if r.participant_id == P5][0]
        assert p5_row.points == 0
        assert p5_row.matches_played == 0
        assert p5_row.wins == 0

    def test_registered_players_no_matches(self):
        """When no matches played, all registered players appear with 0 stats."""
        P5 = uuid4()
        P6 = uuid4()
        standings = compute_standings([], registered_player_ids=[P5, P6])
        assert len(standings) == 2
        assert all(r.points == 0 for r in standings)

    def test_registered_ids_dont_duplicate(self):
        """A player in both registrations and matches appears only once."""
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(
            results, registered_player_ids=[P1, P2],
        )
        assert len(standings) == 2


class TestEdgeCases:
    def test_empty(self):
        assert compute_standings([]) == []

    def test_single_player_appears_only_once(self):
        results = [_match(P1, P2, (6, 3))]
        standings = compute_standings(results)
        ids = [r.participant_id for r in standings]
        assert len(ids) == len(set(ids))
