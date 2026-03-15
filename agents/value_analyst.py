from dataclasses import dataclass

from models.player import Player
from models.roster import Roster
from models.draft_board import DraftBoard
from config_loader import DerivedConfig


@dataclass
class Recommendation:
    """A single pick recommendation."""

    player: Player
    score: float
    rationale: str
    is_preferred: bool = False

    def display(self, rank: int) -> str:
        prefix = "*" if self.is_preferred else " "
        positions = "/".join(self.player.positions)
        return (
            f"  {prefix} {rank}. {self.player.name} ({positions}) "
            f"-- Rank {self.player.overall_rank}, Tier {self.player.tier}\n"
            f"       {self.rationale}"
        )


class ValueAnalystAgent:
    """Agent 3: Identifies best value picks based on rankings, scarcity, and need."""

    BASE_WEIGHTS = {
        "rank_value": 0.35,
        "positional_scarcity": 0.20,
        "roster_need": 0.20,
        "tier_drop_off": 0.10,
        "category_balance": 0.15,
    }

    def __init__(self, derived_config: DerivedConfig):
        self.tag_to_category = derived_config.tag_to_category
        self.above_avg_thresholds = derived_config.above_avg_thresholds
        self.inverted_cats = derived_config.inverted_stats

    def analyze(
        self,
        board: DraftBoard,
        roster: Roster,
        roster_analysis: dict,
        board_analysis: dict,
    ) -> list[Recommendation]:
        """Score candidates and produce ranked recommendations."""
        weights = self._adjust_weights(board_analysis)
        candidates = board.best_available(30)
        needs = set(roster_analysis["needs"])
        urgency = roster_analysis["urgency"]
        scarcity = board_analysis["scarcity"]
        weak_categories = roster_analysis.get("weak_categories", [])

        scored = []
        for player in candidates:
            score = self._score_player(player, needs, urgency, scarcity, weights, roster_analysis)
            rationale = self._build_rationale(player, needs, urgency, scarcity, weak_categories)
            scored.append(Recommendation(player=player, score=score, rationale=rationale))

        scored.sort(key=lambda r: r.score, reverse=True)
        top_3 = scored[:3]

        if top_3:
            top_3[0].is_preferred = True

        return top_3

    def _score_player(
        self,
        player: Player,
        needs: set[str],
        urgency: dict[str, str],
        scarcity: dict[str, dict],
        weights: dict[str, float],
        roster_analysis: dict | None = None,
    ) -> float:
        """Compute composite value score for a player."""
        rank_score = max(0, 100 - (player.overall_rank - 1) * 0.5)

        scarcity_score = 0.0
        for pos in player.positions:
            if pos in scarcity:
                pct_gone = scarcity[pos]["pct_gone"]
                scarcity_score = max(scarcity_score, pct_gone)

        need_score = 0.0
        for pos in player.positions:
            if pos in needs:
                level = urgency.get(pos, "low")
                if level == "critical":
                    need_score = max(need_score, 100.0)
                elif level == "moderate":
                    need_score = max(need_score, 60.0)
                else:
                    need_score = max(need_score, 30.0)

        tier_score = 0.0
        for pos in player.positions:
            if pos in scarcity and scarcity[pos]["tier_drop_off"]:
                drop = scarcity[pos]["tier_drop_off"]
                if drop["from_tier"] == player.tier and drop["players_remaining_in_tier"] <= 3:
                    tier_score = max(tier_score, 80.0)
                elif drop["from_tier"] == player.tier:
                    tier_score = max(tier_score, 40.0)

        cat_score = self._category_balance_score(player, roster_analysis)

        return (
            weights["rank_value"] * rank_score
            + weights["positional_scarcity"] * scarcity_score
            + weights["roster_need"] * need_score
            + weights["tier_drop_off"] * tier_score
            + weights["category_balance"] * cat_score
        )

    def _category_balance_score(self, player: Player, roster_analysis: dict | None) -> float:
        """Score 0-100 for how well a player addresses weak categories."""
        if not roster_analysis:
            return 50.0

        weak_cats = roster_analysis.get("weak_categories", [])
        if not weak_cats:
            return 50.0

        tags = set(player.projected_stats.get("category_tags", []))
        stats = player.projected_stats
        hits = 0
        max_possible = len(weak_cats) * 2

        for cat in weak_cats:
            matched_tag = False
            for tag, tag_cat in self.tag_to_category.items():
                if tag_cat == cat and tag in tags:
                    hits += 2
                    matched_tag = True
                    break
            if not matched_tag and cat == "WHIP" and "elite_ratios" in tags:
                hits += 2
                matched_tag = True

            if not matched_tag and cat in self.above_avg_thresholds:
                threshold = self.above_avg_thresholds[cat]
                val = stats.get(cat, 0)
                if cat in self.inverted_cats:
                    if val > 0 and val <= threshold:
                        hits += 1
                else:
                    if val >= threshold:
                        hits += 1

        return (hits / max_possible) * 100 if max_possible > 0 else 50.0

    def _adjust_weights(self, board_analysis: dict) -> dict[str, float]:
        """Shift weights as draft progresses."""
        total_drafted = board_analysis["total_drafted"]
        total_available = board_analysis["total_available"]
        total = total_drafted + total_available

        if total == 0:
            return dict(self.BASE_WEIGHTS)

        draft_progress = total_drafted / total

        weights = dict(self.BASE_WEIGHTS)
        if draft_progress > 0.5:
            shift = min(0.15, (draft_progress - 0.5) * 0.3)
            weights["rank_value"] -= shift
            weights["positional_scarcity"] += shift * 0.4
            weights["roster_need"] += shift * 0.3
            weights["category_balance"] += shift * 0.3

        return weights

    def _build_rationale(
        self,
        player: Player,
        needs: set[str],
        urgency: dict[str, str],
        scarcity: dict[str, dict],
        weak_categories: list[str] | None = None,
    ) -> str:
        """Build a one-line rationale for recommending this player."""
        parts = []

        fills = [p for p in player.positions if p in needs]
        if fills:
            levels = [urgency.get(p, "low") for p in fills]
            if "critical" in levels:
                parts.append(f"fills critical need at {'/'.join(fills)}")
            else:
                parts.append(f"fills {'/'.join(fills)}")

        for pos in player.positions:
            if pos in scarcity and scarcity[pos]["pct_gone"] > 40:
                parts.append(f"{pos} scarcity at {scarcity[pos]['pct_gone']}%")
                break

        for pos in player.positions:
            if pos in scarcity and scarcity[pos]["tier_drop_off"]:
                drop = scarcity[pos]["tier_drop_off"]
                if drop["from_tier"] == player.tier and drop["players_remaining_in_tier"] <= 3:
                    parts.append(f"last {drop['players_remaining_in_tier']} in tier {player.tier} at {pos}")
                    break

        if weak_categories:
            tags = set(player.projected_stats.get("category_tags", []))
            stats = player.projected_stats
            helped_cats = []
            for cat in weak_categories:
                for tag, tag_cat in self.tag_to_category.items():
                    if tag_cat == cat and tag in tags:
                        helped_cats.append(cat)
                        break
                else:
                    if cat == "WHIP" and "elite_ratios" in tags:
                        helped_cats.append(cat)
                    elif cat in self.above_avg_thresholds:
                        threshold = self.above_avg_thresholds[cat]
                        val = stats.get(cat, 0)
                        if cat in self.inverted_cats:
                            if val > 0 and val <= threshold:
                                helped_cats.append(cat)
                        else:
                            if val >= threshold:
                                helped_cats.append(cat)
            if helped_cats:
                display = []
                for c in helped_cats:
                    if c == "proj_QS":
                        display.append("QS")
                    elif c == "proj_SVH":
                        display.append("SV+H")
                    else:
                        display.append(c)
                parts.append(f"helps weak {'/'.join(display)}")

        if player.overall_rank <= 20:
            parts.append("elite value")
        elif player.overall_rank <= 50:
            parts.append("strong value")

        return "; ".join(parts) if parts else "best available by overall rank"
