import secrets
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, Numeric, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base

# Association tables — tournament_players has extra columns (paid, seed),
# so we use a full ORM model instead of a plain Table for it.

tournament_applicants = Table(
    "tournament_applicants",
    Base.metadata,
    Column("tournament_id", ForeignKey("tournaments.uuid"), primary_key=True),
    Column("player_id", ForeignKey("players.uuid"), primary_key=True),
)


tournament_organizers = Table(
    "tournament_organizers",
    Base.metadata,
    Column("tournament_id", ForeignKey("tournaments.uuid"), primary_key=True),
    Column("user_id", ForeignKey("user.id"), primary_key=True),
    Column("role", String(30), default="co-organizer"),
)


class TournamentRegistration(Base):
    """Many-to-many link between Tournament and Player with extra fields."""

    __tablename__ = "tournament_players"

    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.uuid"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(
        ForeignKey("players.uuid"), primary_key=True
    )
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)

    player = relationship("Player", lazy="selectin")
    tournament = relationship("Tournament", back_populates="registrations", lazy="selectin")


class Tournament(Base):
    __tablename__ = "tournaments"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(nullable=True)
    date: Mapped[str] = mapped_column(nullable=False)  # ISO date string
    location: Mapped[str] = mapped_column(nullable=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
    league_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("leagues.uuid"), nullable=True
    )

    player_mode: Mapped[str] = mapped_column(
        String(30), default="singles"
    )  # "singles" | "doubles"  # singles | doubles_dyp | doubles_monster_dyp | doubles_fixed
    entry_fee: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default="registration"
    )  # registration | running | finished

    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Secret token for QR self-registration (proves physical presence)
    registration_token: Mapped[str] = mapped_column(
        String(32), default=lambda: secrets.token_urlsafe(16)
    )

    is_deleted: Mapped[bool] = mapped_column(default=False)
    is_open: Mapped[bool] = mapped_column(default=True)
    is_registration_open: Mapped[bool] = mapped_column(default=True)

    league = relationship("League", back_populates="tournaments", lazy="selectin")
    stages = relationship(
        "Stage", back_populates="tournament", lazy="selectin",
        order_by="Stage.ordering",
    )
    matches = relationship("Match", back_populates="tournament", lazy="selectin")
    teams = relationship("Team", back_populates="tournament", lazy="selectin")
    registrations = relationship(
        "TournamentRegistration", back_populates="tournament", lazy="selectin",
    )
    applicants = relationship(
        "Player", secondary="tournament_applicants",
        back_populates="applied_tournaments", lazy="selectin",
    )
    co_organizers = relationship(
        "User", secondary="tournament_organizers", lazy="selectin",
    )
