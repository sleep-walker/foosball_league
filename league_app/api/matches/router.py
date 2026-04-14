from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.users.model import User
from league_app.api.users.users import current_active_verified_user
from . import crud, schema

router = APIRouter(tags=["matches"])


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


@router.patch("/{match_id}/score")
async def submit_match_score(
    match_id: UUID,
    data: schema.ScoreSubmit,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Quick score entry — creates/updates a single game and finishes the match.

    Allowed: tournament owner, superuser, or any player participating in the match.
    """
    match = await crud.get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status == "finished":
        raise HTTPException(status_code=400, detail="Match already finished")

    # Authorization: check if user is organizer or participant
    if not user.is_superuser and match.owner_id != user.id:
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
            # Check direct player participation (singles)
            if player.uuid in (match.player_a_id, match.player_b_id):
                allowed = True
            # Check team participation (doubles)
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

    # Create or update game 1
    games = await crud.get_games_by_match(session, match_id)
    if games:
        game = games[0]
        await crud.update_game(session, game.uuid, schema.GameUpdate(
            score_a=data.score_a, score_b=data.score_b, is_finished=True,
        ))
    else:
        await crud.create_game(session, match_id, schema.GameCreate(
            game_number=1, score_a=data.score_a, score_b=data.score_b,
            is_finished=True,
        ))

    # Determine winner and finish match
    winner = "a" if data.score_a > data.score_b else ("b" if data.score_b > data.score_a else "draw")
    await crud.update_match(session, match_id, schema.MatchUpdate(
        status="finished", winner_side=winner,
    ))

    from league_app.realtime.hub import event_hub, Event
    await event_hub.publish(Event("score_updated", match.tournament_id, {
        "match_id": str(match_id),
        "score_a": data.score_a, "score_b": data.score_b,
    }))

    return {"message": "Score saved", "score_a": data.score_a, "score_b": data.score_b}


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
