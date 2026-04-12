"""Score validation and match completion logic.

Validates game scores against stage rules and determines when a match is
finished (best-of-N wins reached).

Pure functions — no database access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class GameScore:
    """A score to validate."""

    score_a: int
    score_b: int


@dataclass
class ValidationResult:
    """Result of score validation."""

    valid: bool
    error: Optional[str] = None


@dataclass
class MatchStatus:
    """Current status of a match (wins per side)."""

    wins_a: int
    wins_b: int
    best_of: int
    is_finished: bool
    winner_side: Optional[str] = None  # "a" | "b" | None


def validate_game_score(
    score: GameScore,
    rules: dict[str, Any] | None = None,
    is_decider: bool = False,
) -> ValidationResult:
    """Validate a single game score against stage rules.

    Rules keys:
    - ``points_per_game`` (default 6): target score
    - ``draw_allowed`` (default False): whether draws are allowed
    - ``margin_in_decider`` (default 2): required margin in deciding games
    """
    rules = rules or {}
    target = rules.get("points_per_game", 6)
    draw_allowed = rules.get("draw_allowed", False)
    margin = rules.get("margin_in_decider", 2) if is_decider else 0

    a, b = score.score_a, score.score_b

    if a < 0 or b < 0:
        return ValidationResult(valid=False, error="Scores cannot be negative")

    # Draw check
    if a == b:
        if draw_allowed and a == target - 1:
            # e.g. 5:5 when target is 6
            return ValidationResult(valid=True)
        if not draw_allowed:
            return ValidationResult(valid=False, error="Draws are not allowed")
        return ValidationResult(valid=False, error=f"Draw must be {target-1}:{target-1}")

    # Someone won
    winner_score = max(a, b)
    loser_score = min(a, b)

    if is_decider and margin > 0:
        # Decider: winner must reach at least target and lead by margin
        if winner_score < target:
            return ValidationResult(
                valid=False,
                error=f"Winner must reach at least {target} points",
            )
        if winner_score - loser_score < margin:
            return ValidationResult(
                valid=False,
                error=f"Decider game requires a margin of at least {margin}",
            )
        return ValidationResult(valid=True)

    # Normal game: winner must have exactly target, loser less
    if winner_score != target:
        return ValidationResult(
            valid=False,
            error=f"Winner must have exactly {target} points",
        )
    if loser_score >= target:
        return ValidationResult(
            valid=False,
            error=f"Loser must have fewer than {target} points",
        )
    return ValidationResult(valid=True)


def compute_match_status(
    game_scores: list[GameScore],
    best_of: int = 1,
) -> MatchStatus:
    """Compute the current match status from game scores.

    Returns wins per side and whether the match is finished.
    """
    wins_a = sum(1 for g in game_scores if g.score_a > g.score_b)
    wins_b = sum(1 for g in game_scores if g.score_b > g.score_a)
    needed = (best_of // 2) + 1

    finished = wins_a >= needed or wins_b >= needed
    winner = None
    if wins_a >= needed:
        winner = "a"
    elif wins_b >= needed:
        winner = "b"

    return MatchStatus(
        wins_a=wins_a,
        wins_b=wins_b,
        best_of=best_of,
        is_finished=finished,
        winner_side=winner,
    )


def is_decider_game(game_scores: list[GameScore], best_of: int) -> bool:
    """Check if the next game would be a decider (match-deciding game)."""
    wins_a = sum(1 for g in game_scores if g.score_a > g.score_b)
    wins_b = sum(1 for g in game_scores if g.score_b > g.score_a)
    needed = (best_of // 2) + 1
    return wins_a == needed - 1 and wins_b == needed - 1
