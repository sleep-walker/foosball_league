"""Regression tests for the authorization findings M1, M2 and M3.

M1  draw-round / redraw-round / generate-bracket had no organizer check,
    so any logged-in user could reshuffle anybody's tournament — and a
    redraw silently deleted already-played matches.
M2  POST /matches/{id}/games/ and PATCH /matches/{id}/games/{game_id}
    wrote scores through raw CRUD, bypassing both the permission check
    and the rule validation of the service layer.
M3  The service layer never enforced authorization at all; it trusted
    the router to have done it, which is exactly how M1 happened.

Style follows test_e2e_flows.py: everything is built from scratch over
the real HTTP API, except where a test deliberately calls the service
directly to prove the service itself refuses (M3).
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.tournaments.router import _get_tournament_service
from league_app.domain.tournament_errors import PermissionDeniedError
from league_app.tests.testlib import assert_response_code

API = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _auth(client: AsyncClient, email: str, password: str = "password123") -> tuple[dict, UUID]:
    """Register + login, return (auth headers, user id)."""
    r = await client.post(f"{API}/users/register", json={"email": email, "password": password})
    assert_response_code(r, 201)
    user_id = UUID(r.json()["id"])
    r = await client.post(
        f"{API}/users/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_response_code(r, 200)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user_id


async def _running_tournament(
    client: AsyncClient,
    headers: dict,
    name: str,
    *,
    players: int = 4,
    stage_rules: dict | None = None,
    extra_player_ids: list[str] | None = None,
) -> dict:
    """Create a tournament with players, start it, return its ids + matches."""
    r = await client.post(
        f"{API}/tournaments/",
        json={"name": name, "date": "2026-05-01", "settings": {"table_count": 2}},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    if stage_rules is not None:
        r = await client.post(
            f"{API}/tournaments/{t_id}/stages/",
            json={
                "name": "Main", "stage_type": "group", "ordering": 0,
                "tournament_id": t_id, "rules": stage_rules,
            },
            headers=headers,
        )
        assert_response_code(r, 200)

    player_ids = list(extra_player_ids or [])
    for i in range(players - len(player_ids)):
        r = await client.post(
            f"{API}/players/", json={"nickname": f"{name}-p{i}"}, headers=headers,
        )
        assert_response_code(r, 200)
        player_ids.append(r.json()["uuid"])

    for player_id in player_ids:
        r = await client.post(
            f"{API}/tournaments/{t_id}/players/?player_id={player_id}",
            headers=headers,
        )
        assert_response_code(r, 200)

    r = await client.post(f"{API}/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)

    r = await client.get(f"{API}/tournaments/{t_id}", headers=headers)
    assert_response_code(r, 200)
    stage_id = r.json()["stages"][0]["uuid"]

    r = await client.get(f"{API}/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    return {"t_id": t_id, "stage_id": stage_id, "matches": r.json()}


# ---------------------------------------------------------------------------
# M1 — organizer-only tournament actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outsider_cannot_draw_redraw_or_generate_bracket(client: AsyncClient):
    """A logged-in non-organizer gets 403 on all three endpoints (M1)."""
    org, _ = await _auth(client, "m1_org@test.com")
    outsider, _ = await _auth(client, "m1_outsider@test.com")
    t = await _running_tournament(client, org, "M1Tour")

    for path in ("draw-round", "redraw-round", "generate-bracket"):
        r = await client.post(
            f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/{path}",
            headers=outsider,
        )
        assert_response_code(r, 403)

    # The round is untouched — no matches were deleted by the redraw attempt.
    r = await client.get(f"{API}/tournaments/{t['t_id']}/matches/", headers=org)
    assert len(r.json()) == len(t["matches"])


@pytest.mark.asyncio
async def test_organizer_can_still_draw_a_round(client: AsyncClient):
    """Control case: the fix must not lock the organizer out (M1)."""
    org, _ = await _auth(client, "m1_owner@test.com")
    t = await _running_tournament(client, org, "M1Owner")

    for m in t["matches"]:
        r = await client.patch(
            f"{API}/matches/{m['uuid']}/score",
            json={"score_a": 6, "score_b": 3}, headers=org,
        )
        assert_response_code(r, 200)

    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/draw-round", headers=org,
    )
    assert_response_code(r, 200)
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_co_organizer_may_draw_but_not_wipe_results(client: AsyncClient):
    """Co-organizers keep organizer rights, except destroying results (M1)."""
    org, _ = await _auth(client, "m1_co_owner@test.com")
    co, co_id = await _auth(client, "m1_co@test.com")
    t = await _running_tournament(client, org, "M1Co")

    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/co-organizers/{co_id}", headers=org,
    )
    assert_response_code(r, 200)

    # Nothing played yet: the co-organizer may redraw.
    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/redraw-round", headers=co,
    )
    assert_response_code(r, 200)

    # Record a result, then the same redraw is refused — only the owner
    # may destroy finished matches, and only with an explicit force.
    match_id = r.json()[0]["uuid"]
    r = await client.patch(
        f"{API}/matches/{match_id}/score", json={"score_a": 6, "score_b": 1}, headers=co,
    )
    assert_response_code(r, 200)

    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/redraw-round?force=true",
        headers=co,
    )
    assert_response_code(r, 403)


@pytest.mark.asyncio
async def test_redraw_of_a_played_round_needs_explicit_confirmation(client: AsyncClient):
    """Even the owner must confirm before a redraw deletes results (M1)."""
    org, _ = await _auth(client, "m1_force@test.com")
    t = await _running_tournament(client, org, "M1Force")

    match_id = t["matches"][0]["uuid"]
    r = await client.patch(
        f"{API}/matches/{match_id}/score", json={"score_a": 6, "score_b": 0}, headers=org,
    )
    assert_response_code(r, 200)

    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/redraw-round", headers=org,
    )
    assert_response_code(r, 400)
    assert "force" in r.json()["detail"].lower()

    # Results still there.
    r = await client.get(f"{API}/tournaments/{t['t_id']}/matches/", headers=org)
    assert any(m["status"] == "finished" for m in r.json())

    # With the explicit confirmation the owner can override.
    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/redraw-round?force=true",
        headers=org,
    )
    assert_response_code(r, 200)


# ---------------------------------------------------------------------------
# M2 — score writes through the validated path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outsider_cannot_write_or_edit_game_scores(client: AsyncClient):
    """POST/PATCH of games is 403 for a non-participant non-organizer (M2)."""
    org, _ = await _auth(client, "m2_org@test.com")
    outsider, _ = await _auth(client, "m2_outsider@test.com")
    t = await _running_tournament(client, org, "M2Tour", stage_rules={"best_of": 3})
    match = t["matches"][0]

    r = await client.post(
        f"{API}/matches/{match['uuid']}/games/",
        json={"score_a": 6, "score_b": 0}, headers=outsider,
    )
    assert_response_code(r, 403)

    # The organizer records a game, the outsider tries to rewrite it.
    r = await client.post(
        f"{API}/matches/{match['uuid']}/games/",
        json={"score_a": 6, "score_b": 2}, headers=org,
    )
    assert_response_code(r, 200)
    game_id = r.json()["uuid"]

    r = await client.patch(
        f"{API}/matches/{match['uuid']}/games/{game_id}",
        json={"score_a": 0, "score_b": 6}, headers=outsider,
    )
    assert_response_code(r, 403)

    r = await client.get(f"{API}/matches/{match['uuid']}/games/", headers=org)
    assert [(g["score_a"], g["score_b"]) for g in r.json()] == [(6, 2)]


@pytest.mark.asyncio
async def test_game_endpoints_validate_scores_against_stage_rules(client: AsyncClient):
    """Raw CRUD accepted any numbers; the validated path does not (M2)."""
    org, _ = await _auth(client, "m2_rules@test.com")
    t = await _running_tournament(client, org, "M2Rules", stage_rules={"best_of": 3})
    match = t["matches"][0]

    # points_per_game defaults to 6 — a 4:2 game cannot happen.
    r = await client.post(
        f"{API}/matches/{match['uuid']}/games/",
        json={"score_a": 4, "score_b": 2}, headers=org,
    )
    assert_response_code(r, 400)
    assert "exactly 6" in r.json()["detail"]

    r = await client.post(
        f"{API}/matches/{match['uuid']}/games/",
        json={"score_a": 6, "score_b": 2}, headers=org,
    )
    assert_response_code(r, 200)
    game = r.json()
    assert game["game_number"] == 1
    assert game["is_finished"] is True

    # The same validation applies to corrections.
    r = await client.patch(
        f"{API}/matches/{match['uuid']}/games/{game['uuid']}",
        json={"score_a": 9, "score_b": 9}, headers=org,
    )
    assert_response_code(r, 400)

    r = await client.patch(
        f"{API}/matches/{match['uuid']}/games/{game['uuid']}",
        json={"score_a": 6, "score_b": 4}, headers=org,
    )
    assert_response_code(r, 200)
    assert (r.json()["score_a"], r.json()["score_b"]) == (6, 4)


@pytest.mark.asyncio
async def test_participant_may_submit_a_game_score(client: AsyncClient):
    """A player of the match keeps write access through the new path (M2)."""
    org, _ = await _auth(client, "m2_part_org@test.com")
    player_user, _ = await _auth(client, "m2_part_player@test.com")

    # A user's first self-created player is auto-linked to that user.
    r = await client.post(
        f"{API}/players/", json={"nickname": "M2Part-me"}, headers=player_user,
    )
    assert_response_code(r, 200)
    my_player_id = r.json()["uuid"]

    t = await _running_tournament(
        client, org, "M2Part", stage_rules={"best_of": 3},
        extra_player_ids=[my_player_id],
    )
    match = next(
        m for m in t["matches"]
        if my_player_id in (m["player_a_id"], m["player_b_id"])
    )

    r = await client.post(
        f"{API}/matches/{match['uuid']}/games/",
        json={"score_a": 6, "score_b": 4}, headers=player_user,
    )
    assert_response_code(r, 200)


# ---------------------------------------------------------------------------
# M3 — the service enforces authorization on its own
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_refuses_unauthorized_caller_without_any_router(
    client: AsyncClient, session: AsyncSession,
):
    """Call the service directly, bypassing the routers entirely (M3).

    This is the real proof that M3 is fixed rather than only M1/M2's
    router symptoms: no HTTP layer is involved here at all.
    """
    org, org_id = await _auth(client, "m3_org@test.com")
    _outsider_headers, outsider_id = await _auth(client, "m3_outsider@test.com")
    t = await _running_tournament(client, org, "M3Tour")

    svc = _get_tournament_service(session)
    t_id, stage_id = UUID(t["t_id"]), UUID(t["stage_id"])
    match_id = UUID(t["matches"][0]["uuid"])

    with pytest.raises(PermissionDeniedError):
        await svc.draw_swiss_round(t_id, stage_id, actor_id=outsider_id)
    with pytest.raises(PermissionDeniedError):
        await svc.redraw_current_round(t_id, stage_id, actor_id=outsider_id)
    with pytest.raises(PermissionDeniedError):
        await svc.generate_bracket(t_id, stage_id, actor_id=outsider_id)
    with pytest.raises(PermissionDeniedError):
        await svc.submit_game_score(match_id, 6, 0, actor_id=outsider_id)
    with pytest.raises(PermissionDeniedError):
        await svc.submit_batch_scores(match_id, [(6, 0)], actor_id=outsider_id)
    with pytest.raises(PermissionDeniedError):
        await svc.start_tournament(t_id, actor_id=outsider_id)

    # A caller that supplies no identity at all is refused too — the
    # service never defaults to "the caller must have been checked".
    with pytest.raises(PermissionDeniedError):
        await svc.draw_swiss_round(t_id, stage_id, actor_id=None)
    with pytest.raises(PermissionDeniedError):
        await svc.submit_game_score(match_id, 6, 0)

    # Control: the organizer is allowed through the very same call.
    game = await svc.submit_game_score(match_id, 6, 0, actor_id=org_id)
    assert game.score_a == 6


@pytest.mark.asyncio
async def test_matches_drawn_by_an_organizer_are_owned_by_that_organizer(
    client: AsyncClient,
):
    """owner_id of drawn matches cannot hand score rights to an outsider.

    ``_check_score_permission`` trusts ``match.owner_id``; with M1 in
    place only an organizer can reach the draw/redraw code that sets it.
    """
    org, org_id = await _auth(client, "m3_owner@test.com")
    outsider, _ = await _auth(client, "m3_nobody@test.com")
    t = await _running_tournament(client, org, "M3Owner")

    assert {m["owner_id"] for m in t["matches"]} == {str(org_id)}

    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/redraw-round",
        headers=outsider,
    )
    assert_response_code(r, 403)

    r = await client.post(
        f"{API}/tournaments/{t['t_id']}/stages/{t['stage_id']}/redraw-round", headers=org,
    )
    assert_response_code(r, 200)
    assert {m["owner_id"] for m in r.json()} == {str(org_id)}

    r = await client.patch(
        f"{API}/matches/{r.json()[0]['uuid']}/score",
        json={"score_a": 6, "score_b": 0}, headers=outsider,
    )
    assert_response_code(r, 403)
