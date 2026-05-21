"""League orchestration service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from league_app.domain.repositories import (
    ILeagueRepository,
    IMatchRepository,
    IStageRepository,
    ITournamentRepository,
)
from league_app.domain.entities_league import League
from league_app.engine import league_standings as ls_engine
from league_app.engine.standings import GameResult, MatchResult

if TYPE_CHECKING:
    from league_app.domain.tournament_service import TournamentService

logger = logging.getLogger(__name__)


class LeagueError(Exception):
    pass


class LeagueService:
    def __init__(
        self,
        leagues: ILeagueRepository,
        tournaments: ITournamentRepository,
        matches: IMatchRepository,
        stages: IStageRepository | None = None,
        tournament_service: "TournamentService | None" = None,
    ) -> None:
        # `stages` and `tournament_service` are optional only so legacy
        # call sites (e.g. existing tests that build a LeagueService
        # directly) keep working; placement_points scoring requires them.
        self._leagues = leagues
        self._tournaments = tournaments
        self._matches = matches
        self._stages = stages
        self._tournament_service = tournament_service

    async def _get_league_or_fail(self, uuid: UUID) -> League:
        league = await self._leagues.get(uuid)
        if league is None:
            raise LeagueError("League not found")
        return league

    def _check_owner(self, league: League, user_id: UUID, is_superuser: bool) -> None:
        if not is_superuser and league.owner_id != user_id:
            raise LeagueError("Permission denied — not the league owner")

    # --- Standings ---

    async def get_standings(
        self, league_id: UUID
    ) -> list[ls_engine.LeagueStandingRow]:
        """Compute league standings according to its scoring_type."""
        league = await self._get_league_or_fail(league_id)
        scoring_type = league.scoring_type
        config = league.scoring_config

        if scoring_type == "placement_points":
            return await self._placement_standings(league_id, config)
        elif scoring_type == "elo":
            return await self._elo_standings(league_id, config)
        elif scoring_type == "win_loss":
            return await self._win_loss_standings(league_id, config)
        else:
            raise LeagueError(f"Unknown scoring type: {scoring_type}")

    async def _placement_standings(
        self, league_id: UUID, config: dict | None
    ) -> list[ls_engine.LeagueStandingRow]:
        """Compute placement-points league standings.

        Iterates finished tournaments in the league (oldest first so
        ``erosion_factor`` can decay older results), picks each
        tournament's final stage (highest ``ordering`` among finished
        stages), converts its standings into ``TournamentPlacement``
        rows keyed by player UUID, and feeds the lot to the engine.

        Doubles tournaments are aggregated at the player level because
        ``TournamentService.get_stage_standings`` already decomposes
        teams into their underlying players.
        """
        if self._stages is None or self._tournament_service is None:
            # Without these collaborators we cannot compute placements;
            # log loudly so the misconfiguration is obvious and fall
            # back to an empty result rather than crashing the request.
            logger.warning(
                "LeagueService missing stages/tournament_service "
                "collaborators; returning empty placement standings."
            )
            return ls_engine.compute_placement_standings([], config)

        tournaments = await self._tournaments.list_by_league(league_id)
        # Only finished tournaments contribute to the league table.
        # Sort oldest -> newest so erosion_factor decays older entries.
        # There is no `finished_at` column today, so fall back to the
        # tournament date (ISO string sorts chronologically) and then
        # uuid as a deterministic tiebreaker.
        finished = sorted(
            (t for t in tournaments if t.status == "finished"),
            key=lambda t: (t.date or "", str(t.uuid)),
        )

        placements_per_tournament: list[list[ls_engine.TournamentPlacement]] = []
        for tournament in finished:
            stages = await self._stages.list_by_tournament(tournament.uuid)
            finished_stages = [s for s in stages if s.status == "finished"]
            if not finished_stages:
                # Tournament marked finished but no finished stages —
                # nothing to score, skip.
                continue
            # "Final" stage = highest ordering among finished stages.
            final_stage = max(finished_stages, key=lambda s: s.ordering)
            standings = await self._tournament_service.get_stage_standings(
                tournament.uuid, final_stage.uuid
            )
            if not standings:
                continue
            # StandingRow list is already sorted by final placement
            # (index 0 == place 1). Convert directly.
            placements_per_tournament.append([
                ls_engine.TournamentPlacement(
                    participant_id=row.participant_id,
                    place=idx + 1,
                )
                for idx, row in enumerate(standings)
            ])

        return ls_engine.compute_placement_standings(
            placements_per_tournament, config
        )

    async def _elo_standings(
        self, league_id: UUID, config: dict | None
    ) -> list[ls_engine.LeagueStandingRow]:
        match_results = await self._collect_league_matches(league_id)
        return ls_engine.compute_elo_ratings(match_results, config)

    async def _win_loss_standings(
        self, league_id: UUID, config: dict | None
    ) -> list[ls_engine.LeagueStandingRow]:
        match_results = await self._collect_league_matches(league_id)
        return ls_engine.compute_win_loss_standings(match_results, config)

    async def _collect_league_matches(self, league_id: UUID) -> list[MatchResult]:
        """Collect all finished matches from all tournaments in this league."""
        tournaments = await self._tournaments.list_by_league(league_id)
        results: list[MatchResult] = []
        for t in tournaments:
            matches = await self._matches.list_by_tournament(t.uuid)
            for m in matches:
                if m.status != "finished":
                    continue
                a_id = m.team_a_id or m.player_a_id
                b_id = m.team_b_id or m.player_b_id
                if a_id and b_id:
                    results.append(MatchResult(
                        participant_a_id=a_id,
                        participant_b_id=b_id,
                        games=[GameResult(g.score_a, g.score_b) for g in m.games],
                    ))
        return results
