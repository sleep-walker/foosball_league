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


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncEngine:
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def get_async_session(engine: AsyncEngine) -> AsyncSession:
    AsyncSessionLocal = sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )
    return AsyncSessionLocal()


@pytest_asyncio.fixture(scope="session")
async def session(engine: AsyncEngine) -> AsyncSession:
    s = get_async_session(engine)
    yield s


@pytest_asyncio.fixture(scope="session")
async def client(session: AsyncSession, engine: AsyncEngine) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: get_async_session(engine)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(scope="function")
def player1():
    yield {
        "first_name": "foo",
        "last_name": "bar",
        "nickname": "foobar",
        "email": "foo@bar.com",
    }


@pytest_asyncio.fixture(scope="function")
async def db_player1(session: sessionmaker, player1: dict) -> models.Player:
    async with session as sess:
        db_player = models.Player(**player1)
        sess.add(db_player)
        await sess.flush()
        await sess.commit()
        await sess.refresh(db_player)
        yield db_player
        await sess.delete(db_player)
        await sess.commit()
