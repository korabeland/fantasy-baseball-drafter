import json
from pathlib import Path

from .player import Player, DraftPick


class DraftBoard:
    """Manages the full player pool and draft history."""

    def __init__(self, players: list[Player]):
        self.players = players
        self.draft_log: list[DraftPick] = []
        self._pick_counter = 0

    @classmethod
    def from_json(cls, path: str | Path) -> "DraftBoard":
        """Load player pool from ranked_players.json."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        players = [Player.from_dict(p) for p in data]
        return cls(players)

    def save_draft_log(self, path: str | Path) -> None:
        """Save the draft log to JSON."""
        path = Path(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([pick.to_dict() for pick in self.draft_log], f, indent=2)

    def save_state(self, path: str | Path, draft_position: int | None = None, current_round: int = 1) -> None:
        """Save minimal draft state for replay."""
        path = Path(path)
        picks = [
            {"name": pick.player.name, "drafter": pick.drafter, "round": pick.round_number}
            for pick in self.draft_log
        ]
        state = {
            "draft_position": draft_position,
            "current_round": current_round,
            "picks": picks,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def load_state(self, path: str | Path) -> dict:
        """Load and replay draft state from a saved state file."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)

        for pick_data in state["picks"]:
            self.record_pick(
                player_name=pick_data["name"],
                drafter=pick_data["drafter"],
                round_number=pick_data["round"],
            )

        return state

    def record_pick(self, player_name: str, drafter: str, round_number: int) -> Player:
        """Record a draft pick -- marks player as drafted and logs it."""
        player = self._find_player(player_name)
        if player.drafted:
            raise ValueError(f"{player.name} has already been drafted (by {player.drafted_by})")

        self._pick_counter += 1
        player.drafted = True
        player.drafted_by = drafter
        player.draft_round = round_number
        player.draft_pick = self._pick_counter

        pick = DraftPick(
            pick_number=self._pick_counter,
            round_number=round_number,
            player=player,
            drafter=drafter,
        )
        self.draft_log.append(pick)
        return player

    def available(self, position: str | None = None) -> list[Player]:
        """Return available (undrafted) players, optionally filtered by position."""
        pool = [p for p in self.players if not p.drafted]
        if position:
            pool = [p for p in pool if position in p.positions]
        return sorted(pool, key=lambda p: p.overall_rank)

    def best_available(self, n: int = 10, position: str | None = None) -> list[Player]:
        """Top N available players by overall rank."""
        return self.available(position=position)[:n]

    def scarcity(self, position: str) -> dict:
        """Analyze positional scarcity."""
        available = self.available(position=position)
        total_at_position = len([p for p in self.players if position in p.positions])
        drafted_at_position = total_at_position - len(available)

        tier_distribution: dict[int, int] = {}
        for p in available:
            tier_distribution[p.tier] = tier_distribution.get(p.tier, 0) + 1

        tier_drop_off = None
        if available:
            current_tier = available[0].tier
            for p in available[1:]:
                if p.tier > current_tier:
                    tier_drop_off = {
                        "from_tier": current_tier,
                        "to_tier": p.tier,
                        "last_player_in_tier": available[available.index(p) - 1].name,
                        "players_remaining_in_tier": tier_distribution.get(current_tier, 0),
                    }
                    break

        return {
            "position": position,
            "total": total_at_position,
            "drafted": drafted_at_position,
            "remaining": len(available),
            "pct_gone": round(drafted_at_position / total_at_position * 100, 1) if total_at_position > 0 else 0,
            "tier_distribution": tier_distribution,
            "tier_drop_off": tier_drop_off,
        }

    def _find_player(self, name: str) -> Player:
        """Find a player by name with case-insensitive matching."""
        name_lower = name.strip().lower()

        for p in self.players:
            if p.name.lower() == name_lower:
                return p

        matches = [p for p in self.players if name_lower in p.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(m.name for m in matches[:5])
            raise ValueError(f"Ambiguous name '{name}'. Matches: {names}")

        raise ValueError(f"Player not found: '{name}'")
