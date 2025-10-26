from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict
from typing import Any


class LeagueBase(BaseModel):
    name: str
    description: Optional[str] = ""
    owner_id: UUID
    registration_type: str = "open"  # "open" or "restricted"
    is_active: bool = True
    is_open: bool = True
    is_registration_open: bool = True
    # secrets for registrations
    #uuid: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)


class LeagueCreate(LeagueBase):
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
        if getattr(obj, "uuid", None) is not None:
            raise ValueError("uuid must not be present in LeagueCreate")
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )


class LeagueUpdate(BaseModel):
    uuid: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    registration_type: Optional[str] = None
    is_active: Optional[bool] = None
    is_open: Optional[bool] = None
    is_registration_open: Optional[bool] = None
    owner_id: Optional[UUID] = None  # <-- Make this optional
    model_config = ConfigDict(from_attributes=True)


class LeagueOutput(LeagueBase):
    uuid: Optional[UUID] = None
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
        if getattr(obj, "uuid", None) is None:
            raise ValueError("uuid must be present in LeagueOutput")
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )
