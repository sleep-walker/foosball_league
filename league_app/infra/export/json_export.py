"""Export tournament data as JSON.

Produces a self-contained JSON document with all tournament information:
settings, players, stages, matches, games, standings.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from league_app.domain import entities as e
from league_app.engine.standings import StandingRow


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def export_tournament_json(
    tournament: e.Tournament,
    stages: list[e.Stage],
    matches: list[e.Match],
    players: dict[UUID, e.Player],
    standings_by_stage: dict[UUID, list[StandingRow]] | None = None,
) -> str:
    """Export full tournament data as a JSON string."""
    standings_by_stage = standings_by_stage or {}

    data = {
        "export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tournament": {
            "uuid": str(tournament.uuid),
            "name": tournament.name,
            "date": tournament.date,
            "location": tournament.location,
            "player_mode": tournament.player_mode,
            "status": tournament.status,
            "settings": tournament.settings,
            "entry_fee": tournament.entry_fee,
        },
        "players": [
            {
                "uuid": str(p.uuid),
                "nickname": p.nickname,
                "first_name": p.first_name,
                "last_name": p.last_name,
            }
            for p in players.values()
        ],
        "registrations": [
            {
                "player_id": str(r.player_id),
                "paid": r.paid,
                "seed": r.seed,
            }
            for r in tournament.registrations
        ],
        "stages": [
            {
                "uuid": str(s.uuid),
                "name": s.name,
                "stage_type": s.stage_type,
                "ordering": s.ordering,
                "rules": s.rules,
                "standings": [
                    {
                        "participant_id": str(row.participant_id),
                        "nickname": players[row.participant_id].nickname
                        if row.participant_id in players else None,
                        "wins": row.wins,
                        "draws": row.draws,
                        "losses": row.losses,
                        "points": row.points,
                        "goals_for": row.goals_for,
                        "goals_against": row.goals_against,
                        "goal_difference": row.goal_difference,
                    }
                    for row in standings_by_stage.get(s.uuid, [])
                ],
            }
            for s in stages
        ],
        "matches": [
            {
                "uuid": str(m.uuid),
                "stage_id": str(m.stage_id) if m.stage_id else None,
                "round_number": m.round_number,
                "bracket_position": m.bracket_position,
                "table_number": m.table_number,
                "best_of": m.best_of,
                "status": m.status,
                "winner_side": m.winner_side,
                "player_a": _player_ref(m.player_a_id, players),
                "player_b": _player_ref(m.player_b_id, players),
                "games": [
                    {
                        "game_number": g.game_number,
                        "score_a": g.score_a,
                        "score_b": g.score_b,
                    }
                    for g in m.games
                ],
            }
            for m in matches
        ],
    }

    return json.dumps(data, cls=_Encoder, indent=2, ensure_ascii=False)


def _player_ref(player_id: UUID | None, players: dict[UUID, e.Player]) -> dict | None:
    if player_id is None:
        return None
    p = players.get(player_id)
    return {"uuid": str(player_id), "nickname": p.nickname if p else None}
