from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from league_app.api.players import models, schema


@pytest.mark.asyncio
async def test_fixture_types(
    engine: AsyncEngine,
    session: AsyncSession,
    client: AsyncClient,
    db_player1: models.Player,
):
    assert isinstance(engine, AsyncEngine)
    assert isinstance(session, AsyncSession)
    assert isinstance(client, AsyncClient)
    assert isinstance(db_player1, models.Player)


@pytest.mark.asyncio
async def test_have_test_db(
    session: AsyncSession,
):
    stmt = select(models.Player).filter(
        models.Player.uuid == UUID("51da75b7-e4a9-460e-a067-c869e82c579c")
    )
    result = await session.scalar(stmt)
    assert result is None


@pytest.mark.asyncio
async def test_have_test_client(
    client: AsyncClient,
):
    assert isinstance(client, AsyncClient)
    response = await client.get("/api/v1/players/51da75b7-e4a9-460e-a067-c869e82c579c")
    data = response.json()
    assert {"detail": "Player not found"} == data


# ** Test /api/v1/players/


@pytest.mark.asyncio
async def test_read_player(
    client: AsyncClient,
    db_player1: models.Player,
) -> None:
    response = await client.get("/api/v1/players/")
    data = response.json()
    assert response.status_code == 200
    assert len(data) == 1
    assert schema.PlayerOutput(**data[0]) == schema.PlayerOutput.model_validate(
        db_player1
    )


@pytest.mark.asyncio
async def test_create_player(client: AsyncClient, session: AsyncSession, player1: dict):
    response = await client.post("/api/v1/players/", json=player1)
    assert response.status_code == 200
    data = response.json()

    stmt = select(models.Player).filter(models.Player.uuid == UUID(data["uuid"]))
    db_player = await session.scalar(stmt)

    assert db_player is not None
    assert schema.PlayerOutput.model_validate(db_player) == schema.PlayerOutput(**data)
    # test cleanup
    await session.delete(db_player)
    await session.commit()


@pytest.mark.asyncio
async def test_create_player_existing_email(
    client: AsyncClient, player1: dict, db_player1: models.Player
):
    response = await client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}


@pytest.mark.asyncio
async def test_create_player_existing_nickname(
    client: AsyncClient, player1: dict, db_player1: models.Player
):
    player1["email"] = "different_" + player1["email"]
    response = await client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Nickname already registered"}


@pytest.mark.asyncio
async def test_update_existing_player_as_the_user_himself(
    client: AsyncClient,
    player1: dict,
    session: AsyncSession,
    db_player1: models.Player,
):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = await client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    assert schema.PlayerOutput(**response.json()) == schema.PlayerOutput(**player1)
    assert response.status_code == 200
    await session.refresh(db_player1)
    assert db_player1.last_name == "baz"


@pytest.mark.skip(reason="I have no way to detect admin at this point")
@pytest.mark.asyncio
async def test_update_existing_player_as_admin(
    client: AsyncClient,
    player1: dict,
    session: AsyncSession,
    db_player1: models.Player,
):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = await client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    assert response.status_code == 200
    assert schema.PlayerOutput(**response.json()) == schema.PlayerOutput(**player1)
    await session.refresh(db_player1)
    assert db_player1.last_name == "baz"


@pytest.mark.skip(reason="I have no way to detect user at this point")
@pytest.mark.asyncio
async def test_update_existing_player_as_another_player(
    client: AsyncClient,
    player1: dict,
    # session: AsyncSession,
    db_player1: models.Player,
):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = await client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)

    assert response.json() == {"detail": "User not authorized to modify someone else."}
    assert response.status_code == 403


@pytest.mark.asyncio
# FIXME: add permissions
async def test_update_email_of_existing_player(
    client: AsyncClient,
    player1: dict,
    session: AsyncSession,
    db_player1: models.Player,
):
    uuid = str(db_player1.uuid)
    player1["email"] = "foo@baz.com"
    player1["uuid"] = uuid
    response = await client.put(f"/api/v1/players/{uuid}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    await session.refresh(db_player1)
    assert schema.PlayerOutput(**player1) == schema.PlayerOutput(**response.json())
    assert schema.PlayerOutput.model_validate(db_player1) == schema.PlayerOutput(
        **player1
    )


@pytest.mark.asyncio
async def test_update_uuid_of_existing_player(
    client: AsyncClient, player1: dict, db_player1: models.Player
):
    uuid = str(db_player1.uuid)
    player1["uuid"] = "12345678-1234-abcd-abcd-1234567890ab"
    response = await client.put(f"/api/v1/players/{uuid}", json=player1)
    assert response.status_code == 403
    assert response.json() == {"detail": "User cannot change his UUID"}


# ** Test self /api/v1/players/self


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_get_self_player(client: AsyncClient, db_player1: models.Player):
    response = await client.get("/api/v1/players/self")
    data = response.json()
    # data["uuid"] = UUID(data["uuid"])
    assert response.status_code == 200
    p1data = schema.PlayerOutput.model_validate(db_player1).model_dump()
    p1data["uuid"] = str(p1data["uuid"])
    assert data == [p1data]


@pytest.mark.skip(reason="not yet")
def test_update_self_player(
    client: AsyncClient, player1: dict, session: AsyncSession, db_player1: models.Player
):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/self", json=player1)

    assert schema.PlayerOutput(**player1) == schema.PlayerOutput(**response.json())
    assert response.status_code == 200


# ** Test users


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_auth_user_register(client):
    response = await client.post(
        "/auth/register",
        json={"email": "foo1@bar.com", "password": "foobar"},
    )
    print(response.json())
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
