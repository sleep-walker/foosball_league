"""Tournament orchestration service.

All tournament business logic lives here.  Routers call this service —
never the repositories or engine directly.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from league_app.domain import entities as e
from league_app.domain.repositories import (
    IMatchRepository,
    IPlayerRepository,
    IStageRepository,
    ITeamRepository,
    ITournamentRepository,
)
from league_app.engine import standings as standings_engine
from league_app.engine import swiss as swiss_engine
from league_app.engine import bracket as bracket_engine
from league_app.engine import scoring as scoring_engine


class TournamentError(Exception):
    """Raised when a business rule is violated."""
    pass


class TournamentService:
    def __init__(
        self,
        tournaments: ITournamentRepository,
        matches: IMatchRepository,
        stages: IStageRepository,
        players: IPlayerRepository,
        teams: ITeamRepository,
    ) -> None:
        self._tournaments = tournaments
        self._matches = matches
        self._stages = stages
        self._players = players
        self._teams = teams

    # --- Helpers ---

    async def _get_tournament_or_fail(self, uuid: UUID) -> e.Tournament:
        t = await self._tournaments.get(uuid)
        if t is None:
            raise TournamentError("Tournament not found")
        return t

    async def _get_stage_or_fail(self, tournament_id: UUID, stage_id: UUID) -> e.Stage:
        s = await self._stages.get(stage_id)
        if s is None or s.tournament_id != tournament_id:
            raise TournamentError("Stage not found in tournament")
        return s

    def _check_owner(self, tournament: e.Tournament, user_id: UUID, is_superuser: bool) -> None:
        if not is_superuser and tournament.owner_id != user_id:
            raise TournamentError("Permission denied — not the tournament owner")

    # --- Lifecycle ---

    async def start_tournament(self, tournament_id: UUID) -> e.Tournament:
        """Transition PREPARING → RUNNING. Closes registration."""
        t = await self._get_tournament_or_fail(tournament_id)
        if not e.TournamentStatus.can_transition(t.status, e.TournamentStatus.RUNNING):
            raise TournamentError(
                f"Cannot start tournament in status '{t.status}'"
            )
        t.status = e.TournamentStatus.RUNNING
        t.is_registration_open = False
        return await self._tournaments.update(t)

    async def finish_tournament(self, tournament_id: UUID) -> e.Tournament:
        """Transition RUNNING → FINISHED."""
        t = await self._get_tournament_or_fail(tournament_id)
        if not e.TournamentStatus.can_transition(t.status, e.TournamentStatus.FINISHED):
            raise TournamentError(
                f"Cannot finish tournament in status '{t.status}'"
            )
        t.status = e.TournamentStatus.FINISHED
        return await self._tournaments.update(t)

    # --- Registration ---

    async def register_player(
        self, tournament_id: UUID, player_id: UUID
    ) -> e.TournamentRegistration:
        t = await self._get_tournament_or_fail(tournament_id)
        if not t.is_registration_open:
            raise TournamentError("Registration is closed")
        p = await self._players.get(player_id)
        if p is None:
            raise TournamentError("Player not found")
        existing = await self._tournaments.get_registration(tournament_id, player_id)
        if existing is not None:
            raise TournamentError("Player already registered")
        reg = e.TournamentRegistration(tournament_id=tournament_id, player_id=player_id)
        return await self._tournaments.add_registration(reg)

    async def unregister_player(self, tournament_id: UUID, player_id: UUID) -> None:
        removed = await self._tournaments.remove_registration(tournament_id, player_id)
        if not removed:
            raise TournamentError("Player not in tournament")

    async def mark_paid(
        self, tournament_id: UUID, player_id: UUID, paid: bool = True
    ) -> e.TournamentRegistration:
        reg = await self._tournaments.get_registration(tournament_id, player_id)
        if reg is None:
            raise TournamentError("Player not in tournament")
        reg.paid = paid
        return await self._tournaments.update_registration(reg)

    async def pause_player(
        self, tournament_id: UUID, player_id: UUID
    ) -> e.TournamentRegistration:
        """Pause a player — they won't be paired in the next round."""
        reg = await self._tournaments.get_registration(tournament_id, player_id)
        if reg is None:
            raise TournamentError("Player not in tournament")
        reg.is_paused = True
        return await self._tournaments.update_registration(reg)

    async def unpause_player(
        self, tournament_id: UUID, player_id: UUID
    ) -> e.TournamentRegistration:
        """Unpause a player — they will be paired again."""
        reg = await self._tournaments.get_registration(tournament_id, player_id)
        if reg is None:
            raise TournamentError("Player not in tournament")
        reg.is_paused = False
        return await self._tournaments.update_registration(reg)

    # --- Standings ---

    async def get_stage_standings(
        self, tournament_id: UUID, stage_id: UUID
    ) -> list[standings_engine.StandingRow]:
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        matches = await self._matches.list_by_stage(stage_id)
        match_results = []
        for m in matches:
            if m.status != "finished":
                continue
            a_id = m.team_a_id or m.player_a_id
            b_id = m.team_b_id or m.player_b_id
            if a_id is None or b_id is None:
                continue
            match_results.append(standings_engine.MatchResult(
                participant_a_id=a_id, participant_b_id=b_id,
                games=[standings_engine.GameResult(g.score_a, g.score_b) for g in m.games],
            ))
        return standings_engine.compute_standings(match_results, rules=stage.rules)

    # --- Swiss draw ---

    async def draw_swiss_round(
        self, tournament_id: UUID, stage_id: UUID, owner_id: UUID
    ) -> list[e.Match]:
        t = await self._get_tournament_or_fail(tournament_id)
        if t.status != e.TournamentStatus.RUNNING:
            raise TournamentError("Tournament must be RUNNING to draw rounds")
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        if stage.stage_type != "group":
            raise TournamentError("Swiss draw only for group stages")

        regs = await self._tournaments.list_registrations(tournament_id)
        participant_ids = [r.player_id for r in regs if not r.is_paused]
        if len(participant_ids) < 2:
            raise TournamentError("Not enough active participants")

        existing = await self._matches.list_by_stage(stage_id)
        history = self._build_match_history(existing)
        current_round = max((m.round_number for m in existing), default=0) + 1

        pairings = swiss_engine.generate_swiss_round(
            participant_ids, history, stage.rules
        )

        best_of = (stage.rules or {}).get("best_of", 1)
        created = []
        for p in pairings:
            match = e.Match(
                uuid=uuid4(), tournament_id=tournament_id, stage_id=stage_id,
                owner_id=owner_id, round_number=current_round, best_of=best_of,
                player_a_id=p.participant_a_id, player_b_id=p.participant_b_id,
            )
            created.append(await self._matches.create(match))
        return created


    # --- Bracket generation ---

    async def generate_bracket(
        self,
        tournament_id: UUID,
        stage_id: UUID,
        owner_id: UUID,
        source_stage_id: UUID | None = None,
    ) -> list[e.Match]:
        t = await self._get_tournament_or_fail(tournament_id)
        if t.status != e.TournamentStatus.RUNNING:
            raise TournamentError("Tournament must be RUNNING to generate bracket")
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        if stage.stage_type != "elimination":
            raise TournamentError("Bracket only for elimination stages")

        if source_stage_id:
            source_matches = await self._matches.list_by_stage(source_stage_id)
            history = self._build_match_history(
                [m for m in source_matches if m.status == "finished"]
            )
            rows = standings_engine.compute_standings(history)
            advancement = stage.advancement_count or len(rows)
            seeded_ids = [r.participant_id for r in rows[:advancement]]
        else:
            regs = await self._tournaments.list_registrations(tournament_id)
            seeded_ids = [r.player_id for r in regs]

        if len(seeded_ids) < 2:
            raise TournamentError("Not enough participants for bracket")

        rules = stage.rules or {}
        consolation = rules.get("consolation_match", True)
        best_of = rules.get("best_of", 3)
        bracket = bracket_engine.generate_bracket(seeded_ids, consolation=consolation)

        created = []
        for bm in bracket.matches:
            match = e.Match(
                uuid=uuid4(), tournament_id=tournament_id, stage_id=stage_id,
                owner_id=owner_id, round_number=bm.round_number,
                bracket_position=bm.position, best_of=best_of,
                player_a_id=bm.participant_a_id, player_b_id=bm.participant_b_id,
            )
            created.append(await self._matches.create(match))
        return created

    # --- Score submission ---

    async def submit_game_score(
        self, match_id: UUID, score_a: int, score_b: int
    ) -> e.Game:
        match = await self._matches.get(match_id)
        if match is None:
            raise TournamentError("Match not found")
        if match.status == "finished":
            raise TournamentError("Match is already finished")

        rules: dict = {}
        if match.stage_id:
            stage = await self._stages.get(match.stage_id)
            if stage and stage.rules:
                rules = stage.rules

        existing_scores = [
            scoring_engine.GameScore(g.score_a, g.score_b)
            for g in match.games if g.is_finished
        ]
        is_decider = scoring_engine.is_decider_game(existing_scores, match.best_of)
        validation = scoring_engine.validate_game_score(
            scoring_engine.GameScore(score_a, score_b), rules, is_decider=is_decider
        )
        if not validation.valid:
            raise TournamentError(f"Invalid score: {validation.error}")

        game = e.Game(
            uuid=uuid4(), match_id=match_id,
            game_number=len(match.games) + 1,
            score_a=score_a, score_b=score_b, is_finished=True,
        )
        game = await self._matches.create_game(game)

        all_scores = existing_scores + [scoring_engine.GameScore(score_a, score_b)]
        status = scoring_engine.compute_match_status(all_scores, match.best_of)
        if status.is_finished:
            match.status = "finished"
            match.winner_side = status.winner_side
            await self._matches.update(match)
        elif match.status == "scheduled":
            match.status = "in_progress"
            await self._matches.update(match)

        return game

    # --- Internal helpers ---

    @staticmethod
    def _build_match_history(matches: list[e.Match]) -> list[standings_engine.MatchResult]:
        results = []
        for m in matches:
            a_id = m.team_a_id or m.player_a_id
            b_id = m.team_b_id or m.player_b_id
            if a_id and b_id:
                results.append(standings_engine.MatchResult(
                    participant_a_id=a_id, participant_b_id=b_id,
                    games=[standings_engine.GameResult(g.score_a, g.score_b) for g in m.games],
                ))
        return results