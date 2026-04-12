"""FastAPI dependency injection for domain services and repositories.

Usage in routers::

    from league_app.domain.dependencies import get_tournament_service

    @router.post("/...")
    async def my_endpoint(
        svc: TournamentService = Depends(get_tournament_service),
    ):
        ...
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.infra.sa_repo_all import (
    FullSAMatchRepository,
    FullSATournamentRepository,
    SALeagueRepository,
    SAPlayerRepository,
    SAStageRepository,
    SATeamRepository,
)

from .tournament_service import TournamentService
from .league_service import LeagueService


# --- Repository factories ---

def get_player_repo(session: AsyncSession = Depends(get_session_for_api)) -> SAPlayerRepository:
    return SAPlayerRepository(session)

def get_team_repo(session: AsyncSession = Depends(get_session_for_api)) -> SATeamRepository:
    return SATeamRepository(session)

def get_match_repo(session: AsyncSession = Depends(get_session_for_api)) -> FullSAMatchRepository:
    return FullSAMatchRepository(session)

def get_stage_repo(session: AsyncSession = Depends(get_session_for_api)) -> SAStageRepository:
    return SAStageRepository(session)

def get_tournament_repo(session: AsyncSession = Depends(get_session_for_api)) -> FullSATournamentRepository:
    return FullSATournamentRepository(session)

def get_league_repo(session: AsyncSession = Depends(get_session_for_api)) -> SALeagueRepository:
    return SALeagueRepository(session)


# --- Service factories ---

def get_tournament_service(
    tournament_repo: FullSATournamentRepository = Depends(get_tournament_repo),
    match_repo: FullSAMatchRepository = Depends(get_match_repo),
    stage_repo: SAStageRepository = Depends(get_stage_repo),
    player_repo: SAPlayerRepository = Depends(get_player_repo),
    team_repo: SATeamRepository = Depends(get_team_repo),
) -> TournamentService:
    return TournamentService(
        tournaments=tournament_repo,
        matches=match_repo,
        stages=stage_repo,
        players=player_repo,
        teams=team_repo,
    )

def get_league_service(
    league_repo: SALeagueRepository = Depends(get_league_repo),
    tournament_repo: FullSATournamentRepository = Depends(get_tournament_repo),
    match_repo: FullSAMatchRepository = Depends(get_match_repo),
) -> LeagueService:
    return LeagueService(
        leagues=league_repo,
        tournaments=tournament_repo,
        matches=match_repo,
    )
