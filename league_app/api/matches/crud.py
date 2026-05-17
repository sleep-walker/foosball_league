from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import model, schema


# --- Match CRUD ---


async def get_match(session: AsyncSession, uuid: UUID) -> model.Match | None:
    return await session.scalar(
        select(model.Match).filter(model.Match.uuid == uuid)
    )


async def get_matches_by_tournament(
    session: AsyncSession, tournament_id: UUID
) -> list[model.Match]:
    from sqlalchemy.orm import subqueryload
    result = await session.scalars(
        select(model.Match)
        .filter(
            model.Match.tournament_id == tournament_id,
            model.Match.is_deleted == False,  # noqa: E712
        )
        .options(subqueryload(model.Match.games))
        .order_by(model.Match.round_number)
    )
    return list(result)


async def get_matches_by_stage(
    session: AsyncSession, stage_id: UUID
) -> list[model.Match]:
    result = await session.scalars(
        select(model.Match).filter(
            model.Match.stage_id == stage_id,
            model.Match.is_deleted == False,  # noqa: E712
        )
    )
    return list(result)


async def create_match(
    session: AsyncSession, match: schema.MatchCreate, owner_id: UUID | None = None
) -> model.Match:
    db_match = model.Match(**match.model_dump(), owner_id=owner_id)
    session.add(db_match)
    await session.flush()
    await session.refresh(db_match)
    return db_match


async def update_match(
    session: AsyncSession, uuid: UUID, data: schema.MatchUpdate
) -> model.Match | None:
    values = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    if values:
        await session.execute(
            update(model.Match).filter(model.Match.uuid == uuid).values(**values)
        )
        await session.flush()
    return await get_match(session, uuid)


async def delete_match(session: AsyncSession, uuid: UUID) -> model.Match | None:
    await session.execute(
        update(model.Match).filter(model.Match.uuid == uuid).values(is_deleted=True)
    )
    await session.flush()
    return await get_match(session, uuid)


# --- Game CRUD (individual games within a match) ---


async def get_game(session: AsyncSession, uuid: UUID) -> model.Game | None:
    return await session.scalar(
        select(model.Game).filter(model.Game.uuid == uuid)
    )


async def get_games_by_match(
    session: AsyncSession, match_id: UUID
) -> list[model.Game]:
    result = await session.scalars(
        select(model.Game)
        .filter(model.Game.match_id == match_id)
        .order_by(model.Game.game_number)
    )
    return list(result)


async def create_game(
    session: AsyncSession, match_id: UUID, game: schema.GameCreate
) -> model.Game:
    db_game = model.Game(match_id=match_id, **game.model_dump())
    session.add(db_game)
    await session.flush()
    await session.refresh(db_game)
    return db_game


async def update_game(
    session: AsyncSession, uuid: UUID, data: schema.GameUpdate
) -> model.Game | None:
    values = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    if values:
        await session.execute(
            update(model.Game).filter(model.Game.uuid == uuid).values(**values)
        )
        await session.flush()
    return await get_game(session, uuid)
