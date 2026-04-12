"""Single-elimination bracket generator.

Takes a seeded list of participants and produces a bracket of matches.
Supports consolation match (3rd-place playoff).

Pure functions — no database access.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass
class BracketMatch:
    """A single match slot in the bracket."""

    position: int  # 1-based position in the bracket
    round_number: int  # 1 = first round, 2 = quarter-final, etc.
    participant_a_id: Optional[UUID] = None
    participant_b_id: Optional[UUID] = None
    is_consolation: bool = False  # True for 3rd-place match
    # Filled after the match is played:
    winner_id: Optional[UUID] = None
    loser_id: Optional[UUID] = None


@dataclass
class Bracket:
    """The complete bracket."""

    matches: list[BracketMatch] = field(default_factory=list)
    has_consolation: bool = False

    def get_round(self, round_number: int) -> list[BracketMatch]:
        return [m for m in self.matches if m.round_number == round_number]

    @property
    def rounds_count(self) -> int:
        if not self.matches:
            return 0
        return max(m.round_number for m in self.matches)


def _next_power_of_2(n: int) -> int:
    return 1 << (n - 1).bit_length()


def generate_bracket(
    seeded_ids: list[UUID],
    consolation: bool = True,
) -> Bracket:
    """Generate a single-elimination bracket from a seeded participant list.

    The first participant is the top seed. Seeding follows the standard
    tournament bracket layout (1 vs N, 2 vs N-1, etc.) with byes for
    non-power-of-2 counts.

    Args:
        seeded_ids: Participants ordered by seed (index 0 = top seed).
        consolation: Whether to include a 3rd-place match.

    Returns:
        A Bracket with all match slots.
    """
    n = len(seeded_ids)
    if n < 2:
        return Bracket()

    bracket_size = _next_power_of_2(n)
    num_rounds = int(math.log2(bracket_size))
    num_byes = bracket_size - n

    # Build first-round seedings using standard bracket positions
    # Seed 1 vs Seed N, Seed 2 vs Seed N-1, etc.
    slots: list[Optional[UUID]] = [None] * bracket_size
    for i, pid in enumerate(seeded_ids):
        slots[i] = pid

    # Pair seeds: 0 vs (bracket_size-1), 1 vs (bracket_size-2), etc.
    first_round_pairs: list[tuple[Optional[UUID], Optional[UUID]]] = []
    for i in range(bracket_size // 2):
        first_round_pairs.append((slots[i], slots[bracket_size - 1 - i]))

    bracket = Bracket(has_consolation=consolation)
    pos = 0

    # Generate first round
    advancing: list[Optional[UUID]] = []
    for a, b in first_round_pairs:
        pos += 1
        if b is None:
            # Bye — participant 'a' advances automatically
            advancing.append(a)
        else:
            bracket.matches.append(
                BracketMatch(
                    position=pos,
                    round_number=1,
                    participant_a_id=a,
                    participant_b_id=b,
                )
            )
            advancing.append(None)  # To be filled when match is played

    # Generate subsequent rounds
    for round_num in range(2, num_rounds + 1):
        next_advancing: list[Optional[UUID]] = []
        for i in range(0, len(advancing), 2):
            pos += 1
            a = advancing[i] if i < len(advancing) else None
            b = advancing[i + 1] if i + 1 < len(advancing) else None
            # Only create match if both slots could be filled
            bracket.matches.append(
                BracketMatch(
                    position=pos,
                    round_number=round_num,
                    participant_a_id=a,
                    participant_b_id=b,
                )
            )
            next_advancing.append(None)
        advancing = next_advancing

    # Add consolation match (3rd place)
    if consolation and num_rounds >= 2:
        pos += 1
        bracket.matches.append(
            BracketMatch(
                position=pos,
                round_number=num_rounds,
                is_consolation=True,
            )
        )

    return bracket


def advance_winner(
    bracket: Bracket, match_position: int, winner_id: UUID, loser_id: UUID
) -> None:
    """Record the winner of a match and propagate them into the next round.

    The winner is placed into the corresponding slot of the next-round match.
    If this was a semi-final and consolation is enabled, the loser is placed
    into the consolation match.
    """
    match = next((m for m in bracket.matches if m.position == match_position), None)
    if match is None:
        raise ValueError(f"Match at position {match_position} not found")

    match.winner_id = winner_id
    match.loser_id = loser_id

    # Find the next-round match this winner feeds into
    current_round = match.round_number
    same_round = sorted(
        [m for m in bracket.matches if m.round_number == current_round and not m.is_consolation],
        key=lambda m: m.position,
    )
    idx_in_round = same_round.index(match)

    next_round = [
        m for m in bracket.matches
        if m.round_number == current_round + 1 and not m.is_consolation
    ]
    next_round.sort(key=lambda m: m.position)

    if next_round:
        next_match = next_round[idx_in_round // 2]
        if idx_in_round % 2 == 0:
            next_match.participant_a_id = winner_id
        else:
            next_match.participant_b_id = winner_id

    # Consolation: semi-final losers go to the 3rd-place match
    is_semi = current_round == bracket.rounds_count - 1 if bracket.rounds_count >= 2 else False
    if is_semi and bracket.has_consolation:
        consolation = next(
            (m for m in bracket.matches if m.is_consolation), None
        )
        if consolation is not None:
            if consolation.participant_a_id is None:
                consolation.participant_a_id = loser_id
            else:
                consolation.participant_b_id = loser_id
