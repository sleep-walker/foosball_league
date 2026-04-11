from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base

# Association tables
tournament_players = Table(
    "tournament_players",
    Base.metadata,
    Column("tournament_id", ForeignKey("tournaments.uuid"), primary_key=True),
    Column("player_id", ForeignKey("players.uuid"), primary_key=True),
)

tournament_applicants = Table(
    "tournament_applicants",
    Base.metadata,
    Column("tournament_id", ForeignKey("tournaments.uuid"), primary_key=True),
    Column("player_id", ForeignKey("players.uuid"), primary_key=True),
)


class Tournament(Base):
    __tablename__ = "tournaments"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(nullable=True)
    date: Mapped[str] = mapped_column(nullable=False)  # ISO date string
    location: Mapped[str] = mapped_column(nullable=True)
    owner_id: Mapped[UUID] = mapped_column(nullable=False)
    league_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("leagues.uuid"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(default=False)
    is_open: Mapped[bool] = mapped_column(default=True)
    is_registration_open: Mapped[bool] = mapped_column(default=True)

    league = relationship("League", back_populates="tournaments", lazy="selectin")
    stages = relationship(
        "Stage", back_populates="tournament", lazy="selectin",
        order_by="Stage.ordering",
    )
    games = relationship("Game", back_populates="tournament", lazy="selectin")
    players = relationship(
        "Player", secondary="tournament_players",
        back_populates="tournaments", lazy="selectin",
    )
    applicants = relationship(
        "Player", secondary="tournament_applicants",
        back_populates="applied_tournaments", lazy="selectin",
    )
