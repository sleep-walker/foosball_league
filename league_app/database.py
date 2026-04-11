from typing import AsyncIterator, Optional, Any

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from league_app.config import get_settings
from logging import Logger

logger = Logger(__file__)


class Base(DeclarativeBase):
    pass


def get_async_engine(
    url: Optional[str] = None, use_static_pool: Optional[bool] = None
) -> AsyncEngine:
    if use_static_pool:
        params: dict[str, Any] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    else:
        params: dict[str, Any] = {}
    return create_async_engine(url or get_settings().ASYNC_DATABASE_URL, **params)


def get_async_session_maker(
    engine: Optional[AsyncEngine] = None,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or get_async_engine(), expire_on_commit=False)


async def get_session(
    session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
) -> AsyncIterator[AsyncSession]:
    session_maker = session_maker or get_async_session_maker()
    async with session_maker() as session:
        yield session


async def get_session_for_api() -> AsyncIterator[AsyncSession]:
    # Always use the default sessionmaker
    async for session in get_session():
        yield session
