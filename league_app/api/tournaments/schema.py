from uuid import UUID
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class TournamentBase(BaseModel):
    name: Optional[str] = None
    date: str
    location: Optional[str] = None
    owner_id: UUID
    model_config = ConfigDict(from_attributes=True)
    is_deleted: bool = False
    is_open: bool = True
    is_registration_open: bool = True


class TournamentCreate(TournamentBase):
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
            raise ValueError("uuid must not be present in TournamentCreate")
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )


class TournamentUpdate(BaseModel):
    uuid: Optional[UUID] = None
    # all other fields are optional
    name: Optional[str] = None
    date: Optional[str] = None
    location: Optional[str] = None
    owner_id: Optional[UUID] = None
    is_deleted: Optional[bool] = None
    is_open: Optional[bool] = None
    is_registration_open: Optional[bool] = None


class TournamentOutput(TournamentBase):
    uuid: UUID
    players: list[UUID] = []
    applicants: list[UUID] = []
