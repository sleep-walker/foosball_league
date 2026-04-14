"""Round-robin schedule generator.

Generates a complete schedule where every participant plays every other
participant exactly once.  Uses the circle method (Berger tables):
one participant is fixed, the rest rotate around a circle.

For odd participant counts, a BYE placeholder is added and matches
involving BYE are omitted.

Pure functions — no database access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class RoundRobinMatch:
    """A scheduled match in a round-robin tournament."""

    round_number: int
    participant_a_id: UUID
    participant_b_id: UUID


@dataclass
class RoundRobinSchedule:
    """Complete round-robin schedule."""

    rounds: list[list[RoundRobinMatch]]

    @property
    def total_matches(self) -> int:
        return sum(len(r) for r in self.rounds)


_BYE = UUID("00000000-0000-0000-0000-000000000000")


def generate_round_robin(
    participant_ids: list[UUID],
    double: bool = False,
) -> RoundRobinSchedule:
    """Generate a round-robin schedule.

    Args:
        participant_ids: List of participant UUIDs.
        double: If True, generate a double round-robin (home + away).

    Returns:
        RoundRobinSchedule with all rounds.
    """
    ids = list(participant_ids)
    if len(ids) < 2:
        return RoundRobinSchedule(rounds=[])

    # For odd number of participants, add a BYE
    has_bye = len(ids) % 2 != 0
    if has_bye:
        ids.append(_BYE)

    n = len(ids)
    rounds_count = n - 1

    # Circle method: fix ids[0], rotate the rest
    fixed = ids[0]
    rotating = ids[1:]

    rounds: list[list[RoundRobinMatch]] = []

    for round_idx in range(rounds_count):
        current = [fixed] + rotating
        round_matches: list[RoundRobinMatch] = []

        for i in range(n // 2):
            a = current[i]
            b = current[n - 1 - i]
            # Skip BYE matches
            if a == _BYE or b == _BYE:
                continue
            round_matches.append(RoundRobinMatch(
                round_number=round_idx + 1,
                participant_a_id=a,
                participant_b_id=b,
            ))

        rounds.append(round_matches)
        # Rotate: last element moves to position 1
        rotating = [rotating[-1]] + rotating[:-1]

    if double:
        # Add reverse fixtures
        reverse_rounds = []
        for orig_round in rounds:
            rev = []
            for m in orig_round:
                rev.append(RoundRobinMatch(
                    round_number=len(rounds) + m.round_number,
                    participant_a_id=m.participant_b_id,
                    participant_b_id=m.participant_a_id,
                ))
            reverse_rounds.append(rev)
        rounds.extend(reverse_rounds)

    return RoundRobinSchedule(rounds=rounds)
