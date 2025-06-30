from uuid import UUID
from typing import Callable
import pytest

from .conftest import PlayerFactoryType

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.players import model, schema
from league_app.api.users.model import User

# * Test reading of players
@pytest.mark.asyncio
async def test_list_players_linked_to_user(logged_client: Callable[[User], object], session: AsyncSession, db_user1: User, player_factory: PlayerFactoryType):
    """
    Test that a user can list all players linked to their user_id.
    """
    # Create two players linked to the same user
    player_a = await player_factory(session, user_id=db_user1.id, nickname="player_a", email="player_a@example.com", first_name="Player", last_name="A", commit=True)
    player_b = await player_factory(session, user_id=db_user1.id, nickname="player_b", email="player_b@example.com", commit=True)

    async with logged_client(as_user=db_user1) as client:
        response = await client.get("/api/v1/players/self")
    assert response.status_code == 200
    data = response.json()
    returned_uuids = {p["uuid"] for p in data}
    assert {str(player_a.uuid), str(player_b.uuid)}.issubset(returned_uuids)


@pytest.mark.asyncio
@pytest.mark.skip(reason="not yet implemented")
async def test_user_cannot_list_players_of_another_user(
    client: AsyncClient, session: AsyncSession, db_user1: User, db_user2: User, player_factory: PlayerFactoryType
):
    """
    Test that a user cannot see players linked to another user.
    """
    # Create a player for another user
    player_other = await player_factory(session, user_id=db_user2.id, nickname="other_player")

    response = await client.get("/api/v1/players/self")
    assert response.status_code == 200
    data = response.json()
    # Ensure the other user's player is not in the list
    assert all(p["uuid"] != str(player_other.uuid) for p in data)

@pytest.mark.asyncio
async def test_admin_can_list_all_players(client: AsyncClient, session: AsyncSession, db_administrator1: User, player_factory: PlayerFactoryType):
    """
    Test that an admin can list all players in the system.
    """
    # Create players for different users
    player1 = await player_factory(session, user_id=None, nickname="p1")
    player2 = await player_factory(session, user_id=None, nickname="p2")

    # Override current user as admin
    # (Assume you have a fixture or helper for this)
    response = await client.get("/api/v1/players/")
    assert response.status_code == 200
    data = response.json()
    returned_uuids = {p["uuid"] for p in data}
    assert {str(player1.uuid), str(player2.uuid)}.issubset(returned_uuids)

@pytest.mark.asyncio
async def test_user_with_no_linked_players_gets_empty_list(client: AsyncClient, db_user1: User):
    """
    Test that a user with no linked players gets an empty list.
    """
    response = await client.get("/api/v1/players/self")
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_player_with_null_user_id_not_returned(client: AsyncClient, session: AsyncSession, db_user1: User, player_factory: PlayerFactoryType):
    """
    Test that players with user_id=None are not returned in /players/self.
    """
    await player_factory(session, user_id=None, nickname="orphan_player")
    response = await client.get("/api/v1/players/self")
    assert response.status_code == 200
    data = response.json()
    assert all(p["nickname"] != "orphan_player" for p in data)

@pytest.mark.asyncio
async def test_user_can_update_own_player(client: AsyncClient, session: AsyncSession, db_user1: User, player_factory: PlayerFactoryType):
    """
    Test that a user can update a player linked to their user_id.
    """
    player = await player_factory(session, user_id=db_user1.id, nickname="editable_player")
    update_data = {"nickname": "updated_nickname"}
    response = await client.put(f"/api/v1/players/{player.uuid}", json=update_data)
    assert response.status_code == 200
    assert response.json()["nickname"] == "updated_nickname"

@pytest.mark.skip(reason="not yet implemented")
@pytest.mark.asyncio
async def test_user_cannot_update_unlinked_player(client: AsyncClient, session: AsyncSession, db_user2: User, player_factory: PlayerFactoryType):
    """
    Test that a user cannot update a player not linked to their user_id.
    """
    player = await player_factory(session, user_id=db_user2.id, nickname="not_my_player")
    update_data = {"nickname": "hacker_attempt"}
    response = await client.put(f"/api/v1/players/{player.uuid}", json=update_data)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_read_player(
    client: AsyncClient,
    db_player1: model.Player,
) -> None:
    """Test that the list of players can be read."""
    response = await client.get("/api/v1/players/")
    data = response.json()
    assert response.status_code == 200
    assert len(data) == 1
    assert schema.PlayerOutput(**data[0]) == schema.PlayerOutput.model_validate(
        db_player1
    )


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_create_player(
    client: AsyncClient,
    session: AsyncSession,
    player1: dict[str, str],
    override_current_user_with_user1: User,
):
    response = await client.post("/api/v1/players/", json=player1)
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    stmt = select(model.Player).filter(model.Player.uuid == UUID(data["uuid"]))
    db_player = await session.scalar(stmt)

    assert db_player is not None
    assert schema.PlayerOutput.model_validate(db_player) == schema.PlayerOutput(**data)
    # test cleanup
    await session.delete(db_player)
    await session.commit()


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_create_player_existing_email(
    client: AsyncClient,
    player1: dict[str, str],
    db_player1: model.Player,
    override_current_user_with_user1: User,
):
    response = await client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.json() == {"detail": "Email already registered"}
    assert response.status_code == 400


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_create_player_existing_nickname(
    client: AsyncClient,
    player1: dict[str, str],
    db_player1: model.Player,
    override_current_user_with_user1: User,
):
    player1["email"] = "different_" + player1["email"]
    response = await client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.json() == {"detail": "Nickname already registered"}
    assert response.status_code == 400


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_update_existing_player_as_the_user_himself(
    client: AsyncClient,
    player1: dict[str, str],
    session: AsyncSession,
    db_player1: model.Player,
    override_current_user_with_user1: User,
) -> None:
    player1["last_name"] = "baz"
    print(db_player1.uuid)
    print(override_current_user_with_user1.id)
    assert override_current_user_with_user1.id == db_player1.uuid
    player1_uuid = db_player1.uuid
    del player1["uuid"]
    response = await client.put(
        f"/api/v1/players/{str(override_current_user_with_user1.id)}", json=player1
    )
    print(response.json())
    assert response.status_code == 200
    assert schema.PlayerOutput(**response.json()) == schema.PlayerOutput(**player1, uuid=player1_uuid)
    assert response.status_code == 200
    await session.refresh(db_player1)
    assert db_player1.last_name == "baz"


@pytest.mark.skip(reason="I have no way to detect admin at this point")
@pytest.mark.asyncio
async def test_update_existing_player_as_admin(
    client: AsyncClient,
    player1: dict[str, str],
    session: AsyncSession,
    db_player1: model.Player,
):
    player1["last_name"] = "baz"
    player1_uuid = db_player1.uuid
    del player1["uuid"]
    response = await client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    assert response.status_code == 200
    assert schema.PlayerOutput(**response.json()) == schema.PlayerOutput(**player1, uuid=player1_uuid)
    await session.refresh(db_player1)
    assert db_player1.last_name == "baz"


@pytest.mark.skip(reason="I have no way to detect user at this point")
@pytest.mark.asyncio
async def test_update_existing_player_as_another_player(
    client: AsyncClient,
    player1: dict[str, str],
    # session: AsyncSession,
    db_player1: model.Player,
    override_current_user_with_user1: User,
):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = await client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)

    assert response.json() == {"detail": "User not authorized to modify someone else."}
    assert response.status_code == 403


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
# FIXME: add permissions
async def test_update_email_of_existing_player(
    client: AsyncClient,
    db_player1: User,
    player1: dict[str, str],
    session: AsyncSession,
    user_player: model.Player,
    override_current_user_with_user1: User,
):
    uuid = str(override_current_user_with_user1.id)
    player = schema.PlayerUpdate.model_validate(user_player)
    player.email = "foo@baz.com"
    player.uuid = UUID(uuid)
    player1_uuid = UUID(player1["uuid"])
    del player1["uuid"]
    response = await client.put(f"/api/v1/players/{uuid}", json=player1)
    print(response.json())
    assert response.status_code == 200
    await session.refresh(db_player1)
    assert schema.PlayerOutput(**player1, uuid=player1_uuid) == schema.PlayerOutput(**response.json())
    assert schema.PlayerOutput.model_validate(db_player1) == schema.PlayerOutput(
        **player1, uuid=player1_uuid
    )


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_update_uuid_of_existing_player(
    client: AsyncClient, db_user1: User, user_player: model.Player, player1: dict[str, str]
):
    uuid = str(db_user1.id)
    player1["uuid"] = "12345678-1234-abcd-abcd-1234567890ab"
    response = await client.put(f"/api/v1/players/{uuid}", json=player1)
    assert response.status_code == 403
    assert response.json() == {"detail": "User cannot change his UUID"}


# ** Test self /api/v1/players/self

@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_get_self_player(client: AsyncClient, db_player1: model.Player):
    response = await client.get("/api/v1/players/self")
    data = response.json()
    # data["uuid"] = UUID(data["uuid"])
    assert response.status_code == 200
    p1data = schema.PlayerOutput.model_validate(db_player1).model_dump()
    p1data["uuid"] = str(p1data["uuid"])
    assert data == [p1data]


@pytest.mark.skip(reason="not yet")
@pytest.mark.asyncio
async def test_update_self_player(
    client: AsyncClient, player1: dict[str, str], session: AsyncSession, db_user1: User, db_player1: model.Player
):
    player1["last_name"] = "baz"
    response = await client.put("/api/v1/players/self", json=player1)
    assert schema.PlayerOutput(**player1, uuid=UUID(str(db_user1.id))) == schema.PlayerOutput(**response.json())
    assert response.status_code == 200


# ** Test users
