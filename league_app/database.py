from typing import AsyncIterator, Optional, Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from logging import Logger

logger = Logger(__file__)

DATABASE_URL = "sqlite:///./sql_app.db"

ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./sql_app.db"


class Base(DeclarativeBase):
    pass

def get_async_engine(url: Optional[str] = None, use_static_pool: Optional[bool] = None) -> AsyncEngine:
    if use_static_pool:
        params: dict[str, Any] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool
        }
    else:
        params: dict[str, Any] = {}
    return create_async_engine(url or ASYNC_DATABASE_URL, **params)

def get_async_session_maker(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or get_async_engine(), expire_on_commit=False)

async def get_session(
    session_maker: Optional[async_sessionmaker[AsyncSession]] = None
) -> AsyncIterator[AsyncSession]:
    session_maker = session_maker or get_async_session_maker()
    async with session_maker() as session:
        yield session

async def get_session_for_api() -> AsyncIterator[AsyncSession]:
    # Always use the default sessionmaker
    async for session in get_session():
        yield session

#async_engine: AsyncEngine = create_async_engine(ASYNC_DATABASE_URL)
#async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)
"""
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.exception(e)
            raise
"""

#async def create_db_and_tables():
#    async with async_engine.begin() as conn:
#        await conn.run_sync(Base.metadata.create_all)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
