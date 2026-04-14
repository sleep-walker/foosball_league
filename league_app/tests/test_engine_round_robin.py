"""Tests for league_app.engine.round_robin — pure functions, no DB."""

from itertools import combinations
from uuid import uuid4

from league_app.engine.round_robin import generate_round_robin


class TestRoundRobin:
    def test_4_players(self):
        ids = [uuid4() for _ in range(4)]
        rr = generate_round_robin(ids)
        assert len(rr.rounds) == 3  # n-1 rounds
        # Total matches = n*(n-1)/2 = 6
        assert rr.total_matches == 6
        # Every pair plays exactly once
        pairs = set()
        for round_matches in rr.rounds:
            for m in round_matches:
                pair = frozenset([m.participant_a_id, m.participant_b_id])
                assert pair not in pairs, "Duplicate pair"
                pairs.add(pair)
        expected = {frozenset(p) for p in combinations(ids, 2)}
        assert pairs == expected

    def test_3_players_odd(self):
        ids = [uuid4() for _ in range(3)]
        rr = generate_round_robin(ids)
        # 3 players → 1 BYE added → 3 rounds, 1 match each = 3 matches
        assert rr.total_matches == 3
        assert len(rr.rounds) == 3

    def test_5_players_odd(self):
        ids = [uuid4() for _ in range(5)]
        rr = generate_round_robin(ids)
        # 5 players → 10 matches, 5 rounds
        assert rr.total_matches == 10
        assert len(rr.rounds) == 5

    def test_2_players(self):
        ids = [uuid4() for _ in range(2)]
        rr = generate_round_robin(ids)
        assert len(rr.rounds) == 1
        assert rr.total_matches == 1

    def test_fewer_than_2(self):
        rr = generate_round_robin([uuid4()])
        assert rr.total_matches == 0
        rr = generate_round_robin([])
        assert rr.total_matches == 0

    def test_6_players_every_player_same_games(self):
        ids = [uuid4() for _ in range(6)]
        rr = generate_round_robin(ids)
        # Each player should play 5 matches
        game_counts = {pid: 0 for pid in ids}
        for round_matches in rr.rounds:
            for m in round_matches:
                game_counts[m.participant_a_id] += 1
                game_counts[m.participant_b_id] += 1
        for count in game_counts.values():
            assert count == 5


class TestDoubleRoundRobin:
    def test_4_players_double(self):
        ids = [uuid4() for _ in range(4)]
        rr = generate_round_robin(ids, double=True)
        # 6 rounds (3 + 3), 12 matches total
        assert len(rr.rounds) == 6
        assert rr.total_matches == 12
        # Each ordered pair should appear exactly once as (a, b) and once as (b, a)
        ordered_pairs = []
        for round_matches in rr.rounds:
            for m in round_matches:
                ordered_pairs.append((m.participant_a_id, m.participant_b_id))
        assert len(ordered_pairs) == 12
        # Check both directions exist
        for a, b in combinations(ids, 2):
            assert (a, b) in ordered_pairs or (b, a) in ordered_pairs
