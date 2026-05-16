from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import model, schema


async def get_stage(session: AsyncSession, uuid: UUID) -> model.Stage | None:
    return await session.scalar(
        select(model.Stage).filter(model.Stage.uuid == uuid)
    )


async def get_stages_by_tournament(
    session: AsyncSession, tournament_id: UUID
) -> list[model.Stage]:
    result = await session.scalars(
        select(model.Stage)
        .filter(
            model.Stage.tournament_id == tournament_id,
            model.Stage.is_deleted == False,  # noqa: E712
        )
        .order_by(model.Stage.ordering)
    )
    return list(result)


async def create_stage(
    session: AsyncSession, stage: schema.StageCreate
) -> model.Stage:
    data = stage.model_dump()
    # Auto-increment ordering so new stages come after existing ones
    existing = await get_stages_by_tournament(session, stage.tournament_id)
    data["ordering"] = max((s.ordering for s in existing), default=-1) + 1
    db_stage = model.Stage(**data)
    session.add(db_stage)
    await session.commit()
    await session.refresh(db_stage)
    return db_stage


async def update_stage(
    session: AsyncSession, uuid: UUID, stage: schema.StageUpdate
) -> model.Stage | None:
    values = {k: v for k, v in stage.model_dump(exclude_none=True).items() if k != "uuid"}
    if not values:
        return await get_stage(session, uuid)
    await session.execute(
        update(model.Stage).filter(model.Stage.uuid == uuid).values(**values)
    )
    await session.commit()
    return await get_stage(session, uuid)


async def delete_stage(session: AsyncSession, uuid: UUID) -> model.Stage | None:
    await session.execute(
        update(model.Stage).filter(model.Stage.uuid == uuid).values(is_deleted=True)
    )
    await session.commit()
    return await get_stage(session, uuid)
