"""SQLAlchemy repositories (cont.) — Tournament registrations/applicants, League."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.domain import entities as e
from league_app.domain.entities_league import League as LeagueEntity
from league_app.api.tournaments import model as tournament_orm
from league_app.api.leagues import model as league_orm
from league_app.api.players import model as player_orm
from . import mappers


# --- Registration / applicant methods for SATournamentRepository ---

class SATournamentRegistrationMixin:
    """Mixin to add registration/applicant methods to SATournamentRepository."""

    _s: AsyncSession

    async def get_registration(
        self, tournament_id: UUID, player_id: UUID
    ) -> e.TournamentRegistration | None:
        m = await self._s.scalar(
            select(tournament_orm.TournamentRegistration).filter(
                tournament_orm.TournamentRegistration.tournament_id == tournament_id,
                tournament_orm.TournamentRegistration.player_id == player_id,
            )
        )
        return mappers.registration_to_entity(m) if m else None

    async def list_registrations(
        self, tournament_id: UUID
    ) -> list[e.TournamentRegistration]:
        rows = await self._s.scalars(
            select(tournament_orm.TournamentRegistration).filter(
                tournament_orm.TournamentRegistration.tournament_id == tournament_id,
            )
        )
        return [mappers.registration_to_entity(r) for r in rows]

    async def add_registration(
        self, reg: e.TournamentRegistration
    ) -> e.TournamentRegistration:
        m = tournament_orm.TournamentRegistration(
            tournament_id=reg.tournament_id, player_id=reg.player_id,
            paid=reg.paid, seed=reg.seed,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.registration_to_entity(m)

    async def update_registration(
        self, reg: e.TournamentRegistration
    ) -> e.TournamentRegistration:
        m = await self._s.scalar(
            select(tournament_orm.TournamentRegistration).filter(
                tournament_orm.TournamentRegistration.tournament_id == reg.tournament_id,
                tournament_orm.TournamentRegistration.player_id == reg.player_id,
            )
        )
        if m is None:
            raise ValueError("Registration not found")
        m.paid = reg.paid
        m.seed = reg.seed
        m.is_paused = reg.is_paused
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.registration_to_entity(m)

    async def remove_registration(self, tournament_id: UUID, player_id: UUID) -> bool:
        m = await self._s.scalar(
            select(tournament_orm.TournamentRegistration).filter(
                tournament_orm.TournamentRegistration.tournament_id == tournament_id,
                tournament_orm.TournamentRegistration.player_id == player_id,
            )
        )
        if m is None:
            return False
        await self._s.delete(m)
        await self._s.flush()
        return True

    async def list_applicants(self, tournament_id: UUID) -> list[e.Player]:
        t = await self._s.get(tournament_orm.Tournament, tournament_id)
        if t is None:
            return []
        return [mappers.player_to_entity(p) for p in (t.applicants or [])]

    async def add_applicant(self, tournament_id: UUID, player_id: UUID) -> None:
        t = await self._s.get(tournament_orm.Tournament, tournament_id)
        p = await self._s.get(player_orm.Player, player_id)
        if t and p:
            t.applicants.append(p)
            await self._s.flush()

    async def remove_applicant(self, tournament_id: UUID, player_id: UUID) -> None:
        t = await self._s.get(tournament_orm.Tournament, tournament_id)
        p = await self._s.get(player_orm.Player, player_id)
        if t and p and p in t.applicants:
            t.applicants.remove(p)
            await self._s.flush()


# --- League ---

class SALeagueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, uuid: UUID) -> LeagueEntity | None:
        m = await self._s.get(league_orm.League, uuid)
        return mappers.league_to_entity(m) if m else None

    async def list_all(self) -> list[LeagueEntity]:
        rows = await self._s.scalars(
            select(league_orm.League).filter(league_orm.League.is_deleted == False)  # noqa: E712
        )
        return [mappers.league_to_entity(r) for r in rows]

    async def search_by_name(self, name: str) -> list[LeagueEntity]:
        rows = await self._s.scalars(
            select(league_orm.League).filter(league_orm.League.name.ilike(f"%{name}%"))
        )
        return [mappers.league_to_entity(r) for r in rows]

    async def create(self, league: LeagueEntity) -> LeagueEntity:
        m = league_orm.League(
            uuid=league.uuid, owner_id=league.owner_id, name=league.name,
            description=league.description, registration_type=league.registration_type,
            scoring_type=league.scoring_type, scoring_config=league.scoring_config,
            is_open=league.is_open, is_registration_open=league.is_registration_open,
        )
        self._s.add(m)
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.league_to_entity(m)

    async def update(self, league: LeagueEntity) -> LeagueEntity:
        m = await self._s.get(league_orm.League, league.uuid)
        if m is None:
            raise ValueError(f"League {league.uuid} not found")
        for f in ("name", "description", "registration_type", "scoring_type",
                   "scoring_config", "is_deleted", "is_open", "is_registration_open"):
            setattr(m, f, getattr(league, f))
        await self._s.flush()
        await self._s.refresh(m)
        return mappers.league_to_entity(m)

    async def delete(self, uuid: UUID) -> None:
        await self._s.execute(
            update(league_orm.League).filter(league_orm.League.uuid == uuid).values(is_deleted=True)
        )
        await self._s.flush()
