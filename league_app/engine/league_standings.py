"""League standings engine.

Computes league-level leaderboards according to the league's scoring_type.

Supported modes:
- **placement_points** — sum of points awarded by tournament placement.
- **elo** — Elo rating adjusted after every game.
- **win_loss** — simple points for wins/draws/losses across all games.

All modes support **score erosion** — older results gradually lose
weight.  Configure via ``erosion_factor`` in the scoring config
(0.0 = no erosion, 1.0 = full erosion of oldest results).

Pure functions — no database access.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from .standings import GameResult, MatchResult


def _erosion_weight(index: int, total: int, erosion_factor: float) -> float:
    """Compute weight for result at ``index`` out of ``total``.

    With erosion_factor=0 all weights are 1.0.
    With erosion_factor=1.0 the oldest result has weight ~0, newest ~1.
    """
    if erosion_factor <= 0 or total <= 1:
        return 1.0
    # Linear decay: oldest=1-erosion, newest=1.0
    return 1.0 - erosion_factor * (1.0 - index / (total - 1))


@dataclass
class LeagueStandingRow:
    participant_id: UUID
    score: float = 0.0
    tournaments_played: int = 0
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0


@dataclass
class TournamentPlacement:
    """A player's final placement in a tournament."""

    participant_id: UUID
    place: int  # 1-based


# --- Placement points ---


def compute_placement_standings(
    placements: list[list[TournamentPlacement]],
    config: dict[str, Any] | None = None,
) -> list[LeagueStandingRow]:
    """Compute league standings from tournament placements.

    ``config`` example: {"1": 10, "2": 7, "3": 5, "4": 4, "default": 1}
    Each key is a placement (as string), "default" is for unranked participants.
    """
    config = config or {"1": 10, "2": 7, "3": 5, "4": 4, "default": 1}
    default_pts = config.get("default", 1)
    erosion = float(config.get("erosion_factor", 0))

    rows: dict[UUID, LeagueStandingRow] = {}
    total_tournaments = len(placements)

    for t_idx, tournament_results in enumerate(placements):
        weight = _erosion_weight(t_idx, total_tournaments, erosion)
        for tp in tournament_results:
            if tp.participant_id not in rows:
                rows[tp.participant_id] = LeagueStandingRow(
                    participant_id=tp.participant_id
                )
            row = rows[tp.participant_id]
            row.score += config.get(str(tp.place), default_pts) * weight
            row.tournaments_played += 1

    # Round scores for clean display
    for row in rows.values():
        row.score = round(row.score, 1)

    return sorted(rows.values(), key=lambda r: r.score, reverse=True)


# --- Elo ---


def compute_elo_ratings(
    match_results: list[MatchResult],
    config: dict[str, Any] | None = None,
) -> list[LeagueStandingRow]:
    """Compute Elo ratings from individual game results.

    ``config`` example: {"k_factor": 32, "initial_rating": 1000}
    """
    config = config or {}
    k = config.get("k_factor", 32)
    initial = config.get("initial_rating", 1000)

    ratings: dict[UUID, float] = {}
    stats: dict[UUID, LeagueStandingRow] = {}

    def _ensure(pid: UUID) -> None:
        if pid not in ratings:
            ratings[pid] = initial
            stats[pid] = LeagueStandingRow(participant_id=pid, score=initial)

    for match in match_results:
        a, b = match.participant_a_id, match.participant_b_id
        _ensure(a)
        _ensure(b)

        for game in match.games:
            ra, rb = ratings[a], ratings[b]
            ea = 1.0 / (1.0 + math.pow(10, (rb - ra) / 400))
            eb = 1.0 - ea

            if game.score_a > game.score_b:
                sa, sb = 1.0, 0.0
                stats[a].wins += 1
                stats[b].losses += 1
            elif game.score_b > game.score_a:
                sa, sb = 0.0, 1.0
                stats[b].wins += 1
                stats[a].losses += 1
            else:
                sa, sb = 0.5, 0.5
                stats[a].draws += 1
                stats[b].draws += 1

            ratings[a] += k * (sa - ea)
            ratings[b] += k * (sb - eb)

        stats[a].matches_played += 1
        stats[b].matches_played += 1

    for pid, row in stats.items():
        row.score = round(ratings[pid], 1)

    return sorted(stats.values(), key=lambda r: r.score, reverse=True)


# --- Win/Loss ---


def compute_win_loss_standings(
    match_results: list[MatchResult],
    config: dict[str, Any] | None = None,
) -> list[LeagueStandingRow]:
    """Simple points-based standings from individual games.

    ``config`` example: {"points_for_win": 3, "points_for_draw": 1, "points_for_loss": 0}
    """
    config = config or {}
    pw = config.get("points_for_win", 3)
    pd = config.get("points_for_draw", 1)
    pl = config.get("points_for_loss", 0)
    erosion = float(config.get("erosion_factor", 0))

    rows: dict[UUID, LeagueStandingRow] = {}
    total = len(match_results)

    def _ensure(pid: UUID) -> LeagueStandingRow:
        if pid not in rows:
            rows[pid] = LeagueStandingRow(participant_id=pid)
        return rows[pid]

    for m_idx, match in enumerate(match_results):
        weight = _erosion_weight(m_idx, total, erosion)
        a_row = _ensure(match.participant_a_id)
        b_row = _ensure(match.participant_b_id)
        a_row.matches_played += 1
        b_row.matches_played += 1

        for game in match.games:
            if game.score_a > game.score_b:
                a_row.wins += 1
                a_row.score += pw * weight
                b_row.losses += 1
                b_row.score += pl * weight
            elif game.score_b > game.score_a:
                b_row.wins += 1
                b_row.score += pw * weight
                a_row.losses += 1
                a_row.score += pl * weight
            else:
                a_row.draws += 1
                a_row.score += pd * weight
                b_row.draws += 1
                b_row.score += pd * weight

    for row in rows.values():
        row.score = round(row.score, 1)

    return sorted(rows.values(), key=lambda r: r.score, reverse=True)
