from uuid import UUID
from fastapi import APIRouter

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException

from . import crud, schema

from league_app.database import get_session_for_api
from league_app.api.users.users import current_active_verified_user
from league_app.api.users.model import User
from logging import Logger

router = APIRouter(tags=["players"])
logger = Logger("players")


@router.post("/", response_model=schema.PlayerOutput)
async def create_player(
    player: schema.PlayerCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    logger.info("checking mail")
    if player.email is not None:
        db_player = await crud.get_player_by_email(session, email=player.email)
        if db_player:
            raise HTTPException(status_code=400, detail="Email already registered")
    logger.info("checking nickname")
    db_player = await crud.get_player_by_nickname(session, nickname=player.nickname)
    if db_player:
        raise HTTPException(status_code=400, detail="Nickname already registered")
    print("checking uuid")
    db_player = await crud.get_player_by_uuid(session, uuid=user.id)
    if db_player is None:
        print("creating player - doesn't have one yet")
        # user doesn't have own player
        player.uuid = user.id
        return await crud.create_player(session=session, player=player)
    if not user.is_superuser:
        print("not creating player - already has one")
        raise HTTPException(
            status_code=400, detail="User have already registered player"
        )
    # superuser can add new players, without linking UUID
    # FIXME: how to link players created by someone else with user account?
    print("creating player - superuser")
    return await crud.create_player(session=session, player=player)


@router.get("/", response_model=list[schema.PlayerOutput])
async def read_players(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_session_for_api)
):
    players = await crud.get_players(db, skip=skip, limit=limit)
    return players


@router.get("/self", response_model=schema.PlayerOutput)
async def read_player_self(
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_player = await crud.get_player(session, uuid=user.id)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


@router.get("/{uuid}", response_model=schema.PlayerOutput)
async def read_player(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


@router.put("/{uuid}", response_model=schema.PlayerOutput)
async def update_player(
    uuid: UUID,
    player: schema.PlayerUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    allowed = user.is_superuser or user.id == uuid
    if not allowed:
        raise HTTPException(
            status_code=401, detail="Only a superuser can change other players"
        )
    if player.uuid is not None and uuid != player.uuid:
        raise HTTPException(status_code=403, detail="User cannot change his UUID")

    player_output = await crud.update_player(session, player=player)
    return player_output


@router.delete("/{uuid}", response_model=schema.PlayerOutput)
async def delete_player(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    allowed = user.is_superuser or user.id == uuid
    if not allowed:
        raise HTTPException(
            status_code=401, detail="Only a superuser can delete other players"
        )
    return crud.delete_player(session=session, uuid=uuid)
