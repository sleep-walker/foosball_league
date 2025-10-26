from typing import AsyncContextManager, Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from league_app.api.tournaments.model import Tournament
from league_app.api.tournaments.schema import (
    TournamentCreate,
    TournamentOutput,
)

from league_app.api.users.model import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import TournamentFactoryType
from .testlib import assert_response_code
from fastapi.encoders import jsonable_encoder


@pytest.mark.asyncio
async def test_admin_can_list_all_tournaments(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    tournament_factory: TournamentFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    tournament1 = await tournament_factory(
        TournamentCreate(
            name="Tournament One",
            date="2025-07-20",
            location="Main Hall",
            owner_id=db_user1.id,
        )
    )
    tournament2 = await tournament_factory(
        TournamentCreate(
            name="Tournament Two",
            date="2025-08-01",
            location="Side Hall",
            owner_id=db_user1.id,
        )
    )
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/tournaments/")
    assert_response_code(response, 200)
    returned_tournaments = [TournamentOutput(**t) for t in response.json()]
    assert TournamentOutput.model_validate(tournament1) in returned_tournaments
    assert TournamentOutput.model_validate(tournament2) in returned_tournaments


@pytest.mark.asyncio
async def test_create_tournament(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    tournament1: dict[str, str],
):
    db_user1 = db_user1_with_pass[0]
    payload = jsonable_encoder(tournament1)
    payload["owner_id"] = str(db_user1.id)
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post("/api/v1/tournaments/", json=payload)
    assert_response_code(response, 200)
    data = response.json()
    stmt = select(Tournament).filter(Tournament.uuid == UUID(data["uuid"]))
    db_tournament = await session.scalar(stmt)
    assert db_tournament is not None
    assert TournamentOutput.model_validate(db_tournament) == TournamentOutput(**data)
    assert TournamentOutput(**payload, uuid=data["uuid"]) == TournamentOutput(**data)
    # test cleanup
    await session.delete(db_tournament)
    await session.commit()


@pytest.mark.asyncio
async def test_get_tournament_details(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    tournament_factory: "TournamentFactoryType",
):
    db_user1 = db_user1_with_pass[0]
    tournament = await tournament_factory(
        TournamentCreate(
            name="Test Tournament",
            date="2025-07-21",
            location="Test Hall",
            owner_id=db_user1.id,
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get(f"/api/v1/tournaments/{tournament.uuid}")
    assert_response_code(response, 200)
    data = response.json()
    assert TournamentOutput.model_validate(tournament) == TournamentOutput(**data)


@pytest.mark.asyncio
async def test_owner_can_update_own_tournament(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    tournament_factory: "TournamentFactoryType",
):
    db_user1 = db_user1_with_pass[0]
    tournament = await tournament_factory(
        TournamentCreate(
            name="Editable Tournament",
            date="2025-07-22",
            location="Edit Hall",
            owner_id=db_user1.id,
        )
    )
    update_data = {
        "uuid": str(tournament.uuid),
        "name": "Updated Tournament",
        "location": "Updated Hall",
    }
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.patch(
            f"/api/v1/tournaments/{tournament.uuid}", json=update_data
        )
    assert_response_code(response, 200)
    assert response.json()["name"] == "Updated Tournament"
    await session.refresh(tournament)
    assert tournament.name == "Updated Tournament"


@pytest.mark.asyncio
async def test_delete_tournament_by_owner(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    tournament_factory: "TournamentFactoryType",
):
    db_user1 = db_user1_with_pass[0]
    tournament = await tournament_factory(
        TournamentCreate(
            name="Deletable Tournament",
            date="2025-07-23",
            location="Delete Hall",
            owner_id=db_user1.id,
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.delete(f"/api/v1/tournaments/{tournament.uuid}")
    assert_response_code(response, 200)
    await session.refresh(tournament)
    assert getattr(tournament, "is_deleted", False)
