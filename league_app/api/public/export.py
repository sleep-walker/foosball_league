"""Export endpoint for tournament data."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.domain.tournament_service import TournamentService
from league_app.domain import entities as e
from league_app.infra.export.json_export import export_tournament_json
from league_app.infra.export.csv_export import export_standings_csv, export_matches_csv

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


async def _load_export_data(
    tournament_id: UUID, session: AsyncSession, svc: TournamentService
):
    """Load all data needed for export."""
    t_entity = await svc._tournaments.get(tournament_id)
    if t_entity is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    stages = await svc._stages.list_by_tournament(tournament_id)
    matches = await svc._matches.list_by_tournament(tournament_id)

    # Load players
    player_ids = set()
    for r in t_entity.registrations:
        player_ids.add(r.player_id)
    for m in matches:
        if m.player_a_id:
            player_ids.add(m.player_a_id)
        if m.player_b_id:
            player_ids.add(m.player_b_id)

    players: dict[UUID, e.Player] = {}
    for pid in player_ids:
        p = await svc._players.get(pid)
        if p:
            players[pid] = p

    # Compute standings per stage
    standings_by_stage = {}
    for stage in stages:
        if stage.stage_type == "group":
            from league_app.domain.tournament_service import TournamentError
            try:
                rows = await svc.get_stage_standings(tournament_id, stage.uuid)
                standings_by_stage[stage.uuid] = rows
            except TournamentError:
                pass

    return t_entity, stages, matches, players, standings_by_stage


@router.get("/tournaments/{tournament_id}/export")
async def export_tournament(
    tournament_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session_for_api),
    svc: TournamentService = Depends(_get_svc),
):
    """Export tournament data.

    Query params:
    - ``format=json`` — full JSON export
    - ``format=csv_standings`` — standings CSV
    - ``format=csv_matches`` — matches CSV
    """
    t, stages, matches, players, standings = await _load_export_data(
        tournament_id, session, svc
    )

    if format == "json":
        content = export_tournament_json(t, stages, matches, players, standings)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{t.name or t.uuid}_export.json"'},
        )

    if format == "csv_standings":
        content = export_standings_csv(stages, standings, players)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{t.name or t.uuid}_standings.csv"'},
        )

    if format == "csv_matches":
        content = export_matches_csv(matches, players)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{t.name or t.uuid}_matches.csv"'},
        )

    raise HTTPException(
        status_code=400,
        detail="Invalid format. Use 'json', 'csv_standings', or 'csv_matches'.",
    )
