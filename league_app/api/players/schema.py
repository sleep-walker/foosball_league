from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class PlayerBase(BaseModel):
    nickname: str
    first_name: str | None = None
    last_name: str | None = None
    uuid: Optional[UUID] = None
    user_id: Optional[UUID] = None
    # secrets for registrations
    model_config = ConfigDict(from_attributes=True)


class PlayerCreate(PlayerBase):
    email: EmailStr | None = None


class PlayerUpdate(PlayerBase):
    uuid: UUID | None = None
    email: EmailStr | None = None


from typing import Any

class PlayerOutput(PlayerBase):
    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ):
        # Ensure uuid is present
        if getattr(obj, "uuid", None) is None:
            raise ValueError("uuid must be present in PlayerOutput")
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )
