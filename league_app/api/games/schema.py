from uuid import UUID
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class GameBase(BaseModel):
    player_a_id: Optional[UUID] = None
    player_b_id: Optional[UUID] = None
    tournament_id: Optional[UUID] = None
    score_a: int = 0
    score_b: int = 0
    is_finished: bool = False
    uuid: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class GameCreate(GameBase):
    pass


class GameUpdate(GameBase):
    uuid: Optional[UUID] = None


class GameOutput(GameBase):
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
            raise ValueError("uuid must be present in GameOutput")
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )
