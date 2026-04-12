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
from league_app.engine import standings as standings_engine, swiss, bracket as bracket_engine

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
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Get current standings for a group stage."""
    stage = await stages_crud.get_stage(session, stage_id)
    if stage is None or stage.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")

    matches = await matches_crud.get_matches_by_stage(session, stage_id)
    match_results = []
    for m in matches:
        if m.status != "finished":
            continue
        a_id = m.team_a_id or m.player_a_id
        b_id = m.team_b_id or m.player_b_id
        if a_id is None or b_id is None:
            continue
        match_results.append(
            standings_engine.MatchResult(
                participant_a_id=a_id,
                participant_b_id=b_id,
                games=[
                    standings_engine.GameResult(score_a=g.score_a, score_b=g.score_b)
                    for g in m.games
                ],
            )
        )

    rows = standings_engine.compute_standings(match_results, rules=stage.rules)
    return [
        StandingRowOutput(
            participant_id=r.participant_id,
            wins=r.wins,
            draws=r.draws,
            losses=r.losses,
            goals_for=r.goals_for,
            goals_against=r.goals_against,
            goal_difference=r.goal_difference,
            points=r.points,
            matches_played=r.matches_played,
        )
        for r in rows
    ]


# --- Draw round (Swiss) ---


@router.post(
    "/{tournament_id}/stages/{stage_id}/draw-round",
    response_model=list[matches_schema.MatchOutput],
    tags=["tournaments"],
)
async def draw_swiss_round(
    tournament_id: UUID,
    stage_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Draw the next Swiss round for a group stage."""
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    stage = await stages_crud.get_stage(session, stage_id)
    if stage is None or stage.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")
    if stage.stage_type != "group":
        raise HTTPException(status_code=400, detail="Swiss draw only for group stages")

    # Gather registered players
    participant_ids = [r.player_id for r in tournament.registrations]
    if len(participant_ids) < 2:
        raise HTTPException(status_code=400, detail="Not enough participants")

    # Build match history from existing matches in this stage
    existing_matches = await matches_crud.get_matches_by_stage(session, stage_id)
    match_history = []
    for m in existing_matches:
        a_id = m.player_a_id
        b_id = m.player_b_id
        if a_id and b_id:
            match_history.append(
                standings_engine.MatchResult(
                    participant_a_id=a_id,
                    participant_b_id=b_id,
                    games=[
                        standings_engine.GameResult(score_a=g.score_a, score_b=g.score_b)
                        for g in m.games
                    ],
                )
            )

    current_round = max((m.round_number for m in existing_matches), default=0) + 1
    pairings = swiss.generate_swiss_round(participant_ids, match_history, stage.rules)

    created = []
    for p in pairings:
        match_create = matches_schema.MatchCreate(
            tournament_id=tournament_id,
            stage_id=stage_id,
            round_number=current_round,
            best_of=stage.rules.get("best_of", 1) if stage.rules else 1,
            player_a_id=p.participant_a_id,
            player_b_id=p.participant_b_id,
        )
        m = await matches_crud.create_match(session, match_create, owner_id=user.id)
        created.append(m)

    return created


# --- Generate elimination bracket ---


@router.post(
    "/{tournament_id}/stages/{stage_id}/generate-bracket",
    response_model=list[matches_schema.MatchOutput],
    tags=["tournaments"],
)
async def generate_elimination_bracket(
    tournament_id: UUID,
    stage_id: UUID,
    source_stage_id: UUID | None = None,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Generate elimination bracket, optionally seeded from a group stage.

    If ``source_stage_id`` is provided, standings from that stage are used
    for seeding (top player = seed 1). Otherwise, registered players are
    used in registration order.
    """
    tournament = await crud.get_tournament(session, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    _check_organizer(tournament, user)
    stage = await stages_crud.get_stage(session, stage_id)
    if stage is None or stage.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Stage not found in tournament")
    if stage.stage_type != "elimination":
        raise HTTPException(status_code=400, detail="Bracket generation only for elimination stages")

    # Determine seeded participants
    if source_stage_id:
        source_matches = await matches_crud.get_matches_by_stage(session, source_stage_id)
        match_results = []
        for m in source_matches:
            a_id = m.team_a_id or m.player_a_id
            b_id = m.team_b_id or m.player_b_id
            if a_id and b_id and m.status == "finished":
                match_results.append(
                    standings_engine.MatchResult(
                        participant_a_id=a_id,
                        participant_b_id=b_id,
                        games=[
                            standings_engine.GameResult(score_a=g.score_a, score_b=g.score_b)
                            for g in m.games
                        ],
                    )
                )
        rows = standings_engine.compute_standings(match_results)
        advancement = stage.advancement_count or len(rows)
        seeded_ids = [r.participant_id for r in rows[:advancement]]
    else:
        seeded_ids = [r.player_id for r in tournament.registrations]

    if len(seeded_ids) < 2:
        raise HTTPException(status_code=400, detail="Not enough participants for bracket")

    consolation = stage.rules.get("consolation_match", True) if stage.rules else True
    best_of = stage.rules.get("best_of", 3) if stage.rules else 3
    bracket = bracket_engine.generate_bracket(seeded_ids, consolation=consolation)

    created = []
    for bm in bracket.matches:
        match_create = matches_schema.MatchCreate(
            tournament_id=tournament_id,
            stage_id=stage_id,
            round_number=bm.round_number,
            bracket_position=bm.position,
            best_of=best_of,
            player_a_id=bm.participant_a_id,
            player_b_id=bm.participant_b_id,
        )
        m = await matches_crud.create_match(session, match_create, owner_id=user.id)
        created.append(m)

    return created