import uuid
from fastapi_users import schemas


class UserSchema(schemas.BaseUser[uuid.UUID]):
    """Base schema for User."""
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass
