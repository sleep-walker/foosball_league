from typing import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from logging import Logger

logger = Logger(__file__)

DATABASE_URL = "sqlite:///./sql_app.db"

ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./sql_app.db"


class Base(DeclarativeBase):
    pass


async_engine = create_async_engine(ASYNC_DATABASE_URL)
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)


async def create_db_and_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
#     async with async_session_maker() as session:
#         yield session


async def get_session() -> AsyncIterator[async_sessionmaker]:
    try:
        yield async_session_maker()
    except SQLAlchemyError as e:
        logger.exception(e)


async def get_user_db(session: AsyncSession = Depends(get_session)):
    yield SQLAlchemyUserDatabase(session, User)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_access_token_db(
    session: AsyncSession = Depends(get_session),
):
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()
