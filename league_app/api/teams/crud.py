from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import model, schema


async def get_team(session: AsyncSession, uuid: UUID) -> model.Team | None:
    return await session.scalar(
        select(model.Team).filter(model.Team.uuid == uuid)
    )


async def get_teams_by_tournament(
    session: AsyncSession, tournament_id: UUID
) -> list[model.Team]:
    result = await session.scalars(
        select(model.Team).filter(model.Team.tournament_id == tournament_id)
    )
    return list(result)


async def create_team(
    session: AsyncSession, team: schema.TeamCreate
) -> model.Team:
    db_team = model.Team(**team.model_dump())
    session.add(db_team)
    await session.commit()
    await session.refresh(db_team)
    return db_team
