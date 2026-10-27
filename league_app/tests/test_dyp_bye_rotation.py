"""Regression tests for review finding M7 — the DYP bye rotates.

``count_games_played`` only looked at ``player_a_id`` / ``player_b_id`` and
carried a comment admitting it could not handle team matches.  A DYP doubles
tournament keys every match by team, so the count stayed zero for everybody,
and the bye-assignment logic in ``draw_swiss_round``
(``max(playing_ids, key=games_played.get)``) therefore always returned the
same first player: in a 5-player DYP tournament one unlucky player sat out
every single round.

The helper now takes the team→players mapping (``_team_player_map``, the one
lookup shared by standings display, the bye counter and bracket seeding) and
attributes team matches to their actual members.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.tournaments.router import _get_tournament_service
from league_app.domain import entities as e
from league_app.domain.tournament_helpers import count_games_played
from league_app.tests.testlib import create_running_tournament, register_and_login

P = [UUID(int=i) for i in range(1, 7)]
TEAM_1, TEAM_2 = uuid4(), uuid4()


# ---------------------------------------------------------------------------
# domain/tournament_helpers.py
# ---------------------------------------------------------------------------


class TestCountGamesPlayed:
    def test_singles_matches_are_counted(self):
        matches = [e.Match(uuid=uuid4(), player_a_id=P[0], player_b_id=P[1])]
        assert count_games_played(matches, P[:3]) == {P[0]: 1, P[1]: 1, P[2]: 0}

    def test_team_match_counts_for_every_member(self):
        matches = [e.Match(uuid=uuid4(), team_a_id=TEAM_1, team_b_id=TEAM_2)]
        team_players = {TEAM_1: [P[0], P[1]], TEAM_2: [P[2], P[3]]}
        assert count_games_played(matches, P[:5], team_players) == {
            P[0]: 1, P[1]: 1, P[2]: 1, P[3]: 1, P[4]: 0,
        }

    def test_scheduled_team_match_already_counts(self):
        """A drawn match is a game given out, score or no score."""
        matches = [
            e.Match(uuid=uuid4(), team_a_id=TEAM_1, team_b_id=TEAM_2,
                    status="scheduled"),
        ]
        counts = count_games_played(
            matches, P[:4], {TEAM_1: [P[0], P[1]], TEAM_2: [P[2], P[3]]},
        )
        assert set(counts.values()) == {1}

    def test_unknown_team_is_ignored(self):
        matches = [e.Match(uuid=uuid4(), team_a_id=TEAM_1, team_b_id=TEAM_2)]
        assert count_games_played(matches, P[:2], {TEAM_1: [P[0], P[1]]}) == {
            P[0]: 1, P[1]: 1,
        }

    def test_players_outside_the_list_are_ignored(self):
        matches = [e.Match(uuid=uuid4(), team_a_id=TEAM_1, team_b_id=TEAM_2)]
        team_players = {TEAM_1: [P[0], P[1]], TEAM_2: [P[2], P[3]]}
        assert count_games_played(matches, [P[0]], team_players) == {P[0]: 1}


# ---------------------------------------------------------------------------
# TournamentService.draw_swiss_round — the bye actually moves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dyp_bye_rotates_across_rounds(
    client: AsyncClient, session: AsyncSession,
):
    """5 players in DYP doubles: one sits out per round, a different one."""
    headers, org_id = await register_and_login(client, "m7_dyp@test.com")
    t = await create_running_tournament(
        client, headers, "M7Dyp", players=5, player_mode="doubles",
    )
    svc = _get_tournament_service(session)
    all_players = set(t["player_ids"])

    async def bye_of(round_number: int) -> UUID:
        team_players = await svc._team_player_map(t["tournament_id"])
        matches = [
            m for m in await svc._matches.list_by_stage(t["stage_id"])
            if m.round_number == round_number
        ]
        assert matches, f"round {round_number} was not drawn"
        playing = {
            pid
            for m in matches
            for team_id in (m.team_a_id, m.team_b_id)
            for pid in team_players.get(team_id, ())
        }
        sitting = all_players - playing
        assert len(sitting) == 1, f"expected exactly one bye, got {sitting}"
        return sitting.pop()

    # Round 1 was drawn by POST /start; draw four more.
    byes = [await bye_of(1)]
    for round_number in range(2, 6):
        await svc.draw_swiss_round(t["tournament_id"], t["stage_id"], org_id)
        byes.append(await bye_of(round_number))

    assert len(set(byes)) > 1, f"the bye never rotated: {byes}"
    # Nobody sits out twice before everybody has sat out once.
    assert len(set(byes)) == 5, f"the bye did not visit every player: {byes}"

    # ...and the load really is even: 5 rounds, 5 players, 4 games each.
    team_players = await svc._team_player_map(t["tournament_id"])
    counts = count_games_played(
        await svc._matches.list_by_stage(t["stage_id"]),
        list(all_players),
        team_players,
    )
    assert set(counts.values()) == {4}, counts


@pytest.mark.asyncio
async def test_singles_bye_still_rotates(
    client: AsyncClient, session: AsyncSession,
):
    """Regression guard for the singles path, which was already correct."""
    headers, org_id = await register_and_login(client, "m7_singles@test.com")
    t = await create_running_tournament(client, headers, "M7Singles", players=5)
    svc = _get_tournament_service(session)
    all_players = set(t["player_ids"])

    byes = []
    for round_number in range(1, 6):
        if round_number > 1:
            await svc.draw_swiss_round(t["tournament_id"], t["stage_id"], org_id)
        matches = [
            m for m in await svc._matches.list_by_stage(t["stage_id"])
            if m.round_number == round_number
        ]
        playing = {m.player_a_id for m in matches} | {m.player_b_id for m in matches}
        (sitting,) = all_players - playing
        byes.append(sitting)

    assert len(set(byes)) == 5, f"the bye did not visit every player: {byes}"
