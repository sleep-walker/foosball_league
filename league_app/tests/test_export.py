"""Tests for export functions — pure functions, no DB."""

import json
from uuid import uuid4

from league_app.domain import entities as e
from league_app.engine.standings import GameResult, MatchResult, StandingRow, compute_standings
from league_app.infra.export.json_export import export_tournament_json
from league_app.infra.export.csv_export import export_standings_csv, export_matches_csv

P1, P2 = uuid4(), uuid4()
T_ID, S_ID = uuid4(), uuid4()


def _make_fixtures():
    tournament = e.Tournament(
        uuid=T_ID, owner_id=uuid4(), date="2026-04-12",
        name="Test Cup", player_mode="singles", status="finished",
        registrations=[
            e.TournamentRegistration(tournament_id=T_ID, player_id=P1),
            e.TournamentRegistration(tournament_id=T_ID, player_id=P2),
        ],
    )
    stages = [e.Stage(uuid=S_ID, tournament_id=T_ID, name="Group A", stage_type="group")]
    match = e.Match(
        uuid=uuid4(), tournament_id=T_ID, stage_id=S_ID,
        player_a_id=P1, player_b_id=P2, status="finished",
        best_of=1, round_number=1, winner_side="a",
        games=[e.Game(uuid=uuid4(), match_id=uuid4(), game_number=1, score_a=6, score_b=3)],
    )
    players = {
        P1: e.Player(uuid=P1, nickname="Alice"),
        P2: e.Player(uuid=P2, nickname="Bob"),
    }
    standings = compute_standings([
        MatchResult(P1, P2, [GameResult(6, 3)])
    ])
    return tournament, stages, [match], players, {S_ID: standings}


class TestJsonExport:
    def test_round_trip(self):
        t, stages, matches, players, standings = _make_fixtures()
        result = export_tournament_json(t, stages, matches, players, standings)
        data = json.loads(result)

        assert data["tournament"]["name"] == "Test Cup"
        assert len(data["players"]) == 2
        assert len(data["matches"]) == 1
        assert data["matches"][0]["games"][0]["score_a"] == 6
        assert len(data["stages"]) == 1
        assert len(data["stages"][0]["standings"]) == 2
        assert data["stages"][0]["standings"][0]["nickname"] == "Alice"
        assert data["export_version"] == "1.0"


class TestCsvExport:
    def test_standings_csv(self):
        t, stages, matches, players, standings = _make_fixtures()
        csv_text = export_standings_csv(stages, standings, players)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 3  # header + 2 players
        assert "Alice" in lines[1]
        assert "Bob" in lines[2]

    def test_matches_csv(self):
        t, stages, matches, players, standings = _make_fixtures()
        csv_text = export_matches_csv(matches, players)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2  # header + 1 match
        assert "6:3" in lines[1]
        assert "Alice" in lines[1]
        assert "Bob" in lines[1]


class TestEmptyExport:
    def test_empty_tournament(self):
        t = e.Tournament(uuid=uuid4(), owner_id=uuid4(), date="2026-04-12")
        result = export_tournament_json(t, [], [], {})
        data = json.loads(result)
        assert data["matches"] == []
        assert data["players"] == []
