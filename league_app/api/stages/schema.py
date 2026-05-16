from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StageBase(BaseModel):
    name: str
    stage_type: str = "group"  # "group" | "elimination" | "round_robin"
    ordering: int = 0
    status: str = "preparing"  # "preparing" | "active" | "finished"
    tournament_id: UUID
    advancement_count: Optional[int] = None
    rules: Optional[dict[str, Any]] = None
    # Pairing method for group stages
    pairing: str = "swiss"  # "swiss" | "round_robin" | "random"
    # Team formation (doubles only)
    team_formation: str = "dyp"  # "dyp" | "fixed" | "from_results" | "monster_dyp"; legacy "random" == "dyp"
    # How many rounds to use random pairing before switching to standings-based
    random_rounds: int = 2
    model_config = ConfigDict(from_attributes=True)


class StageCreate(StageBase):
    pass


class StageUpdate(BaseModel):
    name: Optional[str] = None
    stage_type: Optional[str] = None
    ordering: Optional[int] = None
    status: Optional[str] = None
    advancement_count: Optional[int] = None
    rules: Optional[dict[str, Any]] = None
    pairing: Optional[str] = None
    team_formation: Optional[str] = None
    random_rounds: Optional[int] = None
    is_deleted: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


class StageOutput(StageBase):
    uuid: UUID
    is_deleted: bool = False
