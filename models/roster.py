from dataclasses import dataclass, field

from .player import Player


# Slots excluded from draft needs (filled post-draft)
NON_DRAFT_SLOTS = {"IL"}


@dataclass
class RosterSlot:
    """A single roster position with capacity tracking."""

    position: str
    required: int
    filled: list[Player] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.required - len(self.filled))

    @property
    def is_full(self) -> bool:
        return len(self.filled) >= self.required


class Roster:
    """Tracks my drafted roster and positional needs."""

    def __init__(self, roster_slots: dict[str, int], flex_eligibility: dict[str, set[str]] | None = None):
        """Initialize from league config roster_slots dict.

        Args:
            roster_slots: e.g. {"C": 1, "1B": 1, "OF": 1, "LF": 1, ...}
            flex_eligibility: e.g. {"IF": {"C","1B","2B","3B","SS"}, ...}
                If None, uses default flex rules.
        """
        self.slots: dict[str, RosterSlot] = {
            pos: RosterSlot(position=pos, required=count)
            for pos, count in roster_slots.items()
        }
        self.flex_eligibility = flex_eligibility or {
            "IF": {"C", "1B", "2B", "3B", "SS"},
            "OF": {"LF", "CF", "RF", "OF"},
            "MI": {"2B", "SS"},
            "CI": {"1B", "3B"},
            "P": {"SP", "RP"},
        }

    @property
    def total_slots(self) -> int:
        return sum(
            slot.required for pos, slot in self.slots.items()
            if pos not in NON_DRAFT_SLOTS
        )

    @property
    def total_filled(self) -> int:
        return sum(
            len(slot.filled) for pos, slot in self.slots.items()
            if pos not in NON_DRAFT_SLOTS
        )

    @property
    def all_players(self) -> list[Player]:
        players = []
        for slot in self.slots.values():
            players.extend(slot.filled)
        return players

    def _can_fill_slot(self, player: Player, slot_pos: str) -> bool:
        """Check if a player is eligible to fill a given roster slot."""
        if slot_pos in player.positions:
            return True
        if slot_pos in self.flex_eligibility:
            return bool(set(player.positions) & self.flex_eligibility[slot_pos])
        if slot_pos == "UTIL":
            return player.is_hitter
        if slot_pos == "BN":
            return True
        return False

    def add_player(self, player: Player, position: str) -> None:
        """Add a drafted player to a roster slot."""
        if position not in self.slots:
            raise ValueError(f"Invalid roster position: {position}")
        slot = self.slots[position]
        if slot.is_full:
            raise ValueError(f"Roster slot {position} is already full ({slot.required}/{slot.required})")
        slot.filled.append(player)

    def best_slot_for(self, player: Player) -> str | None:
        """Find the best open roster slot for a player.

        Priority order:
        1. Exact position match
        2. Flex position match
        3. UTIL for hitters
        4. BN for anyone
        """
        # 1. Exact position match
        for pos in player.positions:
            if pos in self.slots and not self.slots[pos].is_full:
                return pos

        # 2. Flex slot match
        flex_priority = ["IF", "OF", "MI", "CI", "P"]
        for flex_pos in flex_priority:
            if flex_pos in self.slots and not self.slots[flex_pos].is_full:
                if flex_pos in self.flex_eligibility:
                    if set(player.positions) & self.flex_eligibility[flex_pos]:
                        return flex_pos

        # 3. UTIL for hitters
        if player.is_hitter and "UTIL" in self.slots and not self.slots["UTIL"].is_full:
            return "UTIL"

        # 4. Bench
        if "BN" in self.slots and not self.slots["BN"].is_full:
            return "BN"

        return None

    def needs(self) -> list[str]:
        """Return positions that still have open required slots (excluding BN and IL)."""
        return [
            pos for pos, slot in self.slots.items()
            if not slot.is_full and pos not in ("BN", "IL")
        ]

    def urgency(self) -> dict[str, str]:
        """Rate positional urgency: critical / moderate / low."""
        result = {}
        for pos, slot in self.slots.items():
            if pos in ("BN", "IL"):
                continue
            if slot.is_full:
                continue
            fill_ratio = len(slot.filled) / slot.required if slot.required > 0 else 1.0
            if slot.remaining == 1 and slot.required > 1:
                result[pos] = "moderate"
            elif slot.remaining == slot.required:
                result[pos] = "critical"
            elif fill_ratio < 0.5:
                result[pos] = "moderate"
            else:
                result[pos] = "low"
        return result

    def summary(self) -> str:
        """Human-readable roster summary."""
        lines = [f"Roster: {self.total_filled}/{self.total_slots} filled"]
        for pos, slot in self.slots.items():
            if pos in NON_DRAFT_SLOTS and not slot.filled:
                continue
            players = ", ".join(p.name for p in slot.filled) if slot.filled else "---"
            status = "FULL" if slot.is_full else f"{slot.remaining} open"
            lines.append(f"  {pos:>4}: {players} [{status}]")
        return "\n".join(lines)
