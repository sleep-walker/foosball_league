"""Public (unauthenticated) read-only endpoints.

These are designed for TV screens, projectors, and spectator devices.
No sensitive data is exposed — only tournament status, standings, bracket,
and current round info.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.tournaments import crud as tournaments_crud
from league_app.api.users.users import current_user_optional
from league_app.domain.tournament_service import TournamentService
from .qr import router as qr_router
from .export import router as export_router

router = APIRouter(tags=["public"])


def _get_svc(session: AsyncSession = Depends(get_session_for_api)) -> TournamentService:
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


# --- Response models (minimal, no sensitive data) ---

class PublicPlayerInfo(BaseModel):
    uuid: UUID
    nickname: str


class PublicRegistration(BaseModel):
    player: PublicPlayerInfo
    seed: int | None = None


class PublicStageInfo(BaseModel):
    uuid: UUID
    name: str | None = None
    stage_type: str
    ordering: int
    status: str = "preparing"
    rules: dict | None = None


class PublicTournamentInfo(BaseModel):
    uuid: UUID
    name: str | None
    date: str
    location: str | None
    player_mode: str
    status: str
    player_count: int
    is_registration_open: bool = True
    players: list[PublicPlayerInfo] = []
    applicants: list[PublicPlayerInfo] = []
    stages: list[PublicStageInfo] = []


class PublicStandingRow(BaseModel):
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


class PublicMatchInfo(BaseModel):
    uuid: UUID
    round_number: int
    bracket_position: int | None = None
    table_number: int | None = None
    status: str
    player_a_name: str | None = None
    player_b_name: str | None = None
    team_a_name: str | None = None
    team_b_name: str | None = None
    score_a: int | None = None
    score_b: int | None = None
    best_of: int
    games: list[dict] = []


# --- Endpoints ---

@router.get("/tournaments/{tournament_id}", response_model=PublicTournamentInfo)
async def get_tournament_info(
    tournament_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
):
    t = await tournaments_crud.get_tournament(session, tournament_id)
    if t is None or t.is_deleted:
        raise HTTPException(status_code=404, detail="Tournament not found")
    players = []
    for reg in t.registrations:
        if reg.player:
            players.append(PublicPlayerInfo(
                uuid=reg.player.uuid, nickname=reg.player.nickname or "—",
            ))
    applicant_infos = [
        PublicPlayerInfo(uuid=a.uuid, nickname=a.nickname or "—")
        for a in t.applicants
    ]
    stage_infos = [
        PublicStageInfo(
            uuid=s.uuid, name=s.name, stage_type=s.stage_type,
            ordering=s.ordering, status=s.status, rules=s.rules,
        )
        for s in (t.stages or [])
    ]
    return PublicTournamentInfo(
        uuid=t.uuid, name=t.name, date=t.date, location=t.location,
        player_mode=t.player_mode, status=t.status,
        player_count=len(t.registrations),
        is_registration_open=t.is_registration_open,
        players=players,
        applicants=applicant_infos,
        stages=stage_infos,
    )


@router.get(
    "/tournaments/{tournament_id}/stages/{stage_id}/standings",
    response_model=list[PublicStandingRow],
)
async def get_public_standings(
    tournament_id: UUID,
    stage_id: UUID,
    svc: TournamentService = Depends(_get_svc),
    session: AsyncSession = Depends(get_session_for_api),
):
    """Public standings for a group stage — visible on TV/projector."""
    from league_app.domain.tournament_service import TournamentError
    try:
        rows = await svc.get_stage_standings(tournament_id, stage_id)
    except TournamentError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Resolve nicknames — participant_id can be a player UUID or a team UUID
    from league_app.api.players import model as player_orm
    from league_app.api.teams import model as team_orm
    nickname_map: dict[UUID, str] = {}
    for r in rows:
        if r.participant_id not in nickname_map:
            # Try player first
            p = await session.get(player_orm.Player, r.participant_id)
            if p:
                nickname_map[r.participant_id] = p.nickname or "—"
            else:
                # Must be a team — resolve both player names
                t = await session.get(team_orm.Team, r.participant_id)
                if t:
                    p1 = await session.get(player_orm.Player, t.player_1_id) if t.player_1_id else None
                    p2 = await session.get(player_orm.Player, t.player_2_id) if t.player_2_id else None
                    n1 = p1.nickname if p1 else "?"
                    n2 = p2.nickname if p2 else "?"
                    nickname_map[r.participant_id] = f"{n1} & {n2}"
                else:
                    nickname_map[r.participant_id] = str(r.participant_id)[:8]

    return [
        PublicStandingRow(
            participant_id=r.participant_id,
            nickname=nickname_map.get(r.participant_id),
            wins=r.wins, draws=r.draws, losses=r.losses,
            goals_for=r.goals_for, goals_against=r.goals_against,
            goal_difference=r.goal_difference, points=r.points,
            matches_played=r.matches_played,
            sets_won=r.sets_won, sets_lost=r.sets_lost,
            sets_difference=r.sets_difference,
        )
        for r in rows
    ]


@router.get(
    "/tournaments/{tournament_id}/stages/{stage_id}/matches",
    response_model=list[PublicMatchInfo],
)
async def get_public_matches(
    tournament_id: UUID,
    stage_id: UUID,
    round_number: int | None = None,
    session: AsyncSession = Depends(get_session_for_api),
):
    """Public match list for a stage — shows bracket or round matches."""
    from league_app.api.matches import crud as matches_crud
    from league_app.api.players import model as player_orm

    matches = await matches_crud.get_matches_by_stage(session, stage_id)
    if round_number is not None:
        matches = [m for m in matches if m.round_number == round_number]

    from league_app.api.teams import model as team_orm

    result = []
    for m in matches:
        if m.is_deleted:
            continue
        pa = await session.get(player_orm.Player, m.player_a_id) if m.player_a_id else None
        pb = await session.get(player_orm.Player, m.player_b_id) if m.player_b_id else None

        # Team names for doubles
        team_a_name = team_b_name = None
        if m.team_a_id:
            ta = await session.get(team_orm.Team, m.team_a_id)
            if ta:
                p1 = await session.get(player_orm.Player, ta.player_1_id) if ta.player_1_id else None
                p2 = await session.get(player_orm.Player, ta.player_2_id) if ta.player_2_id else None
                team_a_name = f"{p1.nickname if p1 else '?'} & {p2.nickname if p2 else '?'}"
        if m.team_b_id:
            tb = await session.get(team_orm.Team, m.team_b_id)
            if tb:
                p1 = await session.get(player_orm.Player, tb.player_1_id) if tb.player_1_id else None
                p2 = await session.get(player_orm.Player, tb.player_2_id) if tb.player_2_id else None
                team_b_name = f"{p1.nickname if p1 else '?'} & {p2.nickname if p2 else '?'}"

        # Compute score from games
        games = m.games or []
        score_a = sum(g.score_a or 0 for g in games) if games else None
        score_b = sum(g.score_b or 0 for g in games) if games else None

        result.append(PublicMatchInfo(
            uuid=m.uuid, round_number=m.round_number,
            bracket_position=m.bracket_position, table_number=m.table_number,
            status=m.status, best_of=m.best_of,
            player_a_name=pa.nickname if pa else None,
            player_b_name=pb.nickname if pb else None,
            team_a_name=team_a_name, team_b_name=team_b_name,
            score_a=score_a, score_b=score_b,
            games=[{"score_a": g.score_a, "score_b": g.score_b, "number": g.game_number}
                   for g in games],
        ))
    return result



# --- League standings (public) ---


class PublicLeagueInfo(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    scoring_type: str
    members: list[PublicPlayerInfo] = []
    tournament_count: int = 0


@router.get("/leagues/{league_id}", response_model=PublicLeagueInfo)
async def public_league_info(
    league_id: UUID,
    session: AsyncSession = Depends(get_session_for_api),
):
    """Public league info — members and tournament count."""
    from league_app.api.leagues import crud as leagues_crud
    league = await leagues_crud.get_league(session, league_id)
    if league is None or league.is_deleted:
        raise HTTPException(status_code=404, detail="League not found")

    members = [
        PublicPlayerInfo(uuid=p.uuid, nickname=p.nickname or "—")
        for p in league.members
    ]
    return PublicLeagueInfo(
        uuid=league.uuid, name=league.name, description=league.description,
        scoring_type=league.scoring_type,
        members=members,
        tournament_count=len([t for t in league.tournaments if not t.is_deleted]),
    )


class SelfRegisterRequest(BaseModel):
    nickname: str
    first_name: str | None = None
    last_name: str | None = None
    token: str  # registration_token from QR code (proves physical presence)


class SelfRegisterResponse(BaseModel):
    player_id: str
    nickname: str
    message: str


@router.post(
    "/tournaments/{tournament_id}/register",
    response_model=SelfRegisterResponse,
)
async def self_register(
    tournament_id: UUID,
    body: SelfRegisterRequest,
    session: AsyncSession = Depends(get_session_for_api),
    user=Depends(current_user_optional),
):
    """Public self-registration — player scans QR, enters nickname.

    Two modes:
      * Anonymous (no Authorization header): always creates a brand-new Player
        with ``user_id=NULL``. A collision on ``nickname`` with ANY existing
        Player is rejected with 409 — anonymous callers must not be able to
        take over an existing identity.
      * Authenticated (valid token): always creates a new Player linked to
        ``user.id``. Nickname collisions with other users' Players are
        irrelevant (a single User may have multiple Players, one per league
        or persona). If this exact User already has a Player with this
        nickname, that Player is reused (idempotency).
    """
    from league_app.api.players import model as player_orm

    t = await tournaments_crud.get_tournament(session, tournament_id)
    if t is None or t.is_deleted:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not t.is_registration_open:
        raise HTTPException(status_code=400, detail="Registration is closed")

    # Validate token (proves player scanned QR at the venue)
    if not body.token or body.token != t.registration_token:
        raise HTTPException(status_code=403, detail="Invalid registration token")

    nickname = body.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname is required")

    from sqlalchemy import select

    if user is None:
        # Anonymous path. Three sub-cases for the existing Player with
        # this nickname:
        #   a) An unclaimed Player already applicant/registered in *this*
        #      tournament → reuse it (idempotent retry of the same scan).
        #   b) Any other Player with this nickname → 409. Never adopt
        #      an existing identity (would enable impersonation).
        #   c) No clash → create a fresh unclaimed Player.
        clash = await session.scalar(
            select(player_orm.Player).where(
                player_orm.Player.nickname == nickname,
                player_orm.Player.is_deleted == False,  # noqa: E712
            )
        )
        if clash is not None:
            reg_ids = {r.player_id for r in t.registrations}
            already_in_tournament = (
                clash in t.applicants or clash.uuid in reg_ids
            )
            if clash.user_id is None and already_in_tournament:
                player = clash  # idempotent retry
            else:
                raise HTTPException(
                    status_code=409,
                    detail="Nickname is taken — please pick a different one",
                )
        else:
            player = player_orm.Player(
                nickname=nickname,
                first_name=body.first_name,
                last_name=body.last_name,
            )
            session.add(player)
            await session.flush()
    else:
        # Authenticated path: reuse the user's own Player with this nickname
        # (idempotency) or create a new one bound to the user.
        existing_mine = await session.scalar(
            select(player_orm.Player).where(
                player_orm.Player.user_id == user.id,
                player_orm.Player.nickname == nickname,
                player_orm.Player.is_deleted == False,  # noqa: E712
            )
        )
        if existing_mine is not None:
            player = existing_mine
        else:
            player = player_orm.Player(
                nickname=nickname,
                first_name=body.first_name,
                last_name=body.last_name,
                user_id=user.id,
            )
            session.add(player)
            await session.flush()

    # Check if already an applicant
    if player in t.applicants:
        await session.commit()
        return SelfRegisterResponse(
            player_id=str(player.uuid), nickname=player.nickname,
            message="Already registered — you're on the list!",
        )

    # Check if already a registered player
    reg_ids = {r.player_id for r in t.registrations}
    if player.uuid in reg_ids:
        await session.commit()
        return SelfRegisterResponse(
            player_id=str(player.uuid), nickname=player.nickname,
            message="You're already registered for this tournament!",
        )

    # Add as applicant
    t.applicants.append(player)
    await session.flush()
    await session.commit()

    # Notify organizer via WebSocket
    from league_app.realtime.hub import event_hub, Event
    await event_hub.publish(Event(
        "applicant_registered", tournament_id,
        {"player_id": str(player.uuid), "nickname": player.nickname},
    ))

    return SelfRegisterResponse(
        player_id=str(player.uuid), nickname=player.nickname,
        message="You're on the list! The organizer will confirm your registration.",
    )


# Include sub-routers (imported at top of module)
router.include_router(qr_router)
router.include_router(export_router)