from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class Player(Base):
    __tablename__ = "players"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    nickname: Mapped[str] = mapped_column(default=None)
    first_name: Mapped[Optional[str]] = mapped_column(default=None)
    last_name: Mapped[Optional[str]] = mapped_column(default=None)
    email: Mapped[Optional[str]] = mapped_column()
    user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(default=False)

    applied_tournaments = relationship(
        "Tournament",
        secondary="tournament_applicants",
        back_populates="applicants",
        lazy="selectin",
    )
