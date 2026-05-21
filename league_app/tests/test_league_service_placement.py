"""Unit tests for LeagueService._placement_standings.

These tests stub out repositories and TournamentService so we can focus
on the placement-aggregation logic itself (ordering, stage selection,
filtering of unfinished tournaments, erosion config plumbing) without
spinning up the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from league_app.domain.entities import Stage, Tournament
from league_app.domain.entities_league import League
from league_app.domain.league_service import LeagueService
from league_app.engine.standings import StandingRow


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeLeagueRepo:
    league: League

    async def get(self, uuid: UUID) -> League | None:
        return self.league if self.league.uuid == uuid else None


@dataclass
class _FakeTournamentRepo:
    by_league: dict[UUID, list[Tournament]] = field(default_factory=dict)

    async def list_by_league(self, league_id: UUID) -> list[Tournament]:
        return list(self.by_league.get(league_id, []))


@dataclass
class _FakeStageRepo:
    by_tournament: dict[UUID, list[Stage]] = field(default_factory=dict)

    async def list_by_tournament(self, tournament_id: UUID) -> list[Stage]:
        return list(self.by_tournament.get(tournament_id, []))


@dataclass
class _FakeTournamentService:
    # Keyed by (tournament_id, stage_id) -> list of standings rows
    # already sorted by final placement (index 0 == place 1).
    standings_by_stage: dict[tuple[UUID, UUID], list[StandingRow]] = field(
        default_factory=dict
    )

    async def get_stage_standings(
        self, tournament_id: UUID, stage_id: UUID
    ) -> list[StandingRow]:
        return list(self.standings_by_stage.get((tournament_id, stage_id), []))


def _make_league(scoring_config: dict | None = None) -> League:
    return League(
        uuid=uuid4(),
        name="Test league",
        owner_id=uuid4(),
        scoring_type="placement_points",
        scoring_config=scoring_config
        or {"1": 10, "2": 7, "3": 5, "4": 3, "default": 1},
    )


def _make_tournament(
    *,
    league_id: UUID,
    date: str,
    status: str = "finished",
) -> Tournament:
    return Tournament(
        uuid=uuid4(),
        owner_id=uuid4(),
        date=date,
        league_id=league_id,
        status=status,
    )


def _make_stage(
    *,
    tournament_id: UUID,
    ordering: int = 0,
    status: str = "finished",
) -> Stage:
    return Stage(
        uuid=uuid4(),
        tournament_id=tournament_id,
        name=f"Stage {ordering}",
        ordering=ordering,
        status=status,
    )


def _row(participant_id: UUID, wins: int = 0) -> StandingRow:
    # `wins` is a cheap way to inject a stable per-row identity that
    # the engine ignores — placements come from list order alone.
    return StandingRow(participant_id=participant_id, wins=wins)


def _build_service(
    league: League,
    tournament_repo: _FakeTournamentRepo,
    stage_repo: _FakeStageRepo,
    tournament_service: _FakeTournamentService,
) -> LeagueService:
    return LeagueService(
        leagues=_FakeLeagueRepo(league=league),
        tournaments=tournament_repo,  # type: ignore[arg-type]
        matches=None,  # type: ignore[arg-type]  # unused for placement scoring
        stages=stage_repo,  # type: ignore[arg-type]
        tournament_service=tournament_service,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_league_returns_empty_standings() -> None:
    league = _make_league()
    svc = _build_service(
        league,
        _FakeTournamentRepo(),
        _FakeStageRepo(),
        _FakeTournamentService(),
    )

    result = await svc.get_standings(league.uuid)

    assert result == []


@pytest.mark.asyncio
async def test_unfinished_tournaments_are_skipped() -> None:
    league = _make_league()
    running = _make_tournament(
        league_id=league.uuid, date="2025-01-01", status="running"
    )
    registration = _make_tournament(
        league_id=league.uuid, date="2025-02-01", status="registration"
    )

    svc = _build_service(
        league,
        _FakeTournamentRepo(by_league={league.uuid: [running, registration]}),
        _FakeStageRepo(),
        _FakeTournamentService(),
    )

    result = await svc.get_standings(league.uuid)
    assert result == []


@pytest.mark.asyncio
async def test_single_finished_singles_tournament() -> None:
    """One finished tournament -> placement points map directly to scores."""
    league = _make_league()
    tournament = _make_tournament(league_id=league.uuid, date="2025-03-01")
    stage = _make_stage(tournament_id=tournament.uuid, ordering=0)

    alice, bob, carol = uuid4(), uuid4(), uuid4()
    standings = [_row(alice), _row(bob), _row(carol)]

    svc = _build_service(
        league,
        _FakeTournamentRepo(by_league={league.uuid: [tournament]}),
        _FakeStageRepo(by_tournament={tournament.uuid: [stage]}),
        _FakeTournamentService(
            standings_by_stage={(tournament.uuid, stage.uuid): standings}
        ),
    )

    result = await svc.get_standings(league.uuid)

    # Scores come straight from config: 10 / 7 / 5 with weight 1.0.
    by_id = {r.participant_id: r.score for r in result}
    assert by_id[alice] == pytest.approx(10.0)
    assert by_id[bob] == pytest.approx(7.0)
    assert by_id[carol] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_multistage_uses_final_stage_only() -> None:
    """Group stage standings are ignored when the bracket is finished."""
    league = _make_league()
    tournament = _make_tournament(league_id=league.uuid, date="2025-04-01")
    group_stage = _make_stage(tournament_id=tournament.uuid, ordering=0)
    bracket_stage = _make_stage(tournament_id=tournament.uuid, ordering=1)

    alice, bob = uuid4(), uuid4()
    # Group stage has Alice first; bracket flips the placement.
    group_standings = [_row(alice), _row(bob)]
    bracket_standings = [_row(bob), _row(alice)]

    svc = _build_service(
        league,
        _FakeTournamentRepo(by_league={league.uuid: [tournament]}),
        _FakeStageRepo(
            by_tournament={tournament.uuid: [group_stage, bracket_stage]}
        ),
        _FakeTournamentService(
            standings_by_stage={
                (tournament.uuid, group_stage.uuid): group_standings,
                (tournament.uuid, bracket_stage.uuid): bracket_standings,
            }
        ),
    )

    result = await svc.get_standings(league.uuid)
    by_id = {r.participant_id: r.score for r in result}
    # Bracket says Bob wins -> Bob gets 10, Alice gets 7.
    assert by_id[bob] == pytest.approx(10.0)
    assert by_id[alice] == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_erosion_factor_decays_older_tournaments() -> None:
    """erosion_factor=1.0 means oldest tournament has weight ~0."""
    league = _make_league(
        {"1": 10, "2": 5, "default": 1, "erosion_factor": 1.0}
    )

    older = _make_tournament(league_id=league.uuid, date="2025-01-01")
    newer = _make_tournament(league_id=league.uuid, date="2025-06-01")
    stage_older = _make_stage(tournament_id=older.uuid)
    stage_newer = _make_stage(tournament_id=newer.uuid)

    alice, bob = uuid4(), uuid4()
    # In the older tournament Alice wins; in the newer one Bob wins.
    older_standings = [_row(alice), _row(bob)]
    newer_standings = [_row(bob), _row(alice)]

    svc = _build_service(
        league,
        _FakeTournamentRepo(by_league={league.uuid: [newer, older]}),  # unsorted on purpose
        _FakeStageRepo(
            by_tournament={
                older.uuid: [stage_older],
                newer.uuid: [stage_newer],
            }
        ),
        _FakeTournamentService(
            standings_by_stage={
                (older.uuid, stage_older.uuid): older_standings,
                (newer.uuid, stage_newer.uuid): newer_standings,
            }
        ),
    )

    result = await svc.get_standings(league.uuid)
    by_id = {r.participant_id: r.score for r in result}

    # With erosion_factor=1.0 the oldest tournament's weight is 0:
    # only the newer tournament counts. Bob (1st newer) = 10,
    # Alice (2nd newer) = 5; the older results are erased.
    assert by_id[bob] == pytest.approx(10.0)
    assert by_id[alice] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_tournaments_sorted_oldest_first_for_erosion() -> None:
    """Tournament order must follow chronological date regardless of
    repository return order; otherwise erosion would penalise the
    wrong entries."""
    league = _make_league(
        {"1": 10, "2": 5, "default": 1, "erosion_factor": 0.5}
    )

    t_old = _make_tournament(league_id=league.uuid, date="2025-01-01")
    t_new = _make_tournament(league_id=league.uuid, date="2025-12-01")
    s_old = _make_stage(tournament_id=t_old.uuid)
    s_new = _make_stage(tournament_id=t_new.uuid)

    alice = uuid4()
    # Alice wins both — score with erosion 0.5 should be:
    #   old weight = 0.5, new weight = 1.0
    #   total = 10 * 0.5 + 10 * 1.0 = 15.0
    standings = [_row(alice)]

    # Return newer first to ensure the service re-sorts internally.
    svc = _build_service(
        league,
        _FakeTournamentRepo(by_league={league.uuid: [t_new, t_old]}),
        _FakeStageRepo(
            by_tournament={t_old.uuid: [s_old], t_new.uuid: [s_new]}
        ),
        _FakeTournamentService(
            standings_by_stage={
                (t_old.uuid, s_old.uuid): standings,
                (t_new.uuid, s_new.uuid): standings,
            }
        ),
    )

    result = await svc.get_standings(league.uuid)
    assert len(result) == 1
    assert result[0].participant_id == alice
    assert result[0].score == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_tournament_without_finished_stages_is_ignored() -> None:
    """A tournament marked finished but with no finished stages
    contributes nothing (defensive — shouldn't normally happen)."""
    league = _make_league()
    finished_tournament = _make_tournament(
        league_id=league.uuid, date="2025-05-01"
    )
    # Only an active (not finished) stage exists.
    active_stage = _make_stage(
        tournament_id=finished_tournament.uuid, status="active"
    )

    svc = _build_service(
        league,
        _FakeTournamentRepo(
            by_league={league.uuid: [finished_tournament]}
        ),
        _FakeStageRepo(
            by_tournament={finished_tournament.uuid: [active_stage]}
        ),
        _FakeTournamentService(),  # no standings registered
    )

    result = await svc.get_standings(league.uuid)
    assert result == []


@pytest.mark.asyncio
async def test_missing_collaborators_falls_back_to_empty() -> None:
    """Legacy construction without stages/tournament_service must not
    crash — returns empty placement standings."""
    league = _make_league()
    svc = LeagueService(
        leagues=_FakeLeagueRepo(league=league),
        tournaments=_FakeTournamentRepo(),  # type: ignore[arg-type]
        matches=None,  # type: ignore[arg-type]
    )

    result = await svc.get_standings(league.uuid)
    assert result == []
