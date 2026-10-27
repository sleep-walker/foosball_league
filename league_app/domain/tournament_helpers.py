"""Pure helper functions extracted from TournamentService.

These were @staticmethods on the service — keeping them at module level
makes the service file shorter and the helpers individually testable
without instantiating the full TournamentService.
"""

from __future__ import annotations

from uuid import UUID

from league_app.domain import entities as e
from league_app.engine import standings as standings_engine


def count_games_played(
    matches: list[e.Match], player_ids: list[UUID]
) -> dict[UUID, int]:
    """Count how many matches each player has participated in."""
    counts: dict[UUID, int] = {pid: 0 for pid in player_ids}
    for m in matches:
        if m.player_a_id and m.player_a_id in counts:
            counts[m.player_a_id] += 1
        if m.player_b_id and m.player_b_id in counts:
            counts[m.player_b_id] += 1
        # For doubles: count team players too
        # (would need team lookup — for now we track at match level)
    return counts


def player_standings(
    matches: list[e.Match], player_ids: list[UUID]
) -> list[UUID]:
    """Rank players by points (3 win, 1 draw) for from_results pairing."""
    points: dict[UUID, int] = {pid: 0 for pid in player_ids}
    for m in matches:
        if m.status != "finished":
            continue
        a, b = m.player_a_id, m.player_b_id
        if a and b and a in points and b in points:
            sa = sum(g.score_a for g in (m.games or []))
            sb = sum(g.score_b for g in (m.games or []))
            if sa > sb:
                points[a] += 3
            elif sb > sa:
                points[b] += 3
            else:
                points[a] += 1
                points[b] += 1
    return sorted(player_ids, key=lambda pid: -points[pid])


def build_match_history(
    matches: list[e.Match],
) -> list[standings_engine.MatchResult]:
    """Convert *finished* domain matches into the engine's MatchResult records.

    Only matches with ``status == "finished"`` are converted.  The standings
    engine decides the outcome of a match from the games it carries, and a
    match that has not been played yet carries none — which the engine would
    read as ``wins_a == wins_b == 0``, i.e. a 0-0 draw, handing both sides a
    point they never earned and corrupting the Swiss pairing of the next
    round (review finding M4).

    Pairings that have merely been *drawn* still have to be remembered so
    that nobody is paired twice; that is what :func:`build_pair_history` is
    for.
    """
    results = []
    for m in matches:
        if m.status != "finished":
            continue
        a_id = m.team_a_id or m.player_a_id
        b_id = m.team_b_id or m.player_b_id
        if a_id and b_id:
            results.append(standings_engine.MatchResult(
                participant_a_id=a_id, participant_b_id=b_id,
                games=[
                    standings_engine.GameResult(g.score_a, g.score_b)
                    for g in m.games
                ],
            ))
    return results


def build_pair_history(
    matches: list[e.Match],
) -> list[tuple[UUID, UUID]]:
    """Every participant pair that has already been drawn against each other.

    Unlike :func:`build_match_history` this deliberately includes matches
    that are still ``scheduled`` or ``in_progress``: a pairing which is
    already on the schedule must not be drawn a second time just because
    its result has not been entered yet.
    """
    pairs: list[tuple[UUID, UUID]] = []
    for m in matches:
        a_id = m.team_a_id or m.player_a_id
        b_id = m.team_b_id or m.player_b_id
        if a_id and b_id:
            pairs.append((a_id, b_id))
    return pairs
