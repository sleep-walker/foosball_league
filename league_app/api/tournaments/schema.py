from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from league_app.api.players.schema import PlayerOutput
from league_app.api.stages.schema import StageOutput


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
    league_id: Optional[UUID] = None
    player_mode: str = "singles"  # "singles" | "doubles"
    entry_fee: Optional[float] = None
    settings: Optional[dict] = None  # {"table_count": 3, "goals_to_win": 6, ...}
    status: str = "registration"  # registration | running | finished
    model_config = ConfigDict(from_attributes=True)
    is_deleted: bool = False
    is_open: bool = True
    is_registration_open: bool = True


class TournamentCreate(TournamentBase):
    owner_id: Optional[UUID] = None  # set by server from logged-in user


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
    owner_id: UUID
    registrations: list[RegistrationOutput] = []
    applicants: list[PlayerOutput] = []
    stages: list[StageOutput] = []
