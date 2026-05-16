from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from league_app.domain.tournament_service import TournamentService, TournamentError
from . import crud, schema

router = APIRouter(tags=["matches"])


def _get_tournament_service(
    session: AsyncSession = Depends(get_session_for_api),
):
    """Build TournamentService with SA repositories."""
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


async def _check_score_permission(session: AsyncSession, match, user: User) -> None:
    """Raise 403 if user is not organizer, superuser, or a match participant."""
    if user.is_superuser or match.owner_id == user.id:
        return
    from league_app.api.players import model as player_model
    from league_app.api.teams import model as team_model
    from sqlalchemy import select as sa_select

    player = (await session.execute(
        sa_select(player_model.Player).filter(
            player_model.Player.user_id == user.id
        )
    )).scalar_one_or_none()

    allowed = False
    if player:
        if player.uuid in (match.player_a_id, match.player_b_id):
            allowed = True
        for tid in (match.team_a_id, match.team_b_id):
            if tid:
                team = await session.get(team_model.Team, tid)
                if team and player.uuid in (team.player_1_id, team.player_2_id):
                    allowed = True
                    break
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Only participants or the organizer can submit scores",
        )


@router.patch("/{match_id}/score")
async def submit_match_score(
    match_id: UUID,
    data: schema.ScoreSubmit,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Submit a game score for a match.

    For best-of-1: creates the game and finishes the match.
    For best-of-N: creates the next game; finishes only when one side
    reaches the required number of wins.

    Allowed: tournament owner, superuser, or any player participating in the match.
    """
    match = await crud.get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status == "finished":
        raise HTTPException(status_code=400, detail="Match already finished")

    await _check_score_permission(session, match, user)

    # Delegate to TournamentService — handles best-of-N, validation, match finish
    try:
        await svc.submit_game_score(match_id, data.score_a, data.score_b)
    except TournamentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Score saved", "score_a": data.score_a, "score_b": data.score_b}


@router.patch("/{match_id}/scores")
async def submit_match_scores(
    match_id: UUID,
    data: schema.ScoresSubmit,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
    svc: TournamentService = Depends(_get_tournament_service),
):
    """Submit multiple game scores for a match in a single request.

    All scores are validated up-front; if any one fails validation, nothing
    is committed (no partial batches). Same authorization rules as
    PATCH /{match_id}/score.
    """
    if not data.scores:
        raise HTTPException(status_code=400, detail="No scores provided")

    match = await crud.get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status == "finished":
        raise HTTPException(status_code=400, detail="Match already finished")

    await _check_score_permission(session, match, user)

    try:
        await svc.submit_batch_scores(
            match_id, [(s.score_a, s.score_b) for s in data.scores],
        )
    except TournamentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    submitted = [{"score_a": s.score_a, "score_b": s.score_b} for s in data.scores]
    return {"message": "Scores saved", "count": len(submitted), "scores": submitted}


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
