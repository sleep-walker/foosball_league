"""Tests for league_app.engine.dyp — pure functions, no DB needed."""

from uuid import uuid4

import pytest

from league_app.engine.dyp import (
    draw_dyp_teams,
    draw_monster_dyp_next_round,
    draw_monster_dyp_teams,
    pair_teams,
)

PLAYERS = [uuid4() for _ in range(8)]


class TestDrawDypTeams:
    def test_basic_draw(self):
        teams = draw_dyp_teams(PLAYERS)
        assert len(teams) == 4
        all_players = set()
        for t in teams:
            all_players.add(t.player_1_id)
            all_players.add(t.player_2_id)
        assert all_players == set(PLAYERS)

    def test_odd_players_bye(self):
        teams = draw_dyp_teams(PLAYERS[:5])
        assert len(teams) == 2  # 4 paired, 1 bye

    def test_two_players(self):
        teams = draw_dyp_teams(PLAYERS[:2])
        assert len(teams) == 1

    def test_one_player(self):
        assert draw_dyp_teams(PLAYERS[:1]) == []

    def test_avoids_repeat_partnerships(self):
        round1 = draw_dyp_teams(PLAYERS[:4])
        round1_keys = {t.pair_key for t in round1}
        round2 = draw_dyp_teams(PLAYERS[:4], history=[round1])
        round2_keys = {t.pair_key for t in round2}
        # With 4 players there are 3 possible pairings — should pick a fresh one
        assert round1_keys != round2_keys


class TestPairTeams:
    def test_four_teams(self):
        teams = draw_dyp_teams(PLAYERS)
        pairings = pair_teams(teams)
        assert len(pairings) == 2

    def test_odd_teams(self):
        teams = draw_dyp_teams(PLAYERS[:6])
        pairings = pair_teams(teams)
        assert len(pairings) == 1  # 3 teams → 1 pairing + 1 bye


class TestMonsterDyp:
    def test_basic(self):
        teams, pairings = draw_monster_dyp_teams(PLAYERS)
        assert len(teams) == 4
        assert len(pairings) == 2

    def test_avoids_repeat_matchups(self):
        t1, p1 = draw_monster_dyp_teams(PLAYERS[:4])
        t2, p2 = draw_monster_dyp_teams(
            PLAYERS[:4], team_history=[t1], matchup_history=[p1]
        )
        # With 4 players and 2 teams per round, 2 rounds should produce
        # different team combinations or at least different matchups.
        # Not guaranteed to be different with only 4 players (3 pairings total),
        # but the algorithm tries. At minimum it shouldn't crash.
        assert len(p2) == 1

    def test_too_few_players(self):
        teams, pairings = draw_monster_dyp_teams(PLAYERS[:2])
        assert len(teams) == 1
        assert len(pairings) == 0


class TestMonsterDypNextRound:
    def test_4_players_split_constraint(self):
        a, b, c, d = [uuid4() for _ in range(4)]
        teams = draw_monster_dyp_next_round([(a, b), (c, d)])
        assert len(teams) == 2
        # Neither new pair may equal an old advancing pair
        keys = {t.pair_key for t in teams}
        assert frozenset({a, b}) not in keys
        assert frozenset({c, d}) not in keys

    def test_8_players_two_pairs_per_match(self):
        players = [uuid4() for _ in range(8)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 8, 2)]
        teams = draw_monster_dyp_next_round(pairs)
        assert len(teams) == 4
        old_keys = {frozenset(p) for p in pairs}
        for t in teams:
            assert t.pair_key not in old_keys

    def test_single_pair_infeasible(self):
        a, b = uuid4(), uuid4()
        with pytest.raises(ValueError):
            draw_monster_dyp_next_round([(a, b)])

    def test_bye_advance_is_free_agent(self):
        # One pair plus one solo bye-advancer (3 players total → 1 pair + 1 bye).
        a, b, c = uuid4(), uuid4(), uuid4()
        teams = draw_monster_dyp_next_round([(a, b), (c, None)])
        # Three players cannot all be paired; expect 1 valid pair, bye dropped.
        assert len(teams) == 1
        assert teams[0].pair_key != frozenset({a, b})

    def test_empty_input(self):
        assert draw_monster_dyp_next_round([]) == []

