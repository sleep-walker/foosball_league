from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from league_app.api.players.model import Player
from league_app.api.players.schema import PlayerCreate
from league_app.api.users.model import User
from league_app.api.users.schema import UserCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from .conftest import PlayerFactoryType, UserFactoryType


@pytest.mark.asyncio
async def test_fixture_types(
    test_engine: AsyncEngine,
    session: AsyncSession,
    client: AsyncClient,
    db_player1: Player,
    db_user1_with_pass: tuple[User, str],
):
    """Test that the fixtures are of the expected types."""
    assert isinstance(test_engine, AsyncEngine)
    assert isinstance(session, AsyncSession)
    assert isinstance(client, AsyncClient)
    assert isinstance(db_player1, Player)
    assert isinstance(db_user1_with_pass[0], User)
    assert isinstance(db_user1_with_pass[1], str)


@pytest.mark.asyncio
async def test_have_test_db(
    session: AsyncSession,
    db_player1: Player,
):
    """Test that the test database is available and can perform query."""
    stmt = select(Player).filter(
        Player.uuid == UUID("00000000-0000-0000-0000-000000000001")
    )
    result = await session.scalar(stmt)
    assert result is None


@pytest.mark.asyncio
async def test_have_test_client(
    client: AsyncClient,
):
    """Test that the test client can make requests."""
    assert isinstance(client, AsyncClient)
    response = await client.get(f"/api/v1/ping")
    data = response.json()
    assert {"message": "pong"} == data, f"Different response: {data}"


@pytest.mark.asyncio
async def test_user_factory_creates_user(user_factory: UserFactoryType):
    """Test that the user factory creates a user."""
    user_create = UserCreate(
        email="test@example.com", username="test", password="testpass"
    )
    user = await user_factory(user_create)
    assert isinstance(user, User)
    assert user.email == "test@example.com"
    assert user.hashed_password != "testpass"  # Should be hashed


@pytest.mark.asyncio
async def test_user_factory_cleanup(
    user_factory: UserFactoryType, session: AsyncSession
):
    """Test that the user factory cleans up after itself."""
    stmt = select(User).filter(User.email == "test@example.com")  # type: ignore
    found = await session.scalar(stmt)
    assert found is None


@pytest.mark.asyncio
async def test_user_factory_creates_multiple_users(
    user_factory: UserFactoryType, session: AsyncSession
):
    num = 3

    user_data = [
        UserCreate(
            email=f"user_{i}@example.com",
            username=f"user_{i}",
            password=f"password_{i}",
        )
        for i in range(num)
    ]

    created_users: list[User] = []
    for udata in user_data:
        user = await user_factory(udata)
        created_users.append(user)

    assert len(created_users) == num
    # Verify all users exist in the database
    for i in range(num):
        user = created_users[i]
        assert isinstance(user, User)
        assert user.email == f"user_{i}@example.com"

        found = await session.get(User, user.id)
        assert found is not None
        assert found.email == user.email


@pytest.mark.asyncio
async def test_player_factory_creates_player(player_factory: PlayerFactoryType):
    player_create = PlayerCreate(
        user_id=uuid4(),
        nickname="testplayer",
        first_name="Test",
        last_name="Player",
        email="testplayer@example.com",
    )
    player = await player_factory(player_create)
    assert isinstance(player, Player)
    assert player.nickname == "testplayer"
    assert player.email == "testplayer@example.com"


@pytest.mark.asyncio
async def test_player_factory_cleanup(
    player_factory: PlayerFactoryType, session: AsyncSession
):
    player_create = PlayerCreate(
        user_id=uuid4(),
        nickname="cleanupplayer",
        first_name="Clean",
        last_name="Up",
        email="cleanupplayer@example.com",
    )
    player = await player_factory(player_create)
    player_id = player.uuid
    # Player should exist
    found = await session.get(Player, player_id)
    assert found is not None
    # Cleanup happens after fixture scope ends (pytest will handle this)


@pytest.mark.asyncio
async def test_player_factory_creates_multiple_players(
    player_factory: PlayerFactoryType, session: AsyncSession
):
    num: int = 3

    player_data = [
        PlayerCreate(
            user_id=uuid4(),
            nickname=f"player_{i}",
            first_name=f"First{i}",
            last_name=f"Last{i}",
            email=f"player_{i}@example.com",
        )
        for i in range(num)
    ]

    created_players: list[Player] = []
    for pdata in player_data:
        player = await player_factory(pdata)
        created_players.append(player)

    assert len(created_players) == num
    # Verify all players exist in the database
    for i in range(num):
        player = created_players[i]
        assert isinstance(player, Player)
        assert player.nickname == f"player_{i}"
        assert player.email == f"player_{i}@example.com"

        found = await session.get(Player, player.uuid)
        assert found is not None
        assert found.nickname == player.nickname
        assert found.email == player.email
