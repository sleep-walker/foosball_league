from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class Match(Base):
    __tablename__ = "matches"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    stage_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("stages.uuid"), nullable=True
    )
    tournament_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tournaments.uuid"), nullable=True
    )
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )

    round_number: Mapped[int] = mapped_column(Integer, default=0)
    table_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bracket_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_of: Mapped[int] = mapped_column(Integer, default=1)

    # Singles participants
    player_a_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("players.uuid"), nullable=True
    )
    player_b_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("players.uuid"), nullable=True
    )
    # Doubles participants
    team_a_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("teams.uuid"), nullable=True
    )
    team_b_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("teams.uuid"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default="scheduled"
    )  # scheduled | in_progress | finished
    winner_side: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True
    )  # "a" | "b" | None

    is_deleted: Mapped[bool] = mapped_column(default=False)

    # Relationships
    stage = relationship("Stage", back_populates="matches", lazy="selectin")
    tournament = relationship("Tournament", back_populates="matches", lazy="selectin")
    player_a = relationship("Player", foreign_keys=[player_a_id], lazy="selectin")
    player_b = relationship("Player", foreign_keys=[player_b_id], lazy="selectin")
    team_a = relationship("Team", foreign_keys=[team_a_id], lazy="selectin")
    team_b = relationship("Team", foreign_keys=[team_b_id], lazy="selectin")
    games = relationship(
        "Game", back_populates="match", lazy="selectin", order_by="Game.game_number"
    )


class Game(Base):
    __tablename__ = "games"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.uuid"), nullable=False
    )
    game_number: Mapped[int] = mapped_column(Integer, default=1)
    score_a: Mapped[int] = mapped_column(Integer, default=0)
    score_b: Mapped[int] = mapped_column(Integer, default=0)
    is_finished: Mapped[bool] = mapped_column(default=False)

    match = relationship("Match", back_populates="games", lazy="selectin")
