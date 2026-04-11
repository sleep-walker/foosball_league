from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.matches import crud as matches_crud, schema as matches_schema
from league_app.api.stages import crud as stages_crud, schema as stages_schema
from league_app.api.tournaments import crud, schema
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from league_app.api.players.schema import PlayerOutput

router = APIRouter(tags=["tournaments"])


def _check_organizer(tournament, user: User) -> None:
    """Raise 403 if the user is neither the tournament owner nor a superuser."""
    if not user.is_superuser and user.id != tournament.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Only the tournament owner or a superuser can perform this action",
        )


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
    existing = await crud.get_tournament(session, tournament_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(existing, user)
    tournament.uuid = tournament_id
    updated = await crud.update_tournament(session, tournament)
    return updated


@router.delete("/{tournament_id}", response_model=schema.TournamentOutput)
async def delete_tournament(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    existing = await crud.get_tournament(session, tournament_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(existing, user)
    return await crud.delete_tournament(session, tournament_id)


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
    _check_organizer(tournament, user)
    applications = await crud.get_applications(session, tournament_id)
    return [PlayerOutput.model_validate(player) for player in applications]


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
    _check_organizer(tournament, user)
    await crud.delete_application(session, tournament_id, player_id)
    return {"message": "Application removed"}


# --- Tournament players ---


@router.get(
    "/{tournament_id}/players/",
    response_model=list[schema.RegistrationOutput],
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
    return tournament.registrations


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
    _check_organizer(tournament, user)
    if await crud.is_player(session, tournament_id, player_id):
        raise HTTPException(status_code=400, detail="Player already registered")
    result = await crud.register_player_for_tournament(
        session, tournament_id, player_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return {"message": "Player added to tournament"}


@router.patch("/{tournament_id}/players/{player_id}/paid", tags=["tournaments"])
async def mark_player_paid(
    tournament_id: UUID,
    player_id: UUID,
    paid: bool = True,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    reg = await crud.mark_player_paid(session, tournament_id, player_id, paid)
    if reg is None:
        raise HTTPException(status_code=404, detail="Player not in tournament")
    return schema.RegistrationOutput.model_validate(reg)


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
    _check_organizer(tournament, user)
    removed = await crud.remove_player_from_tournament(
        session, tournament_id, player_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Player not in tournament")
    return {"message": "Player removed from tournament"}


# --- Tournament matches ---


@router.get(
    "/{tournament_id}/matches/",
    response_model=list[matches_schema.MatchOutput],
    tags=["tournaments"],
)
async def list_tournament_matches(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return await matches_crud.get_matches_by_tournament(session, tournament_id)


@router.post(
    "/{tournament_id}/matches/",
    response_model=matches_schema.MatchOutput,
    tags=["tournaments"],
)
async def create_match_in_tournament(
    tournament_id: UUID,
    match: matches_schema.MatchCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    match.tournament_id = tournament_id
    return await matches_crud.create_match(session, match, owner_id=user.id)


@router.patch(
    "/{tournament_id}/matches/{match_id}",
    response_model=matches_schema.MatchOutput,
    tags=["tournaments"],
)
async def update_match_in_tournament(
    tournament_id: UUID,
    match_id: UUID,
    data: matches_schema.MatchUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    existing = await matches_crud.get_match(session, match_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Match not found in tournament")
    updated = await matches_crud.update_match(session, match_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return updated


@router.delete("/{tournament_id}/matches/{match_id}", tags=["tournaments"])
async def remove_match_from_tournament(
    tournament_id: UUID,
    match_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    existing = await matches_crud.get_match(session, match_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Match not found in tournament")
    await matches_crud.delete_match(session, match_id)
    return {"message": "Match removed from tournament"}


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
    _check_organizer(tournament, user)
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
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
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
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    existing = await stages_crud.get_stage(session, stage_id)
    if existing is None or existing.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")
    await stages_crud.delete_stage(session, stage_id)
    return {"message": "Stage removed from tournament"}
