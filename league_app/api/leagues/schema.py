from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeagueBase(BaseModel):
    name: str
    description: Optional[str] = ""
    registration_type: str = "open"  # "open" | "restricted"
    scoring_type: str = "placement_points"  # placement_points | elo | win_loss
    scoring_config: Optional[dict[str, Any]] = None
    is_deleted: bool = False
    is_open: bool = True
    is_registration_open: bool = True
    model_config = ConfigDict(from_attributes=True)


class LeagueCreate(LeagueBase):
    owner_id: Optional[UUID] = None  # set by server


class LeagueUpdate(BaseModel):
    uuid: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    registration_type: Optional[str] = None
    scoring_type: Optional[str] = None
    scoring_config: Optional[dict[str, Any]] = None
    is_deleted: Optional[bool] = None
    is_open: Optional[bool] = None
    is_registration_open: Optional[bool] = None
    owner_id: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)


class LeagueOutput(LeagueBase):
    uuid: UUID
    owner_id: UUID
