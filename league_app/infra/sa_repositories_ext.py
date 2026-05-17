"""SQLAlchemy repositories (cont.) — Match games, Stage, Tournament, League."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.domain import entities as e
from league_app.api.matches import model as match_orm
from league_app.api.stages import model as stage_orm
from league_app.api.tournaments import model as tournament_orm
from . import mappers


# --- Match games (attached to SAMatchRepository) ---

class SAMatchGamesMixin:
    """Mixin to extend SAMatchRepository with game CRUD."""

    _s: AsyncSession  # provided by SAMatchRepository

    async def list_games(self, match_id: UUID) -> list[e.Game]:
        rows = await self._s.scalars(
            select(match_orm.Game).filter(match_orm.Game.match_id == match_id)
            .order_by(match_orm.Game.game_number)
        )
        return [mappers.game_to_entity(r) for r in rows]

    async def create_game(self, game: e.Game) -> e.Game:
        m = mappers.game_to_orm(game)
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.game_to_entity(m)

    async def update_game(self, game: e.Game) -> e.Game:
        m = await self._s.get(match_orm.Game, game.uuid)
        if m is None:
            raise ValueError(f"Game {game.uuid} not found")
        m.score_a = game.score_a
        m.score_b = game.score_b
        m.is_finished = game.is_finished
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.game_to_entity(m)


# --- Stage ---

class SAStageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> e.Stage | None:
        m = await self._s.get(stage_orm.Stage, uuid)
        return mappers.stage_to_entity(m) if m else None

    async def list_by_tournament(self, tournament_id: UUID) -> list[e.Stage]:
        rows = await self._s.scalars(
            select(stage_orm.Stage).filter(
                stage_orm.Stage.tournament_id == tournament_id,
                stage_orm.Stage.is_deleted == False,  # noqa: E712
            ).order_by(stage_orm.Stage.ordering)
        )
        return [mappers.stage_to_entity(r) for r in rows]

    async def create(self, stage: e.Stage) -> e.Stage:
        m = stage_orm.Stage(
            uuid=stage.uuid, tournament_id=stage.tournament_id, name=stage.name,
            stage_type=stage.stage_type, ordering=stage.ordering, status=stage.status,
            advancement_count=stage.advancement_count, rules=stage.rules,
            pairing=stage.pairing, team_formation=stage.team_formation,
            random_rounds=stage.random_rounds,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.stage_to_entity(m)

    async def update(self, stage: e.Stage) -> e.Stage:
        m = await self._s.get(stage_orm.Stage, stage.uuid)
        if m is None:
            raise ValueError(f"Stage {stage.uuid} not found")
        for f in (
            "name", "stage_type", "ordering", "status", "advancement_count",
            "rules", "is_deleted", "pairing", "team_formation", "random_rounds",
        ):
            setattr(m, f, getattr(stage, f))
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.stage_to_entity(m)

    async def delete(self, uuid: UUID) -> None:
        await self._s.execute(
            update(stage_orm.Stage).filter(stage_orm.Stage.uuid == uuid).values(is_deleted=True)
        )
        await self._s.flush()


# --- Tournament ---

class SATournamentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> e.Tournament | None:
        m = await self._s.get(tournament_orm.Tournament, uuid)
        return mappers.tournament_to_entity(m) if m else None

    async def list_all(self, include_deleted: bool = False) -> list[e.Tournament]:
        q = select(tournament_orm.Tournament)
        if not include_deleted:
            q = q.filter(tournament_orm.Tournament.is_deleted == False)  # noqa: E712
        rows = await self._s.scalars(q)
        return [mappers.tournament_to_entity(r) for r in rows]

    async def list_by_league(self, league_id: UUID) -> list[e.Tournament]:
        rows = await self._s.scalars(
            select(tournament_orm.Tournament).filter(
                tournament_orm.Tournament.league_id == league_id,
                tournament_orm.Tournament.is_deleted == False,  # noqa: E712
            )
        )
        return [mappers.tournament_to_entity(r) for r in rows]

    async def create(self, t: e.Tournament) -> e.Tournament:
        m = tournament_orm.Tournament(
            uuid=t.uuid, owner_id=t.owner_id, date=t.date, name=t.name,
            location=t.location, league_id=t.league_id, format=t.format,
            entry_fee=t.entry_fee, status=t.status, settings=t.settings,
            is_open=t.is_open,
            is_registration_open=t.is_registration_open,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.tournament_to_entity(m)

    async def update(self, t: e.Tournament) -> e.Tournament:
        m = await self._s.get(tournament_orm.Tournament, t.uuid)
        if m is None:
            raise ValueError(f"Tournament {t.uuid} not found")
        for f in ("name", "date", "location", "league_id", "player_mode",
                   "entry_fee", "registration_token", "status", "settings",
                   "is_deleted", "is_open", "is_registration_open"):
            setattr(m, f, getattr(t, f))
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.tournament_to_entity(m)

    async def delete(self, uuid: UUID) -> None:
        await self._s.execute(
            update(tournament_orm.Tournament)
            .filter(tournament_orm.Tournament.uuid == uuid).values(is_deleted=True)
        )
        await self._s.flush()
