"""Table assignment engine.

Assigns matches to available tables, applying soft constraints:

1. Pick from tables with status == ACTIVE (not IN_USE, not INACTIVE).
2. If ``rotate_tables`` is enabled:
   a. Filter out tables where either participant played in the previous round.
   b. Among remaining, prefer a table *type* the participants haven't used yet
      (or used least frequently).
3. If no table survives all filters, relax constraints and pick the best
   remaining option.

Pure functions — no database access.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class TableInfo:
    uuid: UUID
    name: str
    number: int
    table_type: Optional[str]
    status: str  # "active" | "in_use" | "inactive"


@dataclass
class TableHistoryEntry:
    """Records that a participant played on a specific table in a round."""
    participant_id: UUID
    table_uuid: UUID
    table_type: Optional[str]
    round_number: int


def assign_tables(
    matches_needing_tables: list[tuple[UUID, list[UUID]]],  # (match_uuid, [participant_ids])
    available_tables: list[TableInfo],
    history: list[TableHistoryEntry] | None = None,
    rotate_tables: bool = True,
) -> dict[UUID, UUID]:
    """Assign tables to matches.

    Args:
        matches_needing_tables: List of (match_uuid, [participant_a_id, participant_b_id, ...]).
        available_tables: All tables for the tournament.
        history: Previous table assignments.
        rotate_tables: Whether to apply rotation constraints.

    Returns:
        Mapping of match_uuid → table_uuid.
    """
    history = history or []
    assignments: dict[UUID, UUID] = {}
    used_tables: set[UUID] = set()

    # Only consider tables that are currently active
    free_tables = [t for t in available_tables if t.status == "active"]

    if not free_tables:
        return assignments

    # Pre-compute history lookups
    last_round = max((h.round_number for h in history), default=0)
    # Tables used by each participant in the last round
    last_round_tables: dict[UUID, set[UUID]] = {}
    # Count of table types used by each participant across all rounds
    type_counts: dict[UUID, Counter] = {}

    for h in history:
        if h.round_number == last_round:
            last_round_tables.setdefault(h.participant_id, set()).add(h.table_uuid)
        if h.table_type:
            type_counts.setdefault(h.participant_id, Counter())[h.table_type] += 1

    for match_uuid, participant_ids in matches_needing_tables:
        candidates = [t for t in free_tables if t.uuid not in used_tables]
        if not candidates:
            break  # No more tables available

        if rotate_tables and participant_ids:
            best = _pick_best_table(candidates, participant_ids, last_round_tables, type_counts)
        else:
            best = candidates[0]

        assignments[match_uuid] = best.uuid
        used_tables.add(best.uuid)

    return assignments


def _pick_best_table(
    candidates: list[TableInfo],
    participant_ids: list[UUID],
    last_round_tables: dict[UUID, set[UUID]],
    type_counts: dict[UUID, Counter],
) -> TableInfo:
    """Pick the best table for the given participants."""

    # Step 1: filter out tables where any participant played last round
    not_repeated = [
        t for t in candidates
        if not any(
            t.uuid in last_round_tables.get(pid, set())
            for pid in participant_ids
        )
    ]
    pool = not_repeated if not_repeated else candidates

    # Step 2: prefer table type least used by participants
    if len(pool) > 1:
        typed = [t for t in pool if t.table_type is not None]
        if typed:
            def _type_score(t: TableInfo) -> int:
                return sum(
                    type_counts.get(pid, Counter()).get(t.table_type, 0)
                    for pid in participant_ids
                )
            typed.sort(key=_type_score)
            return typed[0]

    return pool[0]
