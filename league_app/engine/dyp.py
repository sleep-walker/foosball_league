"""DYP (Draw Your Partner) team drawing engine.

Generates random teams of two from a list of players, then pairs those
teams into matches.

Two modes:
- **DYP** — fully random teams each round, tries to avoid repeating
  the same partnership.
- **Monster DYP** — same as DYP but additionally avoids repeating
  the same *opponent* pair (team vs team).

Pure functions — no database access.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from uuid import UUID


@dataclass
class DrawnTeam:
    """A team produced by the draw."""

    player_1_id: UUID
    player_2_id: UUID

    @property
    def pair_key(self) -> frozenset[UUID]:
        return frozenset((self.player_1_id, self.player_2_id))


@dataclass
class TeamPairing:
    """A match between two drawn teams."""

    team_a: DrawnTeam
    team_b: DrawnTeam


def _used_partnerships(history: list[list[DrawnTeam]]) -> set[frozenset[UUID]]:
    """Return all partnerships that have occurred in previous rounds."""
    return {team.pair_key for round_teams in history for team in round_teams}


def draw_dyp_teams(
    player_ids: list[UUID],
    history: list[list[DrawnTeam]] | None = None,
    max_retries: int = 50,
) -> list[DrawnTeam]:
    """Draw random pairs from player_ids.

    Tries to avoid repeating partnerships from ``history``.
    If the number of players is odd, the last player is left out (bye).
    """
    if len(player_ids) < 2:
        return []

    history = history or []
    used = _used_partnerships(history)

    best_teams: list[DrawnTeam] = []
    best_repeats = float("inf")

    for _ in range(max_retries):
        shuffled = list(player_ids)
        random.shuffle(shuffled)
        teams = []
        for i in range(0, len(shuffled) - 1, 2):
            teams.append(DrawnTeam(player_1_id=shuffled[i], player_2_id=shuffled[i + 1]))
        repeats = sum(1 for t in teams if t.pair_key in used)
        if repeats == 0:
            return teams
        if repeats < best_repeats:
            best_repeats = repeats
            best_teams = teams

    return best_teams


def pair_teams(teams: list[DrawnTeam]) -> list[TeamPairing]:
    """Pair teams into matches (adjacent pairs)."""
    pairings = []
    for i in range(0, len(teams) - 1, 2):
        pairings.append(TeamPairing(team_a=teams[i], team_b=teams[i + 1]))
    return pairings


def draw_monster_dyp_teams(
    player_ids: list[UUID],
    team_history: list[list[DrawnTeam]] | None = None,
    matchup_history: list[list[TeamPairing]] | None = None,
    max_retries: int = 100,
) -> tuple[list[DrawnTeam], list[TeamPairing]]:
    """Monster DYP: draw teams AND pair them, avoiding repeat partnerships
    AND repeat matchups.

    Returns (teams, pairings).
    """
    if len(player_ids) < 4:
        teams = draw_dyp_teams(player_ids, team_history)
        return teams, pair_teams(teams)

    team_history = team_history or []
    matchup_history = matchup_history or []

    used_matchups: set[frozenset[frozenset[UUID]]] = set()
    for round_pairings in matchup_history:
        for mp in round_pairings:
            used_matchups.add(frozenset((mp.team_a.pair_key, mp.team_b.pair_key)))

    best_teams: list[DrawnTeam] = []
    best_pairings: list[TeamPairing] = []
    best_score = float("inf")

    for _ in range(max_retries):
        teams = draw_dyp_teams(player_ids, team_history, max_retries=1)
        if not teams:
            continue
        random.shuffle(teams)
        pairings = pair_teams(teams)
        # Score: count repeated partnerships + repeated matchups
        used_partnerships = _used_partnerships(team_history)
        p_repeats = sum(1 for t in teams if t.pair_key in used_partnerships)
        m_repeats = sum(
            1 for p in pairings
            if frozenset((p.team_a.pair_key, p.team_b.pair_key)) in used_matchups
        )
        score = p_repeats * 10 + m_repeats
        if score == 0:
            return teams, pairings
        if score < best_score:
            best_score = score
            best_teams = teams
            best_pairings = pairings

    return best_teams, best_pairings
