"""Regression tests for review findings M8 and M9 — one DYP identity.

Both findings come from the same question: *who is a participant in a DYP
doubles tournament?*  The code answered it twice, differently.

* ``get_stage_standings`` (the UI and public endpoint) decomposes teams
  into players, but ``generate_bracket`` computed its own ranking keyed on
  ``team_id`` — so the organizer saw one order on screen and the bracket
  seeded another, and the seeded "teams" were DYP teams that stop existing
  when the round ends (M8).
* ``LeagueService._collect_league_matches`` keyed on
  ``team_a_id or player_a_id``, so every round's brand-new team uuid
  entered the Elo/win-loss table as a fresh participant with exactly one
  match (M9).

The answer is now the player, everywhere: ``build_participant_history`` is
the single decomposition, the bracket seeds from the same
``get_stage_standings`` ranking the organizer sees, and the league
aggregates players.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.tournaments.router import _get_tournament_service
from league_app.domain import entities as e
from league_app.domain.tournament_helpers import (
    build_participant_history,
    participant_ids,
    team_player_map,
)
from league_app.tests.testlib import (
    API,
    assert_response_code,
    create_running_tournament,
    register_and_login,
)

P = [UUID(int=i) for i in range(1, 9)]
TEAM_A, TEAM_B = uuid4(), uuid4()


def _game(score_a: int, score_b: int) -> e.Game:
    return e.Game(uuid=uuid4(), match_id=uuid4(), score_a=score_a,
                  score_b=score_b, is_finished=True)


# ---------------------------------------------------------------------------
# domain/tournament_helpers.py — the shared decomposition
# ---------------------------------------------------------------------------


class TestBuildParticipantHistory:
    TEAM_PLAYERS = {TEAM_A: [P[0], P[1]], TEAM_B: [P[2], P[3]]}

    def _team_match(self, status: str = "finished") -> e.Match:
        return e.Match(
            uuid=uuid4(), team_a_id=TEAM_A, team_b_id=TEAM_B,
            status=status, games=[_game(6, 2)],
        )

    def test_team_match_becomes_one_result_per_member(self):
        results = build_participant_history(
            [self._team_match()], self.TEAM_PLAYERS,
        )
        assert [
            (r.participant_a_id, r.participant_b_id) for r in results
        ] == [(P[0], P[2]), (P[1], P[3])]
        assert all((r.games[0].score_a, r.games[0].score_b) == (6, 2) for r in results)

    def test_no_team_id_survives_the_decomposition(self):
        results = build_participant_history(
            [self._team_match()], self.TEAM_PLAYERS,
        )
        assert TEAM_A not in participant_ids(results)
        assert TEAM_B not in participant_ids(results)
        assert participant_ids(results) == {P[0], P[1], P[2], P[3]}

    def test_unfinished_match_is_skipped(self):
        assert build_participant_history(
            [self._team_match(status="scheduled")], self.TEAM_PLAYERS,
        ) == []

    def test_unknown_team_is_skipped_rather_than_keyed_by_team(self):
        """Mixing team and player keys is the bug, so never fall back."""
        assert build_participant_history([self._team_match()], {}) == []

    def test_singles_match_passes_through(self):
        match = e.Match(
            uuid=uuid4(), player_a_id=P[0], player_b_id=P[1],
            status="finished", games=[_game(6, 1)],
        )
        results = build_participant_history([match])
        assert participant_ids(results) == {P[0], P[1]}

    def test_team_player_map_builds_the_lookup(self):
        teams = [
            e.Team(uuid=TEAM_A, player_1_id=P[0], player_2_id=P[1]),
            e.Team(uuid=TEAM_B, player_1_id=P[2], player_2_id=P[3]),
        ]
        assert team_player_map(teams) == {
            TEAM_A: [P[0], P[1]], TEAM_B: [P[2], P[3]],
        }


# ---------------------------------------------------------------------------
# M8 — seeding a doubles bracket from a player ranking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dyp_ranking_is_paired_strongest_with_weakest(
    client: AsyncClient, session: AsyncSession,
):
    headers, _ = await register_and_login(client, "m8_pairs@test.com")
    t = await create_running_tournament(
        client, headers, "M8Pairs", players=4, player_mode="doubles",
    )
    svc = _get_tournament_service(session)
    ranked = list(t["player_ids"])

    team_ids = await svc._bracket_teams_from_ranking(
        t["tournament_id"], ranked,
        source_stage=None, source_matches=[], team_players={}, advancement=None,
    )

    team_players = await svc._team_player_map(t["tournament_id"])
    assert [team_players[tid] for tid in team_ids] == [
        [ranked[0], ranked[3]], [ranked[1], ranked[2]],
    ]


@pytest.mark.asyncio
async def test_odd_ranking_leaves_the_last_seed_out(
    client: AsyncClient, session: AsyncSession,
):
    headers, _ = await register_and_login(client, "m8_odd@test.com")
    t = await create_running_tournament(
        client, headers, "M8Odd", players=5, player_mode="doubles",
    )
    svc = _get_tournament_service(session)
    ranked = list(t["player_ids"])

    team_ids = await svc._bracket_teams_from_ranking(
        t["tournament_id"], ranked,
        source_stage=None, source_matches=[], team_players={}, advancement=None,
    )

    team_players = await svc._team_player_map(t["tournament_id"])
    seeded_players = {pid for tid in team_ids for pid in team_players[tid]}
    assert len(team_ids) == 2
    assert ranked[4] not in seeded_players, "the lowest seed misses out"


@pytest.mark.asyncio
async def test_fixed_teams_keep_their_identity(
    client: AsyncClient, session: AsyncSession,
):
    """A fixed-team stage seeds its real teams, ordered by best member."""
    headers, _ = await register_and_login(client, "m8_fixed@test.com")
    t = await create_running_tournament(
        client, headers, "M8Fixed", players=4, player_mode="doubles",
    )
    svc = _get_tournament_service(session)
    players = list(t["player_ids"])

    team_1, team_2 = uuid4(), uuid4()
    team_players = {team_1: [players[1], players[2]], team_2: [players[0], players[3]]}
    source_stage = e.Stage(
        uuid=uuid4(), tournament_id=t["tournament_id"], name="Group",
        team_formation="fixed",
    )
    source_matches = [
        e.Match(uuid=uuid4(), team_a_id=team_1, team_b_id=team_2, status="finished"),
    ]

    # Ranking: players[0] on top, so their team leads the seeding.
    seeded = await svc._bracket_teams_from_ranking(
        t["tournament_id"], players,
        source_stage=source_stage, source_matches=source_matches,
        team_players=team_players, advancement=None,
    )
    assert seeded == [team_2, team_1]


@pytest.mark.asyncio
async def test_singles_bracket_seeds_in_the_displayed_order(
    client: AsyncClient, session: AsyncSession,
):
    """The bracket order equals the standings order the organizer sees."""
    headers, org_id = await register_and_login(client, "m8_singles@test.com")
    t = await create_running_tournament(client, headers, "M8Singles", players=4)

    # Play the whole first round so everybody has a record.
    r = await client.get(
        f"{API}/tournaments/{t['tournament_id']}/matches/", headers=headers,
    )
    assert_response_code(r, 200)
    for i, match in enumerate(r.json()):
        r2 = await client.patch(
            f"{API}/matches/{match['uuid']}/score",
            json={"score_a": 6, "score_b": i}, headers=headers,
        )
        assert_response_code(r2, 200)

    svc = _get_tournament_service(session)
    standings = await svc.get_stage_standings(t["tournament_id"], t["stage_id"])
    expected = [row.participant_id for row in standings]

    r = await client.post(
        f"{API}/tournaments/{t['tournament_id']}/stages/",
        json={
            "name": "Playoff", "stage_type": "elimination", "ordering": 1,
            "tournament_id": str(t["tournament_id"]), "rules": {"best_of": 1},
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    elim_id = UUID(r.json()["uuid"])

    created = await svc.generate_bracket(t["tournament_id"], elim_id, org_id)
    first_round = sorted(
        (m for m in created if m.round_number == 1),
        key=lambda m: m.bracket_position or 0,
    )
    # Standard bracket layout: position i pairs seed i with seed (n-1-i),
    # so the seeding reads off as side A top-down then side B bottom-up.
    seeding = (
        [m.player_a_id for m in first_round]
        + [m.player_b_id for m in reversed(first_round)]
    )
    assert seeding == expected


@pytest.mark.asyncio
async def test_doubles_bracket_is_seeded_from_the_player_ranking(
    client: AsyncClient, session: AsyncSession,
):
    """DYP: the bracket no longer seeds last round's ephemeral teams."""
    headers, org_id = await register_and_login(client, "m8_doubles@test.com")
    t = await create_running_tournament(
        client, headers, "M8Doubles", players=4, player_mode="doubles",
    )
    svc = _get_tournament_service(session)

    group_matches = await svc._matches.list_by_stage(t["stage_id"])
    group_team_ids = {
        tid for m in group_matches for tid in (m.team_a_id, m.team_b_id) if tid
    }
    r = await client.get(
        f"{API}/tournaments/{t['tournament_id']}/matches/", headers=headers,
    )
    assert_response_code(r, 200)
    for match in r.json():
        r2 = await client.patch(
            f"{API}/matches/{match['uuid']}/score",
            json={"score_a": 6, "score_b": 1}, headers=headers,
        )
        assert_response_code(r2, 200)

    standings = await svc.get_stage_standings(t["tournament_id"], t["stage_id"])
    ranked = [row.participant_id for row in standings]
    assert set(ranked) == set(t["player_ids"]), "standings rank players, not teams"

    r = await client.post(
        f"{API}/tournaments/{t['tournament_id']}/stages/",
        json={
            "name": "Playoff", "stage_type": "elimination", "ordering": 1,
            "tournament_id": str(t["tournament_id"]), "rules": {"best_of": 1},
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    elim_id = UUID(r.json()["uuid"])

    created = await svc.generate_bracket(t["tournament_id"], elim_id, org_id)
    seeded_team_ids = [
        tid for m in sorted(created, key=lambda m: m.bracket_position or 0)
        for tid in (m.team_a_id, m.team_b_id) if tid
    ]
    assert seeded_team_ids, "the bracket was seeded with teams"
    assert not (set(seeded_team_ids) & group_team_ids), (
        "the bracket reused the group stage's ephemeral DYP teams"
    )

    team_players = await svc._team_player_map(t["tournament_id"])
    # Seeded teams are the advancing players re-paired strongest+weakest.
    assert [sorted(team_players[tid], key=ranked.index) for tid in seeded_team_ids] == [
        [ranked[0], ranked[3]], [ranked[1], ranked[2]],
    ]


# ---------------------------------------------------------------------------
# M9 — league stats are keyed by player
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dyp_league_table_counts_players_not_ephemeral_teams(
    client: AsyncClient, session: AsyncSession,
):
    """Two DYP rounds: 4 players with 2 matches each, not 4 teams with 1."""
    headers, org_id = await register_and_login(client, "m9_league@test.com")
    r = await client.post(
        f"{API}/leagues/",
        json={"name": "M9 League", "scoring_type": "win_loss"},
        headers=headers,
    )
    assert_response_code(r, 200)
    league_id = r.json()["uuid"]

    t = await create_running_tournament(
        client, headers, "M9Dyp", players=4, player_mode="doubles",
    )
    r = await client.patch(
        f"{API}/tournaments/{t['tournament_id']}",
        json={"league_id": league_id}, headers=headers,
    )
    assert_response_code(r, 200)

    svc = _get_tournament_service(session)
    round_team_ids: set[UUID] = set()
    for round_number in (1, 2):
        if round_number > 1:
            await svc.draw_swiss_round(t["tournament_id"], t["stage_id"], org_id)
        matches = [
            m for m in await svc._matches.list_by_stage(t["stage_id"])
            if m.round_number == round_number
        ]
        assert len(matches) == 1, "4 players in doubles → one match per round"
        round_team_ids |= {
            tid for m in matches for tid in (m.team_a_id, m.team_b_id) if tid
        }
        r = await client.patch(
            f"{API}/matches/{matches[0].uuid}/score",
            json={"score_a": 6, "score_b": 2}, headers=headers,
        )
        assert_response_code(r, 200)

    assert len(round_team_ids) == 4, "DYP really did create a new team per round"

    r = await client.get(f"{API}/leagues/{league_id}/standings", headers=headers)
    assert_response_code(r, 200)
    rows = r.json()

    assert {UUID(row["participant_id"]) for row in rows} == set(t["player_ids"])
    assert all(row["matches_played"] == 2 for row in rows), rows
    assert sum(row["wins"] for row in rows) == 4, "two matches, two winners each"
