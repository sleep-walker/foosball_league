from typing import AsyncGenerator, Optional, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi_users.password import PasswordHelper
from httpx import ASGITransport, AsyncClient
from league_app.api.players.model import Player
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from league_app.database import (Base, get_async_engine,
                                 get_async_session_maker, get_session,
                                 get_session_for_api)
from league_app.main import app
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:?cache=shared"

@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = get_async_engine(TEST_DATABASE_URL, use_static_pool=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def session(test_engine: AsyncEngine):
    session_maker = get_async_session_maker(test_engine)
    async for s in get_session(session_maker):
        yield s

@pytest_asyncio.fixture(scope="function")
async def client(session: AsyncSession, test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session
    app.dependency_overrides[get_session_for_api] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def player1() -> AsyncGenerator[dict[str, str], None]:
    yield {
        "first_name": "foo",
        "last_name": "bar",
        "nickname": "foobar",
        "email": "foo@bar.com",
    }


@pytest_asyncio.fixture(scope="function")
async def db_player1(session: AsyncSession, player1: dict[str, str]) -> AsyncGenerator[Player, None]:
    async with session as sess:
        db_player = Player(**player1)
        sess.add(db_player)
        await sess.flush()
        await sess.commit()
        await sess.refresh(db_player)
        yield db_player
        await sess.delete(db_player)
        await sess.commit()


@pytest_asyncio.fixture(scope="function")
async def user1() -> AsyncGenerator[dict[str, str], None]:
    yield {
        "email": "foo@bar.com",
        "password": "foobar",
    }


def create_user(user: dict[str, str]) -> User:
    password_helper = PasswordHelper()
    hashed_password = password_helper.hash(user["password"])
    db_user = User(email=user["email"], hashed_password=hashed_password)
    return db_user


async def create_db_user(session: AsyncSession, db_user: User) -> AsyncGenerator[User, None]:
    async with session as sess:
        sess.add(db_user)
        # db_player = Player(**player1, uuid=db_user.id)
        # sess.add(db_player)
        await sess.flush()
        await sess.commit()
        await sess.refresh(db_user)
        # await sess.refresh(db_player)
        # yield (db_user, db_player)
        yield db_user
        await sess.delete(db_user)
        # await sess.delete(db_player)
        await sess.commit()


@pytest_asyncio.fixture(scope="function")
async def db_user1(session: AsyncSession, user1: dict[str, str]) -> AsyncGenerator[User, None]:
    db_user = create_user(user1)
    async for db_user1 in create_db_user(session, db_user):
        yield db_user1

@pytest_asyncio.fixture(scope="function")
async def user_player(session: AsyncSession, db_user1: User):
    async with session as sess:
        db_player = Player(
            nickname=db_user1.email, email=db_user1.email, uuid=db_user1.id, first_name="first", last_name="last"
        )
        sess.add(db_player)
        await sess.flush()
        await sess.commit()
        await sess.refresh(db_player)
        yield db_player
        await sess.delete(db_player)
        await sess.commit()


@pytest_asyncio.fixture(scope="function")
async def administrator1():
    yield {
        "email": "administrator@bar.com",
        "password": "h4rd_to_cr4ck",
    }


@pytest_asyncio.fixture(scope="function")
async def db_administrator1(session: AsyncSession, administrator1: dict[str, str]) -> AsyncGenerator[User, None]:
    db_administrator = create_user(administrator1)
    db_administrator.is_superuser = True
    async for db_administrator1 in create_db_user(session, db_administrator):
        yield db_administrator1


# FIXME: this affects whole app - isn't there better way?
@pytest_asyncio.fixture(scope="function")
async def override_current_user_with_user1(db_user1: User) -> AsyncGenerator[User, None]:
    orig_fn = app.dependency_overrides.get(current_active_verified_user, None)
    app.dependency_overrides[current_active_verified_user] = lambda: db_user1
    yield db_user1
    if orig_fn:
        app.dependency_overrides[current_active_verified_user] = orig_fn
    else:
        del app.dependency_overrides[current_active_verified_user]

player_factory_type = Callable[
    [AsyncSession, Optional[UUID], str, Optional[str], Optional[str], Optional[str], Optional[UUID], bool],
    Awaitable[Player]
]

class PlayerFactoryType(Protocol):
    def __call__(
        self,
        *,
        user_id: Optional[UUID] = None,
        nickname: str = "test_player",
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        uuid_: Optional[UUID] = None,
        commit: bool = True,
    ) -> Awaitable[Player]: ...

@pytest_asyncio.fixture(scope="function")
async def player_factory(session: AsyncSession) -> AsyncGenerator[PlayerFactoryType, None]:
    created_players: list[Player] = []

    async def _factory(
        session: AsyncSession = session,
        *,
        user_id: Optional[UUID] = None,
        nickname: str = "test_player",
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        uuid_: Optional[UUID] = None,
        commit: bool = True,
    ) -> Player:
        player = Player(
            uuid=uuid_ or uuid4(),
            user_id=user_id,
            nickname=nickname,
            first_name=first_name,
            last_name=last_name,
            email=email or f"{nickname}@example.com",
        )
        session.add(player)
        if commit:
            await session.commit()
            await session.refresh(player)
        created_players.append(player)
        return player

    try:
        yield _factory
    finally:
        # Cleanup after test
        for player in created_players:
            await session.delete(player)
        await session.commit()


@pytest.fixture(scope="function")
def logged_client(client: AsyncClient) -> Callable[[User], object]:
    """
    Returns a function that, when called with as_user=User, returns a client
    with the current_active_verified_user dependency overridden for that user.
    Usage:
        async with logged_client(as_user=db_user1) as ac:
            await ac.get("/api/v1/players/self")
    """
    def _get_logged_client(as_user: User):
        # Save original override
        orig_override = app.dependency_overrides.get(current_active_verified_user, None)
        app.dependency_overrides[current_active_verified_user] = lambda: as_user

        class _ClientContext:
            async def __aenter__(self):
                return client
            async def __aexit__(self, exc_type, exc, tb):
                # Restore original override
                if orig_override:
                    app.dependency_overrides[current_active_verified_user] = orig_override
                else:
                    del app.dependency_overrides[current_active_verified_user]

        return _ClientContext()

    return _get_logged_client