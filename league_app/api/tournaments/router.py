from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.games import crud as games_crud, schema as games_schema
from league_app.api.stages import crud as stages_crud, schema as stages_schema
from league_app.api.tournaments import crud, schema
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
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


# --- Tournament players ---


@router.get(
    "/{tournament_id}/players/",
    response_model=list[PlayerOutput],
    tags=["tournaments"],
)
async def list_tournament_players(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return tournament.players


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
    if await crud.is_player(session, tournament_id, player_id):
        raise HTTPException(status_code=400, detail="Player already registered")
    result = await crud.register_player_for_tournament(
        session, tournament_id, player_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return {"message": "Player added to tournament"}


@router.delete("/{tournament_id}/players/{player_id}", tags=["tournaments"])
async def remove_player_from_tournament(
    tournament_id: UUID,
    player_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    result = await crud.remove_player_from_tournament(
        session, tournament_id, player_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Player not in tournament")
    return {"message": "Player removed from tournament"}


# --- Tournament games ---


@router.get(
    "/{tournament_id}/games/",
    response_model=list[games_schema.GameOutput],
    tags=["tournaments"],
)
async def list_tournament_games(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return await games_crud.get_games_by_tournament(session, tournament_id)


@router.post(
    "/{tournament_id}/games/",
    response_model=games_schema.GameOutput,
    tags=["tournaments"],
)
async def create_game_in_tournament(
    tournament_id: UUID,
    game: games_schema.GameCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    game.tournament_id = tournament_id
    game.owner_id = user.id
    return await games_crud.create_game(session, game)


@router.patch(
    "/{tournament_id}/games/{game_id}",
    response_model=games_schema.GameOutput,
    tags=["tournaments"],
)
async def update_game_in_tournament(
    tournament_id: UUID,
    game_id: UUID,
    game: games_schema.GameUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    existing = await games_crud.get_game(session, game_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Game not found in tournament")
    game.uuid = game_id
    updated = await games_crud.update_game(session, game)
    if updated is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return updated


@router.delete("/{tournament_id}/games/{game_id}", tags=["tournaments"])
async def remove_game_from_tournament(
    tournament_id: UUID,
    game_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    existing = await games_crud.get_game(session, game_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Game not found in tournament")
    await games_crud.delete_game(session, game_id)
    return {"message": "Game removed from tournament"}


# --- Tournament stages ---


@router.get(
    "/{tournament_id}/stages/",
    response_model=list[stages_schema.StageOutput],
    tags=["tournaments"],
)
async def list_tournament_stages(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return await stages_crud.get_stages_by_tournament(session, tournament_id)


@router.post(
    "/{tournament_id}/stages/",
    response_model=stages_schema.StageOutput,
    tags=["tournaments"],
)
async def create_stage_in_tournament(
    tournament_id: UUID,
    stage: stages_schema.StageCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    stage.tournament_id = tournament_id
    return await stages_crud.create_stage(session, stage)


@router.get(
    "/{tournament_id}/stages/{stage_id}",
    response_model=stages_schema.StageOutput,
    tags=["tournaments"],
)
async def get_tournament_stage_details(
    tournament_id: UUID,
    stage_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    stage = await stages_crud.get_stage(session, stage_id)
    if stage is None or stage.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")
    return stage


@router.patch(
    "/{tournament_id}/stages/{stage_id}",
    response_model=stages_schema.StageOutput,
    tags=["tournaments"],
)
async def update_tournament_stage(
    tournament_id: UUID,
    stage_id: UUID,
    stage: stages_schema.StageUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    existing = await stages_crud.get_stage(session, stage_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")
    updated = await stages_crud.update_stage(session, stage_id, stage)
    if updated is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return updated


@router.delete("/{tournament_id}/stages/{stage_id}", tags=["tournaments"])
async def remove_stage_from_tournament(
    tournament_id: UUID,
    stage_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    existing = await stages_crud.get_stage(session, stage_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")
    await stages_crud.delete_stage(session, stage_id)
    return {"message": "Stage removed from tournament"}
