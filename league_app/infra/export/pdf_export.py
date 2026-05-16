"""PDF export for tournament results.

Uses a simple HTML → string approach that can be rendered to PDF via
weasyprint or a similar library.  If no PDF library is available,
falls back to returning HTML that the client can print.

Pure functions — no database access.
"""

from __future__ import annotations

from uuid import UUID

from league_app.domain import entities as e
from league_app.engine.standings import StandingRow


def _html_standings_table(
    stage_name: str,
    rows: list[StandingRow],
    players: dict[UUID, e.Player],
) -> str:
    """Generate an HTML standings table."""
    html = f'<h2>{stage_name}</h2>\n<table border="1" cellpadding="4" cellspacing="0">\n'
    html += "<tr><th>#</th><th>Player</th><th>W</th><th>D</th><th>L</th>"
    html += "<th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr>\n"

    for rank, row in enumerate(rows, 1):
        p = players.get(row.participant_id)
        name = p.nickname if p else str(row.participant_id)[:8]
        html += (
            f"<tr><td>{rank}</td><td>{name}</td>"
            f"<td>{row.wins}</td><td>{row.draws}</td><td>{row.losses}</td>"
            f"<td>{row.goals_for}</td><td>{row.goals_against}</td>"
            f"<td>{row.goal_difference}</td><td>{row.points}</td></tr>\n"
        )

    html += "</table>\n"
    return html


def _html_matches_table(
    matches: list[e.Match],
    players: dict[UUID, e.Player],
) -> str:
    """Generate an HTML matches table."""
    html = '<h2>Matches</h2>\n<table border="1" cellpadding="4" cellspacing="0">\n'
    html += "<tr><th>Round</th><th>Player A</th><th>Player B</th>"
    html += "<th>Score</th><th>Status</th></tr>\n"

    for m in matches:
        pa = players.get(m.player_a_id) if m.player_a_id else None
        pb = players.get(m.player_b_id) if m.player_b_id else None
        scores = " | ".join(f"{g.score_a}:{g.score_b}" for g in m.games)
        html += (
            f"<tr><td>{m.round_number}</td>"
            f"<td>{pa.nickname if pa else '—'}</td>"
            f"<td>{pb.nickname if pb else '—'}</td>"
            f"<td>{scores or '—'}</td>"
            f"<td>{m.status}</td></tr>\n"
        )

    html += "</table>\n"
    return html


def export_tournament_html(
    tournament: e.Tournament,
    stages: list[e.Stage],
    matches: list[e.Match],
    players: dict[UUID, e.Player],
    standings_by_stage: dict[UUID, list[StandingRow]] | None = None,
) -> str:
    """Export tournament results as a printable HTML document."""
    standings_by_stage = standings_by_stage or {}

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{tournament.name or 'Tournament Results'}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; }}
  table {{ border-collapse: collapse; margin-bottom: 20px; }}
  th {{ background-color: #333; color: white; }}
  tr:nth-child(even) {{ background-color: #f2f2f2; }}
  h1 {{ color: #333; }}
</style></head><body>
<h1>{tournament.name or 'Tournament Results'}</h1>
<p><strong>Date:</strong> {tournament.date}</p>
<p><strong>Location:</strong> {tournament.location or '—'}</p>
<p><strong>Mode:</strong> {tournament.player_mode}</p>
<p><strong>Players:</strong> {len(tournament.registrations)}</p>
"""

    for stage in stages:
        rows = standings_by_stage.get(stage.uuid, [])
        if rows:
            html += _html_standings_table(stage.name, rows, players)

    stage_matches = {s.uuid: [] for s in stages}
    for m in matches:
        if m.stage_id in stage_matches:
            stage_matches[m.stage_id].append(m)
        else:
            stage_matches.setdefault(None, []).append(m)

    for stage in stages:
        sm = stage_matches.get(stage.uuid, [])
        if sm:
            html += f"<h2>{stage.name} — Matches</h2>\n"
            html += _html_matches_table(sm, players)

    html += "</body></html>"
    return html


def export_tournament_pdf(
    tournament: e.Tournament,
    stages: list[e.Stage],
    matches: list[e.Match],
    players: dict[UUID, e.Player],
    standings_by_stage: dict[UUID, list[StandingRow]] | None = None,
) -> bytes:
    """Export tournament results as PDF bytes.

    Requires ``weasyprint`` to be installed.
    Raises ImportError if not available.
    """
    html = export_tournament_html(
        tournament, stages, matches, players, standings_by_stage
    )
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()
