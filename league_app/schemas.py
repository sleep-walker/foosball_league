from typing import Annotated, TypeVar
import uuid
from enum import Enum
from typing import TypeAlias
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from fastapi_users import schemas


# * User management


# * Players


# class TeamBase(BaseModel):
#     players: set[PlayerBase]
#     # sometimes the team can have a name
#     name: str | None


#     model_config = ConfigDict(from_attributes=True)


# class TeamCreate(TeamBase):
#     pass


# class TeamUpdate(TeamBase):
#     pass


# MatchResult: TypeAlias = list[tuple[int, int]] | list[TeamBase]


# class MatchBase(BaseModel):
#     team1: TeamBase
#     team2: TeamBase
#     result: MatchResult | None
#     started: datetime | None
#     finished: datetime | None

#     from_attributes: ExcludedField[bool | None] = True


# class MatchCreate(MatchBase):
#     pass


# class MatchUpdate(MatchBase):
#     pass


# class MatchRulesBase(BaseModel):
#     # number of goals to win a game
#     goals_to_win: int
#     # if not none, number of goals for draw (both teams have same)
#     goals_to_draw: int | None
#     # minimal difference between goal counts to recognize win
#     min_goal_diff: int
#     # maximum number of goals in game (ignoring minimal difference)
#     goal_limit: int | None

#     from_attributes: ExcludedField[bool | None] = True


# class TournamentStageType(Enum):
#     GROUP = 1
#     SINGLE_ELIMINATION = 2
#     DOUBLE_ELIMINATION = 3


# class TournamentOponentType(Enum):
#     DYP = 1
#     MONSTER_DYP = 2
#     TEAMS = 3
#     MANUAL = 4


# class TournamentStageStatus(Enum):
#     NOT_STARTED = 1
#     IN_PROGRESS = 2
#     FINISHED = 3


# class TournamentStageBase(BaseModel):
#     stage_type: TournamentStageType
#     stage_rules: MatchRulesBase
#     stage_name: str | None
#     players: list[PlayerBase] | None
#     teams: list[TeamBase] | None
#     rounds: list[list[MatchBase]]
#     status: TournamentStageStatus
#     results: None

#     from_attributes: ExcludedField[bool | None] = True


# class TournamentStageCreate(TournamentStageBase):
#     pass


# class TournamentStageUpdate(TournamentStageBase):
#     pass


# class TournamentBase(BaseModel):
#     stages: list[TournamentStageBase]
#     results: None

#     from_attributes: ExcludedField[bool | None] = True


# class TournamentCreate(TournamentBase):
#     pass


# class TournamentUpdate(TournamentBase):
#     pass


# class LeagueBase(BaseModel):
#     players: set[PlayerBase] = set()
#     tournaments: list[TournamentBase] = []
#     tournament_presets: list[TournamentBase] = []
#     name: str

#     from_attributes: ExcludedField[bool | None] = True


# class LeagueCreate(LeagueBase):
#     pass


# class LeagueUpdate(LeagueBase):
#     pass
