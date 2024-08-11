from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from . import models, schema
from sqlalchemy import select, update


async def get_player(session: AsyncSession, uuid: UUID) -> models.Player | None:
    stmt = select(models.Player).filter(models.Player.uuid == uuid)
    assert isinstance(session, AsyncSession)
    return await session.scalar(stmt)


async def get_players(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    filter_deleted: bool = True,
) -> list[models.Player]:
    stmt = select(models.Player).offset(skip)

    if limit != 0:
        stmt = stmt.limit(limit)

    # if filter_deleted:
    #     stmt = stmt.filter(models.Player.deleted is False)

    assert isinstance(session, AsyncSession)
    result = await session.scalar(stmt.order_by(models.Player.uuid))
    if result is None:
        return []
    return [result]


async def create_player(session: AsyncSession, player: schema.PlayerCreate):
    db_player = models.Player(**player.model_dump())
    session.add(db_player)
    await session.commit()
    await session.refresh(db_player)
    return db_player


async def get_player_by_email(session: AsyncSession, email: str):
    stmt = select(models.Player).filter(models.Player.email == email)
    return await session.scalar(stmt)


async def get_player_by_nickname(session: AsyncSession, nickname: str):
    stmt = select(models.Player).filter(models.Player.nickname == nickname)
    return await session.scalar(stmt)


async def update_player(session: AsyncSession, player: schema.PlayerUpdate):
    stmt = (
        update(models.Player)
        .filter(models.Player.uuid == player.uuid)
        .values(**player.model_dump())
    )
    await session.execute(stmt)
    stmt = select(models.Player).filter(models.Player.uuid == player.uuid)
    return await session.scalar(stmt)


async def delete_player(session: AsyncSession, uuid: UUID):
    stmt = update(models.Player).filter(models.Player.uuid == uuid).values(deleted=True)
    await session.execute(stmt)
    stmt = select(models.Player).filter(models.Player.uuid == uuid)
    db_player = await session.execute(stmt)

    return db_player
