from models.roster import Roster
from models.player import Player
from config_loader import DerivedConfig


class RosterTrackerAgent:
    """Agent 1: Analyzes current roster state and positional needs."""

    def __init__(self, derived_config: DerivedConfig):
        self.config = derived_config

    def analyze(self, roster: Roster) -> dict:
        """Produce a roster analysis snapshot."""
        needs = roster.needs()
        urgency = roster.urgency()

        critical = [pos for pos, level in urgency.items() if level == "critical"]
        moderate = [pos for pos, level in urgency.items() if level == "moderate"]

        result = {
            "total_filled": roster.total_filled,
            "total_slots": roster.total_slots,
            "needs": needs,
            "urgency": urgency,
            "critical_needs": critical,
            "moderate_needs": moderate,
            "summary": roster.summary(),
        }

        cat_analysis = self._analyze_categories(roster)
        result.update(cat_analysis)

        return result

    def _analyze_categories(self, roster: Roster) -> dict:
        """Analyze category coverage across drafted players."""
        players = roster.all_players
        if not players:
            return {
                "category_totals": {},
                "category_coverage": {},
                "weak_categories": [],
            }

        hitters = [p for p in players if p.is_hitter]
        pitchers = [p for p in players if p.is_pitcher]
        has_hitters = len(hitters) > 0
        has_pitchers = len(pitchers) > 0

        season_targets = self.config.season_targets
        counting_stats = self.config.counting_stats
        ratio_stats = self.config.ratio_stats
        inverted_stats = self.config.inverted_stats
        hitting_cats = self.config.hitting_cats
        pitching_cats = self.config.pitching_cats

        totals = {}
        coverage = {}

        for cat, target in season_targets.items():
            if cat in hitting_cats and not has_hitters:
                continue
            if cat in pitching_cats and not has_pitchers:
                continue

            if cat in counting_stats:
                total = sum(p.projected_stats.get(cat, 0) for p in players)
                totals[cat] = round(total, 1)
                coverage[cat] = round(total / target * 100, 1) if target else 0

            elif cat == "AVG":
                weighted_sum = 0
                weight_total = 0
                for p in hitters:
                    pa_proxy = p.projected_stats.get("R", 0) + p.projected_stats.get("HR", 0)
                    avg = p.projected_stats.get("AVG", 0)
                    if pa_proxy > 0 and avg > 0:
                        weighted_sum += avg * pa_proxy
                        weight_total += pa_proxy
                if weight_total > 0:
                    weighted_avg = weighted_sum / weight_total
                    totals[cat] = round(weighted_avg, 3)
                    if weighted_avg >= target:
                        coverage[cat] = 100.0
                    else:
                        coverage[cat] = round(weighted_avg / target * 100, 1)
                else:
                    totals[cat] = 0
                    coverage[cat] = 0

            elif cat in inverted_stats and cat in ratio_stats:
                # Weighted average using IP for pitching ratios
                weighted_sum = 0
                ip_total = 0
                for p in pitchers:
                    ip = p.projected_stats.get("IP", 0)
                    val = p.projected_stats.get(cat, 0)
                    if ip > 0 and val > 0:
                        weighted_sum += val * ip
                        ip_total += ip
                if ip_total > 0:
                    weighted_val = weighted_sum / ip_total
                    totals[cat] = round(weighted_val, 2)
                    if weighted_val <= target:
                        coverage[cat] = 100.0
                    else:
                        coverage[cat] = round(target / weighted_val * 100, 1)
                else:
                    totals[cat] = 0
                    coverage[cat] = 0

            elif cat in ratio_stats:
                # Non-inverted ratio (e.g. OBP, K/9) -- higher is better
                weighted_sum = 0
                weight_total = 0
                relevant = hitters if cat in hitting_cats else pitchers
                weight_key = "IP" if cat in pitching_cats else "R"
                for p in relevant:
                    w = p.projected_stats.get(weight_key, 0) + p.projected_stats.get("HR", 0)
                    val = p.projected_stats.get(cat, 0)
                    if w > 0 and val > 0:
                        weighted_sum += val * w
                        weight_total += w
                if weight_total > 0:
                    weighted_val = weighted_sum / weight_total
                    totals[cat] = round(weighted_val, 3)
                    if weighted_val >= target:
                        coverage[cat] = 100.0
                    else:
                        coverage[cat] = round(weighted_val / target * 100, 1)
                else:
                    totals[cat] = 0
                    coverage[cat] = 0

        # Identify weak categories: bottom 3 by coverage
        if coverage:
            sorted_cats = sorted(coverage.items(), key=lambda x: x[1])
            weak_categories = [cat for cat, _ in sorted_cats[:3]]
        else:
            weak_categories = []

        return {
            "category_totals": totals,
            "category_coverage": coverage,
            "weak_categories": weak_categories,
        }
