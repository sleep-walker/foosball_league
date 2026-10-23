"""Tests for league_app.engine.bracket — pure functions, no DB needed."""

from uuid import uuid4

from league_app.engine.bracket import (
    advance_winner,
    advance_winner_double_elim,
    generate_bracket,
    generate_double_elimination_bracket,
)

SEEDS = [uuid4() for _ in range(8)]


class TestGenerateBracket:
    def test_four_players(self):
        bracket = generate_bracket(SEEDS[:4])
        # 4 players: 2 first-round matches + 1 final + 1 consolation = 4
        assert len(bracket.matches) == 4
        assert bracket.rounds_count == 2
        r1 = bracket.get_round(1)
        assert len(r1) == 2
        # Seed 1 vs Seed 4
        assert r1[0].participant_a_id == SEEDS[0]
        assert r1[0].participant_b_id == SEEDS[3]
        # Seed 2 vs Seed 3
        assert r1[1].participant_a_id == SEEDS[1]
        assert r1[1].participant_b_id == SEEDS[2]

    def test_two_players(self):
        bracket = generate_bracket(SEEDS[:2])
        assert len(bracket.matches) == 1
        assert bracket.matches[0].participant_a_id == SEEDS[0]
        assert bracket.matches[0].participant_b_id == SEEDS[1]

    def test_one_player(self):
        bracket = generate_bracket(SEEDS[:1])
        assert len(bracket.matches) == 0

    def test_eight_players(self):
        bracket = generate_bracket(SEEDS)
        # 8 players: 4 QF + 2 SF + 1 F + 1 consolation = 8
        assert len(bracket.matches) == 8
        assert bracket.rounds_count == 3

    def test_no_consolation(self):
        bracket = generate_bracket(SEEDS[:4], consolation=False)
        assert not bracket.has_consolation
        assert all(not m.is_consolation for m in bracket.matches)
        # 2 first-round + 1 final = 3
        assert len(bracket.matches) == 3

    def test_three_players_with_bye(self):
        bracket = generate_bracket(SEEDS[:3])
        # 3 players → bracket_size=4, 1 bye
        # 1 first-round match (seed 2 vs seed 3) + 1 semi/final + 1 consolation
        r1 = bracket.get_round(1)
        # Only one actual first-round match (the other is a bye)
        assert len(r1) == 1


class TestAdvanceWinner:
    def test_four_player_bracket_flow(self):
        s1, s2, s3, s4 = SEEDS[:4]
        bracket = generate_bracket([s1, s2, s3, s4])

        r1 = bracket.get_round(1)
        # s1 beats s4
        advance_winner(bracket, r1[0].position, winner_id=s1, loser_id=s4)
        # s2 beats s3
        advance_winner(bracket, r1[1].position, winner_id=s2, loser_id=s3)

        # Final should have s1 vs s2
        final = [m for m in bracket.get_round(2) if not m.is_consolation]
        assert len(final) == 1
        assert final[0].participant_a_id == s1
        assert final[0].participant_b_id == s2

        # Consolation should have s4 vs s3
        consolation = [m for m in bracket.matches if m.is_consolation]
        assert len(consolation) == 1
        assert {consolation[0].participant_a_id, consolation[0].participant_b_id} == {
            s3,
            s4,
        }


class TestEdgeCases:
    def test_advance_invalid_position(self):
        bracket = generate_bracket(SEEDS[:4])
        try:
            advance_winner(bracket, 999, winner_id=SEEDS[0], loser_id=SEEDS[1])
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass



class TestDoubleEliminationGeneration:
    def test_4_players(self):
        seeds = [uuid4() for _ in range(4)]
        de = generate_double_elimination_bracket(seeds)
        assert len(de.winners_bracket.matches) > 0
        assert len(de.losers_bracket.matches) > 0
        assert de.grand_final is not None
        assert de.grand_final_reset is not None

    def test_8_players(self):
        seeds = [uuid4() for _ in range(8)]
        de = generate_double_elimination_bracket(seeds)
        # WB: 4 + 2 + 1 = 7 matches
        assert len(de.winners_bracket.matches) == 7
        assert len(de.losers_bracket.matches) > 0
        assert de.grand_final is not None
        # All matches have unique positions
        positions = [m.position for m in de.all_matches]
        assert len(positions) == len(set(positions))

    def test_2_players(self):
        seeds = [uuid4() for _ in range(2)]
        de = generate_double_elimination_bracket(seeds)
        assert len(de.winners_bracket.matches) == 1
        assert de.grand_final is not None

    def test_fewer_than_2(self):
        de = generate_double_elimination_bracket([uuid4()])
        assert len(de.all_matches) == 0


class TestDoubleEliminationAdvancement:
    def test_wb_loser_drops_to_lb(self):
        seeds = [uuid4() for _ in range(4)]
        de = generate_double_elimination_bracket(seeds)
        wb = de.winners_bracket
        # Play first WB match
        first = sorted(wb.matches, key=lambda m: m.position)[0]
        winner = first.participant_a_id
        loser = first.participant_b_id
        advance_winner_double_elim(de, first.position, winner, loser)
        # Loser should be in some LB match
        lb_participants = []
        for m in de.losers_bracket.matches:
            if m.participant_a_id:
                lb_participants.append(m.participant_a_id)
            if m.participant_b_id:
                lb_participants.append(m.participant_b_id)
        assert loser in lb_participants
