from collections.abc import Sequence
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from league_app.database import get_session_for_api
from league_app.api.tournaments import crud, schema
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from league_app.api.players.model import Player
from league_app.api.players.schema import PlayerOutput

router = APIRouter(tags=["tournaments"])


@router.get("/", response_model=list[schema.TournamentOutput])
async def list_tournaments(
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournaments = await crud.get_tournaments(session)
    return tournaments


@router.post("/", response_model=schema.TournamentOutput)
async def create_tournament(
    tournament: schema.TournamentCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament.owner_id = user.id
    return await crud.create_tournament(session, tournament)


@router.get("/{tournament_id}", response_model=schema.TournamentOutput)
async def get_tournament_details(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return tournament


@router.patch("/{tournament_id}", response_model=schema.TournamentOutput)
async def update_tournament(
    tournament_id: UUID,
    tournament: schema.TournamentUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament.uuid = tournament_id
    updated = await crud.update_tournament(session, tournament)
    if updated is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return updated


@router.delete("/{tournament_id}", response_model=schema.TournamentOutput)
async def delete_tournament(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    deleted = await crud.delete_tournament(session, tournament_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return deleted


# ...existing code...

# Tournament registration applications


@router.post("/{tournament_id}/applications/", tags=["tournaments"])
async def apply_for_tournament(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not tournament.is_registration_open:
        raise HTTPException(
            status_code=403, detail="Registration is closed for this tournament"
        )
    # Check if already applied or registered
    if await crud.is_applicant(session, tournament_id, user.id):
        raise HTTPException(status_code=400, detail="Already applied")
    if await crud.is_player(session, tournament_id, user.id):
        raise HTTPException(status_code=400, detail="Already registered")
    await crud.create_application(session, tournament_id, user.id)
    return {"message": "Application submitted"}


@router.get("/{tournament_id}/applications/", tags=["tournaments"])
async def list_tournament_applications(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
) -> Sequence[PlayerOutput]:
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    # TODO: check organizer/owner permissions
    applications = await crud.get_applications(session, tournament_id)
    return [PlayerOutput.model_dump(player) for player in applications]


@router.delete("/{tournament_id}/applications/{player_id}", tags=["tournaments"])
async def remove_tournament_application(
    tournament_id: UUID,
    player_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    # TODO: check organizer/owner permissions
    await crud.delete_application(session, tournament_id, player_id)
    return {"message": "Application removed"}


# Tournament specific players
@router.get("/{tournament_id}/players/", tags=["tournaments"])
async def list_tournament_players(tournament_id: UUID):
    pass


# Owner/organizer registers any player (applicant or not)
@router.post("/{tournament_id}/players/", tags=["tournaments"])
async def add_player_to_tournament(
    tournament_id: UUID,
    player_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    # TODO: check organizer/owner permissions
    if await crud.is_player(session, tournament_id, player_id):
        raise HTTPException(status_code=400, detail="Player already registered")
    await crud.register_player_for_tournament(session, tournament_id, player_id)


@router.post("/{tournament_id}/register", tags=["tournaments"])
async def register_for_tournament(
    tournament_id: UUID,
    player_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not tournament.is_registration_open:
        raise HTTPException(
            status_code=403, detail="Registration is closed for this tournament"
        )

    # Logic to register the user for the tournament
    # This could involve checking if the user is already registered,
    # and if not, adding them to the tournament's list of registered players.
    if player_id in [player.id for player in tournament.players]:
        raise HTTPException(
            status_code=400, detail="User already registered for this tournament"
        )

    await crud.register_player_for_tournament(session, tournament_id, player_id)
    # This would typically involve adding the user to a list of registered players
    return {"message": "Successfully registered for the tournament"}


@router.patch("/{tournament_id}/players/{player_id}", tags=["tournaments"])
async def update_tournament_player(tournament_id: UUID, player_id: UUID):
    pass


@router.delete("/{tournament_id}/players/{player_id}", tags=["tournaments"])
async def remove_player_from_tournament(tournament_id: UUID, player_id: UUID):
    pass


# Tournament specific games
@router.get("/{tournament_id}/games/", tags=["tournaments"])
async def list_tournament_games(tournament_id: UUID):
    pass


@router.post("/{tournament_id}/games/", tags=["tournaments"])
async def create_game_in_tournament(tournament_id: UUID):
    pass


@router.patch("/{tournament_id}/games/{game_id}", tags=["tournaments"])
async def update_game_in_tournament(tournament_id: UUID, game_id: UUID):
    pass


@router.delete("/{tournament_id}/games/{game_id}", tags=["tournaments"])
async def remove_game_from_tournament(tournament_id: UUID, game_id: UUID):
    pass


# Tournament specific stages
@router.get("/{tournament_id}/stages/", tags=["tournaments"])
async def list_tournament_stages(tournament_id: UUID):
    pass


@router.post("/{tournament_id}/stages/", tags=["tournaments"])
async def create_stage_in_tournament(tournament_id: UUID):
    pass


@router.get("/{tournament_id}/stages/{stage_id}", tags=["tournaments"])
async def get_tournament_stage_details(tournament_id: UUID, stage_id: UUID):
    pass


@router.patch("/{tournament_id}/stages/{stage_id}", tags=["tournaments"])
async def update_tournament_stage(tournament_id: UUID, stage_id: UUID):
    pass


@router.delete("/{tournament_id}/stages/{stage_id}", tags=["tournaments"])
async def remove_stage_from_tournament(tournament_id: UUID, stage_id: UUID):
    pass
