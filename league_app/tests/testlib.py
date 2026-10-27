"""Small shared helpers for the test suite."""

from __future__ import annotations

from uuid import UUID

from httpx import AsyncClient, Response

API = "/api/v1"


def assert_response_code(response: Response, expected_code: int) -> None:
    assert (
        response.status_code == expected_code
    ), f"Unexpected response code {response.status_code}: {response.json()}"


async def register_and_login(
    client: AsyncClient, email: str, password: str = "password123",
) -> tuple[dict[str, str], UUID]:
    """Register + log in an organizer; return (auth headers, user id)."""
    r = await client.post(
        f"{API}/users/register", json={"email": email, "password": password},
    )
    assert_response_code(r, 201)
    user_id = UUID(r.json()["id"])
    r = await client.post(
        f"{API}/users/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_response_code(r, 200)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user_id


async def create_running_tournament(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
    *,
    players: int,
    player_mode: str = "singles",
    settings: dict | None = None,
) -> dict:
    """Create + start a tournament with ``players`` registered players.

    ``settings`` is merged into the tournament settings JSON, which
    ``start_tournament`` folds into the auto-created "Main" stage's rules —
    so ``settings={"best_of": 3}`` gives a best-of-3 group stage.

    Returns ``{"tournament_id", "stage_id", "player_ids"}``.
    """
    payload_settings = {"table_count": 2}
    payload_settings.update(settings or {})
    r = await client.post(
        f"{API}/tournaments/",
        json={
            "name": name, "date": "2026-05-01", "player_mode": player_mode,
            "settings": payload_settings,
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    player_ids: list[str] = []
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
        "tournament_id": UUID(t_id),
        "stage_id": UUID(r.json()["stages"][0]["uuid"]),
        "player_ids": [UUID(p) for p in player_ids],
    }
