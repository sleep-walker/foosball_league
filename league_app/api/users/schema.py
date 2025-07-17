import uuid
from fastapi_users import schemas


class UserSchema(schemas.BaseUser[uuid.UUID]):
    """Base schema for User."""

    username: str


class UserCreate(schemas.BaseUserCreate):
    username: str


class UserUpdate(schemas.BaseUserUpdate):
    username: str | None = None  # Optional for partial updates
