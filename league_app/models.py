
""" from typing import TypeAlias
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlalchemy.ext.mutable import MutableList, MutableSet
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
 """
from league_app.api.players.model import Player
from league_app.api.users.model import User
from league_app.api.leagues.model import League

__all__ = ["Player", "User", "League"]

""" class Team(Base):
    __tablename__ = "teams"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    players = Column(MutableSet.as_mutable(ForeignKey("players.uuid")))
    name: Mapped[str] = mapped_column(nullable=True)

    deleted: Mapped[bool] = mapped_column(default=False)


MatchResult: TypeAlias = list[tuple[Team, Team]] | list[Team]


class Match(Base):
    __tablename__ = "matches"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team1: Mapped["Team"] = mapped_column(ForeignKey("teams.uuid"))
    team2: Mapped["Team"] = mapped_column(ForeignKey("teams.uuid"))
    result: Mapped[JSON] = mapped_column(type_=JSON, default=[])
    name = Column(String, nullable=True)

    deleted: Mapped[bool] = mapped_column(default=False)


class TournamentStage(Base):
    __tablename__ = "stages"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    matches = Column(MutableList.as_mutable(ForeignKey("matches.uuid")))
    name: Mapped[str] = mapped_column()
    stage_type: Mapped[str] = mapped_column()
    # stage_rules
    #    tournament: Mapped["Tournament"] = mapped_column(ForeignKey("tournaments.uuid"))

    deleted: Mapped[bool] = mapped_column(default=False)


class Tournament(Base):
    __tablename__ = "tournaments"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column()
    stages: Mapped["TournamentStage"] = mapped_column(ForeignKey("stages.uuid"))

    deleted: Mapped[bool] = mapped_column(default=False)
 """

""" class League(Base):
    __tablename__ = "leagues"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column()
    teams = Column(MutableSet.as_mutable(ForeignKey("teams.uuid")))
    players = Column(MutableSet.as_mutable(ForeignKey("players.uuid")))
    tournaments = Column(MutableSet.as_mutable(ForeignKey("tournaments.uuid")))

    deleted: Mapped[bool] = mapped_column(default=False)
 """
