from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StageBase(BaseModel):
    name: str
    stage_type: str = "group"  # "group" | "elimination"
    ordering: int = 0
    tournament_id: UUID
    advancement_count: Optional[int] = None
    rules: Optional[dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)


class StageCreate(StageBase):
    pass


class StageUpdate(BaseModel):
    name: Optional[str] = None
    stage_type: Optional[str] = None
    ordering: Optional[int] = None
    advancement_count: Optional[int] = None
    rules: Optional[dict[str, Any]] = None
    is_deleted: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


class StageOutput(StageBase):
    uuid: UUID
    is_deleted: bool = False
