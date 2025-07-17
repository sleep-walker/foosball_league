from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from . import model, schema
from sqlalchemy import select, update


async def get_player(session: AsyncSession, uuid: UUID) -> model.Player | None:
    stmt = select(model.Player).filter(model.Player.uuid == uuid)
    assert isinstance(session, AsyncSession)
    return await session.scalar(stmt)


async def get_players(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    filter_deleted: bool = True,
) -> list[model.Player]:
    stmt = select(model.Player).offset(skip)

    if limit != 0:
        stmt = stmt.limit(limit)

    result = await session.scalars(stmt.order_by(model.Player.uuid))
    return list(result)


async def create_player(session: AsyncSession, player: schema.PlayerCreate):
    db_player = model.Player(**player.model_dump())
    session.add(db_player)
    await session.commit()
    await session.refresh(db_player)
    return db_player


async def get_player_by_email(session: AsyncSession, email: str):
    stmt = select(model.Player).filter(model.Player.email == email)
    return await session.scalar(stmt)


async def get_player_by_nickname(session: AsyncSession, nickname: str):
    stmt = select(model.Player).filter(model.Player.nickname == nickname)
    return await session.scalar(stmt)


async def get_player_by_uuid(session: AsyncSession, uuid: UUID):
    stmt = select(model.Player).filter(model.Player.uuid == uuid)
    return await session.scalar(stmt)


async def get_players_by_user_id(
    session: AsyncSession, user_id: UUID
) -> list[model.Player]:
    stmt = (
        select(model.Player)
        .filter(model.Player.user_id == user_id)
        .order_by(model.Player.uuid)
    )
    result = await session.scalars(stmt)
    return list(result)


async def update_player(session: AsyncSession, player: schema.PlayerUpdate):
    stmt = (
        update(model.Player)
        .filter(model.Player.uuid == player.uuid)
        .values(**player.model_dump())
    )
    await session.execute(stmt)
    stmt = select(model.Player).filter(model.Player.uuid == player.uuid)
    return await session.scalar(stmt)


async def delete_player(session: AsyncSession, uuid: UUID):
    stmt = update(model.Player).filter(model.Player.uuid == uuid).values(deleted=True)
    await session.execute(stmt)
    stmt = select(model.Player).filter(model.Player.uuid == uuid)
    db_player = await session.execute(stmt)

    return db_player


async def search_players(
    session: AsyncSession,
    nickname: str | None = None,
    email: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[model.Player]:
    stmt = select(model.Player)

    if nickname is not None:
        # FIXME: consider security implications of using ilike
        stmt = stmt.where(model.Player.nickname.ilike(f"%{nickname}%"))
    if email is not None:
        stmt = stmt.where(model.Player.email.ilike(f"%{email}%"))

    stmt = stmt.offset(skip).limit(limit)
    result = await session.scalars(stmt)
    return list(result)
