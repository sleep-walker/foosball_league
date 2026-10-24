"""Tournament orchestration service.

All tournament business logic lives here.  Routers call this service —
never the repositories or engine directly.
"""

from __future__ import annotations

import logging
import random
from typing import Any
from uuid import UUID, uuid4

from league_app.domain import entities as e
from league_app.domain.repositories import (
    ILeagueRepository,
    IMatchRepository,
    IPlayerRepository,
    IStageRepository,
    ITableRepository,
    ITeamRepository,
    ITournamentRepository,
)
from league_app.domain._bracket_mixin import BracketMixin
from league_app.domain._registration_mixin import RegistrationMixin
from league_app.domain._stage_mixin import StageMixin
from league_app.domain.tournament_errors import TournamentError
from league_app.domain.tournament_helpers import (
    build_match_history,
    count_games_played,
    player_standings,
)
from league_app.engine import standings as standings_engine
from league_app.engine import swiss as swiss_engine
from league_app.engine import bracket as bracket_engine
from league_app.engine import scoring as scoring_engine
from league_app.realtime.hub import Event, event_hub

log = logging.getLogger(__name__)

# Re-export so existing ``from league_app.domain.tournament_service
# import TournamentError`` callsites keep working after the exception
# moved to its own module.
__all__ = ["TournamentError", "TournamentService"]


class TournamentService(RegistrationMixin, StageMixin, BracketMixin):
    def __init__(
        self,
        tournaments: ITournamentRepository,
        matches: IMatchRepository,
        stages: IStageRepository,
        players: IPlayerRepository,
        teams: ITeamRepository,
        tables: ITableRepository | None = None,
        leagues: ILeagueRepository | None = None,
    ) -> None:
        self._tournaments = tournaments
        self._matches = matches
        self._stages = stages
        self._players = players
        self._teams = teams
        self._tables = tables
        self._leagues = leagues

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

    async def start_tournament(
        self, tournament_id: UUID, owner_id: UUID | None = None
    ) -> e.Tournament:
        """Transition REGISTRATION → RUNNING.

        Closes registration, creates a default stage if none exists,
        and draws the first Swiss round automatically.
        """
        t = await self._get_tournament_or_fail(tournament_id)
        if not e.TournamentStatus.can_transition(t.status, e.TournamentStatus.RUNNING):
            raise TournamentError(
                f"Cannot start tournament in status '{t.status}'"
            )

        regs = await self._tournaments.list_registrations(tournament_id)
        active = [r for r in regs if not r.is_paused]
        min_players = 4 if t.player_mode == "doubles" else 2
        if len(active) < min_players:
            raise TournamentError(
                f"Need at least {min_players} players to start "
                f"(have {len(active)})"
            )

        t.status = e.TournamentStatus.RUNNING
        t.is_registration_open = False
        result = await self._tournaments.update(t)
        await event_hub.publish(Event("tournament_started", t.uuid))

        # Build effective game rules: hard defaults → league → tournament settings
        game_rules: dict[str, Any] = {
            "points_per_game": 6,
            "draw_allowed": True,
            "points_for_win": 2,
            "points_for_draw": 1,
            "points_for_loss": 0,
        }
        # Inherit from league if tournament belongs to one
        if t.league_id and self._leagues:
            league = await self._leagues.get(t.league_id)
            if league and league.default_game_rules:
                game_rules.update(league.default_game_rules)
        # Tournament-level overrides (from settings JSON)
        if t.settings:
            game_rules.update(t.settings)

        # Auto-create default stage if none exists
        stages = await self._stages.list_by_tournament(tournament_id)
        if not stages:
            default_stage = e.Stage(
                uuid=uuid4(), tournament_id=tournament_id,
                name="Main", stage_type="group", ordering=0,
                status="active",
                rules=game_rules,
            )
            default_stage = await self._stages.create(default_stage)
            stages = [default_stage]

        # Activate the first group stage (if still preparing)
        first_group = next(
            (s for s in sorted(stages, key=lambda s: s.ordering)
             if s.stage_type == "group"), None
        )
        if first_group and first_group.status == "preparing":
            first_group.status = "active"
            await self._stages.update(first_group)

        # Draw first round of the first group stage
        if first_group and owner_id:
            try:
                await self.draw_swiss_round(
                    tournament_id, first_group.uuid, owner_id,
                    _internal=True,
                )
            except TournamentError as exc:
                log.warning(
                    "Auto-draw failed for tournament %s: %s", tournament_id, exc
                )

        return result

    async def finish_tournament(self, tournament_id: UUID) -> e.Tournament:
        """Transition RUNNING → FINISHED."""
        t = await self._get_tournament_or_fail(tournament_id)
        if not e.TournamentStatus.can_transition(t.status, e.TournamentStatus.FINISHED):
            raise TournamentError(
                f"Cannot finish tournament in status '{t.status}'"
            )
        t.status = e.TournamentStatus.FINISHED
        result = await self._tournaments.update(t)
        await event_hub.publish(Event("tournament_finished", t.uuid))
        return result

    # --- Stage lifecycle ---
    #
    # Note: stage creation and rule updates are handled directly by the
    # API layer (``stages_crud.create_stage`` and
    # ``api/stages/router.py`` for rule patching). Earlier versions of
    # this service exposed ``create_stage`` and ``update_stage_rules``
    # methods; they were unreferenced and got removed as part of the
    # service split. If a service-level entry point becomes useful
    # again, restore them in a dedicated module rather than here.

    # ``activate_stage`` / ``finish_stage`` live in
    # :class:`StageMixin` (``_stage_mixin.py``).

    # --- Registration ---
    #
    # Implemented in :class:`RegistrationMixin`
    # (``_registration_mixin.py``): ``register_player``,
    # ``unregister_player``, ``mark_paid``, ``pause_player``,
    # ``unpause_player``.

    # --- Standings ---

    async def get_stage_standings(
        self, tournament_id: UUID, stage_id: UUID
    ) -> list[standings_engine.StandingRow]:
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        matches = await self._matches.list_by_stage(stage_id)
        # Detect doubles from matches (avoids lazy-load issue with tournament.get)
        is_doubles = any(m.team_a_id for m in matches)

        # Build team→players lookup for doubles (DYP: teams change every round)
        team_players: dict[UUID, list[UUID]] = {}
        if is_doubles and self._teams:
            teams = await self._teams.list_by_tournament(tournament_id)
            for team in teams:
                members = []
                if team.player_1_id:
                    members.append(team.player_1_id)
                if team.player_2_id:
                    members.append(team.player_2_id)
                team_players[team.uuid] = members

        match_results = []
        for m in matches:
            if m.status != "finished":
                continue
            games = [standings_engine.GameResult(g.score_a, g.score_b) for g in m.games]

            if is_doubles and m.team_a_id and m.team_b_id:
                # Decompose: each player gets the team's result as their own.
                # Use a synthetic pairing of player pairs (one from each side).
                players_a = team_players.get(m.team_a_id, [])
                players_b = team_players.get(m.team_b_id, [])
                # Pair up: player_a[0] vs player_b[0], player_a[1] vs player_b[1]
                # Each player gets exactly 1 match result with the team's score.
                for i in range(max(len(players_a), len(players_b))):
                    pa = players_a[i] if i < len(players_a) else players_a[0]
                    pb = players_b[i] if i < len(players_b) else players_b[0]
                    match_results.append(standings_engine.MatchResult(
                        participant_a_id=pa, participant_b_id=pb,
                        games=games,
                    ))
            else:
                a_id = m.player_a_id
                b_id = m.player_b_id
                if a_id is None or b_id is None:
                    continue
                match_results.append(standings_engine.MatchResult(
                    participant_a_id=a_id, participant_b_id=b_id,
                    games=games,
                ))
        # Gather all registered player IDs so players without matches still appear
        regs = await self._tournaments.list_registrations(tournament_id)
        if is_doubles:
            # In doubles, individual players from teams already appear via decomposition
            all_player_ids = list({pid for members in team_players.values() for pid in members})
            # Also include registered players who might not be on any team yet
            all_player_ids = list(set(all_player_ids) | {r.player_id for r in regs if not r.is_paused})
        else:
            all_player_ids = [r.player_id for r in regs if not r.is_paused]

        return standings_engine.compute_standings(
            match_results, rules=stage.rules,
            registered_player_ids=all_player_ids,
        )


    async def redraw_current_round(
        self,
        tournament_id: UUID,
        stage_id: UUID,
        owner_id: UUID,
    ) -> list[e.Match]:
        """Delete all matches in the latest round and draw again.

        Useful when admin changes rules (e.g. table count) after a round
        was already drawn.  Only unfinished rounds can be redrawn.
        """
        t = await self._get_tournament_or_fail(tournament_id)
        if t.status != e.TournamentStatus.RUNNING:
            raise TournamentError("Tournament must be RUNNING")
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        if stage.status != "active":
            raise TournamentError("Stage must be active")

        existing = await self._matches.list_by_stage(stage_id)
        if not existing:
            raise TournamentError("No rounds to redraw")

        max_round = max(m.round_number for m in existing)
        current_round = [m for m in existing if m.round_number == max_round]

        # Delete current round matches (including finished ones — admin override)
        for m in current_round:
            await self._matches.delete(m.uuid)

        # Draw again (will create round with same number)
        return await self.draw_swiss_round(tournament_id, stage_id, owner_id)

    # --- Swiss draw ---

    async def draw_swiss_round(
        self, tournament_id: UUID, stage_id: UUID, owner_id: UUID,
        *, _internal: bool = False,
    ) -> list[e.Match]:
        """Draw the next Swiss round.

        For DYP doubles: forms new random teams each round, handles bye.
        For singles: pairs players, handles bye.
        """
        t = await self._get_tournament_or_fail(tournament_id)
        if not _internal and t.status != e.TournamentStatus.RUNNING:
            raise TournamentError("Tournament must be RUNNING to draw rounds")
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        if stage.stage_type != "group":
            raise TournamentError("Swiss draw only for group stages")
        if not _internal and stage.status != "active":
            raise TournamentError(
                f"Cannot draw round — stage '{stage.name}' is {stage.status}"
            )

        regs = await self._tournaments.list_registrations(tournament_id)
        active_player_ids = [r.player_id for r in regs if not r.is_paused]

        if len(active_player_ids) < 2:
            raise TournamentError("Not enough active players")

        existing = await self._matches.list_by_stage(stage_id)
        current_round = max((m.round_number for m in existing), default=0) + 1
        is_doubles = (t.player_mode == "doubles")

        # --- Bye selection ---
        # Count games played per player; player(s) with most games sit out
        games_played = count_games_played(existing, active_player_ids)
        bye_player_ids: list[UUID] = []
        playing_ids = list(active_player_ids)

        if is_doubles:
            # Need even number of players for team formation
            if len(playing_ids) % 2 != 0:
                # Pick the player who played the most to sit out
                bye_pid = max(playing_ids, key=lambda pid: games_played.get(pid, 0))
                bye_player_ids.append(bye_pid)
                playing_ids.remove(bye_pid)
            # If still odd number of teams (i.e. odd pairs), sit out 2 more
            if (len(playing_ids) // 2) % 2 != 0 and len(playing_ids) >= 4:
                # Odd number of teams → 1 team (2 players) sits out
                remaining = sorted(playing_ids, key=lambda pid: -games_played.get(pid, 0))
                bye_player_ids.extend(remaining[:2])
                playing_ids = remaining[2:]
        else:
            # Singles: odd number → 1 player sits out
            if len(playing_ids) % 2 != 0:
                bye_pid = max(playing_ids, key=lambda pid: games_played.get(pid, 0))
                bye_player_ids.append(bye_pid)
                playing_ids.remove(bye_pid)

        # --- Team formation (doubles) ---
        if is_doubles:
            team_formation = getattr(stage, "team_formation", "dyp") or "dyp"
            # Legacy alias: "random" was renamed to "dyp"; "monster_dyp" behaves
            # like "dyp" in group stages (reshuffle is an elim-only feature).
            if team_formation in ("random", "monster_dyp"):
                team_formation = "dyp"
            random_rounds = getattr(stage, "random_rounds", 2) or 2

            if team_formation == "fixed":
                # Reuse existing teams
                teams = await self._teams.list_by_tournament(tournament_id)
                # Filter to teams whose players are all in playing_ids
                playing_set = set(playing_ids)
                teams = [t for t in teams
                         if t.player_1_id in playing_set
                         and t.player_2_id in playing_set]
            elif team_formation == "dyp" or current_round <= random_rounds:
                # DYP: form new random teams
                random.shuffle(playing_ids)
                teams = []
                for i in range(0, len(playing_ids), 2):
                    team = e.Team(
                        uuid=uuid4(), tournament_id=tournament_id,
                        player_1_id=playing_ids[i],
                        player_2_id=playing_ids[i + 1],
                    )
                    team = await self._teams.create(team)
                    teams.append(team)
            else:
                # from_results: pair strong + weak by standings
                standings = player_standings(existing, playing_ids)
                teams = []
                top_half = standings[:len(standings) // 2]
                bottom_half = standings[len(standings) // 2:]
                random.shuffle(bottom_half)
                for top, bot in zip(top_half, bottom_half, strict=False):
                    team = e.Team(
                        uuid=uuid4(), tournament_id=tournament_id,
                        player_1_id=top, player_2_id=bot,
                    )
                    team = await self._teams.create(team)
                    teams.append(team)

            participant_ids = [team.uuid for team in teams]
        else:
            participant_ids = playing_ids

        # --- Swiss pairing ---
        history = build_match_history(existing)
        pairings = swiss_engine.generate_swiss_round(
            participant_ids, history, stage.rules
        )

        best_of = (stage.rules or {}).get("best_of", 1)
        table_count = (stage.rules or {}).get("table_count", 0) or (t.settings or {}).get("table_count", 4)
        created: list[e.Match] = []
        for idx, p in enumerate(pairings):
            # Table assignment: first table_count matches get a table
            table_num = (idx + 1) if (idx < table_count) else None
            if is_doubles:
                match = e.Match(
                    uuid=uuid4(), tournament_id=tournament_id,
                    stage_id=stage_id, owner_id=owner_id,
                    round_number=current_round, best_of=best_of,
                    team_a_id=p.participant_a_id,
                    team_b_id=p.participant_b_id,
                    table_number=table_num,
                )
            else:
                match = e.Match(
                    uuid=uuid4(), tournament_id=tournament_id,
                    stage_id=stage_id, owner_id=owner_id,
                    round_number=current_round, best_of=best_of,
                    player_a_id=p.participant_a_id,
                    player_b_id=p.participant_b_id,
                    table_number=table_num,
                )
            created.append(await self._matches.create(match))

        log.info(
            "Round %d drawn: %d matches, %d bye players, tables: %d/%d",
            current_round, len(created), len(bye_player_ids),
            min(len(created), table_count), table_count,
        )

        await event_hub.publish(Event(
            "round_drawn", tournament_id,
            {"stage_id": str(stage_id), "round_number": current_round,
             "match_count": len(created),
             "bye_player_ids": [str(pid) for pid in bye_player_ids]},
        ))
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

        is_doubles = (t.player_mode == "doubles")

        # Auto-detect source group stage if not explicitly provided
        if not source_stage_id:
            all_stages = await self._stages.list_by_tournament(tournament_id)
            # Find the closest preceding group stage (by ordering, excluding self)
            # Only use it if it has finished matches (otherwise fall back to registrations)
            group_stages = [
                s for s in sorted(all_stages, key=lambda s: s.ordering)
                if s.stage_type == "group"
                and s.uuid != stage_id
                and s.ordering <= stage.ordering
            ]
            for candidate in reversed(group_stages):
                candidate_matches = await self._matches.list_by_stage(candidate.uuid)
                if any(m.status == "finished" for m in candidate_matches):
                    source_stage_id = candidate.uuid
                    break

        if source_stage_id:
            source_stage = await self._stages.get(source_stage_id)
            source_matches = await self._matches.list_by_stage(source_stage_id)
            history = build_match_history(
                [m for m in source_matches if m.status == "finished"]
            )
            source_rules = source_stage.rules if source_stage else None
            rows = standings_engine.compute_standings(history, source_rules)
            advancement = stage.advancement_count or len(rows)
            seeded_ids = [r.participant_id for r in rows[:advancement]]
        else:
            regs = await self._tournaments.list_registrations(tournament_id)
            seeded_ids = [r.player_id for r in regs if not r.is_paused]

        # For doubles, form teams from seeded players
        if is_doubles and not source_stage_id:
            # Form new random teams for elimination
            random.shuffle(seeded_ids)
            teams = []
            for i in range(0, len(seeded_ids) - 1, 2):
                team = e.Team(
                    uuid=uuid4(), tournament_id=tournament_id,
                    player_1_id=seeded_ids[i],
                    player_2_id=seeded_ids[i + 1],
                )
                team = await self._teams.create(team)
                teams.append(team)
            seeded_ids = [team.uuid for team in teams]

        if len(seeded_ids) < 2:
            raise TournamentError("Not enough participants for bracket")

        rules = stage.rules or {}
        consolation = rules.get("consolation_match", True)
        best_of = rules.get("best_of", 3)
        finals_best_of = rules.get("finals_best_of", best_of)
        table_count = rules.get("table_count", 0) or (t.settings or {}).get("table_count", 4)
        bracket = bracket_engine.generate_bracket(seeded_ids, consolation=consolation)

        # Determine max round number so finals/consolation get finals_best_of
        max_round = max(bm.round_number for bm in bracket.matches) if bracket.matches else 1

        created = []
        # Assign tables to first-round matches that have both participants
        table_idx = 0
        for bm in bracket.matches:
            match_best_of = finals_best_of if bm.round_number == max_round else best_of
            # Assign table only to playable matches (both participants known)
            has_both = bm.participant_a_id is not None and bm.participant_b_id is not None
            table_num = None
            if has_both and table_idx < table_count:
                table_idx += 1
                table_num = table_idx
            if is_doubles:
                match = e.Match(
                    uuid=uuid4(), tournament_id=tournament_id, stage_id=stage_id,
                    owner_id=owner_id, round_number=bm.round_number,
                    bracket_position=bm.position, best_of=match_best_of,
                    team_a_id=bm.participant_a_id, team_b_id=bm.participant_b_id,
                    table_number=table_num,
                )
            else:
                match = e.Match(
                    uuid=uuid4(), tournament_id=tournament_id, stage_id=stage_id,
                    owner_id=owner_id, round_number=bm.round_number,
                    bracket_position=bm.position, best_of=match_best_of,
                    player_a_id=bm.participant_a_id, player_b_id=bm.participant_b_id,
                    table_number=table_num,
                )
            created.append(await self._matches.create(match))
        await event_hub.publish(Event(
            "bracket_generated", tournament_id,
            {"stage_id": str(stage_id), "match_count": len(created)},
        ))
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
        stage = None
        if match.stage_id:
            stage = await self._stages.get(match.stage_id)
            if stage:
                if stage.status != "active":
                    raise TournamentError(
                        f"Cannot submit scores — stage '{stage.name}' is {stage.status}"
                    )
                if stage.rules:
                    rules = stage.rules

        # Re-read games via repo (rather than the lazy-loaded match.games
        # relationship) so successive calls in a batch see freshly committed
        # rows instead of a cached snapshot from the first call.
        existing_games = await self._matches.list_games(match_id)
        existing_scores = [
            scoring_engine.GameScore(g.score_a, g.score_b)
            for g in existing_games if g.is_finished
        ]
        is_decider = scoring_engine.is_decider_game(existing_scores, match.best_of)
        validation = scoring_engine.validate_game_score(
            scoring_engine.GameScore(score_a, score_b), rules, is_decider=is_decider
        )
        if not validation.valid:
            raise TournamentError(f"Invalid score: {validation.error}")

        game = e.Game(
            uuid=uuid4(), match_id=match_id,
            game_number=len(existing_games) + 1,
            score_a=score_a, score_b=score_b, is_finished=True,
        )
        game = await self._matches.create_game(game)

        all_scores = existing_scores + [scoring_engine.GameScore(score_a, score_b)]
        status = scoring_engine.compute_match_status(all_scores, match.best_of)
        if status.is_finished:
            match.status = "finished"
            match.winner_side = status.winner_side
            await self._matches.update(match)
            if match.tournament_id:
                await event_hub.publish(Event(
                    "match_finished", match.tournament_id,
                    {"match_id": str(match.uuid), "winner_side": status.winner_side},
                ))

            # --- Bracket advancement (elimination stages) ---
            # Fills participants in next-round matches; table allocation is
            # handled uniformly by _assign_free_tables below.
            if stage and stage.stage_type == "elimination" and match.bracket_position is not None:
                await self._advance_bracket_winner(match, stage, status.winner_side)

            # Single source of truth for table allocation: works for any stage
            # type — finished match frees its table; pending fillable matches
            # (incl. ones just filled by bracket advancement) can pick it up.
            if match.stage_id and match.tournament_id:
                await self._assign_free_tables(
                    match.stage_id, match.tournament_id,
                    prefer_round=match.round_number,
                )

        elif match.status == "scheduled":
            match.status = "in_progress"
            await self._matches.update(match)

        if match.tournament_id:
            await event_hub.publish(Event(
                "score_updated", match.tournament_id,
                {"match_id": str(match.uuid), "score_a": score_a, "score_b": score_b,
                 "game_number": game.game_number},
            ))

        return game

    async def submit_batch_scores(
        self, match_id: UUID, scores: list[tuple[int, int]]
    ) -> list[e.Game]:
        """Submit multiple game scores for a match as one logical operation.

        All scores are validated up-front against an in-memory rolling state
        before any are written. If any single score fails validation (or would
        leave extra games after the match would already be decided), nothing
        is committed and the error is raised. This protects the user from
        partial commits when the dialog batches several legs together.

        Note: per-game DB writes still commit individually inside
        ``submit_game_score``; only validation is atomic. A DB error mid-loop
        could still cause partial commits but those are extremely rare
        compared to user validation mistakes.
        """
        if not scores:
            raise TournamentError("No scores provided")

        match = await self._matches.get(match_id)
        if match is None:
            raise TournamentError("Match not found")
        if match.status == "finished":
            raise TournamentError("Match is already finished")

        rules: dict = {}
        if match.stage_id:
            stage = await self._stages.get(match.stage_id)
            if stage:
                if stage.status != "active":
                    raise TournamentError(
                        f"Cannot submit scores — stage '{stage.name}' is {stage.status}"
                    )
                if stage.rules:
                    rules = stage.rules

        existing = [
            scoring_engine.GameScore(g.score_a, g.score_b)
            for g in match.games if g.is_finished
        ]
        for i, (sa, sb) in enumerate(scores):
            is_decider = scoring_engine.is_decider_game(existing, match.best_of)
            v = scoring_engine.validate_game_score(
                scoring_engine.GameScore(sa, sb), rules, is_decider=is_decider,
            )
            if not v.valid:
                raise TournamentError(f"Game {i + 1}: Invalid score: {v.error}")
            existing.append(scoring_engine.GameScore(sa, sb))
            status = scoring_engine.compute_match_status(existing, match.best_of)
            if status.is_finished and i < len(scores) - 1:
                raise TournamentError(
                    f"Game {i + 1}: Match is already decided here — "
                    f"{len(scores) - i - 1} extra game(s) supplied"
                )

        games: list[e.Game] = []
        for sa, sb in scores:
            games.append(await self.submit_game_score(match_id, sa, sb))
        return games

    # --- Bracket advancement ---
    #
    # ``_advance_bracket_winner`` and
    # ``_monster_dyp_reshuffle_next_round`` live in
    # :class:`BracketMixin` (``_bracket_mixin.py``).

    # --- Internal helpers ---

    async def _assign_free_tables(
        self, stage_id: UUID, tournament_id: UUID,
        *, prefer_round: int | None = None,
    ) -> None:
        """Assign any free tables to pending matches in a stage that need one.

        Single source of truth for stage-level table allocation. Works for both
        group/Swiss and elimination stages — invoked whenever the set of
        pending-but-fillable matches or the set of free tables may have changed
        (e.g., after a match finishes or after a bracket advancement).

        prefer_round: when picking among pending matches, prefer this round
        first (typically the round of the just-finished match).
        """
        stage = await self._stages.get(stage_id)
        if stage is None:
            return
        t = await self._tournaments.get(tournament_id)
        table_count = ((stage.rules or {}).get("table_count", 0)
                       or ((t.settings if t else None) or {}).get("table_count", 4))
        if not table_count:
            return

        stage_matches = await self._matches.list_by_stage(stage_id)
        used_tables = {
            m.table_number for m in stage_matches
            if m.status != "finished" and m.table_number is not None
        }
        free_tables = sorted(
            tn for tn in range(1, table_count + 1) if tn not in used_tables
        )
        if not free_tables:
            return

        def _has_both(m: e.Match) -> bool:
            return ((m.player_a_id is not None and m.player_b_id is not None)
                    or (m.team_a_id is not None and m.team_b_id is not None))

        candidates = [
            m for m in stage_matches
            if m.status != "finished"
            and m.table_number is None
            and _has_both(m)
        ]
        # Prefer the requested round, then earliest round
        candidates.sort(key=lambda m: (
            0 if (prefer_round is not None and m.round_number == prefer_round) else 1,
            m.round_number or 0,
        ))

        for table_num, m in zip(free_tables, candidates, strict=False):
            m.table_number = table_num
            await self._matches.update(m)
            log.info(
                "Assigned table %d to match %s (round %s, stage %s)",
                table_num, m.uuid, m.round_number, stage_id,
            )

