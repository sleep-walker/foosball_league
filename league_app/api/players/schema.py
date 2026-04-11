from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class PlayerBase(BaseModel):
    nickname: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    uuid: Optional[UUID] = None
    user_id: Optional[UUID] = None
    email: Optional[EmailStr] = None
    model_config = ConfigDict(from_attributes=True)


class PlayerCreate(PlayerBase):
    pass


class PlayerUpdate(BaseModel):
    uuid: Optional[UUID] = None
    nickname: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    model_config = ConfigDict(from_attributes=True)


class PlayerOutput(PlayerBase):
    uuid: UUID
    is_deleted: bool = False
