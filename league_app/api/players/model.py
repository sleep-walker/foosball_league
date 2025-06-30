from typing import Optional
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from league_app.database import Base
from uuid import UUID, uuid4


class Player(Base):
    __tablename__ = "players"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    nickname: Mapped[str] = mapped_column(default=None)
    first_name: Mapped[Optional[str]] = mapped_column(default=None)
    last_name: Mapped[Optional[str]] = mapped_column(default=None)
    email: Mapped[Optional[str]] = mapped_column()
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("user.id"), nullable=True)

    deleted: Mapped[bool] = mapped_column(default=False)
