"""Tests for league_app.engine.swiss — pure function, no DB needed."""

from uuid import uuid4

from league_app.engine.standings import GameResult, MatchResult
from league_app.engine.swiss import generate_swiss_round

P1, P2, P3, P4, P5 = [uuid4() for _ in range(5)]


class TestSwissFirstRound:
    def test_four_players_first_round(self):
        pairings = generate_swiss_round([P1, P2, P3, P4], [])
        assert len(pairings) == 2
        all_ids = {p.participant_a_id for p in pairings} | {
            p.participant_b_id for p in pairings
        }
        assert all_ids == {P1, P2, P3, P4}

    def test_odd_players_one_bye(self):
        pairings = generate_swiss_round([P1, P2, P3], [])
        assert len(pairings) == 1

    def test_two_players(self):
        pairings = generate_swiss_round([P1, P2], [])
        assert len(pairings) == 1

    def test_one_player_no_pairings(self):
        assert generate_swiss_round([P1], []) == []

    def test_empty(self):
        assert generate_swiss_round([], []) == []


def _match(a, b, sa, sb):
    return MatchResult(
        participant_a_id=a,
        participant_b_id=b,
        games=[GameResult(score_a=sa, score_b=sb)],
    )


class TestAvoidRepeats:
    def test_no_repeat_with_four_players(self):
        # Round 1: P1 vs P2, P3 vs P4 (we simulate this history)
        history = [_match(P1, P2, 6, 3), _match(P3, P4, 6, 4)]
        pairings = generate_swiss_round([P1, P2, P3, P4], history)
        pairs_as_sets = [
            frozenset((p.participant_a_id, p.participant_b_id)) for p in pairings
        ]
        # Should not repeat P1-P2 or P3-P4
        assert frozenset((P1, P2)) not in pairs_as_sets
        assert frozenset((P3, P4)) not in pairs_as_sets
        assert len(pairings) == 2

    def test_forced_repeat_when_unavoidable(self):
        # 2 players, already played — must repeat
        history = [_match(P1, P2, 6, 3)]
        pairings = generate_swiss_round([P1, P2], history)
        assert len(pairings) == 1


class TestSortedByStandings:
    def test_winners_play_winners(self):
        # P1 beat P2, P3 beat P4 → P1 and P3 are top, should be paired
        history = [_match(P1, P2, 6, 3), _match(P3, P4, 6, 4)]
        pairings = generate_swiss_round([P1, P2, P3, P4], history)
        top_pair = frozenset(
            (pairings[0].participant_a_id, pairings[0].participant_b_id)
        )
        # The top two (P1, P3) should play each other
        assert top_pair == frozenset((P1, P3))


class TestFivePlayersMultipleRounds:
    def test_three_rounds(self):
        players = [P1, P2, P3, P4, P5]
        history = []

        for round_num in range(3):
            pairings = generate_swiss_round(players, history)
            assert len(pairings) >= 2  # 5 players = 2 pairings + 1 bye
            # Simulate results: first player always wins
            for p in pairings:
                history.append(_match(p.participant_a_id, p.participant_b_id, 6, 3))
