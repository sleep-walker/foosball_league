"""Import tournament data from kickertool JSON format.

Kickertool exports a JSON with:
- tournament info (name, status, currentRound)
- settings (mode, tableCount, goalsToWin, matchesToWin, pointsForWinner, ...)
- matches (roundNumber, scoreHome, scoreVisiting, homeTeam, visitingTeam)
- playtables (tableNumber, status)
- players embedded in team objects (firstName, lastName, uid)

This module parses that format and produces domain entities ready for
persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from league_app.domain import entities as e


@dataclass
class KickertoolImportResult:
    """Result of importing a kickertool JSON."""

    tournament: e.Tournament
    players: list[e.Player]
    matches: list[e.Match]
    tables: list[e.GameTable]
    warnings: list[str] = field(default_factory=list)


def _parse_uuid(val: Any) -> UUID:
    """Parse a UUID from string, or generate a new one if invalid."""
    if val is None:
        return uuid4()
    try:
        return UUID(str(val))
    except ValueError:
        return uuid4()


def _parse_player(data: dict, seen: dict[str, e.Player]) -> e.Player:
    """Parse a player from kickertool PlayerDTO. Deduplicates by uid."""
    uid = str(data.get("uid", ""))
    if uid in seen:
        return seen[uid]

    player = e.Player(
        uuid=_parse_uuid(data.get("uid")),
        nickname=f"{data.get('firstName', '')} {data.get('lastName', '')}".strip() or "Unknown",
        first_name=data.get("firstName"),
        last_name=data.get("lastName"),
    )
    seen[uid] = player
    return player


def import_kickertool_json(
    json_data: str | dict,
    owner_id: UUID,
    stage_id: UUID | None = None,
) -> KickertoolImportResult:
    """Import a kickertool tournament JSON.

    Args:
        json_data: Raw JSON string or parsed dict.
        owner_id: UUID of the user who will own the imported tournament.
        stage_id: Optional stage UUID to assign matches to.

    Returns:
        KickertoolImportResult with domain entities.
    """
    if isinstance(json_data, str):
        raw = json.loads(json_data)
    else:
        raw = json_data

    # Kickertool wraps in {"dtoStatus": "SUCCESS", "dtoValue": {...}}
    if "dtoValue" in raw:
        raw = raw["dtoValue"]

    warnings: list[str] = []
    tournament_id = _parse_uuid(raw.get("uid"))

    # Parse settings
    settings_raw = raw.get("settings", {})
    settings_dict = {
        "goals_to_win": settings_raw.get("goalsToWin", 6),
        "matches_to_win": settings_raw.get("matchesToWin", 1),
        "points_for_win": settings_raw.get("pointsForWinner", 2),
        "points_for_draw": settings_raw.get("pointsForDraw", 1),
        "table_count": settings_raw.get("tableCount", 2),
        "random_rounds": settings_raw.get("randomRounds", 2),
        "fixed_teams": settings_raw.get("fixedTeams", False),
    }

    # Map kickertool status
    status_map = {"PREPARING": "registration", "RUNNING": "running", "FINISHED": "finished"}
    status = status_map.get(str(raw.get("status", "")), "registration")

    tournament = e.Tournament(
        uuid=tournament_id, owner_id=owner_id,
        date="", name=raw.get("name", "Imported Tournament"),
        status=status, settings=settings_dict, player_mode="doubles",
    )

    # Parse players (deduplicated)
    seen_players: dict[str, e.Player] = {}
    matches: list[e.Match] = []

    for match_raw in raw.get("matches", []):
        home = match_raw.get("homeTeam", {})
        away = match_raw.get("visitingTeam", {})

        # Parse players from teams
        player_a = _parse_player(home.get("player1", {}), seen_players) if home.get("player1") else None
        player_b = _parse_player(away.get("player1", {}), seen_players) if away.get("player1") else None

        # Skip dummy matches
        if player_a is None or player_b is None:
            warnings.append(f"Skipped match {match_raw.get('matchID')} — missing player")
            continue

        ms_map = {"PLANNED": "scheduled", "ONGOING": "in_progress", "FINISHED": "finished"}
        m_status = ms_map.get(str(match_raw.get("status", "")), "scheduled")

        score_a = match_raw.get("scoreHome", 0)
        score_b = match_raw.get("scoreVisiting", 0)

        match_uuid = _parse_uuid(match_raw.get("matchID"))
        match = e.Match(
            uuid=match_uuid, tournament_id=tournament_id, stage_id=stage_id,
            owner_id=owner_id, round_number=match_raw.get("roundNumber", 1),
            best_of=settings_raw.get("matchesToWin", 1) * 2 - 1,
            player_a_id=player_a.uuid, player_b_id=player_b.uuid,
            status=m_status,
            winner_side="a" if (m_status == "finished" and score_a > score_b) else
                        ("b" if (m_status == "finished" and score_b > score_a) else None),
            games=[e.Game(
                uuid=uuid4(), match_id=match_uuid, game_number=1,
                score_a=score_a, score_b=score_b,
                is_finished=(m_status == "finished"),
            )] if score_a > 0 or score_b > 0 else [],
        )
        matches.append(match)

    # Parse tables
    tables: list[e.GameTable] = []
    for pt in raw.get("playtables", []):
        gt_status = {"INACTIVE": "inactive", "ACTIVE": "active", "IN_USE": "in_use"}
        tables.append(e.GameTable(
            uuid=uuid4(), tournament_id=tournament_id,
            name=f"Table {pt.get('tableNumber', 0)}",
            number=pt.get("tableNumber", 0),
            status=gt_status.get(str(pt.get("status", "")), "active"),
        ))

    # Build registrations
    tournament.registrations = [
        e.TournamentRegistration(tournament_id=tournament_id, player_id=p.uuid)
        for p in seen_players.values()
    ]

    return KickertoolImportResult(
        tournament=tournament,
        players=list(seen_players.values()),
        matches=matches,
        tables=tables,
        warnings=warnings,
    )
