from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from league_app.api.players.schema import PlayerOutput


class RegistrationOutput(BaseModel):
    player_id: UUID
    paid: bool = False
    seed: Optional[int] = None
    player: Optional[PlayerOutput] = None
    model_config = ConfigDict(from_attributes=True)


class TournamentBase(BaseModel):
    name: Optional[str] = None
    date: str
    location: Optional[str] = None
    owner_id: UUID
    league_id: Optional[UUID] = None
    format: str = "singles"
    entry_fee: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)
    is_deleted: bool = False
    is_open: bool = True
    is_registration_open: bool = True


class TournamentCreate(TournamentBase):
    pass


class TournamentUpdate(BaseModel):
    uuid: Optional[UUID] = None
    name: Optional[str] = None
    date: Optional[str] = None
    location: Optional[str] = None
    owner_id: Optional[UUID] = None
    league_id: Optional[UUID] = None
    format: Optional[str] = None
    entry_fee: Optional[float] = None
    is_deleted: Optional[bool] = None
    is_open: Optional[bool] = None
    is_registration_open: Optional[bool] = None


class TournamentOutput(TournamentBase):
    uuid: UUID
    registrations: list[RegistrationOutput] = []
    applicants: list[PlayerOutput] = []
