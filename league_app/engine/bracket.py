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



# ---------------------------------------------------------------------------
# Double-elimination bracket
# ---------------------------------------------------------------------------


@dataclass
class DoubleEliminationBracket:
    """Double-elimination bracket with winners and losers brackets."""

    winners_bracket: Bracket = field(default_factory=Bracket)
    losers_bracket: Bracket = field(default_factory=Bracket)
    grand_final: Optional[BracketMatch] = None
    grand_final_reset: Optional[BracketMatch] = None  # if losers winner wins GF

    @property
    def all_matches(self) -> list[BracketMatch]:
        matches = list(self.winners_bracket.matches) + list(self.losers_bracket.matches)
        if self.grand_final:
            matches.append(self.grand_final)
        if self.grand_final_reset:
            matches.append(self.grand_final_reset)
        return matches


def generate_double_elimination_bracket(
    seeded_ids: list[UUID],
) -> DoubleEliminationBracket:
    """Generate a double-elimination bracket.

    Winners bracket: standard single-elimination (no consolation).
    Losers bracket: losers from each winners round drop into the losers
    bracket.  Losers bracket has roughly 2x as many rounds (each round
    alternates between "drop-down" rounds where winners-bracket losers
    enter, and "normal" rounds within losers bracket).
    Grand final: winners bracket champion vs losers bracket champion.
    Grand final reset: if the losers bracket champion wins the grand
    final, a reset match is played (the WB champion hasn't lost yet).

    Returns match slots — participants are filled as matches are played.
    """
    n = len(seeded_ids)
    if n < 2:
        return DoubleEliminationBracket()

    # Generate winners bracket (no consolation)
    wb = generate_bracket(seeded_ids, consolation=False)

    bracket_size = _next_power_of_2(n)
    wb_rounds = int(math.log2(bracket_size))

    # Generate losers bracket structure
    # Losers bracket has (wb_rounds - 1) * 2 rounds:
    #   Odd LB rounds: WB losers drop in + play against LB survivors
    #   Even LB rounds: LB internal matchups (halving)
    lb = Bracket()
    pos = max((m.position for m in wb.matches), default=0)

    lb_round_count = (wb_rounds - 1) * 2 if wb_rounds > 1 else 1
    # In losers bracket, first round has bracket_size // 2 players (R1 losers)
    # Each subsequent pair of rounds halves the count.
    lb_match_count_per_round: list[int] = []
    current_count = bracket_size // 2
    for lb_r in range(1, lb_round_count + 1):
        if lb_r % 2 == 1:
            # Drop-down round: same count (WB losers join)
            lb_match_count_per_round.append(current_count // 2)
        else:
            # Internal round: halve
            current_count = current_count // 2
            lb_match_count_per_round.append(current_count // 2)
            if current_count // 2 == 0:
                # Ensure at least 1 match in final LB rounds
                lb_match_count_per_round[-1] = max(1, lb_match_count_per_round[-1])

    for lb_round_idx, match_count in enumerate(lb_match_count_per_round, 1):
        for _ in range(max(1, match_count)):
            pos += 1
            lb.matches.append(BracketMatch(
                position=pos,
                round_number=lb_round_idx,
            ))

    # Grand final
    pos += 1
    gf = BracketMatch(position=pos, round_number=wb_rounds + lb_round_count + 1)

    # Grand final reset (optional — played only if LB champion wins GF)
    pos += 1
    gf_reset = BracketMatch(position=pos, round_number=wb_rounds + lb_round_count + 2)

    return DoubleEliminationBracket(
        winners_bracket=wb,
        losers_bracket=lb,
        grand_final=gf,
        grand_final_reset=gf_reset,
    )


def advance_winner_double_elim(
    de_bracket: DoubleEliminationBracket,
    match_position: int,
    winner_id: UUID,
    loser_id: UUID,
) -> None:
    """Record a result in a double-elimination bracket.

    - Winners bracket losers drop to losers bracket.
    - Losers bracket losers are eliminated.
    - Winners bracket champion goes to grand final.
    - Losers bracket champion goes to grand final.
    """
    wb = de_bracket.winners_bracket
    lb = de_bracket.losers_bracket

    # Check if match is in WB
    wb_match = next((m for m in wb.matches if m.position == match_position), None)
    if wb_match:
        wb_match.winner_id = winner_id
        wb_match.loser_id = loser_id

        # Advance winner in WB
        advance_winner(wb, match_position, winner_id, loser_id)

        # Drop loser to LB — find the corresponding LB drop-down round
        wb_round_matches = sorted(
            [m for m in wb.matches if m.round_number == wb_match.round_number],
            key=lambda m: m.position,
        )
        loser_idx = wb_round_matches.index(wb_match)

        # LB drop-down round = (wb_round - 1) * 2 + 1, 1-based
        lb_drop_round = (wb_match.round_number - 1) * 2 + 1 if wb_match.round_number > 1 else 1
        lb_round_matches = sorted(
            [m for m in lb.matches if m.round_number == lb_drop_round],
            key=lambda m: m.position,
        )
        if loser_idx < len(lb_round_matches):
            lb_target = lb_round_matches[loser_idx]
            if lb_target.participant_a_id is None:
                lb_target.participant_a_id = loser_id
            else:
                lb_target.participant_b_id = loser_id

        # If this was the WB final, winner goes to grand final
        if wb_match.round_number == wb.rounds_count:
            if de_bracket.grand_final:
                de_bracket.grand_final.participant_a_id = winner_id
        return

    # Check if match is in LB
    lb_match = next((m for m in lb.matches if m.position == match_position), None)
    if lb_match:
        lb_match.winner_id = winner_id
        lb_match.loser_id = loser_id  # eliminated

        # Advance winner in LB
        lb_same_round = sorted(
            [m for m in lb.matches if m.round_number == lb_match.round_number],
            key=lambda m: m.position,
        )
        idx = lb_same_round.index(lb_match)

        lb_next = sorted(
            [m for m in lb.matches if m.round_number == lb_match.round_number + 1],
            key=lambda m: m.position,
        )
        if lb_next:
            target = lb_next[idx // 2] if idx // 2 < len(lb_next) else lb_next[-1]
            if idx % 2 == 0:
                target.participant_a_id = winner_id
            else:
                target.participant_b_id = winner_id
        elif de_bracket.grand_final:
            # LB final winner goes to grand final
            de_bracket.grand_final.participant_b_id = winner_id
        return

    # Grand final
    if de_bracket.grand_final and de_bracket.grand_final.position == match_position:
        de_bracket.grand_final.winner_id = winner_id
        de_bracket.grand_final.loser_id = loser_id
        return