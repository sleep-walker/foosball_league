from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class League(Base):
    """A league groups players and/or tournaments over time.

    ``scoring_config`` is a JSON dict whose shape depends on ``scoring_type``:

    placement_points example::

        {"1": 10, "2": 7, "3": 5, "4": 4, "default": 1}

    elo example::

        {"k_factor": 32, "initial_rating": 1000}

    win_loss example::

        {"points_for_win": 3, "points_for_draw": 1, "points_for_loss": 0}
    """

    __tablename__ = "leagues"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    description: Mapped[str] = mapped_column(default="")
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
    registration_type: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # "open" | "restricted"

    scoring_type: Mapped[str] = mapped_column(
        String(30), default="placement_points"
    )  # placement_points | elo | win_loss
    scoring_config: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )

    is_deleted: Mapped[bool] = mapped_column(default=False)
    is_open: Mapped[bool] = mapped_column(default=True)
    is_registration_open: Mapped[bool] = mapped_column(default=True)

    tournaments = relationship("Tournament", back_populates="league", lazy="selectin")
    seasons = relationship("Season", back_populates="league", lazy="selectin")


class Season(Base):
    __tablename__ = "seasons"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    league_id: Mapped[UUID] = mapped_column(
        ForeignKey("leagues.uuid"), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)  # e.g. "Spring 2026"
    start_date: Mapped[Optional[str]] = mapped_column(nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    league = relationship("League", back_populates="seasons", lazy="selectin")