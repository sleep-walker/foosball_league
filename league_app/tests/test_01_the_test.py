from uuid import UUID

import pytest

from httpx import AsyncClient
from league_app.api.players import model
from league_app.api.users.model import User
from league_app.api.players.model import Player
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.mark.asyncio
async def test_fixture_types(
    test_engine: AsyncEngine,
    session: AsyncSession,
    client: AsyncClient,
    db_player1: model.Player,
):
    assert isinstance(test_engine, AsyncEngine)
    assert isinstance(session, AsyncSession)
    assert isinstance(client, AsyncClient)
    assert isinstance(db_player1, model.Player)


UUID_OF_ANY_EXISTING_USER_IN_MAIN_DB = "51da75b7-e4a9-460e-a067-c869e82c579c"


@pytest.mark.asyncio
async def test_have_test_db(
    session: AsyncSession,
):
    stmt = select(model.Player).filter(
        model.Player.uuid == UUID(UUID_OF_ANY_EXISTING_USER_IN_MAIN_DB)
    )
    result = await session.scalar(stmt)
    assert result is None


@pytest.mark.asyncio
async def test_have_test_client(
    client: AsyncClient,
    override_current_user_with_user1: User,
):
    assert isinstance(client, AsyncClient)
    response = await client.get(
        f"/api/v1/players/{UUID_OF_ANY_EXISTING_USER_IN_MAIN_DB}"
    )
    data = response.json()
    assert {"detail": "Player not found"} == data


@pytest.mark.asyncio
async def test_use_user_override_fixture(
    client: AsyncClient,
    override_current_user_with_user1: User,
):
    response = await client.get("/authenticated-route")
    assert response.status_code == 200
    assert response.json() == {
        "message": f"Hello {override_current_user_with_user1.id}!"
    }

@pytest.mark.asyncio
async def test_user_player_fixture(
    user_player: Player, db_user1: User, override_current_user_with_user1: User
):
    assert True
    assert user_player.uuid == db_user1.id
    assert user_player.email == override_current_user_with_user1.email
