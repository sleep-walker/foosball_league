"""SQLAlchemy implementations of repository interfaces (Player, Team, Match)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.domain import entities as e
from league_app.api.players import model as player_orm
from league_app.api.teams import model as team_orm
from league_app.api.matches import model as match_orm
from . import mappers


class SAPlayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> e.Player | None:
        m = await self._s.get(player_orm.Player, uuid)
        return mappers.player_to_entity(m) if m else None

    async def get_by_user_id(self, user_id: UUID) -> e.Player | None:
        m = await self._s.scalar(
            select(player_orm.Player).filter(player_orm.Player.user_id == user_id)
        )
        return mappers.player_to_entity(m) if m else None

    async def list_all(self) -> list[e.Player]:
        rows = await self._s.scalars(
            select(player_orm.Player).filter(player_orm.Player.is_deleted == False)  # noqa: E712
        )
        return [mappers.player_to_entity(r) for r in rows]

    async def create(self, player: e.Player) -> e.Player:
        m = mappers.player_to_orm(player)
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.player_to_entity(m)

    async def update(self, player: e.Player) -> e.Player:
        m = await self._s.get(player_orm.Player, player.uuid)
        if m is None:
            raise ValueError(f"Player {player.uuid} not found")
        for field in ("nickname", "first_name", "last_name", "email", "is_deleted"):
            setattr(m, field, getattr(player, field))
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.player_to_entity(m)

    async def delete(self, uuid: UUID) -> None:
        await self._s.execute(
            update(player_orm.Player).filter(player_orm.Player.uuid == uuid).values(is_deleted=True)
        )
        await self._s.flush()


class SATeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> e.Team | None:
        m = await self._s.get(team_orm.Team, uuid)
        return mappers.team_to_entity(m) if m else None

    async def list_by_tournament(self, tournament_id: UUID) -> list[e.Team]:
        rows = await self._s.scalars(
            select(team_orm.Team).filter(team_orm.Team.tournament_id == tournament_id)
        )
        return [mappers.team_to_entity(r) for r in rows]

    async def create(self, team: e.Team) -> e.Team:
        m = mappers.team_to_orm(team)
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.team_to_entity(m)


class SAMatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> e.Match | None:
        m = await self._s.get(match_orm.Match, uuid)
        return mappers.match_to_entity(m) if m else None

    async def list_by_tournament(self, tournament_id: UUID) -> list[e.Match]:
        rows = await self._s.scalars(
            select(match_orm.Match).filter(
                match_orm.Match.tournament_id == tournament_id,
                match_orm.Match.is_deleted == False,  # noqa: E712
            )
        )
        return [mappers.match_to_entity(r) for r in rows]

    async def list_by_stage(self, stage_id: UUID) -> list[e.Match]:
        from sqlalchemy.orm import subqueryload
        rows = await self._s.scalars(
            select(match_orm.Match)
            .filter(
                match_orm.Match.stage_id == stage_id,
                match_orm.Match.is_deleted == False,  # noqa: E712
            )
            .execution_options(populate_existing=True)
            .options(subqueryload(match_orm.Match.games))
        )
        return [mappers.match_to_entity(r) for r in rows]

    async def create(self, match: e.Match) -> e.Match:
        m = match_orm.Match(
            uuid=match.uuid, tournament_id=match.tournament_id,
            stage_id=match.stage_id, owner_id=match.owner_id,
            round_number=match.round_number, table_number=match.table_number,
            bracket_position=match.bracket_position, best_of=match.best_of,
            player_a_id=match.player_a_id, player_b_id=match.player_b_id,
            team_a_id=match.team_a_id, team_b_id=match.team_b_id,
            status=match.status, winner_side=match.winner_side,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.match_to_entity(m)

    async def update(self, match: e.Match) -> e.Match:
        m = await self._s.get(match_orm.Match, match.uuid)
        if m is None:
            raise ValueError(f"Match {match.uuid} not found")
        for f in (
            "status", "winner_side", "table_number", "bracket_position",
            "player_a_id", "player_b_id", "team_a_id", "team_b_id",
        ):
            setattr(m, f, getattr(match, f))
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.match_to_entity(m)

    async def delete(self, uuid: UUID) -> None:
        await self._s.execute(
            update(match_orm.Match).filter(match_orm.Match.uuid == uuid).values(is_deleted=True)
        )
        await self._s.flush()

    # Game sub-entity

    async def get_game(self, uuid: UUID) -> e.Game | None:
        m = await self._s.get(match_orm.Game, uuid)
        return mappers.game_to_entity(m) if m else None
