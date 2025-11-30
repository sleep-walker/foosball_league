from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from . import model, schema
from sqlalchemy import select, update


async def get_game(session: AsyncSession, uuid: UUID) -> model.Game | None:
    stmt = select(model.Game).filter(model.Game.uuid == uuid)
    assert isinstance(session, AsyncSession)
    return await session.scalar(stmt)


async def get_games(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    filter_deleted: bool = True,
) -> list[model.Game]:
    stmt = select(model.Game).offset(skip)

    if limit != 0:
        stmt = stmt.limit(limit)

    result = await session.scalars(stmt.order_by(model.Game.uuid))
    return list(result)


async def create_game(session: AsyncSession, game: schema.GameCreate):
    db_game = model.Game(**game.model_dump())
    session.add(db_game)
    await session.commit()
    await session.refresh(db_game)
    return db_game


async def update_game(session: AsyncSession, game: schema.GameUpdate):
    # avoid overwriting fields with None
    values = game.model_dump(exclude_none=True)
    if "uuid" in values:
        values.pop("uuid")
    stmt = (
        update(model.Game)
        .filter(model.Game.uuid == game.uuid)
        .values(**values)
    )
    await session.execute(stmt)
    stmt = select(model.Game).filter(model.Game.uuid == game.uuid)
    return await session.scalar(stmt)


async def delete_game(session: AsyncSession, uuid: UUID):
    stmt = update(model.Game).filter(model.Game.uuid == uuid).values(is_deleted=True)
    await session.execute(stmt)
    stmt = select(model.Game).filter(model.Game.uuid == uuid)
    return await session.scalar(stmt)


async def search_games(
    session: AsyncSession,
    tournament_id: UUID | None = None,
    player_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[model.Game]:
    stmt = select(model.Game)

    if tournament_id is not None:
        stmt = stmt.where(model.Game.tournament_id == tournament_id)
    if player_id is not None:
        stmt = stmt.where(
            (model.Game.player_a_id == player_id) | (model.Game.player_b_id == player_id)
        )

    stmt = stmt.offset(skip).limit(limit)
    result = await session.scalars(stmt)
    return list(result)
