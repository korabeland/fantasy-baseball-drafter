from models.draft_board import DraftBoard
from config_loader import DerivedConfig


class BoardManagerAgent:
    """Agent 2: Tracks available player pool and positional scarcity."""

    def __init__(self, derived_config: DerivedConfig):
        self.tracked_positions = derived_config.tracked_positions

    def analyze(self, board: DraftBoard) -> dict:
        """Produce a board state analysis."""
        scarcity_report = {}
        for pos in self.tracked_positions:
            scarcity_report[pos] = board.scarcity(pos)

        scarce_positions = []
        for pos, data in scarcity_report.items():
            if data["pct_gone"] > 50:
                scarce_positions.append(pos)

        drop_off_alerts = []
        for pos, data in scarcity_report.items():
            if data["tier_drop_off"]:
                drop = data["tier_drop_off"]
                if drop["players_remaining_in_tier"] <= 3:
                    drop_off_alerts.append({
                        "position": pos,
                        "tier": drop["from_tier"],
                        "remaining_in_tier": drop["players_remaining_in_tier"],
                        "last_player": drop["last_player_in_tier"],
                    })

        return {
            "total_available": len(board.available()),
            "total_drafted": len(board.draft_log),
            "scarcity": scarcity_report,
            "scarce_positions": scarce_positions,
            "drop_off_alerts": drop_off_alerts,
            "best_available_10": [
                {"name": p.name, "rank": p.overall_rank, "positions": p.positions, "tier": p.tier}
                for p in board.best_available(10)
            ],
        }
