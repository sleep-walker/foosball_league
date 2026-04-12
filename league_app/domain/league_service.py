"""League orchestration service."""

from __future__ import annotations

from uuid import UUID

from league_app.domain.repositories import ILeagueRepository, IMatchRepository, ITournamentRepository
from league_app.domain.entities_league import League
from league_app.engine import league_standings as ls_engine
from league_app.engine.standings import GameResult, MatchResult


class LeagueError(Exception):
    pass


class LeagueService:
    def __init__(
        self,
        leagues: ILeagueRepository,
        tournaments: ITournamentRepository,
        matches: IMatchRepository,
    ) -> None:
        self._leagues = leagues
        self._tournaments = tournaments
        self._matches = matches

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
        # For placement_points we need tournament results (placements).
        # This is a placeholder — real implementation needs tournament
        # final standings which requires TournamentService.
        # For now, return empty list.
        return ls_engine.compute_placement_standings([], config)

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
