"""Registration-management methods for :class:`TournamentService`.

This mixin owns the per-player registration lifecycle (register,
unregister, mark paid, pause, unpause). It assumes the host class
provides ``self._tournaments`` (an ``ITournamentRepository``),
``self._players`` (an ``IPlayerRepository``) and the
``_get_tournament_or_fail`` helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from league_app.domain import entities as e
from league_app.domain.tournament_errors import TournamentError

if TYPE_CHECKING:
    from league_app.domain.repositories import (
        IPlayerRepository,
        ITournamentRepository,
    )


class RegistrationMixin:
    # Repository handles supplied by the host service. Declared here for
    # type checkers only; the real attributes are set in
    # ``TournamentService.__init__``.
    if TYPE_CHECKING:
        _tournaments: ITournamentRepository
        _players: IPlayerRepository

        async def _get_tournament_or_fail(self, uuid: UUID) -> e.Tournament: ...

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

