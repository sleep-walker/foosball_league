"""Tournament settings — a unified configuration object.

Inspired by kickertool Settings.  The Tournament holds a default
``TournamentSettings``.  Each Stage can optionally override individual
fields (stage-level rules take precedence where set).

Usage::

    ts = TournamentSettings()               # all defaults
    ts = TournamentSettings(goals_to_win=6)  # override one field
    effective = ts.merge(stage_overrides)     # stage overrides tournament defaults
"""

from __future__ import annotations

from dataclasses import dataclass, fields, asdict
from typing import Any, Optional


@dataclass
class TournamentSettings:
    """Flat settings object — all tournament/stage rules in one place.

    Kickertool equivalents in comments.
    """

    # --- Mode / format ---
    mode: str = "swiss_dyp"
    # "swiss_dyp"            — Swiss + random teams each round (kickertool SWISS_DYP)
    # "swiss_fixed"          — Swiss + fixed teams (kickertool SWISS_TUPEL)
    # "singles"              — Swiss singles
    # "monster_dyp"          — Swiss + aggressive team rotation
    # "elimination"          — Single-elimination bracket only
    # "group_then_elimination" — Group stage followed by elimination

    # --- Table management ---
    table_count: int = 2                   # kickertool: tableCount
    rotate_tables: bool = True             # our extension: try to rotate table types

    # --- Round / match rules ---
    random_rounds: int = 2                 # kickertool: randomRounds (random before Swiss)
    total_rounds: Optional[int] = None     # max rounds (None = unlimited)
    goals_to_win: int = 6                  # kickertool: goalsToWin (points per game)
    matches_to_win: int = 1                # kickertool: matchesToWin (best-of-N → games to win)
    minutes_per_match: Optional[int] = None  # kickertool: minutesPerMatch (time limit)

    # --- Scoring ---
    points_for_win: int = 3                # kickertool: pointsForWinner (default 2 there)
    points_for_draw: int = 1               # kickertool: pointsForDraw
    points_for_loss: int = 0               # our extension
    draw_allowed: bool = True              # whether group games can end in a draw

    # --- Elimination specifics ---
    consolation_match: bool = True         # 3rd-place match
    margin_in_decider: int = 2             # required margin in deciding games
    advancement_count: Optional[int] = None  # how many advance from group to elimination

    # --- Teams ---
    fixed_teams: bool = False              # kickertool: fixedTeams

    def merge(self, overrides: dict[str, Any] | None) -> TournamentSettings:
        """Return a new TournamentSettings with ``overrides`` applied.

        Used to let stage-level rules override tournament defaults.
        """
        if not overrides:
            return self
        data = asdict(self)
        data.update({k: v for k, v in overrides.items() if v is not None})
        valid_keys = {f.name for f in fields(TournamentSettings)}
        return TournamentSettings(**{k: v for k, v in data.items() if k in valid_keys})

    def to_stage_rules(self) -> dict[str, Any]:
        """Convert to the JSON dict used in Stage.rules."""
        return {
            "points_per_game": self.goals_to_win,
            "best_of": (self.matches_to_win * 2) - 1,  # matches_to_win=2 → best_of=3
            "draw_allowed": self.draw_allowed,
            "points_for_win": self.points_for_win,
            "points_for_draw": self.points_for_draw,
            "points_for_loss": self.points_for_loss,
            "margin_in_decider": self.margin_in_decider,
            "consolation_match": self.consolation_match,
        }

    @classmethod
    def from_stage_rules(cls, rules: dict[str, Any] | None) -> TournamentSettings:
        """Reconstruct settings from a Stage.rules JSON dict."""
        if not rules:
            return cls()
        best_of = rules.get("best_of", 1)
        return cls(
            goals_to_win=rules.get("points_per_game", 6),
            matches_to_win=(best_of // 2) + 1,
            draw_allowed=rules.get("draw_allowed", True),
            points_for_win=rules.get("points_for_win", 3),
            points_for_draw=rules.get("points_for_draw", 1),
            points_for_loss=rules.get("points_for_loss", 0),
            margin_in_decider=rules.get("margin_in_decider", 2),
            consolation_match=rules.get("consolation_match", True),
        )
