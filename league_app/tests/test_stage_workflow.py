"""Stage workflow tests — PREPARING → ACTIVE → FINISHED transitions and
the rules-lock contract while a stage is active.

The contract: rules that influence already-drawn matches are immutable
once the stage is ``active``, unless the caller passes ``?force=true``
(which is the UI's signal that a redraw will follow).  ``finished``
stages are completely immutable.
"""

import pytest
from httpx import AsyncClient

from league_app.tests.testlib import assert_response_code


def _url(path: str) -> str:
    return f"/api/v1{path}"


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    """Register + verify-skip + login an organiser. Returns auth headers."""
    r = await client.post(
        "/api/v1/users/register",
        json={"email": email, "password": "password123"},
    )
    assert_response_code(r, 201)
    r = await client.post(
        "/api/v1/users/login",
        data={"username": email, "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_response_code(r, 200)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _create_tournament_with_stage(
    client: AsyncClient, headers: dict, suffix: str,
) -> tuple[str, str]:
    """Create a fresh tournament with 2 players + one group stage.

    Two players is the minimum required by ``POST /tournaments/{id}/start``;
    we use ``singles`` mode so no DYP team formation is needed.
    """
    r = await client.post(
        _url("/tournaments/"),
        json={
            "name": f"Cup-{suffix}",
            "date": "2026-06-01",
            "player_mode": "singles",
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # Two players is the bare minimum the start endpoint accepts
    for i in range(2):
        r = await client.post(
            _url("/players/"),
            json={"nickname": f"sw_{suffix}_{i}"},
            headers=headers,
        )
        assert_response_code(r, 200)
        pid = r.json()["uuid"]
        r = await client.post(
            _url(f"/tournaments/{t_id}/players/?player_id={pid}"),
            headers=headers,
        )
        assert_response_code(r, 200)

    r = await client.post(
        _url(f"/tournaments/{t_id}/stages/"),
        json={
            "name": "Group",
            "stage_type": "group",
            "tournament_id": t_id,
            "rules": {"points_per_game": 6, "best_of": 1, "table_count": 2},
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    return t_id, r.json()["uuid"]


# ---------------------------------------------------------------------------
# preparing → freely editable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preparing_stage_allows_rule_changes(client: AsyncClient):
    headers = await _register_and_login(client, "prep_org@test.com")
    t_id, stage_id = await _create_tournament_with_stage(client, headers, "prep")

    r = await client.patch(
        _url(f"/tournaments/{t_id}/stages/{stage_id}"),
        json={"rules": {"points_per_game": 11, "best_of": 3}},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["rules"]["points_per_game"] == 11
    assert r.json()["rules"]["best_of"] == 3


# ---------------------------------------------------------------------------
# active → locked-rule changes rejected without force
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_stage_rejects_locked_rule_changes(client: AsyncClient):
    headers = await _register_and_login(client, "active_lock@test.com")
    t_id, stage_id = await _create_tournament_with_stage(client, headers, "lock")

    # POST /start auto-activates the first stage and draws the first round.
    r = await client.post(_url(f"/tournaments/{t_id}/start"), headers=headers)
    assert_response_code(r, 200)

    # Attempt to change a locked rule (points_per_game)
    r = await client.patch(
        _url(f"/tournaments/{t_id}/stages/{stage_id}"),
        json={"rules": {"points_per_game": 11}},
        headers=headers,
    )
    assert r.status_code == 409
    assert "points_per_game" in r.json()["detail"]


@pytest.mark.asyncio
async def test_active_stage_allows_locked_rule_changes_with_force(
    client: AsyncClient,
):
    headers = await _register_and_login(client, "active_force@test.com")
    t_id, stage_id = await _create_tournament_with_stage(client, headers, "force")
    r = await client.post(_url(f"/tournaments/{t_id}/start"), headers=headers)
    assert_response_code(r, 200)

    r = await client.patch(
        _url(f"/tournaments/{t_id}/stages/{stage_id}?force=true"),
        json={"rules": {"points_per_game": 11}},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["rules"]["points_per_game"] == 11


@pytest.mark.asyncio
async def test_active_stage_allows_no_op_locked_rule(client: AsyncClient):
    """Re-sending the same value for a locked rule is fine (idempotent)."""
    headers = await _register_and_login(client, "active_noop@test.com")
    t_id, stage_id = await _create_tournament_with_stage(client, headers, "noop")
    r = await client.post(_url(f"/tournaments/{t_id}/start"), headers=headers)
    assert_response_code(r, 200)

    # Same value as already set — no actual change → allowed
    r = await client.patch(
        _url(f"/tournaments/{t_id}/stages/{stage_id}"),
        json={"rules": {"points_per_game": 6}},
        headers=headers,
    )
    assert_response_code(r, 200)


# ---------------------------------------------------------------------------
# active → name / non-rule metadata still editable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_stage_allows_name_change(client: AsyncClient):
    headers = await _register_and_login(client, "active_name@test.com")
    t_id, stage_id = await _create_tournament_with_stage(client, headers, "name")
    r = await client.post(_url(f"/tournaments/{t_id}/start"), headers=headers)
    assert_response_code(r, 200)

    r = await client.patch(
        _url(f"/tournaments/{t_id}/stages/{stage_id}"),
        json={"name": "Renamed Mid-Stage"},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["name"] == "Renamed Mid-Stage"


# ---------------------------------------------------------------------------
# finished → fully immutable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finished_stage_rejects_all_changes(client: AsyncClient):
    headers = await _register_and_login(client, "finished_lock@test.com")
    t_id, stage_id = await _create_tournament_with_stage(client, headers, "fin")
    r = await client.post(_url(f"/tournaments/{t_id}/start"), headers=headers)
    assert_response_code(r, 200)
    r = await client.post(
        _url(f"/tournaments/{t_id}/stages/{stage_id}/finish"),
        headers=headers,
    )
    assert_response_code(r, 200)

    # Even non-rule changes should be rejected on a finished stage
    r = await client.patch(
        _url(f"/tournaments/{t_id}/stages/{stage_id}"),
        json={"name": "Too late"},
        headers=headers,
    )
    assert r.status_code == 409
    assert "finished" in r.json()["detail"].lower()
