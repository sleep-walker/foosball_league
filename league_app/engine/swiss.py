"""Swiss-system pairing engine for group stages.

Given current standings and match history, produce the next round's pairings
while avoiding repeat matchups as much as possible.

This is a pure function — no database access.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from uuid import UUID

from .standings import MatchResult, compute_standings


@dataclass
class Pairing:
    """A single pairing for the next round."""

    participant_a_id: UUID
    participant_b_id: UUID


def _played_pairs(match_history: list[MatchResult]) -> set[frozenset[UUID]]:
    """Return a set of all pairs that have already played each other."""
    return {
        frozenset((m.participant_a_id, m.participant_b_id))
        for m in match_history
    }


def generate_swiss_round(
    participant_ids: list[UUID],
    match_history: list[MatchResult],
    rules: dict | None = None,
    rng: random.Random | None = None,
) -> list[Pairing]:
    """Generate pairings for the next Swiss round.

    Algorithm:
    1. Compute current standings (or use initial random order if no history).
    2. Walk down the sorted list and pair adjacent participants.
    3. If a pair has already played, try to swap with the next available
       participant to find a fresh matchup.
    4. If the number of participants is odd, the last one gets a bye (omitted
       from pairings).

    ``rng`` lets a caller inject a seeded ``random.Random`` so that the
    shuffled parts (initial order and participants without history, which
    also decide who gets the bye) are reproducible.  When omitted the global
    ``random`` module is used, which is the production default.

    Returns a list of Pairing objects.
    """
    if len(participant_ids) < 2:
        return []

    played = _played_pairs(match_history)
    draw = rng or random

    # Sort by standings if we have history, otherwise shuffle
    active_set = set(participant_ids)
    if match_history:
        standings = compute_standings(match_history, rules)
        # Only keep participants that are actually in this round
        ranked_ids = [r.participant_id for r in standings
                      if r.participant_id in active_set]
        # Add any participants that haven't played yet (not in standings)
        remaining = [p for p in participant_ids if p not in set(ranked_ids)]
        draw.shuffle(remaining)
        ordered = ranked_ids + remaining
    else:
        ordered = list(participant_ids)
        draw.shuffle(ordered)

    pairings: list[Pairing] = []
    used: set[UUID] = set()
    available = list(ordered)

    while len(available) >= 2:
        a = available.pop(0)
        if a in used:
            continue

        # Find the best opponent: first one not yet used and not a repeat
        paired = False
        for i, candidate in enumerate(available):
            if candidate in used:
                continue
            pair_key = frozenset((a, candidate))
            if pair_key not in played:
                pairings.append(Pairing(participant_a_id=a, participant_b_id=candidate))
                used.add(a)
                used.add(candidate)
                available.pop(i)
                paired = True
                break

        if not paired:
            # All remaining opponents are repeats — pick the closest in standings
            for i, candidate in enumerate(available):
                if candidate in used:
                    continue
                pairings.append(Pairing(participant_a_id=a, participant_b_id=candidate))
                used.add(a)
                used.add(candidate)
                available.pop(i)
                paired = True
                break

        if not paired:
            # Only one participant left — bye
            break

    return pairings
