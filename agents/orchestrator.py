from concurrent.futures import ThreadPoolExecutor

from models.roster import Roster
from models.draft_board import DraftBoard
from config_loader import LeagueConfig, DerivedConfig
from .roster_tracker import RosterTrackerAgent
from .board_manager import BoardManagerAgent
from .value_analyst import ValueAnalystAgent, Recommendation


class Orchestrator:
    """Runs all three agents in parallel and synthesizes recommendations."""

    def __init__(self, config: LeagueConfig, derived_config: DerivedConfig):
        self.config = config
        self.derived_config = derived_config
        self.roster_agent = RosterTrackerAgent(derived_config)
        self.board_agent = BoardManagerAgent(derived_config)
        self.value_agent = ValueAnalystAgent(derived_config)

    def recommend(self, roster: Roster, board: DraftBoard) -> list[Recommendation]:
        """Run agents and return pick recommendations."""
        with ThreadPoolExecutor(max_workers=2) as pool:
            roster_future = pool.submit(self.roster_agent.analyze, roster)
            board_future = pool.submit(self.board_agent.analyze, board)

        roster_analysis = roster_future.result()
        board_analysis = board_future.result()

        recommendations = self.value_agent.analyze(
            board=board,
            roster=roster,
            roster_analysis=roster_analysis,
            board_analysis=board_analysis,
        )

        return recommendations

    def display_recommendations(self, recommendations: list[Recommendation]) -> str:
        """Format recommendations for CLI display."""
        if not recommendations:
            return "  No recommendations available."

        lines = []
        for i, rec in enumerate(recommendations, 1):
            lines.append(rec.display(i))
        return "\n".join(lines)

    def display_status(self, roster: Roster, board: DraftBoard) -> str:
        """Quick status summary."""
        available = len(board.available())
        drafted = len(board.draft_log)
        needs = roster.needs()

        lines = [
            f"Pick {drafted} | {available} players available | {len(needs)} positions open",
        ]

        urgency = roster.urgency()
        critical = [p for p, l in urgency.items() if l == "critical"]
        if critical:
            lines.append(f"Critical needs: {', '.join(critical)}")

        return " | ".join(lines) if len(lines) == 1 else "\n".join(lines)
