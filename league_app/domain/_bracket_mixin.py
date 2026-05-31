"""Bracket advancement & Monster-DYP reshuffle internals.

Pulled out of :class:`TournamentService` so the elimination-stage
post-game machinery sits in its own ~160-line module. The mixin only
calls back into the host service via two attributes:

* ``self._matches`` — :class:`IMatchRepository`
* ``self._teams`` — :class:`ITeamRepository`

Both ``_advance_bracket_winner`` and ``_monster_dyp_reshuffle_next_round``
remain underscore-prefixed because they are private collaborators of
:meth:`TournamentService.submit_game_score` / ``submit_batch_scores``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from league_app.domain import entities as e
from league_app.engine import bracket as bracket_engine
from league_app.engine import dyp as dyp_engine

if TYPE_CHECKING:
    from league_app.domain.repositories import (
        IMatchRepository,
        ITeamRepository,
    )

log = logging.getLogger(__name__)


class BracketMixin:
    if TYPE_CHECKING:
        _matches: IMatchRepository
        _teams: ITeamRepository

    async def _advance_bracket_winner(
        self, finished_match: e.Match, stage: e.Stage, winner_side: str
    ) -> None:
        """Place the winner (and loser for consolation) into the next bracket match."""
        is_doubles = finished_match.team_a_id is not None

        if winner_side == "a":
            winner_id = finished_match.team_a_id if is_doubles else finished_match.player_a_id
            loser_id = finished_match.team_b_id if is_doubles else finished_match.player_b_id
        else:
            winner_id = finished_match.team_b_id if is_doubles else finished_match.player_b_id
            loser_id = finished_match.team_a_id if is_doubles else finished_match.player_a_id

        if not winner_id:
            return

        all_matches = await self._matches.list_by_stage(finished_match.stage_id)

        # Reconstruct a Bracket from DB matches for advance_winner()
        has_consolation = any(
            m.bracket_position is not None
            and m.round_number == finished_match.round_number
            and m.bracket_position > finished_match.bracket_position
            and m.status == "scheduled"
            and m.player_a_id is None and m.player_b_id is None
            and m.team_a_id is None and m.team_b_id is None
            for m in all_matches
        ) or bool((stage.rules or {}).get("consolation_match", True))

        bracket = bracket_engine.Bracket(has_consolation=has_consolation)
        pos_to_match: dict[int, e.Match] = {}
        for m in all_matches:
            if m.bracket_position is None:
                continue
            a_id = m.team_a_id if is_doubles else m.player_a_id
            b_id = m.team_b_id if is_doubles else m.player_b_id
            # Determine winner for already-finished matches
            w_id = None
            l_id = None
            if m.status == "finished" and m.winner_side:
                if m.winner_side == "a":
                    w_id = a_id
                    l_id = b_id
                else:
                    w_id = b_id
                    l_id = a_id
            # Detect consolation: highest position in max round
            max_round = max(
                (mx.round_number for mx in all_matches if mx.bracket_position is not None),
                default=1,
            )
            is_consolation = (
                m.round_number == max_round
                and m.bracket_position == max(
                    (mx.bracket_position for mx in all_matches
                     if mx.bracket_position is not None and mx.round_number == max_round),
                    default=0,
                )
                and has_consolation
                and sum(1 for mx in all_matches
                        if mx.bracket_position is not None and mx.round_number == max_round) > 1
            )
            bm = bracket_engine.BracketMatch(
                position=m.bracket_position,
                round_number=m.round_number,
                participant_a_id=a_id,
                participant_b_id=b_id,
                is_consolation=is_consolation,
                winner_id=w_id,
                loser_id=l_id,
            )
            bracket.matches.append(bm)
            pos_to_match[m.bracket_position] = m

        # Run pure advancement logic
        bracket_engine.advance_winner(
            bracket, finished_match.bracket_position, winner_id, loser_id or winner_id,
        )

        # Apply changes from BracketMatch objects back to DB matches
        for bm in bracket.matches:
            db_match = pos_to_match.get(bm.position)
            if db_match is None or db_match.uuid == finished_match.uuid:
                continue
            # Check if participant slots changed
            old_a = db_match.team_a_id if is_doubles else db_match.player_a_id
            old_b = db_match.team_b_id if is_doubles else db_match.player_b_id
            if bm.participant_a_id != old_a or bm.participant_b_id != old_b:
                if is_doubles:
                    db_match.team_a_id = bm.participant_a_id
                    db_match.team_b_id = bm.participant_b_id
                else:
                    db_match.player_a_id = bm.participant_a_id
                    db_match.player_b_id = bm.participant_b_id

                await self._matches.update(db_match)
                log.info(
                    "Bracket advancement: winner of pos %d → pos %d",
                    finished_match.bracket_position, bm.position,
                )

        # --- Monster DYP reshuffle ---
        # When the next-round match has just become "fully populated" by the
        # advancement above (both team slots filled, no games started), and
        # the stage is configured for Monster DYP, reshuffle the 4 advancing
        # players into 2 new pairs. Applies equally to consolation matches.
        if is_doubles and stage.team_formation == "monster_dyp":
            await self._monster_dyp_reshuffle_next_round(
                finished_match.stage_id, finished_match.round_number + 1,
                tournament_id=finished_match.tournament_id,
            )

    async def _monster_dyp_reshuffle_next_round(
        self, stage_id: UUID, next_round: int, *, tournament_id: UUID | None
    ) -> None:
        """Reshuffle round ``next_round`` matches whose two feeders just finished.

        For each match in the target round that has both team_a_id and
        team_b_id set but no games yet, the 4 players from those teams are
        re-paired (former teammates must end up on opposite sides) and the
        match's participants are replaced with the newly created teams.
        """
        all_matches = await self._matches.list_by_stage(stage_id)
        for db_match in all_matches:
            if db_match.round_number != next_round:
                continue
            if db_match.status == "finished":
                continue
            if not (db_match.team_a_id and db_match.team_b_id):
                continue
            if db_match.games:
                continue
            team_a = await self._teams.get(db_match.team_a_id)
            team_b = await self._teams.get(db_match.team_b_id)
            if team_a is None or team_b is None:
                continue
            try:
                new_teams = dyp_engine.draw_monster_dyp_next_round([
                    (team_a.player_1_id, team_a.player_2_id),
                    (team_b.player_1_id, team_b.player_2_id),
                ])
            except ValueError as exc:
                log.warning("Monster DYP reshuffle skipped at round %d: %s",
                            next_round, exc)
                continue
            if len(new_teams) != 2:
                continue
            tid = tournament_id or db_match.tournament_id
            new_a = await self._teams.create(e.Team(
                uuid=uuid4(), tournament_id=tid,
                player_1_id=new_teams[0].player_1_id,
                player_2_id=new_teams[0].player_2_id,
            ))
            new_b = await self._teams.create(e.Team(
                uuid=uuid4(), tournament_id=tid,
                player_1_id=new_teams[1].player_1_id,
                player_2_id=new_teams[1].player_2_id,
            ))
            db_match.team_a_id = new_a.uuid
            db_match.team_b_id = new_b.uuid
            await self._matches.update(db_match)
            log.info(
                "Monster DYP reshuffle: round %d pos %d → teams %s, %s",
                next_round, db_match.bracket_position, new_a.uuid, new_b.uuid,
            )
