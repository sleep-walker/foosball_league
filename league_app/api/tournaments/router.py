from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.matches import crud as matches_crud, schema as matches_schema
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
        SALeagueRepository,
    )
    from league_app.infra.sa_table_repo import SATableRepository
    return TournamentService(
        tournaments=FullSATournamentRepository(session),
        matches=FullSAMatchRepository(session),
        stages=SAStageRepository(session),
        players=SAPlayerRepository(session),
        teams=SATeamRepository(session),
        tables=SATableRepository(session),
        leagues=SALeagueRepository(session),
    )

router = APIRouter(tags=["tournaments"])


def _check_organizer(tournament, user: User) -> None:
    """Raise 403 unless the user is owner, co-organizer, or superuser."""
    if user.is_superuser:
        return
    if user.id == tournament.owner_id:
        return
    co_ids = {u.id for u in (tournament.co_organizers or [])}
    if user.id in co_ids:
        return
    raise HTTPException(
        status_code=403,
        detail="Only the tournament owner, co-organizer, or superuser can perform this action",
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
    if tournament is None or tournament.is_deleted:
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



@router.post("/{tournament_id}/co-organizers/{user_id}", tags=["tournaments"])
async def add_co_organizer(
    tournament_id: UUID,
    user_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Add a co-organizer. Only the owner can add co-organizers."""
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not user.is_superuser and user.id != tournament.owner_id:
        raise HTTPException(status_code=403, detail="Only the owner can add co-organizers")
    from league_app.api.users.model import User as UserModel
    co_user = await session.get(UserModel, user_id)
    if co_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if co_user in tournament.co_organizers:
        raise HTTPException(status_code=400, detail="User is already a co-organizer")
    tournament.co_organizers.append(co_user)
    await session.flush()
    return {"message": f"User {user_id} added as co-organizer"}


@router.delete("/{tournament_id}/co-organizers/{user_id}", tags=["tournaments"])
async def remove_co_organizer(
    tournament_id: UUID,
    user_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Remove a co-organizer. Only the owner can remove co-organizers."""
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not user.is_superuser and user.id != tournament.owner_id:
        raise HTTPException(status_code=403, detail="Only the owner can remove co-organizers")
    from league_app.api.users.model import User as UserModel
    co_user = await session.get(UserModel, user_id)
    if co_user is None or co_user not in tournament.co_organizers:
        raise HTTPException(status_code=404, detail="User is not a co-organizer")
    tournament.co_organizers.remove(co_user)
    await session.flush()
    return {"message": f"User {user_id} removed from co-organizers"}


@router.post("/{tournament_id}/start", tags=["tournaments"])
async def start_tournament(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Transition tournament REGISTRATION → RUNNING."""
    existing = await crud.get_tournament(session, tournament_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(existing, user)
    try:
        return await svc.start_tournament(tournament_id, owner_id=user.id)
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
    session: AsyncSession = Depends(get_session_for_api),
    svc: TournamentService = Depends(_get_tournament_service),
):
    try:
        # force=True: organizer can add players to a running tournament (late-join)
        await svc.register_player(tournament_id, player_id, force=True)
    except TournamentError as e:
        raise _handle_svc_error(e)
    # Remove from applicants if they were pre-registered via QR
    await crud.delete_application(session, tournament_id, player_id)
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
    raw = await matches_crud.get_matches_by_tournament(session, tournament_id)
    return await _enrich_matches(session, raw)


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


# Rule keys that affect already-drawn matches.  Changing these on an
# ``active`` stage silently invalidates standings, so we require
# ``?force=true``.  UI should pair such an update with a redraw.
_LOCKED_STAGE_RULE_KEYS = frozenset({
    "points_per_game",
    "best_of",
    "draw_allowed",
    "points_for_win",
    "points_for_draw",
    "points_for_loss",
    "margin_in_decider",
    "consolation_match",
    "table_count",
})


@router.patch(
    "/{tournament_id}/stages/{stage_id}",
    response_model=stages_schema.StageOutput,
    tags=["tournaments"],
)
async def update_tournament_stage(
    tournament_id: UUID,
    stage_id: UUID,
    stage: stages_schema.StageUpdate,
    force: bool = False,
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

    # Reject finished-stage edits outright and lock rules on active stages
    # unless ``force=true`` is supplied.  See _LOCKED_STAGE_RULE_KEYS for
    # the affected fields.
    if existing.status == "finished":
        update_dict = stage.model_dump(exclude_unset=True)
        # Only allow no-op or non-rule metadata changes
        if any(k != "is_deleted" for k in update_dict):
            raise HTTPException(
                status_code=409,
                detail="Cannot modify a finished stage",
            )
    elif existing.status == "active" and not force:
        new_rules = stage.rules
        if new_rules:
            current = existing.rules or {}
            locked = [
                k for k in new_rules
                if k in _LOCKED_STAGE_RULE_KEYS and new_rules[k] != current.get(k)
            ]
            if locked:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Stage is active; rule changes affecting drawn "
                        "matches require ?force=true and a follow-up "
                        "redraw-round call. Locked keys: "
                        + ", ".join(sorted(locked))
                    ),
                )

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


@router.post(
    "/{tournament_id}/stages/{stage_id}/activate",
    response_model=stages_schema.StageOutput,
    tags=["tournaments"],
)
async def activate_stage(
    tournament_id: UUID,
    stage_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Activate a stage (preparing → active)."""
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    try:
        return await svc.activate_stage(stage_id)
    except TournamentError as e:
        raise _handle_svc_error(e)


@router.post(
    "/{tournament_id}/stages/{stage_id}/finish",
    response_model=stages_schema.StageOutput,
    tags=["tournaments"],
)
async def finish_stage(
    tournament_id: UUID,
    stage_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Finish a stage (active → finished)."""
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    try:
        return await svc.finish_stage(stage_id)
    except TournamentError as e:
        raise _handle_svc_error(e)


# --- Standings ---


class StandingRowOutput(BaseModel):
    participant_id: UUID
    nickname: str | None = None
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    matches_played: int
    sets_won: int = 0
    sets_lost: int = 0
    sets_difference: int = 0


@router.get(
    "/{tournament_id}/stages/{stage_id}/standings",
    response_model=list[StandingRowOutput],
    tags=["tournaments"],
)
async def get_stage_standings(
    tournament_id: UUID,
    stage_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Get current standings for a group stage."""
    try:
        rows = await svc.get_stage_standings(tournament_id, stage_id)
    except TournamentError as e:
        raise _handle_svc_error(e)

    # Resolve nicknames
    from league_app.api.players import model as player_orm
    from league_app.api.teams import model as team_orm
    nickname_map: dict[UUID, str] = {}
    for r in rows:
        if r.participant_id not in nickname_map:
            p = await session.get(player_orm.Player, r.participant_id)
            if p:
                nickname_map[r.participant_id] = p.nickname or "—"
            else:
                t = await session.get(team_orm.Team, r.participant_id)
                if t:
                    p1 = await session.get(player_orm.Player, t.player_1_id)
                    p2 = await session.get(player_orm.Player, t.player_2_id)
                    nickname_map[r.participant_id] = (
                        f"{p1.nickname if p1 else '?'} & {p2.nickname if p2 else '?'}"
                    )

    return [
        StandingRowOutput(
            participant_id=r.participant_id,
            nickname=nickname_map.get(r.participant_id),
            wins=r.wins, draws=r.draws,
            losses=r.losses, goals_for=r.goals_for, goals_against=r.goals_against,
            goal_difference=r.goal_difference, points=r.points,
            matches_played=r.matches_played,
            sets_won=r.sets_won, sets_lost=r.sets_lost,
            sets_difference=r.sets_difference,
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


@router.post(
    "/{tournament_id}/stages/{stage_id}/redraw-round",
    tags=["tournaments"],
)
async def redraw_current_round(
    tournament_id: UUID,
    stage_id: UUID,
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Delete all matches in the latest unfinished round and draw again."""
    try:
        created = await svc.redraw_current_round(tournament_id, stage_id, owner_id=user.id)
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


async def _enrich_matches(session: AsyncSession, matches):
    """Add player nicknames, team names, and computed scores to match dicts."""
    from league_app.api.players import model as player_model
    from league_app.api.teams import model as team_model

    # Collect all player/team IDs
    player_ids = set()
    team_ids = set()
    for m in matches:
        if hasattr(m, "player_a_id") and m.player_a_id:
            player_ids.add(m.player_a_id)
        if hasattr(m, "player_b_id") and m.player_b_id:
            player_ids.add(m.player_b_id)
        if hasattr(m, "team_a_id") and m.team_a_id:
            team_ids.add(m.team_a_id)
        if hasattr(m, "team_b_id") and m.team_b_id:
            team_ids.add(m.team_b_id)

    # Batch-load players
    players = {}
    for pid in player_ids:
        p = await session.get(player_model.Player, pid)
        if p:
            players[pid] = p.nickname or f"{p.first_name or ''} {p.last_name or ''}".strip() or str(pid)[:8]

    # Batch-load teams
    teams = {}
    for tid in team_ids:
        t = await session.get(team_model.Team, tid)
        if t:
            p1 = players.get(t.player_1_id, str(t.player_1_id)[:8])
            p2 = players.get(t.player_2_id, str(t.player_2_id)[:8])
            # Also load players if not already loaded
            if t.player_1_id not in players:
                pp = await session.get(player_model.Player, t.player_1_id)
                if pp:
                    p1 = pp.nickname or str(t.player_1_id)[:8]
                    players[t.player_1_id] = p1
            if t.player_2_id not in players:
                pp = await session.get(player_model.Player, t.player_2_id)
                if pp:
                    p2 = pp.nickname or str(t.player_2_id)[:8]
                    players[t.player_2_id] = p2
            teams[tid] = f"{p1} & {p2}"

    # Enrich
    result = []
    for m in matches:
        d = {
            "uuid": m.uuid, "tournament_id": m.tournament_id,
            "stage_id": m.stage_id, "round_number": m.round_number,
            "best_of": m.best_of, "table_number": m.table_number,
            "status": m.status, "winner_side": m.winner_side,
            "player_a_id": m.player_a_id, "player_b_id": m.player_b_id,
            "team_a_id": m.team_a_id, "team_b_id": m.team_b_id,
            "owner_id": m.owner_id, "is_deleted": m.is_deleted,
            "games": [],
        }
        d["player_a_nickname"] = players.get(m.player_a_id) if m.player_a_id else None
        d["player_b_nickname"] = players.get(m.player_b_id) if m.player_b_id else None
        d["team_a_name"] = teams.get(m.team_a_id) if m.team_a_id else None
        d["team_b_name"] = teams.get(m.team_b_id) if m.team_b_id else None

        # Compute score from games
        games = getattr(m, "games", []) or []
        d["score_a"] = sum(g.score_a or 0 for g in games)
        d["score_b"] = sum(g.score_b or 0 for g in games)
        d["games"] = [
            {"uuid": g.uuid, "match_id": g.match_id,
             "game_number": g.game_number,
             "score_a": g.score_a, "score_b": g.score_b,
             "is_finished": g.is_finished}
            for g in games
        ]
        result.append(d)
    return result