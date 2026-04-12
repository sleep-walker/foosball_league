from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.matches import schema as matches_schema
from league_app.api.stages import crud as stages_crud, schema as stages_schema
from league_app.api.tournaments import crud, schema
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from league_app.api.players.schema import PlayerOutput
from league_app.domain.tournament_service import TournamentService, TournamentError


def _get_tournament_service(
    session: AsyncSession = Depends(get_session_for_api),
):
    """Build TournamentService with SA repositories — avoids circular imports."""
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

router = APIRouter(tags=["tournaments"])


def _check_organizer(tournament, user: User) -> None:
    """Raise 403 if the user is neither the tournament owner nor a superuser."""
    if not user.is_superuser and user.id != tournament.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Only the tournament owner or a superuser can perform this action",
        )


def _handle_svc_error(e: TournamentError) -> HTTPException:
    """Map domain errors to HTTP status codes."""
    msg = str(e)
    if "not found" in msg.lower():
        return HTTPException(status_code=404, detail=msg)
    if "permission" in msg.lower():
        return HTTPException(status_code=403, detail=msg)
    return HTTPException(status_code=400, detail=msg)


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



@router.post("/{tournament_id}/start", tags=["tournaments"])
async def start_tournament(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Transition tournament PREPARING → RUNNING."""
    existing = await crud.get_tournament(session, tournament_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(existing, user)
    try:
        return await svc.start_tournament(tournament_id)
    except TournamentError as e:
        raise _handle_svc_error(e)


@router.post("/{tournament_id}/finish", tags=["tournaments"])
async def finish_tournament(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Transition tournament RUNNING → FINISHED."""
    existing = await crud.get_tournament(session, tournament_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(existing, user)
    try:
        return await svc.finish_tournament(tournament_id)
    except TournamentError as e:
        raise _handle_svc_error(e)

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
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    try:
        await svc.register_player(tournament_id, player_id)
    except TournamentError as e:
        raise _handle_svc_error(e)
    return {"message": "Player added to tournament"}


@router.patch("/{tournament_id}/players/{player_id}/paid", tags=["tournaments"])
async def mark_player_paid(
    tournament_id: UUID,
    player_id: UUID,
    paid: bool = True,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    try:
        reg = await svc.mark_paid(tournament_id, player_id, paid)
    except TournamentError as e:
        raise _handle_svc_error(e)
    return reg


@router.post("/{tournament_id}/players/{player_id}/pause", tags=["tournaments"])
async def pause_player(
    tournament_id: UUID,
    player_id: UUID,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    try:
        return await svc.pause_player(tournament_id, player_id)
    except TournamentError as e:
        raise _handle_svc_error(e)


@router.post("/{tournament_id}/players/{player_id}/unpause", tags=["tournaments"])
async def unpause_player(
    tournament_id: UUID,
    player_id: UUID,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    try:
        return await svc.unpause_player(tournament_id, player_id)
    except TournamentError as e:
        raise _handle_svc_error(e)


@router.delete("/{tournament_id}/players/{player_id}", tags=["tournaments"])
async def remove_player_from_tournament(
    tournament_id: UUID,
    player_id: UUID,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    try:
        await svc.unregister_player(tournament_id, player_id)
    except TournamentError as e:
        raise _handle_svc_error(e)
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



# --- Standings ---


class StandingRowOutput(BaseModel):
    participant_id: UUID
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    matches_played: int


@router.get(
    "/{tournament_id}/stages/{stage_id}/standings",
    response_model=list[StandingRowOutput],
    tags=["tournaments"],
)
async def get_stage_standings(
    tournament_id: UUID,
    stage_id: UUID,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Get current standings for a group stage."""
    try:
        rows = await svc.get_stage_standings(tournament_id, stage_id)
    except TournamentError as e:
        raise _handle_svc_error(e)
    return [
        StandingRowOutput(
            participant_id=r.participant_id, wins=r.wins, draws=r.draws,
            losses=r.losses, goals_for=r.goals_for, goals_against=r.goals_against,
            goal_difference=r.goal_difference, points=r.points,
            matches_played=r.matches_played,
        )
        for r in rows
    ]


# --- Draw round (Swiss) ---


@router.post(
    "/{tournament_id}/stages/{stage_id}/draw-round",
    tags=["tournaments"],
)
async def draw_swiss_round(
    tournament_id: UUID,
    stage_id: UUID,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Draw the next Swiss round for a group stage."""
    try:
        created = await svc.draw_swiss_round(tournament_id, stage_id, owner_id=user.id)
    except TournamentError as e:
        raise _handle_svc_error(e)
    return created


# --- Generate elimination bracket ---


@router.post(
    "/{tournament_id}/stages/{stage_id}/generate-bracket",
    tags=["tournaments"],
)
async def generate_elimination_bracket(
    tournament_id: UUID,
    stage_id: UUID,
    source_stage_id: UUID | None = None,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Generate elimination bracket, optionally seeded from a group stage."""
    try:
        created = await svc.generate_bracket(
            tournament_id, stage_id, owner_id=user.id,
            source_stage_id=source_stage_id,
        )
    except TournamentError as e:
        raise _handle_svc_error(e)
    return created