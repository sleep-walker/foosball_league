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
    - ``draw_allowed`` (default True): whether draws are allowed
    - ``margin_required`` (default 0): required win margin (0 = no margin rule)
    - ``score_cap`` (default 0): maximum score (0 = no cap, only with margin)
    - ``margin_in_decider`` (default 2): margin for deciding games in best-of-N
    """
    rules = rules or {}
    target = rules.get("points_per_game", 6)
    draw_allowed = rules.get("draw_allowed", True)
    # margin_required in rules applies to ALL games in the stage
    # margin_in_decider applies only when is_decider=True (best-of-N last game)
    margin = rules.get("margin_required", 0)
    if is_decider and margin == 0:
        margin = rules.get("margin_in_decider", 2)
    score_cap = rules.get("score_cap", 0)

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

    # Margin/cap rules: apply when a margin is in effect
    use_margin = margin > 0
    if use_margin:
        # Winner must reach at least target and lead by margin, capped at score_cap
        if winner_score < target:
            return ValidationResult(
                valid=False,
                error=f"Winner must reach at least {target} points",
            )
        if score_cap > 0 and winner_score > score_cap:
            return ValidationResult(
                valid=False,
                error=f"Score cannot exceed cap of {score_cap}",
            )
        if winner_score - loser_score < margin:
            return ValidationResult(
                valid=False,
                error=f"Winner must lead by at least {margin} points",
            )
        # At score_cap, exact margin is required: e.g. 10:8 when cap=10, margin=2
        if score_cap > 0 and winner_score == score_cap and loser_score != score_cap - margin:
            return ValidationResult(
                valid=False,
                error=f"At cap {score_cap}, loser must have {score_cap - margin}",
            )
        return ValidationResult(valid=True)

    # Normal game: winner must have exactly target points.
    # The game ends the moment a player reaches target OR a draw occurs at
    # (target-1):(target-1).  Therefore the loser can have at most (target-2)
    # when draws are allowed, or (target-1) when draws are not allowed.
    if winner_score != target:
        return ValidationResult(
            valid=False,
            error=f"Winner must have exactly {target} points",
        )
    max_loser = target - 2 if draw_allowed else target - 1
    if loser_score > max_loser:
        return ValidationResult(
            valid=False,
            error=(
                f"Loser cannot have {loser_score} points — "
                f"game ends at {target-1}:{target-1} (draw) or {target}:{max_loser} (win)"
                if draw_allowed
                else f"Loser cannot have more than {max_loser} points in a game to {target}"
            ),
        )
    return ValidationResult(valid=True)


def compute_match_status(
    game_scores: list[GameScore],
    best_of: int = 1,
) -> MatchStatus:
    """Compute the current match status from game scores.

    Returns wins per side and whether the match is finished.

    A match is finished as soon as one side reaches ``best_of // 2 + 1``
    game wins, **or** once ``best_of`` games have been played.  The second
    condition is what guarantees termination: individual games may be draws
    (``5:5`` under the default rules), and a match in which every game is
    drawn would otherwise never reach the required number of wins and would
    keep accepting games forever (review finding M6).

    When the game cap is reached without either side reaching the required
    number of wins, the side with more game wins takes the match; if the
    game wins are level too, the match is a draw (``winner_side == "draw"``),
    which is exactly how a drawn single game has always been reported for
    ``best_of == 1``.
    """
    wins_a = sum(1 for g in game_scores if g.score_a > g.score_b)
    wins_b = sum(1 for g in game_scores if g.score_b > g.score_a)
    needed = (best_of // 2) + 1

    # The hard cap: a best-of-N match is never longer than N games.  It also
    # subsumes the old ``best_of == 1`` special case (one game, then done,
    # a draw being a valid outcome).
    cap = max(best_of, 1)
    cap_reached = len(game_scores) >= cap

    finished = wins_a >= needed or wins_b >= needed or cap_reached

    winner = None
    if wins_a >= needed or (cap_reached and wins_a > wins_b):
        winner = "a"
    elif wins_b >= needed or (cap_reached and wins_b > wins_a):
        winner = "b"
    elif finished and wins_a == wins_b:
        winner = "draw"

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
