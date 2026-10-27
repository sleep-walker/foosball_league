"""Regression tests for review finding M5 — bracket matches have a winner.

``compute_match_status`` can report ``winner_side == "draw"`` for a level
match, and ``_advance_bracket_winner`` only asked ``if winner_side == "a"``
— so a drawn elimination match fell into the ``else`` branch and advanced
side B, silently promoting a team that had not won.

An elimination round needs a winner, so the fix removes the draw instead of
picking a side for it:

* ``generate_bracket`` writes ``draw_allowed: False`` and an odd
  ``best_of`` / ``finals_best_of`` onto the elimination stage (an odd
  best-of cannot end level on game wins once games cannot be drawn), so the
  organizer sees the same contract the validator enforces;
* the score paths derive their validation rules via ``_score_rules``, which
  refuses draws for elimination stages even if the stage rules were patched
  afterwards, and refuse a submission that would finish a bracket match
  level before anything is written;
* ``_advance_bracket_winner`` raises on anything other than ``"a"``/``"b"``
  instead of defaulting to B.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.tournaments.router import _get_tournament_service
from league_app.domain.entities import Stage
from league_app.domain.tournament_errors import TournamentError
from league_app.domain.tournament_service import TournamentService
from league_app.tests.testlib import (
    API,
    assert_response_code,
    create_running_tournament,
    register_and_login,
)


async def _elimination_stage(
    client: AsyncClient, headers: dict, tournament_id: UUID, *,
    name: str = "Playoff", ordering: int = 1, rules: dict | None = None,
) -> UUID:
    """Create an *active* elimination stage so scores can be submitted."""
    r = await client.post(
        f"{API}/tournaments/{tournament_id}/stages/",
        json={
            "name": name, "stage_type": "elimination", "ordering": ordering,
            "status": "active", "tournament_id": str(tournament_id),
            "rules": rules if rules is not None else {"best_of": 1},
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    return UUID(r.json()["uuid"])


# ---------------------------------------------------------------------------
# Pure helpers on the service
# ---------------------------------------------------------------------------


class TestDecisiveBestOf:
    def test_odd_values_are_kept(self):
        assert TournamentService._decisive_best_of(1) == 1
        assert TournamentService._decisive_best_of(3) == 3
        assert TournamentService._decisive_best_of(5) == 5

    def test_even_values_are_rounded_up(self):
        assert TournamentService._decisive_best_of(2) == 3
        assert TournamentService._decisive_best_of(4) == 5

    def test_missing_or_zero_becomes_one(self):
        assert TournamentService._decisive_best_of(None) == 1
        assert TournamentService._decisive_best_of(0) == 1


class TestScoreRules:
    def _stage(self, stage_type: str, rules: dict | None) -> Stage:
        return Stage(
            uuid=UUID(int=1), tournament_id=UUID(int=2), name="S",
            stage_type=stage_type, rules=rules,
        )

    def test_elimination_never_allows_draws(self):
        rules = TournamentService._score_rules(
            self._stage("elimination", {"draw_allowed": True, "points_per_game": 6})
        )
        assert rules["draw_allowed"] is False
        assert rules["points_per_game"] == 6

    def test_group_rules_are_untouched(self):
        rules = TournamentService._score_rules(
            self._stage("group", {"draw_allowed": True})
        )
        assert rules["draw_allowed"] is True

    def test_group_default_is_still_draws_allowed(self):
        assert TournamentService._score_rules(self._stage("group", None)) == {}

    def test_no_stage_means_no_rules(self):
        assert TournamentService._score_rules(None) == {}


# ---------------------------------------------------------------------------
# generate_bracket — the rules it pins down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_bracket_enforces_decisive_rules(
    client: AsyncClient, session: AsyncSession,
):
    headers, org_id = await register_and_login(client, "m5_rules@test.com")
    t = await create_running_tournament(client, headers, "M5Rules", players=4)
    # best_of 2 would allow a 1-1 match: level on game wins, no winner.
    stage_id = await _elimination_stage(
        client, headers, t["tournament_id"],
        rules={"best_of": 2, "draw_allowed": True},
    )

    svc = _get_tournament_service(session)
    created = await svc.generate_bracket(t["tournament_id"], stage_id, org_id)

    stage = await svc._stages.get(stage_id)
    assert stage.rules["draw_allowed"] is False
    assert stage.rules["best_of"] == 3, "even best_of must be rounded up to odd"
    assert stage.rules["finals_best_of"] == 3
    assert all(m.best_of % 2 == 1 for m in created)


# ---------------------------------------------------------------------------
# Submitting a draw in a bracket match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drawn_game_is_rejected_in_a_bracket_match(
    client: AsyncClient, session: AsyncSession,
):
    """5:5 is a legal group-stage score but must be refused in the bracket."""
    headers, org_id = await register_and_login(client, "m5_draw@test.com")
    t = await create_running_tournament(client, headers, "M5Draw", players=4)
    stage_id = await _elimination_stage(client, headers, t["tournament_id"])

    svc = _get_tournament_service(session)
    created = await svc.generate_bracket(t["tournament_id"], stage_id, org_id)
    playable = [
        m for m in created
        if m.player_a_id is not None and m.player_b_id is not None
    ]
    assert playable, "sanity: the bracket has a playable first-round match"
    match_id = playable[0].uuid

    r = await client.patch(
        f"{API}/matches/{match_id}/score",
        json={"score_a": 5, "score_b": 5}, headers=headers,
    )
    assert r.status_code == 400
    assert "draw" in r.json()["detail"].lower()

    r = await client.get(f"{API}/matches/{match_id}/games/", headers=headers)
    assert_response_code(r, 200)
    assert r.json() == [], "a refused draw must not leave a game behind"

    # A decisive score in the very same match is still accepted.
    r = await client.patch(
        f"{API}/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 3}, headers=headers,
    )
    assert_response_code(r, 200)
    r = await client.get(f"{API}/matches/{match_id}", headers=headers)
    assert r.json()["winner_side"] == "a"


# ---------------------------------------------------------------------------
# _advance_bracket_winner — no side is promoted by accident
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draw_does_not_advance_side_b(
    client: AsyncClient, session: AsyncSession,
):
    """The original bug, driven directly at the advance-winner logic."""
    headers, org_id = await register_and_login(client, "m5_advance@test.com")
    t = await create_running_tournament(client, headers, "M5Advance", players=4)
    stage_id = await _elimination_stage(client, headers, t["tournament_id"])

    svc = _get_tournament_service(session)
    created = await svc.generate_bracket(t["tournament_id"], stage_id, org_id)
    stage = await svc._stages.get(stage_id)

    first_round = min(m.round_number for m in created)
    semi = next(
        m for m in created
        if m.round_number == first_round
        and m.player_a_id is not None and m.player_b_id is not None
    )
    later_rounds = [m for m in created if m.round_number > first_round]
    assert later_rounds, "sanity: there is a later round to advance into"

    with pytest.raises(TournamentError, match="no winner"):
        await svc._advance_bracket_winner(semi, stage, "draw")

    # Nobody moved on: before the fix, player B of the drawn match would
    # already be sitting in the next round.
    for m in await svc._matches.list_by_stage(stage_id):
        if m.round_number > first_round:
            assert m.player_a_id is None and m.player_b_id is None

    # A real winner still advances.
    await svc._advance_bracket_winner(semi, stage, "a")
    advanced = [
        m for m in await svc._matches.list_by_stage(stage_id)
        if m.round_number > first_round
        and semi.player_a_id in (m.player_a_id, m.player_b_id)
    ]
    assert advanced, "the winner of side A must advance"
