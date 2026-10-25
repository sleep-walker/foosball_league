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
    rng: random.Random | None = None,
) -> list[DrawnTeam]:
    """Draw random pairs from player_ids.

    Tries to avoid repeating partnerships from ``history``.
    If the number of players is odd, the last player is left out (bye).

    ``rng`` lets a caller inject a seeded ``random.Random`` for reproducible
    draws; when omitted the global ``random`` module is used, which is the
    production default.
    """
    if len(player_ids) < 2:
        return []

    history = history or []
    used = _used_partnerships(history)
    draw = rng or random

    best_teams: list[DrawnTeam] = []
    best_repeats = float("inf")

    for _ in range(max_retries):
        shuffled = list(player_ids)
        draw.shuffle(shuffled)
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
    rng: random.Random | None = None,
) -> tuple[list[DrawnTeam], list[TeamPairing]]:
    """Monster DYP: draw teams AND pair them, avoiding repeat partnerships
    AND repeat matchups.

    ``rng`` lets a caller inject a seeded ``random.Random`` for reproducible
    draws; when omitted the global ``random`` module is used.

    Returns (teams, pairings).
    """
    if len(player_ids) < 4:
        teams = draw_dyp_teams(player_ids, team_history, rng=rng)
        return teams, pair_teams(teams)

    team_history = team_history or []
    matchup_history = matchup_history or []
    draw = rng or random

    used_matchups: set[frozenset[frozenset[UUID]]] = set()
    for round_pairings in matchup_history:
        for mp in round_pairings:
            used_matchups.add(frozenset((mp.team_a.pair_key, mp.team_b.pair_key)))

    best_teams: list[DrawnTeam] = []
    best_pairings: list[TeamPairing] = []
    best_score = float("inf")

    for _ in range(max_retries):
        teams = draw_dyp_teams(player_ids, team_history, max_retries=1, rng=rng)
        if not teams:
            continue
        draw.shuffle(teams)
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



def draw_monster_dyp_next_round(
    advancing_pairs: list[tuple[UUID, UUID | None]],
    rng: random.Random | None = None,
) -> list[DrawnTeam]:
    """Reshuffle advancing players into new pairs for the next elimination round.

    Hard constraint: no new pair may contain both players from the same input
    ``advancing_pair`` — i.e. former teammates must end up on opposite teams.

    ``advancing_pairs`` items represent the teams that won the previous round.
    A pair may have ``None`` as its second player when the team advanced via
    a bye; that lone player participates in the reshuffle as a free agent.

    ``rng`` lets a caller inject a seeded ``random.Random`` for reproducible
    reshuffles; when omitted the global ``random`` module is used.

    Raises ``ValueError`` when the constraint cannot be satisfied (e.g. a
    single advancing pair with no free agents — the only possible pairing
    would re-pair the original teammates).
    """
    if not advancing_pairs:
        return []

    draw = rng or random

    # Flatten into players and remember which input-pair each came from so the
    # constraint check is fast.  A free-agent (bye) gets its own group id so it
    # never conflicts with anyone.
    players: list[UUID] = []
    group_of: dict[UUID, int] = {}
    for idx, pair in enumerate(advancing_pairs):
        a, b = pair
        if a is None:
            continue
        players.append(a)
        group_of[a] = idx
        if b is not None:
            players.append(b)
            group_of[b] = idx

    if len(players) < 2:
        return []

    def _violates(pairs: list[tuple[UUID, UUID]]) -> bool:
        return any(group_of[a] == group_of[b] for a, b in pairs)

    # Exhaustive solver: build pairings recursively, prune on constraint.
    def _solve(remaining: list[UUID]) -> list[tuple[UUID, UUID]] | None:
        if not remaining:
            return []
        head = remaining[0]
        for j in range(1, len(remaining)):
            cand = remaining[j]
            if group_of[head] == group_of[cand]:
                continue
            rest = remaining[1:j] + remaining[j + 1 :]
            sub = _solve(rest)
            if sub is not None:
                return [(head, cand)] + sub
        return None

    # Build pool of candidate player lists to attempt:
    #  - even count: just the full list,
    #  - odd count: try dropping each player in turn (one will be the bye).
    if len(players) % 2 == 0:
        candidate_pools = [players]
    else:
        candidate_pools = [
            players[:i] + players[i + 1 :] for i in range(len(players))
        ]

    for pool in candidate_pools:
        n = len(pool)
        # Quick path: random retries (cheap for typical 4–16 players).
        for _ in range(200):
            shuffled = list(pool)
            draw.shuffle(shuffled)
            pairs = [(shuffled[i], shuffled[i + 1]) for i in range(0, n, 2)]
            if not _violates(pairs):
                return [DrawnTeam(player_1_id=a, player_2_id=b) for a, b in pairs]
        # Deterministic fallback for this pool.
        solution = _solve(pool)
        if solution is not None:
            return [DrawnTeam(player_1_id=a, player_2_id=b) for a, b in solution]

    raise ValueError(
        "Monster DYP reshuffle constraint cannot be satisfied: "
        "former teammates cannot all be split apart with the given pool."
    )
