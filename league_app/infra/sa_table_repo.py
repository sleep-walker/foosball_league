"""SQLAlchemy implementation of ITableRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.domain import entities as e
from league_app.api.tables import model as table_orm
from . import mappers


class SATableRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> e.GameTable | None:
        m = await self._s.get(table_orm.GameTable, uuid)
        return mappers.table_to_entity(m) if m else None

    async def list_by_tournament(self, tournament_id: UUID) -> list[e.GameTable]:
        rows = await self._s.scalars(
            select(table_orm.GameTable).filter(
                table_orm.GameTable.tournament_id == tournament_id
            ).order_by(table_orm.GameTable.number)
        )
        return [mappers.table_to_entity(r) for r in rows]

    async def create(self, table: e.GameTable) -> e.GameTable:
        m = table_orm.GameTable(
            uuid=table.uuid, tournament_id=table.tournament_id,
            name=table.name, number=table.number,
            table_type=table.table_type, status=table.status,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.table_to_entity(m)

    async def update(self, table: e.GameTable) -> e.GameTable:
        m = await self._s.get(table_orm.GameTable, table.uuid)
        if m is None:
            raise ValueError(f"GameTable {table.uuid} not found")
        for f in ("name", "number", "table_type", "status"):
            setattr(m, f, getattr(table, f))
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.table_to_entity(m)

    async def delete(self, uuid: UUID) -> None:
        m = await self._s.get(table_orm.GameTable, uuid)
        if m:
            await self._s.delete(m)
            await self._s.flush()
