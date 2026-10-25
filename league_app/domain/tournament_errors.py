"""Exceptions raised by the tournament domain service.

Kept in a leaf module so that ``TournamentService`` mixins (which
live alongside the main service) can import the exception without
re-importing the service itself, avoiding circular imports.
"""

from __future__ import annotations


class TournamentError(Exception):
    """Raised when a business rule is violated."""
    pass


class PermissionDeniedError(TournamentError):
    """Raised when the acting user may not perform the operation.

    A subclass of :class:`TournamentError` so that existing
    ``except TournamentError`` handlers keep working; routers map it to
    HTTP 403 instead of 400.
    """
    pass
