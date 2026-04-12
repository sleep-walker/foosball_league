from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from . import crud, schema

router = APIRouter(tags=["matches"])


@router.get("/", response_model=list[schema.MatchOutput])
async def list_matches(
    tournament_id: UUID | None = None,
    stage_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    if stage_id is not None:
        return await crud.get_matches_by_stage(session, stage_id)
    if tournament_id is not None:
        return await crud.get_matches_by_tournament(session, tournament_id)
    raise HTTPException(
        status_code=400, detail="Provide tournament_id or stage_id filter"
    )


@router.get("/{match_id}", response_model=schema.MatchOutput)
async def get_match(
    match_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    match = await crud.get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


# --- Games within a match ---


@router.get("/{match_id}/games/", response_model=list[schema.GameOutput])
async def list_match_games(
    match_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    match = await crud.get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return await crud.get_games_by_match(session, match_id)


@router.post("/{match_id}/games/", response_model=schema.GameOutput)
async def create_game_in_match(
    match_id: UUID,
    game: schema.GameCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    match = await crud.get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return await crud.create_game(session, match_id, game)


@router.patch("/{match_id}/games/{game_id}", response_model=schema.GameOutput)
async def update_game_in_match(
    match_id: UUID,
    game_id: UUID,
    data: schema.GameUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    game = await crud.get_game(session, game_id)
    if game is None or game.match_id != match_id:
        raise HTTPException(status_code=404, detail="Game not found in match")
    updated = await crud.update_game(session, game_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return updated
