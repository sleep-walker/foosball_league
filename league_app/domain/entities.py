"""Pure domain entities — no ORM, no framework dependencies.

These dataclasses represent the core business objects.  They are used by
services and the engine layer.  The infrastructure layer (repositories)
maps between these entities and ORM models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

@dataclass
class Player:
    uuid: UUID
    nickname: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    user_id: Optional[UUID] = None
    is_deleted: bool = False


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

@dataclass
class Team:
    uuid: UUID
    player_1_id: UUID
    player_2_id: UUID
    tournament_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Game  (single game inside a match)
# ---------------------------------------------------------------------------

@dataclass
class Game:
    uuid: UUID
    match_id: UUID
    game_number: int = 1
    score_a: int = 0
    score_b: int = 0
    is_finished: bool = False


# ---------------------------------------------------------------------------
# GameTable
# ---------------------------------------------------------------------------

class TableStatus:
    INACTIVE = "inactive"
    ACTIVE = "active"
    IN_USE = "in_use"

@dataclass
class GameTable:
    uuid: UUID
    tournament_id: UUID
    name: str                              # e.g. "Table 1" or "Bonzini #3"
    number: int = 1
    table_type: Optional[str] = None       # e.g. "bonzini", "tornado", "leonhart"
    status: str = "active"                 # inactive | active | in_use


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------

@dataclass
class Match:
    uuid: UUID
    tournament_id: Optional[UUID] = None
    stage_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    round_number: int = 0
    table_number: Optional[int] = None
    bracket_position: Optional[int] = None
    best_of: int = 1
    # Singles
    player_a_id: Optional[UUID] = None
    player_b_id: Optional[UUID] = None
    # Doubles
    team_a_id: Optional[UUID] = None
    team_b_id: Optional[UUID] = None
    status: str = "scheduled"          # scheduled | in_progress | finished
    winner_side: Optional[str] = None  # "a" | "b"
    is_deleted: bool = False
    games: list[Game] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

class StageStatus:
    PREPARING = "preparing"
    ACTIVE = "active"
    FINISHED = "finished"

    VALID = {PREPARING, ACTIVE, FINISHED}
    TRANSITIONS = {
        PREPARING: {ACTIVE},
        ACTIVE: {FINISHED},
        FINISHED: set(),
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        return target in cls.TRANSITIONS.get(current, set())


@dataclass
class Stage:
    uuid: UUID
    tournament_id: UUID
    name: str
    stage_type: str = "group"  # group | elimination
    ordering: int = 0
    status: str = "preparing"  # preparing | active | finished
    advancement_count: Optional[int] = None
    rules: Optional[dict[str, Any]] = None
    is_deleted: bool = False
    pairing: str = "swiss"  # swiss | round_robin | random (group only)
    team_formation: str = "dyp"  # dyp | fixed | from_results | monster_dyp
    random_rounds: int = 2


# ---------------------------------------------------------------------------
# Tournament registration
# ---------------------------------------------------------------------------

@dataclass
class TournamentRegistration:
    tournament_id: UUID
    player_id: UUID
    paid: bool = False
    seed: Optional[int] = None
    is_paused: bool = False


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

class TournamentStatus:
    REGISTRATION = "registration"
    RUNNING = "running"
    FINISHED = "finished"

    VALID = {REGISTRATION, RUNNING, FINISHED}
    TRANSITIONS = {
        REGISTRATION: {RUNNING},
        RUNNING: {FINISHED},
        FINISHED: set(),
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        return target in cls.TRANSITIONS.get(current, set())


@dataclass
class Tournament:
    uuid: UUID
    owner_id: UUID
    date: str
    name: Optional[str] = None
    location: Optional[str] = None
    league_id: Optional[UUID] = None
    player_mode: str = "singles"  # "singles" | "doubles"
    entry_fee: Optional[float] = None
    registration_token: str = ""  # secret for QR self-registration
    status: str = "registration"  # registration | running | finished
    settings: Optional[dict[str, Any]] = None  # JSON — TournamentSettings serialised
    is_deleted: bool = False
    is_open: bool = True
    is_registration_open: bool = True
    co_organizer_ids: list[UUID] = field(default_factory=list)
    registrations: list[TournamentRegistration] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------

@dataclass
class Season:
    uuid: UUID
    league_id: UUID
    name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True
