from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class GameTable(Base):
    __tablename__ = "game_tables"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.uuid"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    number: Mapped[int] = mapped_column(Integer, default=1)
    table_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active"
    )  # inactive | active | in_use

    tournament = relationship("Tournament", lazy="selectin")
