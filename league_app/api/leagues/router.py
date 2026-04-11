from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.tournaments import crud as tournaments_crud, schema as tournaments_schema
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user, current_superuser
from . import crud, schema

router = APIRouter(tags=["leagues"])


@router.post("/", response_model=schema.LeagueOutput)
async def create_league(
    league: schema.LeagueCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    # Check if league name already exists
    existing_league = await crud.get_league_by_name(session, name=league.name)
    if existing_league:
        raise HTTPException(status_code=400, detail="League name already exists")
    # Only owner can create league, set owner_id to user.id
    league.owner_id = user.id
    return await crud.create_league(session=session, league=league)


@router.get("/search", response_model=list[schema.LeagueOutput])
async def search_leagues(
    name: str,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    leagues = await crud.search_leagues_by_name(session, name=name)
    return leagues


@router.get("/", response_model=list[schema.LeagueOutput])
async def read_leagues(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    leagues = await crud.get_leagues(session, skip=skip, limit=limit)
    return leagues


@router.get("/{uuid}", response_model=schema.LeagueOutput)
async def read_league(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_league = await crud.get_league(session, uuid=uuid)
    if db_league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return db_league


@router.put("/{uuid}", response_model=schema.LeagueOutput)
async def update_league(
    uuid: UUID,
    league: schema.LeagueUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_league = await crud.get_league(session, uuid=uuid)
    if db_league is None:
        raise HTTPException(status_code=404, detail="League not found")
    allowed = user.is_superuser or user.id == db_league.owner_id
    if not allowed:
        raise HTTPException(
            status_code=403, detail="Only owner or superuser can update league"
        )
    league.uuid = uuid
    return await crud.update_league(session, league=league)


@router.delete("/{uuid}", response_model=schema.LeagueOutput)
async def delete_league(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
):
    db_league = await crud.get_league(session, uuid=uuid)
    if db_league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return await crud.delete_league(session, uuid=uuid)



# --- League tournaments ---


@router.get(
    "/{uuid}/tournaments/",
    response_model=list[tournaments_schema.TournamentOutput],
    tags=["leagues"],
)
async def list_league_tournaments(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    league = await crud.get_league(session, uuid=uuid)
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return await tournaments_crud.get_tournaments_by_league(session, uuid)