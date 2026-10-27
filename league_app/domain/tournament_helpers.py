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
    matches: list[e.Match],
    player_ids: list[UUID],
    team_players: dict[UUID, list[UUID]] | None = None,
) -> dict[UUID, int]:
    """Count how many matches each player has been drawn into.

    Doubles matches are keyed by team, not by player, so attributing them
    needs ``team_players`` — a mapping of team uuid to its members (review
    finding M7).  Without it every player in a DYP tournament counted zero
    games and the bye never rotated: ``max()`` over an all-zero mapping
    always returns the first player in the list.

    Every match that has been *drawn* counts, played or not: sitting out is
    about who was given a game, not about who has already entered a score.
    """
    counts: dict[UUID, int] = {pid: 0 for pid in player_ids}
    team_players = team_players or {}
    for m in matches:
        participants: list[UUID] = [
            pid for pid in (m.player_a_id, m.player_b_id) if pid
        ]
        for team_id in (m.team_a_id, m.team_b_id):
            if team_id:
                participants.extend(team_players.get(team_id, ()))
        for pid in participants:
            if pid in counts:
                counts[pid] += 1
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


def team_player_map(teams: list[e.Team]) -> dict[UUID, list[UUID]]:
    """Map each team uuid to the player ids it is made of."""
    return {
        team.uuid: [pid for pid in (team.player_1_id, team.player_2_id) if pid]
        for team in teams
    }


def build_participant_history(
    matches: list[e.Match],
    team_players: dict[UUID, list[UUID]] | None = None,
) -> list[standings_engine.MatchResult]:
    """Convert finished matches into *player-level* MatchResult records.

    A doubles match is stored against a team, but the participant whose
    record matters is the player: in DYP the team is redrawn every round, so
    a team uuid stops meaning anything the moment the round is over.  Keying
    stats on it made every round's ephemeral team look like a brand-new
    participant with exactly one match (review findings M8/M9).

    Every team match is therefore decomposed into one result per member —
    member *i* of side A against member *i* of side B, each carrying the
    team's games, which is how the standings screen has always displayed
    doubles.  This is the single implementation of that decomposition:
    standings display, league Elo/win-loss aggregation and bracket seeding
    all go through it, so they cannot disagree about who a participant is.

    A team whose members are not in ``team_players`` is skipped rather than
    silently falling back to the team uuid: mixing the two identities is
    exactly the bug this function exists to prevent.
    """
    team_players = team_players or {}
    results: list[standings_engine.MatchResult] = []
    for m in matches:
        if m.status != "finished":
            continue
        games = [
            standings_engine.GameResult(g.score_a, g.score_b) for g in m.games
        ]
        if m.team_a_id and m.team_b_id:
            players_a = team_players.get(m.team_a_id) or []
            players_b = team_players.get(m.team_b_id) or []
            if not players_a or not players_b:
                continue
            # Pair up: players_a[i] vs players_b[i]; each player gets exactly
            # one result carrying the team's score.
            for i in range(max(len(players_a), len(players_b))):
                pa = players_a[i] if i < len(players_a) else players_a[0]
                pb = players_b[i] if i < len(players_b) else players_b[0]
                results.append(standings_engine.MatchResult(
                    participant_a_id=pa, participant_b_id=pb, games=games,
                ))
        elif m.player_a_id and m.player_b_id:
            results.append(standings_engine.MatchResult(
                participant_a_id=m.player_a_id,
                participant_b_id=m.player_b_id,
                games=games,
            ))
    return results


def participant_ids(
    match_results: list[standings_engine.MatchResult],
) -> set[UUID]:
    """Every participant that appears in ``match_results``."""
    return {
        pid
        for result in match_results
        for pid in (result.participant_a_id, result.participant_b_id)
    }
