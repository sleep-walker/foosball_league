from uuid import UUID, uuid4

from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class League(Base):
    __tablename__ = "leagues"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    description: Mapped[str] = mapped_column(default="")
    owner_id: Mapped[UUID] = mapped_column(nullable=False)
    registration_type: Mapped[str] = mapped_column(default="open")
    is_active: Mapped[bool] = mapped_column(default=True)
    is_open: Mapped[bool] = mapped_column(default=True)
    is_registration_open: Mapped[bool] = mapped_column(default=True)

    tournaments = relationship("Tournament", back_populates="league", lazy="selectin")