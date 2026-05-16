from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from . import model, schema
from sqlalchemy import select, update


async def get_league(session: AsyncSession, uuid: UUID) -> model.League | None:
    stmt = select(model.League).filter(model.League.uuid == uuid)
    return await session.scalar(stmt)


async def get_league_by_name(session: AsyncSession, name: str) -> model.League | None:
    stmt = select(model.League).filter(model.League.name == name)
    return await session.scalar(stmt)


async def get_leagues(
    session: AsyncSession, skip: int = 0, limit: int = 100
) -> list[model.League]:
    stmt = select(model.League).offset(skip)
    if limit != 0:
        stmt = stmt.limit(limit)
    result = await session.scalars(stmt.order_by(model.League.uuid))
    return list(result)


async def create_league(session: AsyncSession, league: schema.LeagueCreate):
    db_league = model.League(**league.model_dump())
    session.add(db_league)
    await session.commit()
    await session.refresh(db_league)
    return db_league


async def update_league(session: AsyncSession, league: schema.LeagueUpdate):
    stmt = (
        update(model.League)
        .filter(model.League.uuid == league.uuid)
        .values(**{k: v for k, v in league.model_dump().items() if v is not None})
    )
    await session.execute(stmt)
    stmt = select(model.League).filter(model.League.uuid == league.uuid)
    return await session.scalar(stmt)


async def delete_league(session: AsyncSession, uuid: UUID):
    stmt = (
        update(model.League).filter(model.League.uuid == uuid).values(is_deleted=True)
    )
    await session.execute(stmt)
    stmt = select(model.League).filter(model.League.uuid == uuid)
    db_league = await session.scalar(stmt)
    return db_league


async def search_leagues_by_name(
    session: AsyncSession, name: str
) -> list[model.League]:
    stmt = select(model.League).filter(model.League.name.ilike(f"%{name}%"))
    result = await session.scalars(stmt)
    return list(result)



# --- Rule Presets ---


async def get_rule_presets(
    session: AsyncSession, league_id: UUID
) -> list[model.RulePreset]:
    stmt = select(model.RulePreset).filter(model.RulePreset.league_id == league_id)
    result = await session.scalars(stmt)
    return list(result)


async def get_rule_preset(
    session: AsyncSession, preset_id: UUID
) -> model.RulePreset | None:
    stmt = select(model.RulePreset).filter(model.RulePreset.uuid == preset_id)
    return await session.scalar(stmt)


async def create_rule_preset(
    session: AsyncSession, league_id: UUID, preset: schema.RulePresetCreate
) -> model.RulePreset:
    db_preset = model.RulePreset(
        league_id=league_id,
        name=preset.name,
        rules=preset.rules,
    )
    session.add(db_preset)
    await session.commit()
    await session.refresh(db_preset)
    return db_preset


async def update_rule_preset(
    session: AsyncSession, preset_id: UUID, data: schema.RulePresetUpdate
) -> model.RulePreset | None:
    preset = await get_rule_preset(session, preset_id)
    if preset is None:
        return None
    if data.name is not None:
        preset.name = data.name
    if data.rules is not None:
        preset.rules = data.rules
    await session.commit()
    await session.refresh(preset)
    return preset


async def delete_rule_preset(
    session: AsyncSession, preset_id: UUID
) -> bool:
    preset = await get_rule_preset(session, preset_id)
    if preset is None:
        return False
    await session.delete(preset)
    await session.commit()
    return True