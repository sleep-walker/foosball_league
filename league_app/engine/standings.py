"""Standings calculation for group stages.

Given a list of finished matches (each with their games), compute a sorted
leaderboard according to the stage rules.

The standings engine is a pure function — it takes data in and returns results.
No database access happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class StandingRow:
    """One row in the group standings table."""

    participant_id: UUID  # player or team uuid
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    matches_played: int = 0
    sets_won: int = 0      # games/sets won within matches (tiebreaker)
    sets_lost: int = 0     # games/sets lost within matches

    @property
    def points(self) -> int:
        return self._pts_win * self.wins + self._pts_draw * self.draws + self._pts_loss * self.losses

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def sets_difference(self) -> int:
        return self.sets_won - self.sets_lost

    # set by compute_standings based on stage rules
    _pts_win: int = field(default=2, repr=False)
    _pts_draw: int = field(default=1, repr=False)
    _pts_loss: int = field(default=0, repr=False)


@dataclass
class MatchResult:
    """Minimal representation of a finished match needed for standings."""

    participant_a_id: UUID
    participant_b_id: UUID
    games: list[GameResult]


@dataclass
class GameResult:
    """Score of a single game within a match."""

    score_a: int
    score_b: int


def compute_standings(
    match_results: list[MatchResult],
    rules: dict[str, Any] | None = None,
    *,
    registered_player_ids: list[UUID] | None = None,
) -> list[StandingRow]:
    """Compute sorted group standings from match results.

    ``rules`` is the stage's ``rules`` JSON dict. Recognised keys:

    - ``points_for_win`` (default 2, matching Kickertool MonsterDYP standard)
    - ``points_for_draw`` (default 1)
    - ``points_for_loss`` (default 0)

    ``registered_player_ids`` — if provided, ensures every registered player
    appears in standings even if they haven't played any matches yet.
    """
    rules = rules or {}
    pts_win = rules.get("points_for_win", 2)
    pts_draw = rules.get("points_for_draw", 1)
    pts_loss = rules.get("points_for_loss", 0)

    rows: dict[UUID, StandingRow] = {}

    # Pre-populate rows for all registered players (so they appear even with 0 matches)
    if registered_player_ids:
        for pid in registered_player_ids:
            rows[pid] = StandingRow(participant_id=pid, _pts_win=pts_win, _pts_draw=pts_draw, _pts_loss=pts_loss)

    def _get(pid: UUID) -> StandingRow:
        if pid not in rows:
            rows[pid] = StandingRow(
                participant_id=pid,
                _pts_win=pts_win,
                _pts_draw=pts_draw,
                _pts_loss=pts_loss,
            )
        return rows[pid]

    for match in match_results:
        a = _get(match.participant_a_id)
        b = _get(match.participant_b_id)

        # Aggregate all games in the match
        total_a = sum(g.score_a for g in match.games)
        total_b = sum(g.score_b for g in match.games)

        a.goals_for += total_a
        a.goals_against += total_b
        b.goals_for += total_b
        b.goals_against += total_a
        a.matches_played += 1
        b.matches_played += 1

        # Determine match outcome by games won
        wins_a = sum(1 for g in match.games if g.score_a > g.score_b)
        wins_b = sum(1 for g in match.games if g.score_b > g.score_a)

        # Track sets (games within a match) for tiebreaking
        a.sets_won += wins_a
        a.sets_lost += wins_b
        b.sets_won += wins_b
        b.sets_lost += wins_a

        if wins_a > wins_b:
            a.wins += 1
            b.losses += 1
        elif wins_b > wins_a:
            b.wins += 1
            a.losses += 1
        else:
            # Draw (equal game wins — possible in group stage single-game matches)
            a.draws += 1
            b.draws += 1

    # Sort: points desc, sets_difference desc, goal_difference desc
    return sorted(
        rows.values(),
        key=lambda r: (r.points, r.sets_difference, r.goal_difference),
        reverse=True,
    )
