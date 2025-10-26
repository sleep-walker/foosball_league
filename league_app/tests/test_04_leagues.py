from typing import AsyncContextManager, Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from league_app.api.leagues.model import League
from league_app.api.leagues.schema import LeagueCreate, LeagueOutput, LeagueUpdate
from league_app.api.users.model import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import LeagueFactoryType
from .testlib import assert_response_code
from fastapi.encoders import jsonable_encoder

# * /api/v1/leagues/


@pytest.mark.asyncio
async def test_admin_can_list_all_leagues(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    league1 = await league_factory(
        LeagueCreate(
            name="League One",
            description="First",
            registration_type="open",
            owner_id=db_user1.id,
        )
    )
    league2 = await league_factory(
        LeagueCreate(
            name="League Two",
            description="Second",
            registration_type="restricted",
            owner_id=db_user1.id,
        )
    )
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/leagues/")
    assert_response_code(response, 200)
    returned_leagues = [LeagueOutput(**l) for l in response.json()]
    assert LeagueOutput.model_validate(league1) in returned_leagues
    assert LeagueOutput.model_validate(league2) in returned_leagues


@pytest.mark.asyncio
async def test_create_league(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    league1: dict[str, str],
):
    db_user1 = db_user1_with_pass[0]
    payload = jsonable_encoder(league1)
    payload["owner_id"] = str(db_user1.id)
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post("/api/v1/leagues/", json=payload)
    assert_response_code(response, 200)
    data = response.json()
    stmt = select(League).filter(League.uuid == UUID(data["uuid"]))
    db_league = await session.scalar(stmt)
    assert db_league is not None
    assert LeagueOutput.model_validate(db_league) == LeagueOutput(**data)
    assert LeagueOutput(**payload, uuid=data["uuid"]) == LeagueOutput(
        **data
    )
    # test cleanup
    await session.delete(db_league)
    await session.commit()


@pytest.mark.asyncio
async def test_create_league_existing_name(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    league1: dict[str, str],
    league_factory: LeagueFactoryType,
    db_league1: League,  # type: ignore[unused-argument]
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
):
    db_user2 = db_user2_with_pass[0]
    payload = jsonable_encoder(league1)
    payload["owner_id"] = str(db_user2.id)
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post("/api/v1/leagues/", json=payload)
    assert_response_code(response, 400)
    assert response.json() == {"detail": "League name already exists"}


# * /api/v1/leagues/{uuid}


@pytest.mark.asyncio
async def test_get_league_details(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    league = await league_factory(
        LeagueCreate(
            name="Test League",
            description="Details",
            registration_type="open",
            owner_id=db_user1.id,
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get(f"/api/v1/leagues/{league.uuid}")
    assert_response_code(response, 200)
    data = response.json()
    assert LeagueOutput.model_validate(league) == LeagueOutput(**data)


@pytest.mark.asyncio
async def test_owner_can_update_own_league(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    league = await league_factory(
        LeagueCreate(
            name="Editable League",
            description="Edit",
            registration_type="open",
            owner_id=db_user1.id,
        )
    )
    update_data = {
        "uuid": str(league.uuid),
        "name": "Updated League",
        "description": "Updated",
    }
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(f"/api/v1/leagues/{league.uuid}", json=update_data)
    assert_response_code(response, 200)
    assert response.json()["name"] == "Updated League"
    await session.refresh(league)
    assert league.name == "Updated League"


@pytest.mark.asyncio
async def test_admin_can_update_any_league(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    league = await league_factory(
        LeagueCreate(
            name="Admin Editable",
            description="Edit",
            registration_type="open",
            owner_id=db_user1.id,
        )
    )
    updated_data = {"uuid": str(league.uuid), "name": "Admin Updated"}
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.put(f"/api/v1/leagues/{league.uuid}", json=updated_data)
    assert_response_code(response, 200)
    assert response.json()["name"] == "Admin Updated"
    await session.refresh(league)
    assert league.name == "Admin Updated"


@pytest.mark.asyncio
async def test_user_cannot_update_league_of_another_owner(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user2 = db_user2_with_pass[0]
    league = await league_factory(
        LeagueCreate(name="Not My League", owner_id=db_user2.id)
    )
    updated_league = LeagueUpdate.model_validate(league)
    updated_league.name = "Hacker Attempt"
    updated_payload = jsonable_encoder(updated_league)
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(
            f"/api/v1/leagues/{league.uuid}", json=updated_payload
        )
    assert_response_code(response, 403)


@pytest.mark.asyncio
async def test_delete_league_by_admin(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    league = await league_factory(
        LeagueCreate(name="Deletable League", owner_id=db_user1.id)
    )
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.delete(f"/api/v1/leagues/{league.uuid}")
    assert_response_code(response, 200)
    await session.refresh(league)
    assert not league.is_active


# * /api/v1/leagues/search?name={name}


@pytest.mark.asyncio
async def test_search_leagues_by_name(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
    session: AsyncSession,
):
    db_user1 = db_user1_with_pass[0]
    league = await league_factory(
        LeagueCreate(name="Searched League", description="Search", owner_id=db_user1.id)
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/leagues/search?name=Searched%20League")
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_league = LeagueOutput(**(data[0]))
    output_db_league = LeagueOutput.model_validate(league)
    assert output_league == output_db_league


@pytest.mark.asyncio
async def test_admin_search_leagues_by_name(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    league_factory: LeagueFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    league = await league_factory(
        LeagueCreate(name="Admin Searched League", owner_id=db_user1.id)
    )
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get(
            "/api/v1/leagues/search?name=Admin%20Searched%20League"
        )
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_league = LeagueOutput(**(data[0]))
    output_db_league = LeagueOutput.model_validate(league)
    assert output_league == output_db_league
