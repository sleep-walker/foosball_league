from uuid import UUID
from fastapi import APIRouter

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException

from . import crud, schema

from league_app.database import get_session, get_db
from league_app.api.users.router import current_active_user
from league_app.api.users.model import User

router = APIRouter(tags=["players"])


@router.post("/", response_model=schema.PlayerOutput)
async def create_player(
    player: schema.PlayerCreate, session: AsyncSession = Depends(get_session)
):
    db_player = await crud.get_player_by_email(session, email=player.email)
    if db_player:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_player = await crud.get_player_by_nickname(session, nickname=player.nickname)
    if db_player:
        raise HTTPException(status_code=400, detail="Nickname already registered")
    return await crud.create_player(session=session, player=player)


@router.get("/", response_model=list[schema.PlayerOutput])
async def read_players(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_session)
):
    players = await crud.get_players(db, skip=skip, limit=limit)
    return players


@router.get("/", response_model=list[schema.PlayerOutput])
async def read_players(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> list[schema.PlayerOutput]:
    players = await crud.get_players(db, skip=skip, limit=limit)
    return players


@router.get("/self", response_model=schema.PlayerOutput)
async def read_player(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
):
    db_player = await crud.get_player(session, uuid=user.uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


@router.get("/{uuid}", response_model=schema.PlayerOutput)
async def read_player(uuid: UUID, session: AsyncSession = Depends(get_session)):
    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


@router.put("/{uuid}", response_model=schema.PlayerOutput)
async def update_player(
    uuid: UUID,
    player: schema.PlayerUpdate,
    session: AsyncSession = Depends(get_session),
):
    if uuid != player.uuid:
        raise HTTPException(status_code=403, detail="User cannot change his UUID")

    player = await crud.update_player(session, player=player)
    return player


@router.delete("/{uuid}", response_model=schema.PlayerOutput)
async def delete_player(uuid: UUID, session: AsyncSession = Depends(get_session)):
    # FIXME: ensure required permissions
    return crud.delete_player(session=session, uuid=uuid)
