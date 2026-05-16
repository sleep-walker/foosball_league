"""League domain entity — separated to keep entities.py under 150 lines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID


@dataclass
class League:
    uuid: UUID
    owner_id: UUID
    name: str
    description: str = ""
    registration_type: str = "open"   # open | restricted
    scoring_type: str = "placement_points"  # placement_points | elo | win_loss
    scoring_config: Optional[dict[str, Any]] = None
    default_game_rules: Optional[dict[str, Any]] = None  # default stage rules for tournaments
    is_deleted: bool = False
    is_open: bool = True
    is_registration_open: bool = True
