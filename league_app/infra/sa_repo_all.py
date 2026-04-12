"""Composed SQLAlchemy repository classes.

These classes combine base implementations with mixins to satisfy
the full repository interface contracts.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from .sa_repositories import SAMatchRepository, SAPlayerRepository, SATeamRepository
from .sa_repositories_ext import (
    SAMatchGamesMixin,
    SAStageRepository,
    SATournamentRepository,
)
from .sa_repositories_reg import SALeagueRepository, SATournamentRegistrationMixin


class FullSAMatchRepository(SAMatchRepository, SAMatchGamesMixin):
    """SAMatchRepository + game CRUD."""
    pass


class FullSATournamentRepository(SATournamentRepository, SATournamentRegistrationMixin):
    """SATournamentRepository + registration/applicant methods."""
    pass


# Re-export everything from one place
__all__ = [
    "SAPlayerRepository",
    "SATeamRepository",
    "FullSAMatchRepository",
    "SAStageRepository",
    "FullSATournamentRepository",
    "SALeagueRepository",
]
