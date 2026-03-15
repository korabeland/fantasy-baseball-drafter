from dataclasses import dataclass, field


@dataclass
class Player:
    """A player in the draft pool."""

    name: str
    team: str
    positions: list[str]
    overall_rank: int
    positional_rank: dict[str, int] = field(default_factory=dict)
    tier: int = 0
    projected_stats: dict = field(default_factory=dict)
    notes: str = ""
    drafted: bool = False
    drafted_by: str | None = None
    draft_round: int | None = None
    draft_pick: int | None = None

    @property
    def primary_position(self) -> str:
        return self.positions[0] if self.positions else "UTIL"

    @property
    def is_pitcher(self) -> bool:
        return any(p in ("SP", "RP", "P") for p in self.positions)

    @property
    def is_hitter(self) -> bool:
        return any(p not in ("SP", "RP", "P") for p in self.positions)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "team": self.team,
            "positions": self.positions,
            "overall_rank": self.overall_rank,
            "positional_rank": self.positional_rank,
            "tier": self.tier,
            "projected_stats": self.projected_stats,
            "notes": self.notes,
            "drafted": self.drafted,
            "drafted_by": self.drafted_by,
            "draft_round": self.draft_round,
            "draft_pick": self.draft_pick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DraftPick:
    """A single pick in the draft."""

    pick_number: int
    round_number: int
    player: Player
    drafter: str  # "me" or team name / "opponent"

    def to_dict(self) -> dict:
        return {
            "pick_number": self.pick_number,
            "round_number": self.round_number,
            "player_name": self.player.name,
            "player_team": self.player.team,
            "drafter": self.drafter,
        }
