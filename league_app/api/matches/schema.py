from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# --- Game (individual game within a match) ---


class GameBase(BaseModel):
    score_a: int = 0
    score_b: int = 0
    is_finished: bool = False
    model_config = ConfigDict(from_attributes=True)


class GameCreate(GameBase):
    game_number: int = 1


class GameUpdate(BaseModel):
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    is_finished: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


class GameOutput(GameBase):
    uuid: UUID
    match_id: UUID
    game_number: int


# --- Match ---


class MatchBase(BaseModel):
    tournament_id: Optional[UUID] = None
    stage_id: Optional[UUID] = None
    round_number: int = 0
    table_number: Optional[int] = None
    bracket_position: Optional[int] = None
    best_of: int = 1
    # Singles
    player_a_id: Optional[UUID] = None
    player_b_id: Optional[UUID] = None
    # Doubles
    team_a_id: Optional[UUID] = None
    team_b_id: Optional[UUID] = None
    model_config = ConfigDict(from_attributes=True)


class MatchCreate(MatchBase):
    pass


class MatchUpdate(BaseModel):
    table_number: Optional[int] = None
    status: Optional[str] = None
    winner_side: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ScoreSubmit(BaseModel):
    score_a: int
    score_b: int


class ScoresSubmit(BaseModel):
    scores: list[ScoreSubmit]


class MatchOutput(MatchBase):
    uuid: UUID
    owner_id: Optional[UUID] = None
    status: str = "scheduled"
    winner_side: Optional[str] = None
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    player_a_nickname: Optional[str] = None
    player_b_nickname: Optional[str] = None
    team_a_name: Optional[str] = None
    team_b_name: Optional[str] = None
    is_deleted: bool = False
    games: list[GameOutput] = []
