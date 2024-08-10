import pytest
from uuid import uuid4, UUID
from fastapi.testclient import TestClient
from . import models
from . import schemas
from .main import app, get_session

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from httpx import AsyncClient
from sqlalchemy import select


# ** Test /api/v1/players/


@pytest.mark.asyncio
async def test_fixture_types(
    async_engine: AsyncEngine,
    #    async_session: async_sessionmaker,
    async_session: AsyncSession,
    async_client: AsyncClient,
    async_db_player1: models.Player,
):
    assert isinstance(async_engine, AsyncEngine)
    assert isinstance(async_session, AsyncSession)
    assert isinstance(async_client, AsyncClient)
    assert isinstance(async_db_player1, models.Player)


@pytest.mark.asyncio
async def test_have_test_db(
    async_session: AsyncSession,
):
    stmt = select(models.Player).filter(
        models.Player.uuid == UUID("51da75b7-e4a9-460e-a067-c869e82c579c")
    )
    result = await async_session.scalar(stmt)
    assert result is None


@pytest.mark.asyncio
async def test_have_test_client(
    async_client: AsyncClient,
):
    assert isinstance(async_client, AsyncClient)
    response = await async_client.get(
        "/api/v1/players/51da75b7-e4a9-460e-a067-c869e82c579c"
    )
    data = response.json()
    assert {"detail": "Player not found"} == data


# def test_create_player(client, player1, db):
#     response = client.post(
#         "/api/v1/players/",
#         json=player1,
#     )
#     assert response.status_code == 200
#     data = response.json()
#     db_player = (
#         db.query(models.Player).filter(models.Player.uuid == UUID(data["uuid"])).first()
#     )
#     player1["uuid"] = UUID(data["uuid"])
#     for field in ("first_name", "last_name", "nickname", "email", "uuid"):
#         assert getattr(db_player, field) == player1[field]

#     db.delete(db_player)
#     db.commit()


@pytest.mark.asyncio
async def test_read_player_async(async_client, async_session, async_db_player1):
    response = await async_client.get("/api/v1/players/")
    data = response.json()
    assert response.status_code == 200
    # async_session
    stmt = select(models.Player).filter(models.Player.uuid == async_db_player1.uuid)
    x = await async_session.scalar(stmt)
    assert x == async_db_player1
    p1data = schemas.PlayerOutput.model_validate(async_db_player1).model_dump()
    p1data["uuid"] = str(p1data["uuid"])
    assert data == [p1data]


# @pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_create_player_async(async_client, async_session, player1):
    response = await async_client.post("/api/v1/players/", json=player1)
    assert response.status_code == 200
    data = response.json()
    stmt = select(models.Player).filter(models.Player.uuid == UUID(data["uuid"]))
    s = app.dependency_overrides[get_session]()
    db_player = await s.scalar(stmt)
    # db_player = await async_session.scalar(stmt)

    assert db_player is not None
    player1["uuid"] = UUID(data["uuid"])
    for field in ("first_name", "last_name", "nickname", "email", "uuid"):
        assert getattr(db_player, field) == player1[field]

    await async_session.delete(db_player)
    await async_session.commit()


# def test_read_player(client, db_player1):
#     response = client.get("/api/v1/players/")
#     data = response.json()
#     # data["uuid"] = UUID(data["uuid"])
#     assert response.status_code == 200
#     p1data = schemas.PlayerOutput.model_validate(db_player1).model_dump()
#     p1data["uuid"] = str(p1data["uuid"])
#     assert data == [p1data]


@pytest.mark.skip(reason="not yet")
def test_create_player_existing_email(client, player1, db_player1):
    response = client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}


@pytest.mark.skip(reason="not yet")
def test_create_player_existing_nickname(client, player1, db_player1):
    player1["email"] = "different_" + player1["email"]
    response = client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Nickname already registered"}


@pytest.mark.skip(reason="not yet")
def test_update_existing_player_as_the_user_himself(client, player1, db, db_player1):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    assert response.json() == p1_data
    db.refresh(db_player1)
    assert db_player1.last_name == "baz"


@pytest.mark.skip(reason="not yet")
def test_update_existing_player_as_admin(client, player1, db, db_player1):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    assert response.json() == p1_data
    db.refresh(db_player1)
    assert db_player1.last_name == "baz"


@pytest.mark.skip(reason="not yet")
def test_update_existing_player_as_another_player(client, player1, db, db_player1):
    response = client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 403
    assert response.json() == {"detail": "User not authorized to modify someone else."}


@pytest.mark.skip(reason="not yet")
def test_update_email_of_existing_player(client, player1, db, db_player1):
    uuid = str(db_player1.uuid)
    player1["email"] = "foo@baz.com"
    player1["uuid"] = uuid
    response = client.put(f"/api/v1/players/{uuid}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    db.refresh(db_player1)
    assert db_player1.email == "foo@baz.com"


@pytest.mark.skip(reason="not yet")
def test_update_uuid_of_existing_player(client, player1, db_player1):
    uuid = str(db_player1.uuid)
    player1["uuid"] = "12345678-1234-abcd-abcd-1234567890ab"
    response = client.put(f"/api/v1/players/{uuid}", json=player1)
    assert response.status_code == 403
    assert response.json() == {"detail": "User cannot change his UUID"}


# ** Test self /api/v1/players/self


@pytest.mark.skip(reason="not yet")
def test_get_self_player(client, db_player1):
    response = client.get("/api/v1/players/self")
    data = response.json()
    # data["uuid"] = UUID(data["uuid"])
    assert response.status_code == 200
    p1data = schemas.PlayerOutput.model_validate(db_player1).model_dump()
    p1data["uuid"] = str(p1data["uuid"])
    assert data == [p1data]


@pytest.mark.skip(reason="not yet")
def test_update_self_player(client, player1, db, db_player1):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/self", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    assert response.json() == p1_data
    db.refresh(db_player1)
    assert db_player1.last_name == "baz"


# ** Test users


@pytest.mark.skip(reason="not yet")
def test_auth_user_register(client):
    response = client.post(
        "/auth/register",
        json={"email": "foo1@bar.com", "password": "foobar"},
    )
    assert response.status_code == 201


# def test_read_item():
#     response = client.get("/items/foo", headers={"X-Token": "coneofsilence"})
#     assert response.status_code == 200
#     assert response.json() == {
#         "id": "foo",
#         "title": "Foo",
#         "description": "There goes my hero",
#     }


# def test_read_item_bad_token():
#     response = client.get("/items/foo", headers={"X-Token": "hailhydra"})
#     assert response.status_code == 400
#     assert response.json() == {"detail": "Invalid X-Token header"}


# def test_read_nonexistent_item():
#     response = client.get("/items/baz", headers={"X-Token": "coneofsilence"})
#     assert response.status_code == 404
#     assert response.json() == {"detail": "Item not found"}


# def test_create_item():
#     response = client.post(
#         "/items/",
#         headers={"X-Token": "coneofsilence"},
#         json={"id": "foobar", "title": "Foo Bar", "description": "The Foo Barters"},
#     )
#     assert response.status_code == 200
#     assert response.json() == {
#         "id": "foobar",
#         "title": "Foo Bar",
#         "description": "The Foo Barters",
#     }


# def test_create_item_bad_token():
#     response = client.post(
#         "/items/",
#         headers={"X-Token": "hailhydra"},
#         json={"id": "bazz", "title": "Bazz", "description": "Drop the bazz"},
#     )
#     assert response.status_code == 400
#     assert response.json() == {"detail": "Invalid X-Token header"}


# def test_create_existing_item():
#     response = client.post(
#         "/items/",
#         headers={"X-Token": "coneofsilence"},
#         json={
#             "id": "foo",
#             "title": "The Foo ID Stealers",
#             "description": "There goes my stealer",
#         },
#     )
#     assert response.status_code == 409
#     assert response.json() == {"detail": "Item already exists"}
