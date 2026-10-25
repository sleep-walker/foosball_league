"""Tests for the injectable RNG (review finding N5).

Everything that shuffles in the draw path used to call the module-level
``random.shuffle()``, so no test could pin an outcome that depends on it:
who sits out a round, how Swiss orders participants without history, which
players end up on the same DYP team, how the bracket seeds are formed.

Each of those functions now takes an optional ``rng``.  These tests pass a
``random.Random(seed)`` and assert *exact* outcomes — the pinned values below
were produced by running the code, and they are the point of the exercise:
if the injected RNG were ignored (e.g. a call site slipped back to the global
module) these assertions would start failing instead of silently passing.

The first half is pure-function engine level; the second half drives the real
``TournamentService`` over the HTTP-created fixtures, proving that the
parameter is actually threaded from the service down into the engines.
"""

from __future__ import annotations

import random
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.teams.model import Team
from league_app.api.tournaments.router import _get_tournament_service
from league_app.engine.dyp import (
    DrawnTeam,
    draw_dyp_teams,
    draw_monster_dyp_next_round,
    draw_monster_dyp_teams,
    pair_teams,
)
from league_app.engine.swiss import generate_swiss_round
from league_app.tests.testlib import assert_response_code

API = "/api/v1"

# Fixed, ordered ids so that a pinned expectation can be written down as
# small integers instead of per-run uuid4() values.
IDS = [UUID(int=i) for i in range(1, 9)]


def _ints(*uuids: UUID) -> tuple[int, ...]:
    return tuple(u.int for u in uuids)


# ---------------------------------------------------------------------------
# engine/swiss.py — pairing order, and therefore the bye
# ---------------------------------------------------------------------------


class TestSwissSeededBye:
    """5 participants, no history: the shuffle decides who sits out."""

    def test_seed_pins_the_pairings_and_the_bye(self):
        pairings = generate_swiss_round(IDS[:5], [], rng=random.Random(0))
        assert [
            _ints(p.participant_a_id, p.participant_b_id) for p in pairings
        ] == [(3, 2), (1, 5)]
        paired = {p.participant_a_id for p in pairings} | {
            p.participant_b_id for p in pairings
        }
        assert [p for p in IDS[:5] if p not in paired] == [IDS[3]]  # id 4 byes

    def test_same_seed_twice_is_identical(self):
        first = generate_swiss_round(IDS[:5], [], rng=random.Random(1234))
        second = generate_swiss_round(IDS[:5], [], rng=random.Random(1234))
        assert first == second

    def test_the_seed_is_what_decides_the_bye(self):
        """Different seeds must move the bye around — otherwise the pinned
        assertion above could be passing for the wrong reason."""
        byes = set()
        for seed in range(6):
            pairings = generate_swiss_round(IDS[:5], [], rng=random.Random(seed))
            paired = {p.participant_a_id for p in pairings} | {
                p.participant_b_id for p in pairings
            }
            (bye,) = [p for p in IDS[:5] if p not in paired]
            byes.add(bye)
        assert len(byes) > 1

    def test_default_rng_is_the_global_module(self):
        """No ``rng`` argument must behave exactly as before: draw from the
        process-wide ``random`` module, so seeding it globally is reproducible.
        """
        random.seed(99)
        first = generate_swiss_round(IDS[:5], [])
        random.seed(99)
        second = generate_swiss_round(IDS[:5], [])
        assert first == second

    def test_injected_rng_does_not_consume_global_state(self):
        random.seed(99)
        state = random.getstate()
        generate_swiss_round(IDS[:5], [], rng=random.Random(5))
        assert random.getstate() == state


# ---------------------------------------------------------------------------
# engine/dyp.py — team drawing
# ---------------------------------------------------------------------------


class TestDypSeededDraw:
    def test_seed_pins_the_teams(self):
        teams = draw_dyp_teams(IDS, rng=random.Random(0))
        assert [_ints(t.player_1_id, t.player_2_id) for t in teams] == [
            (5, 2), (6, 3), (1, 4), (8, 7),
        ]

    def test_same_seed_twice_is_identical(self):
        assert draw_dyp_teams(IDS, rng=random.Random(7)) == draw_dyp_teams(
            IDS, rng=random.Random(7)
        )

    def test_different_seeds_draw_different_teams(self):
        drawn = {
            tuple(sorted(t.pair_key for t in draw_dyp_teams(IDS, rng=random.Random(s))))
            for s in range(4)
        }
        assert len(drawn) > 1

    def test_monster_dyp_seed_pins_teams_and_matchups(self):
        teams, pairings = draw_monster_dyp_teams(IDS, rng=random.Random(3))
        assert [_ints(t.player_1_id, t.player_2_id) for t in teams] == [
            (8, 3), (5, 4), (2, 7), (1, 6),
        ]
        assert [
            (
                _ints(p.team_a.player_1_id, p.team_a.player_2_id),
                _ints(p.team_b.player_1_id, p.team_b.player_2_id),
            )
            for p in pairings
        ] == [((8, 3), (5, 4)), ((2, 7), (1, 6))]

    def test_monster_dyp_next_round_seed_pins_the_reshuffle(self):
        advancing = [(IDS[i], IDS[i + 1]) for i in range(0, 8, 2)]
        teams = draw_monster_dyp_next_round(advancing, rng=random.Random(0))
        assert [_ints(t.player_1_id, t.player_2_id) for t in teams] == [
            (4, 8), (2, 3), (7, 6), (1, 5),
        ]
        # The hard constraint still holds under an injected RNG.
        old_keys = {frozenset(p) for p in advancing}
        assert all(t.pair_key not in old_keys for t in teams)

    def test_dyp_default_rng_is_the_global_module(self):
        random.seed(99)
        first = draw_dyp_teams(IDS)
        random.seed(99)
        second = draw_dyp_teams(IDS)
        assert first == second


class TestDypExhaustedRetries:
    """The "every draw repeats something" fallback, reached deterministically.

    When no draw can avoid a repeat, both DYP functions give up after
    ``max_retries`` and return the least-bad attempt.  That path used to be
    reached only by luck of the global RNG, which is exactly why measured
    coverage jittered run to run; with the partnerships exhausted on purpose
    it is now hit every time.
    """

    # All three ways of splitting four players into two pairs.
    ALL_PAIRINGS = [
        [(0, 1), (2, 3)],
        [(0, 2), (1, 3)],
        [(0, 3), (1, 2)],
    ]

    def _history(self):
        return [
            [DrawnTeam(player_1_id=IDS[a], player_2_id=IDS[b]) for a, b in pairing]
            for pairing in self.ALL_PAIRINGS
        ]

    def test_dyp_returns_the_least_bad_draw(self):
        teams = draw_dyp_teams(
            IDS[:4], history=self._history(), max_retries=5, rng=random.Random(1),
        )
        assert len(teams) == 2
        # Every partnership is already used, so the result necessarily repeats.
        used = {t.pair_key for round_teams in self._history() for t in round_teams}
        assert all(t.pair_key in used for t in teams)

    def test_monster_dyp_returns_the_least_bad_draw(self):
        history = self._history()
        teams, pairings = draw_monster_dyp_teams(
            IDS[:4],
            team_history=history,
            matchup_history=[pair_teams(round_teams) for round_teams in history],
            max_retries=5,
            rng=random.Random(1),
        )
        assert len(teams) == 2
        assert len(pairings) == 1


# ---------------------------------------------------------------------------
# TournamentService — the parameter is threaded all the way down
# ---------------------------------------------------------------------------


async def _auth(client: AsyncClient, email: str) -> tuple[dict, UUID]:
    r = await client.post(
        f"{API}/users/register", json={"email": email, "password": "password123"},
    )
    assert_response_code(r, 201)
    user_id = UUID(r.json()["id"])
    r = await client.post(
        f"{API}/users/login",
        data={"username": email, "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_response_code(r, 200)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user_id


async def _running_tournament(
    client: AsyncClient, headers: dict, name: str, *,
    players: int, player_mode: str = "singles",
) -> dict:
    """Create + start a tournament with ``players`` registered players."""
    r = await client.post(
        f"{API}/tournaments/",
        json={
            "name": name, "date": "2026-05-01", "player_mode": player_mode,
            "settings": {"table_count": 2},
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    player_ids = []
    for i in range(players):
        r = await client.post(
            f"{API}/players/", json={"nickname": f"{name}-p{i}"}, headers=headers,
        )
        assert_response_code(r, 200)
        player_ids.append(r.json()["uuid"])
    for player_id in player_ids:
        r = await client.post(
            f"{API}/tournaments/{t_id}/players/?player_id={player_id}", headers=headers,
        )
        assert_response_code(r, 200)

    r = await client.post(f"{API}/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)
    r = await client.get(f"{API}/tournaments/{t_id}", headers=headers)
    assert_response_code(r, 200)
    return {
        "t_id": UUID(t_id),
        "stage_id": UUID(r.json()["stages"][0]["uuid"]),
        "player_ids": [UUID(p) for p in player_ids],
    }


def _singles_pairs(matches) -> list[frozenset[UUID]]:
    return [frozenset((m.player_a_id, m.player_b_id)) for m in matches]


@pytest.mark.asyncio
async def test_seeded_redraw_is_reproducible(
    client: AsyncClient, session: AsyncSession,
):
    """``redraw_current_round(rng=...)`` → same seed, same round.

    Redrawing the very same round twice with the same seed must produce
    exactly the same pairings, and a different seed must be able to produce
    different ones.  Note that for *singles* the player who sits out is not
    drawn at random at all — the service picks whoever has played the most
    games — so the bye is expected to be stable across seeds here; the
    randomly drawn bye lives in the Swiss engine and is pinned by
    ``TestSwissSeededBye`` above.
    """
    headers, org_id = await _auth(client, "rng_redraw_org@test.com")
    t = await _running_tournament(client, headers, "RngRedraw", players=5)
    svc = _get_tournament_service(session)

    def bye_of(matches) -> UUID:
        playing = {m.player_a_id for m in matches} | {m.player_b_id for m in matches}
        (bye,) = [p for p in t["player_ids"] if p not in playing]
        return bye

    first = await svc.redraw_current_round(
        t["t_id"], t["stage_id"], actor_id=org_id, force=True, rng=random.Random(4242),
    )
    second = await svc.redraw_current_round(
        t["t_id"], t["stage_id"], actor_id=org_id, force=True, rng=random.Random(4242),
    )
    assert len(first) == 2  # 5 players → 2 matches + 1 bye
    assert _singles_pairs(first) == _singles_pairs(second)
    assert bye_of(first) == bye_of(second)

    # ...and the seed is really what drives it: some other seed draws a
    # different round out of the same five players.
    pairs = {tuple(_singles_pairs(first))}
    for seed in range(8):
        drawn = await svc.redraw_current_round(
            t["t_id"], t["stage_id"], actor_id=org_id, force=True,
            rng=random.Random(seed),
        )
        pairs.add(tuple(_singles_pairs(drawn)))
    assert len(pairs) > 1


@pytest.mark.asyncio
async def test_seeded_bracket_seeding_is_reproducible(
    client: AsyncClient, session: AsyncSession,
):
    """``generate_bracket(rng=...)`` → the doubles seeding is reproducible.

    With no finished group stage to seed from, the bracket forms teams by
    shuffling the registered players.  Two elimination stages of the same
    tournament, generated with the same seed, must therefore end up with the
    same teams in the same bracket positions — and a different seed must not.
    """
    headers, org_id = await _auth(client, "rng_bracket_org@test.com")
    t = await _running_tournament(
        client, headers, "RngBracket", players=8, player_mode="doubles",
    )
    svc = _get_tournament_service(session)

    async def team_pairs(stage_id: UUID) -> list[frozenset[UUID]]:
        """First-round team compositions, in bracket order."""
        rows = (await session.execute(
            select(Team).where(Team.tournament_id == t["t_id"])
        )).scalars().all()
        by_id = {row.uuid: frozenset((row.player_1_id, row.player_2_id)) for row in rows}
        matches = await svc._matches.list_by_stage(stage_id)
        first_round = min(m.round_number for m in matches)
        return [
            by_id[m.team_a_id]
            for m in sorted(
                (m for m in matches if m.round_number == first_round),
                key=lambda m: m.bracket_position or 0,
            )
            if m.team_a_id in by_id
        ]

    async def elimination_stage(name: str, ordering: int) -> UUID:
        r = await client.post(
            f"{API}/tournaments/{t['t_id']}/stages/",
            json={
                "name": name, "stage_type": "elimination", "ordering": ordering,
                "tournament_id": str(t["t_id"]), "rules": {"best_of": 1},
            },
            headers=headers,
        )
        assert_response_code(r, 200)
        return UUID(r.json()["uuid"])

    stage_a = await elimination_stage("ElimA", 1)
    stage_b = await elimination_stage("ElimB", 2)
    stage_c = await elimination_stage("ElimC", 3)

    await svc.generate_bracket(t["t_id"], stage_a, org_id, rng=random.Random(11))
    await svc.generate_bracket(t["t_id"], stage_b, org_id, rng=random.Random(11))
    await svc.generate_bracket(t["t_id"], stage_c, org_id, rng=random.Random(12))

    seeding_a = await team_pairs(stage_a)
    seeding_b = await team_pairs(stage_b)
    seeding_c = await team_pairs(stage_c)

    assert seeding_a  # sanity: teams were actually formed
    assert seeding_a == seeding_b, "same seed must produce the same bracket seeding"
    assert seeding_a != seeding_c, "a different seed must produce a different seeding"
