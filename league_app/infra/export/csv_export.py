"""Export tournament data as CSV.

Produces two CSV documents:
- **standings.csv** — one row per participant per stage
- **matches.csv** — one row per match with game scores
"""

from __future__ import annotations

import csv
import io
from uuid import UUID

from league_app.domain import entities as e
from league_app.engine.standings import StandingRow


def export_standings_csv(
    stages: list[e.Stage],
    standings_by_stage: dict[UUID, list[StandingRow]],
    players: dict[UUID, e.Player],
) -> str:
    """Export standings as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "stage", "rank", "player_id", "nickname",
        "wins", "draws", "losses", "points",
        "goals_for", "goals_against", "goal_difference",
        "matches_played",
        "sets_won", "sets_lost", "sets_difference",
    ])

    for stage in stages:
        rows = standings_by_stage.get(stage.uuid, [])
        for rank, row in enumerate(rows, 1):
            p = players.get(row.participant_id)
            writer.writerow([
                stage.name, rank, str(row.participant_id),
                p.nickname if p else "",
                row.wins, row.draws, row.losses, row.points,
                row.goals_for, row.goals_against, row.goal_difference,
                row.matches_played,
                row.sets_won, row.sets_lost, row.sets_difference,
            ])

    return buf.getvalue()


def export_matches_csv(
    matches: list[e.Match],
    players: dict[UUID, e.Player],
) -> str:
    """Export matches as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "match_id", "round", "bracket_pos", "table",
        "player_a", "player_b", "status", "winner_side",
        "best_of", "games",
    ])

    for m in matches:
        pa = players.get(m.player_a_id) if m.player_a_id else None
        pb = players.get(m.player_b_id) if m.player_b_id else None
        games_str = " | ".join(
            f"{g.score_a}:{g.score_b}" for g in m.games
        )
        writer.writerow([
            str(m.uuid), m.round_number, m.bracket_position or "",
            m.table_number or "",
            pa.nickname if pa else "", pb.nickname if pb else "",
            m.status, m.winner_side or "",
            m.best_of, games_str,
        ])

    return buf.getvalue()
