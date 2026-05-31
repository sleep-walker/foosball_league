"""Stage-status transitions for :class:`TournamentService`.

This mixin owns the simple ``preparing → active → finished`` state
machine for stages. Stage creation and rule editing live in the API
layer (``stages_crud`` and ``api/stages/router.py``); only the
status transitions need to publish realtime events and therefore
belong on the service.

The host class is expected to supply ``self._stages`` (an
``IStageRepository``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from league_app.domain import entities as e
from league_app.domain.tournament_errors import TournamentError
from league_app.realtime.hub import Event, event_hub

if TYPE_CHECKING:
    from league_app.domain.repositories import IStageRepository


class StageMixin:
    if TYPE_CHECKING:
        _stages: IStageRepository

    async def activate_stage(self, stage_id: UUID) -> e.Stage:
        """Transition a stage from preparing → active."""
        stage = await self._stages.get(stage_id)
        if stage is None:
            raise TournamentError("Stage not found")
        if not e.StageStatus.can_transition(stage.status, "active"):
            raise TournamentError(
                f"Cannot activate stage in status '{stage.status}'"
            )
        stage.status = "active"
        return await self._stages.update(stage)

    async def finish_stage(self, stage_id: UUID) -> e.Stage:
        """Transition a stage from active → finished."""
        stage = await self._stages.get(stage_id)
        if stage is None:
            raise TournamentError("Stage not found")
        if not e.StageStatus.can_transition(stage.status, "finished"):
            raise TournamentError(
                f"Cannot finish stage in status '{stage.status}'"
            )
        stage.status = "finished"
        result = await self._stages.update(stage)
        await event_hub.publish(
            Event("stage_finished", stage.tournament_id, {"stage_id": str(stage_id)})
        )
        return result
