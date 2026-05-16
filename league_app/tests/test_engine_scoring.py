"""Tests for league_app.engine.scoring — pure functions, no DB needed."""

from league_app.engine.scoring import (
    GameScore,
    compute_match_status,
    is_decider_game,
    validate_game_score,
)


class TestValidateGroupGame:
    """Group stage: game to 6, draws allowed at 5:5."""

    RULES = {"points_per_game": 6, "draw_allowed": True}

    def test_normal_win(self):
        r = validate_game_score(GameScore(6, 3), self.RULES)
        assert r.valid

    def test_draw_5_5(self):
        r = validate_game_score(GameScore(5, 5), self.RULES)
        assert r.valid

    def test_invalid_draw_4_4(self):
        r = validate_game_score(GameScore(4, 4), self.RULES)
        assert not r.valid

    def test_winner_must_have_6(self):
        r = validate_game_score(GameScore(5, 3), self.RULES)
        assert not r.valid

    def test_zero_zero_invalid(self):
        r = validate_game_score(GameScore(0, 0), self.RULES)
        assert not r.valid

    def test_6_5_invalid_when_draws_allowed(self):
        """6:5 impossible — game should have ended at 5:5 draw."""
        r = validate_game_score(GameScore(6, 5), self.RULES)
        assert not r.valid

    def test_5_6_invalid_when_draws_allowed(self):
        r = validate_game_score(GameScore(5, 6), self.RULES)
        assert not r.valid

    def test_negative_score(self):
        r = validate_game_score(GameScore(-1, 3), self.RULES)
        assert not r.valid


class TestValidateEliminationGame:
    """Elimination: game to 6, no draws."""

    RULES = {"points_per_game": 6, "draw_allowed": False}

    def test_normal_win(self):
        r = validate_game_score(GameScore(6, 4), self.RULES)
        assert r.valid

    def test_6_5_valid_in_elimination(self):
        """6:5 is valid when draws are NOT allowed — game continues past 5:5."""
        r = validate_game_score(GameScore(6, 5), self.RULES)
        assert r.valid

    def test_draw_not_allowed(self):
        r = validate_game_score(GameScore(5, 5), self.RULES)
        assert not r.valid


class TestValidateDeciderGame:
    """Deciding game: must have margin >= 2."""

    RULES = {"points_per_game": 6, "draw_allowed": False, "margin_in_decider": 2}

    def test_clear_win(self):
        r = validate_game_score(GameScore(6, 3), self.RULES, is_decider=True)
        assert r.valid

    def test_margin_exactly_2(self):
        r = validate_game_score(GameScore(6, 4), self.RULES, is_decider=True)
        assert r.valid

    def test_margin_too_small(self):
        r = validate_game_score(GameScore(6, 5), self.RULES, is_decider=True)
        assert not r.valid

    def test_extended_play(self):
        # 8:6 — both past target, margin=2 → OK
        r = validate_game_score(GameScore(8, 6), self.RULES, is_decider=True)
        assert r.valid

    def test_extended_play_margin_too_small(self):
        r = validate_game_score(GameScore(7, 6), self.RULES, is_decider=True)
        assert not r.valid


class TestShortGames:
    """Games to 5, draw at 4:4."""

    RULES = {"points_per_game": 5, "draw_allowed": True}

    def test_win(self):
        assert validate_game_score(GameScore(5, 2), self.RULES).valid

    def test_draw(self):
        assert validate_game_score(GameScore(4, 4), self.RULES).valid

    def test_5_4_invalid(self):
        """5:4 impossible with draws allowed — game ends at 4:4."""
        assert not validate_game_score(GameScore(5, 4), self.RULES).valid


class TestMarginAndCap:
    """Game to 8, win by 2, cap at 10 (e.g. Liga B rules)."""

    RULES = {
        "points_per_game": 8,
        "draw_allowed": False,
        "margin_required": 2,
        "score_cap": 10,
    }

    def test_clean_win(self):
        assert validate_game_score(GameScore(8, 3), self.RULES).valid

    def test_8_6_win_by_2(self):
        assert validate_game_score(GameScore(8, 6), self.RULES).valid

    def test_9_7_win_by_2(self):
        assert validate_game_score(GameScore(9, 7), self.RULES).valid

    def test_10_8_cap_win(self):
        assert validate_game_score(GameScore(10, 8), self.RULES).valid

    def test_8_7_margin_too_small(self):
        assert not validate_game_score(GameScore(8, 7), self.RULES).valid

    def test_9_8_margin_too_small(self):
        assert not validate_game_score(GameScore(9, 8), self.RULES).valid

    def test_11_9_over_cap(self):
        assert not validate_game_score(GameScore(11, 9), self.RULES).valid


class TestMatchStatus:
    def test_best_of_1_win(self):
        s = compute_match_status([GameScore(6, 3)], best_of=1)
        assert s.is_finished
        assert s.winner_side == "a"

    def test_best_of_3_in_progress(self):
        s = compute_match_status([GameScore(6, 3)], best_of=3)
        assert not s.is_finished
        assert s.wins_a == 1

    def test_best_of_3_finished_2_0(self):
        s = compute_match_status([GameScore(6, 3), GameScore(6, 4)], best_of=3)
        assert s.is_finished
        assert s.winner_side == "a"

    def test_best_of_3_finished_2_1(self):
        scores = [GameScore(6, 3), GameScore(3, 6), GameScore(6, 4)]
        s = compute_match_status(scores, best_of=3)
        assert s.is_finished
        assert s.winner_side == "a"

    def test_best_of_5_needs_3(self):
        scores = [GameScore(6, 3), GameScore(6, 4)]
        s = compute_match_status(scores, best_of=5)
        assert not s.is_finished

    def test_best_of_5_finished(self):
        scores = [GameScore(6, 3), GameScore(3, 6), GameScore(6, 4), GameScore(6, 2)]
        s = compute_match_status(scores, best_of=5)
        assert s.is_finished
        assert s.winner_side == "a"


class TestIsDeciderGame:
    def test_tied_1_1_in_best_of_3(self):
        scores = [GameScore(6, 3), GameScore(3, 6)]
        assert is_decider_game(scores, best_of=3)

    def test_not_decider_1_0(self):
        scores = [GameScore(6, 3)]
        assert not is_decider_game(scores, best_of=3)

    def test_tied_2_2_in_best_of_5(self):
        scores = [GameScore(6, 3), GameScore(3, 6), GameScore(6, 4), GameScore(4, 6)]
        assert is_decider_game(scores, best_of=5)



class TestDefaultRules:
    """Default rules (no explicit config): draw_allowed=True, ppg=6."""

    def test_default_6_0_valid(self):
        assert validate_game_score(GameScore(6, 0), {}).valid

    def test_default_6_4_valid(self):
        assert validate_game_score(GameScore(6, 4), {}).valid

    def test_default_5_5_draw_valid(self):
        """Default allows draws at 5:5."""
        assert validate_game_score(GameScore(5, 5), {}).valid

    def test_default_6_5_invalid(self):
        """6:5 impossible — game ends at 5:5 draw."""
        r = validate_game_score(GameScore(6, 5), {})
        assert not r.valid

    def test_default_negative_invalid(self):
        r = validate_game_score(GameScore(-1, 6), {})
        assert not r.valid

    def test_default_7_3_invalid(self):
        r = validate_game_score(GameScore(7, 3), {})
        assert not r.valid