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
from league_app.realtime.hub import event_hub
from logging import Logger

logger = Logger(__file__)


class Base(DeclarativeBase):
    pass


# Process-wide singletons for the default (config-driven) engine and
# sessionmaker. Without caching, every FastAPI request would create a
# fresh engine + pool, and the underlying aiosqlite connection threads
# would each retain an open file descriptor to the SQLite database —
# exhausting the per-process FD limit within a few thousand requests.
_default_engine: Optional[AsyncEngine] = None
_default_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine(
    url: Optional[str] = None, use_static_pool: Optional[bool] = None
) -> AsyncEngine:
    global _default_engine
    if url is None and not use_static_pool:
        if _default_engine is None:
            _default_engine = create_async_engine(get_settings().ASYNC_DATABASE_URL)
        return _default_engine
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
    global _default_session_maker
    if engine is None:
        if _default_session_maker is None:
            _default_session_maker = async_sessionmaker(
                get_async_engine(), expire_on_commit=False
            )
        return _default_session_maker
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
) -> AsyncIterator[AsyncSession]:
    session_maker = session_maker or get_async_session_maker()
    async with session_maker() as session:
        yield session


async def get_session_for_api() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: session bound to a single HTTP request.

    Commits on clean exit, rolls back on any exception.  Individual CRUD
    helpers should call ``await session.flush()`` (to obtain generated
    primary keys / defaults) but NOT ``await session.commit()`` — the
    request boundary is the only correct commit point.

    This is migrated incrementally per domain — older CRUD helpers may
    still self-commit.  Their commits become no-ops here (nothing dirty)
    so the migration is forward-compatible.

    Real-time events published during the request are buffered by the
    event hub and only delivered once the transaction has committed —
    otherwise a rolled-back request would announce state that does not
    exist in the database.
    """
    session_maker = get_async_session_maker()
    pending_events = event_hub.begin_deferred()
    committed = False
    async with session_maker() as session:
        try:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()
                committed = True
        finally:
            if committed:
                event_hub.flush_deferred(pending_events)
            else:
                event_hub.discard_deferred(pending_events)
