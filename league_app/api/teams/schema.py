from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    player_1_id: UUID
    player_2_id: UUID
    tournament_id: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)


class TeamCreate(TeamBase):
    pass


class TeamOutput(TeamBase):
    uuid: UUID
