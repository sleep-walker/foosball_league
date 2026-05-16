from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from league_app.database import Base


class Stage(Base):
    """A phase of a tournament (e.g. group stage, elimination).

    ``rules`` is a JSON dict whose keys depend on ``stage_type``:

    Group stage example::

        {
            "rounds": 6,
            "points_per_game": 6,
            "draw_allowed": true,
            "points_for_win": 3,
            "points_for_draw": 1,
            "points_for_loss": 0
        }

    Elimination stage example::

        {
            "best_of": 3,
            "points_per_game": 6,
            "margin_in_decider": 2,
            "consolation_match": true
        }
    """

    __tablename__ = "stages"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(nullable=False)
    stage_type: Mapped[str] = mapped_column(
        String(20), default="group"
    )  # "group" | "elimination"
    ordering: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default="preparing"
    )  # "preparing" | "active" | "finished"
    advancement_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # how many advance to next stage
    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.uuid"), nullable=False
    )

    rules: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Pairing method for group stages
    pairing: Mapped[str] = mapped_column(
        String(20), default="swiss"
    )  # "swiss" | "round_robin" | "random"
    # Team formation for doubles
    team_formation: Mapped[str] = mapped_column(
        String(20), default="dyp"
    )  # "dyp" | "fixed" | "from_results" | "monster_dyp"
    # Note: legacy value "random" is treated as "dyp" alias for back-compat.
    # How many rounds to use random pairing before standings-based
    random_rounds: Mapped[int] = mapped_column(Integer, default=2)

    is_deleted: Mapped[bool] = mapped_column(default=False)

    tournament = relationship("Tournament", back_populates="stages", lazy="selectin")
    matches = relationship("Match", back_populates="stage", lazy="selectin")
