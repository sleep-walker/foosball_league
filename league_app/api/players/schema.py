import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class PlayerBase(BaseModel):
    nickname: str
    first_name: str | None
    last_name: str | None
    # secrets for registrations
    model_config = ConfigDict(from_attributes=True)


class PlayerCreate(PlayerBase):
    email: EmailStr


class PlayerUpdate(PlayerBase):
    uuid: uuid.UUID
    email: EmailStr | None


class PlayerOutput(PlayerBase):
    uuid: uuid.UUID
