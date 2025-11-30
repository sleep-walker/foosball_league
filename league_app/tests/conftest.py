from typing import AsyncGenerator, Awaitable, Callable, Protocol, AsyncContextManager
from uuid import uuid4

from contextlib import asynccontextmanager
from faker import Faker
import pytest
import pytest_asyncio
from fastapi_users.password import PasswordHelper
from httpx import ASGITransport, AsyncClient
from league_app.api.users.model import User
from league_app.api.players.model import Player
from league_app.api.leagues.model import League
from league_app.api.users.schema import UserCreate
from league_app.api.players.schema import PlayerCreate
from league_app.api.leagues.schema import LeagueCreate
from league_app.api.tournaments.model import Tournament
from league_app.api.tournaments.schema import TournamentCreate
from league_app.api.games.model import Game
from league_app.api.games.schema import GameCreate

from league_app.database import (
    Base,
    get_async_engine,
    get_async_session_maker,
    get_session,
    get_session_for_api,
)
from league_app.main import app
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:?cache=shared"

faker = Faker()


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
async def client(
    session: AsyncSession, test_engine: AsyncEngine
) -> AsyncGenerator[AsyncClient, None]:
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
async def db_player1(
    session: AsyncSession, player1: dict[str, str]
) -> AsyncGenerator[Player, None]:
    async with session as sess:
        db_player = Player(**player1)
        sess.add(db_player)
        await sess.flush()
        await sess.commit()
        await sess.refresh(db_player)
        yield db_player
        await sess.delete(db_player)
        await sess.commit()


class UserFactoryType(Protocol):
    def __call__(
        self,
        user_create: UserCreate,
        *,
        commit: bool = True,
    ) -> Awaitable[User]: ...


def create_user(user: dict[str, str]) -> User:
    password_helper = PasswordHelper()
    hashed_password = password_helper.hash(user["password"])
    db_user = User(email=user["email"], hashed_password=hashed_password)
    return db_user


@pytest_asyncio.fixture(scope="function")
async def user_factory(session: AsyncSession) -> AsyncGenerator[UserFactoryType, None]:
    created_users: list[User] = []

    async def _factory(
        user_create: UserCreate,
        *,
        commit: bool = True,
    ) -> User:
        password_helper = PasswordHelper()
        hashed_password = password_helper.hash(user_create.password)
        user = User(
            email=user_create.email,
            hashed_password=hashed_password,
            username=user_create.username,
            is_superuser=getattr(user_create, "is_superuser", False),
            is_active=getattr(user_create, "is_active", True),
            is_verified=getattr(user_create, "is_verified", True),
        )
        session.add(user)
        if commit:
            await session.commit()
            await session.refresh(user)
        created_users.append(user)
        return user

    try:
        yield _factory
    finally:
        for user in created_users:
            db_user = await session.get(User, user.id)
            if db_user:
                await session.delete(user)
        await session.commit()


@pytest_asyncio.fixture(scope="function")
async def user1():
    yield UserCreate(
        email="foo@bar.com", username="foo bar", password="foobar", is_verified=True
    )


@pytest_asyncio.fixture(scope="function")
async def user2():
    yield UserCreate(
        email="baz@qux.com", username="baz qux", password="bazqux", is_verified=True
    )


@pytest_asyncio.fixture(scope="function")
async def administrator1():
    yield UserCreate(
        email="administrator@bar.com",
        username="some admin",
        password="h4rd_to_cr4ck",
        is_superuser=True,
        is_verified=True,
    )


@pytest_asyncio.fixture(scope="function")
async def db_user1_with_pass(
    user_factory: UserFactoryType, user1: UserCreate
) -> AsyncGenerator[tuple[User, str], None]:
    user = await user_factory(user1)
    yield user, user1.password


@pytest_asyncio.fixture(scope="function")
async def db_user2_with_pass(
    user_factory: UserFactoryType, user2: UserCreate
) -> AsyncGenerator[tuple[User, str], None]:
    user = await user_factory(user2)
    yield user, user2.password


@pytest_asyncio.fixture(scope="function")
async def db_administrator1_with_pass(
    user_factory: UserFactoryType, administrator1: UserCreate
) -> AsyncGenerator[tuple[User, str], None]:
    user = await user_factory(administrator1)
    yield user, administrator1.password


class PlayerFactoryType(Protocol):
    def __call__(
        self,
        player_create: PlayerCreate,
        *,
        commit: bool = True,
    ) -> Awaitable[Player]: ...


@pytest_asyncio.fixture(scope="function")
async def player_factory(
    session: AsyncSession,
) -> AsyncGenerator[PlayerFactoryType, None]:
    created_players: list[Player] = []

    async def _factory(
        player_create: PlayerCreate,
        *,
        commit: bool = True,
    ) -> Player:
        player = Player(
            uuid=player_create.uuid or uuid4(),
            user_id=player_create.user_id,
            nickname=player_create.nickname,
            first_name=player_create.first_name,
            last_name=player_create.last_name,
            email=player_create.email or faker.email(),
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


"""
@pytest.fixture(scope="function")
def logged_client(
    client: AsyncClient,
) -> Callable[[User], AsyncContextManager[AsyncClient]]:
    ""
    Returns a function that, when called with as_user=User, returns a client
    with the current_active_verified_user dependency overridden for that user.
    Usage:
        async with logged_client(as_user=db_user1) as ac:
            await ac.get("/api/v1/players/self")
    ""

    @asynccontextmanager
    async def _context(as_user: User):

        orig_current_active_verified_override = app.dependency_overrides.get(
            current_active_verified_user, None
        )
        orig_superuser_override = app.dependency_overrides.get(current_superuser, None)
        app.dependency_overrides[current_active_verified_user] = lambda: as_user
        app.dependency_overrides[current_superuser] = (
            lambda: as_user
        )  # if as_user.is_superuser else None
        try:
            yield client
        finally:
            if orig_current_active_verified_override:
                app.dependency_overrides[current_active_verified_user] = (
                    orig_current_active_verified_override
                )
            else:
                del app.dependency_overrides[current_active_verified_user]
            if orig_superuser_override:
                app.dependency_overrides[current_superuser] = orig_superuser_override
            else:
                del app.dependency_overrides[current_superuser]

    return _context
"""


@pytest.fixture(scope="function")
def logged_client(
    client: AsyncClient,
) -> Callable[[User, str], AsyncContextManager[AsyncClient]]:
    @asynccontextmanager
    async def _context(as_user: User, password: str):
        response = await client.post(
            "/api/v1/users/login",
            data={"username": as_user.email, "password": password},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        token = response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        try:
            yield client
        finally:
            client.headers.pop("Authorization", None)

    return _context


class LeagueFactoryType(Protocol):
    def __call__(
        self,
        league_create: LeagueCreate,
        *,
        commit: bool = True,
    ) -> Awaitable[League]: ...


@pytest_asyncio.fixture(scope="function")
async def league_factory(
    session: AsyncSession,
) -> AsyncGenerator["LeagueFactoryType", None]:
    created_leagues: list[League] = []

    async def _factory(
        league_create: LeagueCreate,
        *,
        commit: bool = True,
    ) -> League:
        league = League(
            uuid=uuid4(),
            name=league_create.name,
            description=league_create.description or "",
            owner_id=league_create.owner_id,
            registration_type=league_create.registration_type or "open",
            is_active=getattr(league_create, "is_active", True),
        )
        session.add(league)
        if commit:
            await session.commit()
            await session.refresh(league)
        created_leagues.append(league)
        return league

    try:
        yield _factory
    finally:
        # Cleanup after test
        for league in created_leagues:
            await session.delete(league)
        await session.commit()

@pytest_asyncio.fixture(scope="function")
async def league1(db_user1_with_pass: tuple[User, str]) -> AsyncGenerator[LeagueCreate, None]:
    yield LeagueCreate(
        name="League 1",
        description="Description for League 1",
        registration_type="open",
        owner_id=db_user1_with_pass[0].id,
    )

@pytest_asyncio.fixture(scope="function")
async def league2(db_user2_with_pass: tuple[User, str]) -> AsyncGenerator[LeagueCreate, None]:
    yield LeagueCreate(
        name="League 2",
        description="Description for League 2",
        registration_type="open",
        owner_id=db_user2_with_pass[0].id,
    )


@pytest_asyncio.fixture(scope="function")
async def db_league1(
    league_factory: LeagueFactoryType, league1: LeagueCreate
) -> AsyncGenerator[League, None]:
    db_league = await league_factory(league1)
    yield db_league

@pytest_asyncio.fixture(scope="function")
async def db_league2(
    league_factory: LeagueFactoryType, league2: LeagueCreate
) -> AsyncGenerator[League, None]:
    db_league = await league_factory(league2)
    yield db_league


class TournamentFactoryType(Protocol):
    def __call__(
        self,
        tournament_create: TournamentCreate,
        *,
        commit: bool = True,
    ) -> Awaitable[Tournament]: ...

@pytest_asyncio.fixture(scope="function")
async def tournament_factory(
    session: AsyncSession,
) -> AsyncGenerator["TournamentFactoryType", None]:
    created_tournaments: list[Tournament] = []

    async def _factory(
        tournament_create: TournamentCreate,
        *,
        commit: bool = True,
    ) -> Tournament:
        tournament = Tournament(
            uuid=uuid4(),
            name=tournament_create.name,
            date=tournament_create.date,
            location=tournament_create.location,
            owner_id=tournament_create.owner_id,
            is_deleted=getattr(tournament_create, "is_deleted", False),
            is_open=getattr(tournament_create, "is_open", True),
            is_registration_open=getattr(tournament_create, "is_registration_open", True),
        )
        session.add(tournament)
        if commit:
            await session.commit()
            await session.refresh(tournament)
        created_tournaments.append(tournament)
        return tournament

    try:
        yield _factory
    finally:
        for tournament in created_tournaments:
            await session.delete(tournament)
        await session.commit()

@pytest_asyncio.fixture(scope="function")
async def tournament1(db_user1_with_pass: tuple[User, str]) -> AsyncGenerator[TournamentCreate, None]:
    yield TournamentCreate(
        name="Tournament 1",
        date="2025-07-20",
        location="Main Hall",
        owner_id=db_user1_with_pass[0].id,
    )

@pytest_asyncio.fixture(scope="function")
async def tournament2(db_user2_with_pass: tuple[User, str]) -> AsyncGenerator[TournamentCreate, None]:
    yield TournamentCreate(
        name="Tournament 2",
        date="2025-08-01",
        location="Side Hall",
        owner_id=db_user2_with_pass[0].id,
    )


class GameFactoryType(Protocol):
    def __call__(
        self,
        game_create: GameCreate,
        *,
        commit: bool = True,
    ) -> Awaitable[Game]: ...


@pytest_asyncio.fixture(scope="function")
async def game_factory(
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
) -> AsyncGenerator["GameFactoryType", None]:
    created_games: list[Game] = []

    async def _factory(
        game_create: GameCreate,
        *,
        commit: bool = True,
    ) -> Game:
        # Default owner is db_user1 if not provided
        owner_id = getattr(game_create, "owner_id", None) or db_user1_with_pass[0].id
        game = Game(
            uuid=uuid4(),
            player_a_id=getattr(game_create, "player_a_id", None),
            player_b_id=getattr(game_create, "player_b_id", None),
            tournament_id=getattr(game_create, "tournament_id", None),
            owner_id=owner_id,
            score_a=getattr(game_create, "score_a", 0),
            score_b=getattr(game_create, "score_b", 0),
            is_finished=getattr(game_create, "is_finished", False),
        )
        session.add(game)
        if commit:
            await session.commit()
            await session.refresh(game)
        created_games.append(game)
        return game

    try:
        yield _factory
    finally:
        for game in created_games:
            db_game = await session.get(Game, game.uuid)
            if db_game:
                await session.delete(db_game)
        await session.commit()
