from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
import pytest_asyncio

from .database import Base
from .main import app, get_db, get_session
from . import models

from contextlib import asynccontextmanager
from async_generator import async_generator, yield_

# copilot, generate async engine:
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from httpx import AsyncClient, ASGITransport

SQLALCHEMY_DATABASE_URL = "sqlite://"
ASYNC_DATABASE_URL = "sqlite+aiosqlite://"
# async_engine = create_async_engine(ASYNC_DATABASE_URL)
# async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)


# async def create_db_and_tables():
#     async with async_engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)


# fixture which returns async engine:
# @pytest.fixture(scope="session")
# async def async_engine():
#     yield create_async_engine(SQLALCHEMY_DATABASE_URL)


# fixture which prepares the database
# @pytest.fixture(scope="session")
# async def database_engine(async_engine):
#     async with async_engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)
#     yield async_engine


# fixture which returns async session
# @pytest.fixture(scope="function")
# async def async_session(database_engine):
#     async with database_engine.begin() as conn:
#         async with async_sessionmaker(database_engine) as session:
#             yield session


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="session")
async def async_engine() -> AsyncEngine:
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def get_async_session(async_engine: AsyncEngine):
    AsyncSessionLocal = sessionmaker(
        bind=async_engine, expire_on_commit=False, class_=AsyncSession
    )
    return AsyncSessionLocal()


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="session")
async def async_session(async_engine: AsyncEngine) -> AsyncSession:
    s = get_async_session(async_engine)
    assert isinstance(s, AsyncSession)
    yield s
    # AsyncSessionLocal = sessionmaker(
    #     bind=async_engine, expire_on_commit=False, class_=AsyncSession
    # )
    # yield AsyncSessionLocal()


# @pytest.fixture(scope="session")
@pytest_asyncio.fixture(scope="session")
async def async_client(
    async_session: AsyncSession, async_engine: AsyncEngine
) -> AsyncClient:
    # async def test_get_db():
    #     try:
    #         yield async_session
    #     except SQLAlchemyError:
    #         pass

    # @asynccontextmanager
    # async def override_get_db():
    #     # yield session
    #     async with async_session as session:
    #         assert isinstance(session, AsyncSession)
    #         yield session

    # app.dependency_overrides[get_db] = get_session
    # app.dependency_overrides[get_session] = override_get_db
    app.dependency_overrides[get_session] = lambda: get_async_session(async_engine)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def client():
    yield TestClient(app)


@pytest.fixture(scope="function")
def player1():
    yield {
        "first_name": "foo",
        "last_name": "bar",
        "nickname": "foobar",
        "email": "foo@bar.com",
    }


@pytest.fixture(scope="session")
def db():
    yield TestingSessionLocal()


@pytest.fixture(scope="function")
def db_player1(db, player1):
    db_player = models.Player(**player1)

    db.add(db_player)
    db.commit()
    db.refresh(db_player)

    yield db_player

    db.delete(db_player)
    db.commit()


@pytest_asyncio.fixture(scope="function")
async def async_db_player1(async_session: sessionmaker, player1: dict) -> models.Player:
    async with async_session as session:
        db_player = models.Player(**player1)
        session.add(db_player)
        await session.flush()
        await session.commit()
        await session.refresh(db_player)
        yield db_player
        await session.delete(db_player)
        await session.commit()
