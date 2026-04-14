"""Tournament orchestration service.

All tournament business logic lives here.  Routers call this service —
never the repositories or engine directly.
"""

from __future__ import annotations

import logging
import random
from uuid import UUID, uuid4

from league_app.domain import entities as e

log = logging.getLogger(__name__)
from league_app.domain.repositories import (
    IMatchRepository,
    IPlayerRepository,
    IStageRepository,
    ITableRepository,
    ITeamRepository,
    ITournamentRepository,
)
from league_app.engine import standings as standings_engine
from league_app.engine import swiss as swiss_engine
from league_app.engine import bracket as bracket_engine
from league_app.engine import scoring as scoring_engine
from league_app.engine import table_assignment as table_engine
from league_app.realtime.hub import Event, event_hub


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
        tables: ITableRepository | None = None,
    ) -> None:
        self._tournaments = tournaments
        self._matches = matches
        self._stages = stages
        self._players = players
        self._teams = teams
        self._tables = tables

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

        # Auto-create default stage if none exists
        stages = await self._stages.list_by_tournament(tournament_id)
        if not stages:
            default_stage = e.Stage(
                uuid=uuid4(), tournament_id=tournament_id,
                name="Main", stage_type="group", ordering=0,
            )
            default_stage = await self._stages.create(default_stage)
            stages = [default_stage]

        # Draw first round of the first group stage
        first_group = next(
            (s for s in sorted(stages, key=lambda s: s.ordering)
             if s.stage_type == "group"), None
        )
        if first_group and owner_id:
            try:
                await self.draw_swiss_round(
                    tournament_id, first_group.uuid, owner_id
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

    # --- Registration ---

    async def register_player(
        self, tournament_id: UUID, player_id: UUID,
        *, force: bool = False,
    ) -> e.TournamentRegistration:
        """Register a player.

        Args:
            force: If True, allow late-join even when registration is closed
                   (organizer adding a player to a running tournament).
        """
        t = await self._get_tournament_or_fail(tournament_id)
        if not t.is_registration_open and not force:
            raise TournamentError("Registration is closed")
        if t.status == e.TournamentStatus.FINISHED:
            raise TournamentError("Tournament is finished")
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
        t = await self._tournaments.get(tournament_id)
        is_doubles = t is not None and t.player_mode == "doubles"
        matches = await self._matches.list_by_stage(stage_id)

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
        return standings_engine.compute_standings(match_results, rules=stage.rules)

    # --- Swiss draw ---

    async def draw_swiss_round(
        self, tournament_id: UUID, stage_id: UUID, owner_id: UUID
    ) -> list[e.Match]:
        """Draw the next Swiss round.

        For DYP doubles: forms new random teams each round, handles bye.
        For singles: pairs players, handles bye.
        """
        t = await self._get_tournament_or_fail(tournament_id)
        if t.status != e.TournamentStatus.RUNNING:
            raise TournamentError("Tournament must be RUNNING to draw rounds")
        stage = await self._get_stage_or_fail(tournament_id, stage_id)
        if stage.stage_type != "group":
            raise TournamentError("Swiss draw only for group stages")

        regs = await self._tournaments.list_registrations(tournament_id)
        active_player_ids = [r.player_id for r in regs if not r.is_paused]

        if len(active_player_ids) < 2:
            raise TournamentError("Not enough active players")

        existing = await self._matches.list_by_stage(stage_id)
        current_round = max((m.round_number for m in existing), default=0) + 1
        is_doubles = (t.player_mode == "doubles")

        # --- Bye selection ---
        # Count games played per player; player(s) with most games sit out
        games_played = self._count_games_played(existing, active_player_ids)
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
            team_formation = getattr(stage, "team_formation", "random") or "random"
            random_rounds = getattr(stage, "random_rounds", 2) or 2

            if team_formation == "fixed":
                # Reuse existing teams
                teams = await self._teams.list_by_tournament(tournament_id)
                # Filter to teams whose players are all in playing_ids
                playing_set = set(playing_ids)
                teams = [t for t in teams
                         if t.player_1_id in playing_set
                         and t.player_2_id in playing_set]
            elif team_formation == "random" or current_round <= random_rounds:
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
                standings = self._player_standings(existing, playing_ids)
                teams = []
                top_half = standings[:len(standings) // 2]
                bottom_half = standings[len(standings) // 2:]
                random.shuffle(bottom_half)
                for top, bot in zip(top_half, bottom_half):
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
        history = self._build_match_history(existing)
        pairings = swiss_engine.generate_swiss_round(
            participant_ids, history, stage.rules
        )

        best_of = (stage.rules or {}).get("best_of", 1)
        table_count = (t.settings or {}).get("table_count", 4)
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

    @staticmethod
    def _count_games_played(
        matches: list[e.Match], player_ids: list[UUID]
    ) -> dict[UUID, int]:
        """Count how many matches each player has participated in."""
        counts: dict[UUID, int] = {pid: 0 for pid in player_ids}
        for m in matches:
            if m.player_a_id and m.player_a_id in counts:
                counts[m.player_a_id] += 1
            if m.player_b_id and m.player_b_id in counts:
                counts[m.player_b_id] += 1
            # For doubles: count team players too
            # (would need team lookup — for now we track at match level)
        return counts

    @staticmethod
    def _player_standings(
        matches: list[e.Match], player_ids: list[UUID]
    ) -> list[UUID]:
        """Rank players by points (3 win, 1 draw) for from_results pairing."""
        points: dict[UUID, int] = {pid: 0 for pid in player_ids}
        for m in matches:
            if m.status != "finished":
                continue
            a, b = m.player_a_id, m.player_b_id
            if a and b and a in points and b in points:
                sa = sum(g.score_a for g in (m.games or []))
                sb = sum(g.score_b for g in (m.games or []))
                if sa > sb:
                    points[a] += 3
                elif sb > sa:
                    points[b] += 3
                else:
                    points[a] += 1
                    points[b] += 1
        return sorted(player_ids, key=lambda pid: -points[pid])

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
            if match.tournament_id:
                await event_hub.publish(Event(
                    "match_finished", match.tournament_id,
                    {"match_id": str(match.uuid), "winner_side": status.winner_side},
                ))
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

    async def _auto_assign_tables(
        self,
        tournament_id: UUID,
        new_matches: list[e.Match],
        existing_matches: list[e.Match],
        tournament_settings: dict | None,
    ) -> None:
        """Auto-assign tables to newly created matches if tables are available."""
        if self._tables is None:
            return

        tables = await self._tables.list_by_tournament(tournament_id)
        if not tables:
            return

        from league_app.domain.settings import TournamentSettings
        settings = TournamentSettings()
        if tournament_settings:
            settings = settings.merge(tournament_settings)

        # Build table history from existing matches
        history: list[table_engine.TableHistoryEntry] = []
        for m in existing_matches:
            if m.table_number is None:
                continue
            # Find table by number
            table_match = next(
                (t for t in tables if t.number == m.table_number), None
            )
            if table_match is None:
                continue
            for pid in [m.player_a_id, m.player_b_id, m.team_a_id, m.team_b_id]:
                if pid:
                    history.append(table_engine.TableHistoryEntry(
                        participant_id=pid,
                        table_uuid=table_match.uuid,
                        table_type=table_match.table_type,
                        round_number=m.round_number,
                    ))

        # Build match list for assignment
        matches_needing = []
        for m in new_matches:
            participants = [p for p in [m.player_a_id, m.player_b_id,
                                        m.team_a_id, m.team_b_id] if p]
            matches_needing.append((m.uuid, participants))

        table_infos = [
            table_engine.TableInfo(
                uuid=t.uuid, name=t.name, number=t.number,
                table_type=t.table_type, status=t.status,
            )
            for t in tables
        ]

        assignments = table_engine.assign_tables(
            matches_needing, table_infos,
            history=history, rotate_tables=settings.rotate_tables,
        )

        # Apply assignments
        for m in new_matches:
            if m.uuid in assignments:
                assigned_table = next(
                    t for t in tables if t.uuid == assignments[m.uuid]
                )
                m.table_number = assigned_table.number
                await self._matches.update(m)