from typing import AsyncContextManager, Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from league_app.api.players.model import Player
from league_app.api.players.schema import PlayerCreate, PlayerOutput, PlayerUpdate
from league_app.api.users.model import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import PlayerFactoryType
from .testlib import assert_response_code
from fastapi.encoders import jsonable_encoder


# * /api/v1/players/


@pytest.mark.asyncio
async def test_admin_can_list_all_players(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that an admin can list all players in the system.
    """
    db_user1 = db_user1_with_pass[0]
    # Create players for different users
    player1 = await player_factory(PlayerCreate(user_id=None, nickname="p1"))
    player2 = await player_factory(PlayerCreate(user_id=db_user1.id, nickname="p2"))

    print(f"Created players: {player1.uuid}, {player2.uuid}")
    # Override current user as admin
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/players/")
    assert_response_code(response, 200)

    returned_players = [PlayerOutput(**p) for p in response.json()]
    assert PlayerOutput.model_validate(player1) in returned_players
    assert PlayerOutput.model_validate(player2) in returned_players


@pytest.mark.asyncio
async def test_create_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player1: dict[str, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post("/api/v1/players/", json=player1)
    print(response.json())
    assert_response_code(response, 200)
    data = response.json()
    stmt = select(Player).filter(Player.uuid == UUID(data["uuid"]))
    db_player = await session.scalar(stmt)

    assert db_player is not None
    assert PlayerOutput.model_validate(db_player) == PlayerOutput(**data)

    # test cleanup
    await session.delete(db_player)
    await session.commit()


@pytest.mark.asyncio
async def test_create_player_existing_email(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    player1: dict[str, str],
    db_player1: Player,
    db_user1_with_pass: tuple[User, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            "/api/v1/players/",
            json=player1,
        )
    assert response.json() == {"detail": "Email already registered"}
    assert_response_code(response, 400)


@pytest.mark.asyncio
async def test_create_player_existing_nickname(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    player1: dict[str, str],
    db_player1: Player,
    db_user1_with_pass: tuple[User, str],
):
    player1["email"] = "different_" + player1["email"]
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            "/api/v1/players/",
            json=player1,
        )
    assert response.json() == {"detail": "Nickname already registered"}
    assert_response_code(response, 400)


# * /api/v1/players/{uuid}


@pytest.mark.asyncio
async def test_get_player_details(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can get details of a player linked to their user_id.
    """
    db_user1 = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=db_user1.id, nickname="test_player")
    )
    async with logged_client(*db_user2_with_pass) as client:
        response = await client.get(f"/api/v1/players/{player.uuid}")
    assert_response_code(response, 200)
    data = response.json()
    assert PlayerOutput.model_validate(player) == PlayerOutput(**data)


@pytest.mark.asyncio
async def test_user_can_update_own_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can update a player linked to their user_id.
    """
    db_user1 = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=db_user1.id, nickname="editable_player")
    )
    update_data = {"uuid": str(player.uuid), "nickname": "updated_nickname"}
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(f"/api/v1/players/{player.uuid}", json=update_data)
    assert_response_code(response, 200)
    assert response.json()["nickname"] == "updated_nickname"
    await session.refresh(player)
    assert player.nickname == "updated_nickname"


@pytest.mark.asyncio
async def test_admin_can_update_any_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that an admin can update any player's details.
    """
    db_user1 = db_user1_with_pass[0]
    db_player = await player_factory(
        PlayerCreate(nickname="admin_editable_player", user_id=db_user1.id)
    )
    updated_data = {"uuid": str(db_player.uuid), "nickname": "admin_updated_nickname"}

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.put(
            f"/api/v1/players/{db_player.uuid}", json=updated_data
        )
    assert_response_code(response, 200)
    assert response.json()["nickname"] == "admin_updated_nickname"
    await session.refresh(db_player)
    assert db_player.nickname == "admin_updated_nickname"


@pytest.mark.asyncio
async def test_user_cannot_update_player_of_another_user(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user cannot update a player not linked to their user_id.
    """
    db_user2 = db_user2_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=db_user2.id, nickname="not_my_player")
    )
    updated_player = PlayerUpdate.model_validate(player)
    updated_player.nickname = "hacker_attempt"
    updated_payload = jsonable_encoder(updated_player)

    async with logged_client(*db_user1_with_pass) as client:
        # Attempt to update a player not linked to the user
        response = await client.put(
            f"/api/v1/players/{player.uuid}", json=updated_payload
        )
    assert_response_code(response, 403)


@pytest.mark.asyncio
async def test_update_email_of_existing_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    db_player = await player_factory(
        PlayerCreate(
            user_id=db_user1.id,
            nickname="player_a",
            email="foo@example.com",
            first_name="Player",
            last_name="A",
        )
    )
    updated_player = PlayerUpdate.model_validate(db_player)
    updated_player.email = "foo@baz.com"
    updated_payload = jsonable_encoder(updated_player)

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(
            f"/api/v1/players/{db_player.uuid}", json=updated_payload
        )
    print(response.json())
    assert_response_code(response, 200)
    await session.refresh(db_player)
    assert updated_payload["email"] == response.json()["email"]
    assert PlayerOutput(**response.json()) == PlayerOutput.model_validate(db_player)


@pytest.mark.asyncio
async def test_update_uuid_of_existing_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    db_player = await player_factory(
        PlayerCreate(
            user_id=db_user1.id,
            nickname="player_a",
            email="foo@example.com",
            first_name="Player",
            last_name="A",
        )
    )
    updated_player = PlayerUpdate.model_validate(db_player)
    updated_player.uuid = UUID("12345678-1234-abcd-abcd-1234567890ab")
    updated_payload = jsonable_encoder(updated_player)
    uuid = str(db_player.uuid)
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(f"/api/v1/players/{uuid}", json=updated_payload)
    assert_response_code(response, 403)
    assert response.json() == {"detail": "User cannot change his UUID"}


# * Test self /api/v1/players/self


@pytest.mark.asyncio
async def test_user_with_no_linked_players_gets_empty_list(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    """
    Test that a user with no linked players gets an empty list.
    """
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    assert response.json() == []


@pytest.mark.asyncio
async def test_player_with_null_user_id_not_returned(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that players with user_id=None are not returned in /players/self.
    """
    await player_factory(PlayerCreate(user_id=None, nickname="orphan_player"))
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    data = response.json()
    assert all(p["nickname"] != "orphan_player" for p in data)


@pytest.mark.asyncio
async def test_list_players_linked_to_user(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can list all players linked to their user_id.
    """
    db_user1 = db_user1_with_pass[0]
    # Create two players linked to the same user
    player_a = await player_factory(
        PlayerCreate(
            user_id=db_user1.id,
            nickname="player_a",
            email="player_a@example.com",
            first_name="Player",
            last_name="A",
        )
    )
    player_b = await player_factory(
        PlayerCreate(
            user_id=db_user1.id, nickname="player_b", email="player_b@example.com"
        )
    )

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    data = response.json()
    returned_uuids = {p["uuid"] for p in data}
    assert {str(player_a.uuid), str(player_b.uuid)}.issubset(returned_uuids)


@pytest.mark.asyncio
async def test_user_cannot_list_players_of_another_user(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user cannot see players linked to another user.
    """
    db_user1 = db_user1_with_pass[0]
    db_user2 = db_user2_with_pass[0]
    player = await player_factory(PlayerCreate(user_id=db_user1.id, nickname="my_player"))  # type: ignore
    # Create a player for another user
    player_other = await player_factory(
        PlayerCreate(user_id=db_user2.id, nickname="other_player")
    )

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    data = response.json()
    # Ensure the other user's player is not in the list
    assert all(p["uuid"] != str(player_other.uuid) for p in data)


# * /api/v1/players/search?nickname={nickname}


@pytest.mark.asyncio
async def test_user_search_players_by_nickname(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
    session: AsyncSession,
):
    """
    Test that a user can search for players by nickname.
    """
    db_player = await player_factory(
        PlayerCreate(
            user_id=None,
            nickname="searched player",
            email="searched_player@example.com",
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/search?nickname=searched%20player")
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_player = PlayerOutput(**(data[0]))
    output_db_player = PlayerOutput.model_validate(db_player)
    assert output_player.email == None, "Email should not be visible to regular users"
    output_db_player.email = None  # Ensure email is not compared
    assert output_player == output_db_player


@pytest.mark.asyncio
async def test_user_search_players_by_email(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can search for players by email.
    """
    db_player = await player_factory(  # type: ignore
        PlayerCreate(
            user_id=None,
            nickname="searched player",
            email="searched_player@example.com",
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get(
            "/api/v1/players/search?email=searched_player@example.com"
        )
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_player = PlayerOutput(**(data[0]))
    output_db_player = PlayerOutput.model_validate(db_player)
    # FIXME: check e-mail visibility based on user role
    assert output_player == output_db_player
    assert (
        output_player.email == output_db_player.email
    ), "Email should be visible to regular users if searched by email"


@pytest.mark.asyncio
async def test_admin_search_players_by_nickname(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that an admin can search for players by nickname.
    """
    db_player = await player_factory(  # type: ignore
        PlayerCreate(
            user_id=None,
            nickname="searched player",
            email="searched_player@example.com",
        )
    )
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/players/search?nickname=searched%20player")
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_player = PlayerOutput(**(data[0]))
    output_db_player = PlayerOutput.model_validate(db_player)
    assert output_player == output_db_player
    assert output_player.email is not None, "Email should be visible to admins"
