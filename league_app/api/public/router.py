"""Public (unauthenticated) read-only endpoints.

These are designed for TV screens, projectors, and spectator devices.
No sensitive data is exposed — only tournament status, standings, bracket,
and current round info.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.stages import crud as stages_crud
from league_app.api.tournaments import crud as tournaments_crud
from league_app.domain.tournament_service import TournamentService

router = APIRouter(tags=["public"])


def _get_svc(session: AsyncSession = Depends(get_session_for_api)) -> TournamentService:
    from league_app.infra.sa_repo_all import (
        FullSAMatchRepository, FullSATournamentRepository,
        SAPlayerRepository, SAStageRepository, SATeamRepository,
    )
    return TournamentService(
        tournaments=FullSATournamentRepository(session),
        matches=FullSAMatchRepository(session),
        stages=SAStageRepository(session),
        players=SAPlayerRepository(session),
        teams=SATeamRepository(session),
    )


# --- Response models (minimal, no sensitive data) ---

class PublicPlayerInfo(BaseModel):
    uuid: UUID
    nickname: str


class PublicRegistration(BaseModel):
    player: PublicPlayerInfo
    seed: int | None = None


class PublicTournamentInfo(BaseModel):
    uuid: UUID
    name: str | None
    date: str
    location: str | None
    format: str
    status: str
    player_count: int


class PublicStandingRow(BaseModel):
    participant_id: UUID
    nickname: str | None = None
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    matches_played: int


class PublicMatchInfo(BaseModel):
    uuid: UUID
    round_number: int
    bracket_position: int | None = None
    table_number: int | None = None
    status: str
    player_a_name: str | None = None
    player_b_name: str | None = None
    best_of: int
    games: list[dict] = []


# --- Endpoints ---

@router.get("/tournaments/{tournament_id}", response_model=PublicTournamentInfo)
async def get_tournament_info(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
):
    t = await tournaments_crud.get_tournament(session, tournament_id)
    if t is None or t.is_deleted:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return PublicTournamentInfo(
        uuid=t.uuid, name=t.name, date=t.date, location=t.location,
        format=t.format, status=t.status,
        player_count=len(t.registrations),
    )


@router.get(
    "/tournaments/{tournament_id}/stages/{stage_id}/standings",
    response_model=list[PublicStandingRow],
)
async def get_public_standings(
    tournament_id: UUID,
    stage_id: UUID,
    svc: TournamentService = Depends(_get_svc),
    session: AsyncSession = Depends(get_session_for_api),
):
    """Public standings for a group stage — visible on TV/projector."""
    from league_app.domain.tournament_service import TournamentError
    try:
        rows = await svc.get_stage_standings(tournament_id, stage_id)
    except TournamentError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Resolve nicknames
    from league_app.api.players import model as player_orm
    nickname_map: dict[UUID, str] = {}
    for r in rows:
        if r.participant_id not in nickname_map:
            p = await session.get(player_orm.Player, r.participant_id)
            nickname_map[r.participant_id] = p.nickname if p else "?"

    return [
        PublicStandingRow(
            participant_id=r.participant_id,
            nickname=nickname_map.get(r.participant_id),
            wins=r.wins, draws=r.draws, losses=r.losses,
            goals_for=r.goals_for, goals_against=r.goals_against,
            goal_difference=r.goal_difference, points=r.points,
            matches_played=r.matches_played,
        )
        for r in rows
    ]


@router.get(
    "/tournaments/{tournament_id}/stages/{stage_id}/matches",
    response_model=list[PublicMatchInfo],
)
async def get_public_matches(
    tournament_id: UUID,
    stage_id: UUID,
    round_number: int | None = None,
    session: AsyncSession = Depends(get_session_for_api),
):
    """Public match list for a stage — shows bracket or round matches."""
    from league_app.api.matches import crud as matches_crud
    from league_app.api.players import model as player_orm

    matches = await matches_crud.get_matches_by_stage(session, stage_id)
    if round_number is not None:
        matches = [m for m in matches if m.round_number == round_number]

    result = []
    for m in matches:
        if m.is_deleted:
            continue
        pa = await session.get(player_orm.Player, m.player_a_id) if m.player_a_id else None
        pb = await session.get(player_orm.Player, m.player_b_id) if m.player_b_id else None
        result.append(PublicMatchInfo(
            uuid=m.uuid, round_number=m.round_number,
            bracket_position=m.bracket_position, table_number=m.table_number,
            status=m.status, best_of=m.best_of,
            player_a_name=pa.nickname if pa else None,
            player_b_name=pb.nickname if pb else None,
            games=[{"score_a": g.score_a, "score_b": g.score_b, "number": g.game_number}
                   for g in (m.games or [])],
        ))
    return result



# Include sub-routers
from .qr import router as qr_router
from .export import router as export_router
router.include_router(qr_router)
router.include_router(export_router)