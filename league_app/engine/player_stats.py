"""Player statistics engine.

Computes per-player statistics from match results:
- Win rate
- Head-to-head records
- Most frequent opponents/teammates
- Elo rating progression

Pure functions — no database access.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from .standings import MatchResult


@dataclass
class PlayerStats:
    """Aggregated statistics for a single player."""

    participant_id: UUID
    matches_played: int = 0
    games_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    win_rate: float = 0.0
    opponents: list[tuple[UUID, int]] = field(default_factory=list)  # (opponent_id, count)
    h2h: dict[UUID, dict] = field(default_factory=dict)  # opponent_id → {wins, draws, losses}


@dataclass
class EloSnapshot:
    """Single data point in Elo progression."""

    match_index: int
    rating: float
    opponent_id: UUID


def compute_player_stats(
    participant_id: UUID,
    match_results: list[MatchResult],
) -> PlayerStats:
    """Compute statistics for a single player across all matches."""
    stats = PlayerStats(participant_id=participant_id)
    opponent_counter: Counter = Counter()
    h2h: dict[UUID, dict] = {}

    for match in match_results:
        # Determine which side this player is on
        if match.participant_a_id == participant_id:
            opponent_id = match.participant_b_id
            side = "a"
        elif match.participant_b_id == participant_id:
            opponent_id = match.participant_a_id
            side = "b"
        else:
            continue

        stats.matches_played += 1
        opponent_counter[opponent_id] += 1

        if opponent_id not in h2h:
            h2h[opponent_id] = {"wins": 0, "draws": 0, "losses": 0}

        for game in match.games:
            stats.games_played += 1
            my_score = game.score_a if side == "a" else game.score_b
            their_score = game.score_b if side == "a" else game.score_a
            stats.goals_for += my_score
            stats.goals_against += their_score

            if my_score > their_score:
                stats.wins += 1
                h2h[opponent_id]["wins"] += 1
            elif my_score < their_score:
                stats.losses += 1
                h2h[opponent_id]["losses"] += 1
            else:
                stats.draws += 1
                h2h[opponent_id]["draws"] += 1

    total_games = stats.wins + stats.draws + stats.losses
    stats.win_rate = round(stats.wins / total_games, 3) if total_games > 0 else 0.0
    stats.opponents = opponent_counter.most_common()
    stats.h2h = h2h

    return stats


def compute_elo_progression(
    participant_id: UUID,
    match_results: list[MatchResult],
    k_factor: float = 32,
    initial_rating: float = 1000,
) -> list[EloSnapshot]:
    """Compute Elo rating progression for a player over time."""
    import math

    ratings: dict[UUID, float] = {}
    snapshots: list[EloSnapshot] = []
    match_idx = 0

    for match in match_results:
        if match.participant_a_id == participant_id:
            me, opp = match.participant_a_id, match.participant_b_id
            side = "a"
        elif match.participant_b_id == participant_id:
            me, opp = match.participant_b_id, match.participant_a_id
            side = "b"
        else:
            continue

        if me not in ratings:
            ratings[me] = initial_rating
        if opp not in ratings:
            ratings[opp] = initial_rating

        for game in match.games:
            ra, rb = ratings[me], ratings[opp]
            ea = 1.0 / (1.0 + math.pow(10, (rb - ra) / 400))

            my_score = game.score_a if side == "a" else game.score_b
            their_score = game.score_b if side == "a" else game.score_a
            sa = 1.0 if my_score > their_score else (0.0 if my_score < their_score else 0.5)

            ratings[me] += k_factor * (sa - ea)
            ratings[opp] += k_factor * ((1 - sa) - (1 - ea))

        match_idx += 1
        snapshots.append(EloSnapshot(
            match_index=match_idx,
            rating=round(ratings[me], 1),
            opponent_id=opp,
        ))

    return snapshots
