from uuid import UUID
from fastapi import APIRouter

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException

from . import crud, schema

from league_app.database import get_session_for_api
from league_app.api.users.users import current_active_verified_user, current_superuser
from league_app.api.users.model import User
from logging import Logger

router = APIRouter(tags=["games"])
logger = Logger("games")


@router.post("/", response_model=schema.GameOutput)
async def create_game(
    game: schema.GameCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    # owner is the authenticated user by default
    created = await crud.create_game(session=session, game=game)
    return created


@router.get("/", response_model=list[schema.GameOutput])
async def read_games(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
):
    if not user.is_superuser:
        raise HTTPException(status_code=401, detail="Only superuser can list all games")

    games = await crud.get_games(db, skip=skip, limit=limit)
    return games


@router.get("/search", response_model=list[schema.GameOutput])
async def search_games(
    tournament_id: UUID | None = None,
    player_id: UUID | None = None,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    games = await crud.search_games(session, tournament_id=tournament_id, player_id=player_id)
    return [schema.GameOutput.model_validate(g) for g in games]


@router.get("/{uuid}", response_model=schema.GameOutput)
async def read_game(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_game = await crud.get_game(session, uuid=uuid)
    if db_game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return db_game


@router.put("/{uuid}", response_model=schema.GameOutput)
async def update_game(
    uuid: UUID,
    game: schema.GameUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_game = await crud.get_game(session, uuid=uuid)
    if db_game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # only owner or superuser can update
    allowed = user.is_superuser or (user.id == db_game.owner_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Only owner or superuser can change this game")
    if game.uuid is not None and uuid != game.uuid:
        raise HTTPException(status_code=403, detail="Game UUID mismatch")

    game.uuid = uuid
    updated = await crud.update_game(session, game=game)
    return updated


@router.delete("/{uuid}", response_model=schema.GameOutput)
async def delete_game(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    game = await crud.get_game(session, uuid=uuid)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    allowed = user.is_superuser or (user.id == game.owner_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Only owner or superuser can delete this game")
    return await crud.delete_game(session=session, uuid=uuid)
