"""Research compiler for building the ranked player list.

Provides helpers for compiling player rankings from free sources
into a unified ranked_players.json that the draft-day system consumes.
"""

import json
from pathlib import Path

from models.player import Player


OUTPUT_PATH = Path("data/ranked_players.json")


def create_player(
    name: str,
    team: str,
    positions: list[str],
    overall_rank: int,
    tier: int = 0,
    positional_rank: dict[str, int] | None = None,
    projected_stats: dict | None = None,
    notes: str = "",
) -> Player:
    """Create a Player entry for the ranked list."""
    return Player(
        name=name,
        team=team,
        positions=positions,
        overall_rank=overall_rank,
        positional_rank=positional_rank or {},
        tier=tier,
        projected_stats=projected_stats or {},
        notes=notes,
    )


def save_ranked_list(players: list[Player], path: str | Path = OUTPUT_PATH) -> None:
    """Save the compiled ranked list to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [p.to_dict() for p in players]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(players)} players to {path}")


def load_ranked_list(path: str | Path = OUTPUT_PATH) -> list[Player]:
    """Load a previously compiled ranked list."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Player.from_dict(p) for p in data]


def merge_rankings(
    base: list[Player],
    updates: dict[str, dict],
) -> list[Player]:
    """Merge additional data into an existing ranked list."""
    name_map = {p.name.lower(): p for p in base}
    for name, fields in updates.items():
        player = name_map.get(name.lower())
        if player:
            for key, value in fields.items():
                if hasattr(player, key):
                    setattr(player, key, value)
    return base
