from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from . import model, schema
from sqlalchemy import select, update
from league_app.api.players.model import Player


async def get_tournament(session: AsyncSession, uuid: UUID) -> model.Tournament | None:
    from sqlalchemy.orm import subqueryload
    stmt = (
        select(model.Tournament)
        .filter(model.Tournament.uuid == uuid)
        .execution_options(populate_existing=True)
        .options(
            subqueryload(model.Tournament.registrations)
            .subqueryload(model.TournamentRegistration.player),
            subqueryload(model.Tournament.applicants),
            subqueryload(model.Tournament.stages),
            subqueryload(model.Tournament.co_organizers),
        )
    )
    return await session.scalar(stmt)


async def get_tournaments(
    session: AsyncSession, skip: int = 0, limit: int = 100
) -> list[model.Tournament]:
    stmt = select(model.Tournament).filter(
        model.Tournament.is_deleted == False  # noqa: E712
    ).offset(skip)
    if limit != 0:
        stmt = stmt.limit(limit)
    result = await session.scalars(stmt.order_by(model.Tournament.date))
    return list(result)


async def create_tournament(
    session: AsyncSession, tournament: schema.TournamentCreate
) -> model.Tournament:
    db_tournament = model.Tournament(**tournament.model_dump())
    session.add(db_tournament)
    await session.flush()
    await session.refresh(db_tournament)
    return db_tournament


async def update_tournament(
    session: AsyncSession, tournament: schema.TournamentUpdate
) -> model.Tournament | None:
    update_fields = {k: v for k, v in tournament.model_dump().items() if v is not None}
    stmt = (
        update(model.Tournament)
        .filter(model.Tournament.uuid == tournament.uuid)
        .values(**update_fields)
    )
    await session.execute(stmt)
    stmt = select(model.Tournament).filter(model.Tournament.uuid == tournament.uuid)
    return await session.scalar(stmt)


async def delete_tournament(
    session: AsyncSession, uuid: UUID
) -> model.Tournament | None:
    stmt = (
        update(model.Tournament)
        .filter(model.Tournament.uuid == uuid)
        .values(is_deleted=True)
    )
    await session.execute(stmt)
    await session.flush()
    stmt = select(model.Tournament).filter(model.Tournament.uuid == uuid)
    db_tournament = await session.scalar(stmt)
    return db_tournament


async def is_applicant(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID
) -> bool:
    stmt = (
        select(model.tournament_applicants)
        .where(model.tournament_applicants.c.tournament_id == tournament_uuid)
        .where(model.tournament_applicants.c.player_id == player_uuid)
    )
    result = await session.execute(stmt)
    return result.first() is not None


async def is_player(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID
) -> bool:
    stmt = (
        select(model.TournamentRegistration)
        .where(model.TournamentRegistration.tournament_id == tournament_uuid)
        .where(model.TournamentRegistration.player_id == player_uuid)
    )
    return await session.scalar(stmt) is not None


async def get_applications(
    session: AsyncSession, tournament_uuid: UUID
) -> list[Player]:
    stmt = (
        select(Player)
        .join(
            model.tournament_applicants,
            Player.uuid == model.tournament_applicants.c.player_id,
        )
        .where(model.tournament_applicants.c.tournament_id == tournament_uuid)
    )
    result = await session.scalars(stmt)
    return list(result)


async def create_application(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID
) -> model.Tournament | None:
    if await is_applicant(session, tournament_uuid, player_uuid):
        return None  # Already an applicant
    tournament = await get_tournament(session, tournament_uuid)
    if tournament is None:
        return None
    player = await session.get(Player, player_uuid)
    if player is None:
        return None
    tournament.applicants.append(player)
    await session.flush()
    await session.refresh(tournament)
    return tournament


async def delete_application(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID
) -> model.Tournament | None:
    if not await is_applicant(session, tournament_uuid, player_uuid):
        return None  # Not an applicant
    tournament = await get_tournament(session, tournament_uuid)
    if tournament is None:
        return None
    player = await session.get(Player, player_uuid)
    if player is None:
        return None
    tournament.applicants.remove(player)
    await session.flush()
    await session.refresh(tournament)
    return tournament


async def register_player_for_tournament(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID
) -> model.TournamentRegistration | None:
    if await is_player(session, tournament_uuid, player_uuid):
        return None  # Already registered
    player = await session.get(Player, player_uuid)
    if player is None:
        return None
    reg = model.TournamentRegistration(
        tournament_id=tournament_uuid, player_id=player_uuid
    )
    session.add(reg)
    await session.flush()
    await session.refresh(reg)
    return reg


async def remove_player_from_tournament(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID
) -> bool:
    reg = await session.scalar(
        select(model.TournamentRegistration)
        .where(model.TournamentRegistration.tournament_id == tournament_uuid)
        .where(model.TournamentRegistration.player_id == player_uuid)
    )
    if reg is None:
        return False
    await session.delete(reg)
    await session.flush()
    return True


async def mark_player_paid(
    session: AsyncSession, tournament_uuid: UUID, player_uuid: UUID, paid: bool = True
) -> model.TournamentRegistration | None:
    reg = await session.scalar(
        select(model.TournamentRegistration)
        .where(model.TournamentRegistration.tournament_id == tournament_uuid)
        .where(model.TournamentRegistration.player_id == player_uuid)
    )
    if reg is None:
        return None
    reg.paid = paid
    await session.flush()
    await session.refresh(reg)
    return reg


async def get_tournaments_by_league(
    session: AsyncSession, league_uuid: UUID
) -> list[model.Tournament]:
    result = await session.scalars(
        select(model.Tournament)
        .filter(
            model.Tournament.league_id == league_uuid,
            model.Tournament.is_deleted == False,  # noqa: E712
        )
    )
    return list(result)
