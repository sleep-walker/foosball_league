from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class Game(Base):
    __tablename__ = "games"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    player_a_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("players.uuid"), nullable=True
    )
    player_b_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("players.uuid"), nullable=True
    )
    tournament_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tournaments.uuid"), nullable=True
    )
    stage_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("stages.uuid"), nullable=True
    )
    owner_id: Mapped[Optional[UUID]] = mapped_column(nullable=True)

    score_a: Mapped[int] = mapped_column(Integer, default=0)
    score_b: Mapped[int] = mapped_column(Integer, default=0)

    is_finished: Mapped[bool] = mapped_column(default=False)
    is_deleted: Mapped[bool] = mapped_column(default=False)

    player_a = relationship("Player", foreign_keys=[player_a_id], lazy="selectin")
    player_b = relationship("Player", foreign_keys=[player_b_id], lazy="selectin")
    tournament = relationship("Tournament", back_populates="games", lazy="selectin")
    stage = relationship("Stage", back_populates="games", lazy="selectin")
