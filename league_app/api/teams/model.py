from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class Team(Base):
    __tablename__ = "teams"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    player_1_id: Mapped[UUID] = mapped_column(
        ForeignKey("players.uuid"), nullable=False
    )
    player_2_id: Mapped[UUID] = mapped_column(
        ForeignKey("players.uuid"), nullable=False
    )
    tournament_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tournaments.uuid"), nullable=True
    )

    player_1 = relationship("Player", foreign_keys=[player_1_id], lazy="selectin")
    player_2 = relationship("Player", foreign_keys=[player_2_id], lazy="selectin")
    tournament = relationship("Tournament", back_populates="teams", lazy="selectin")
