"""Build the final ranked_players.json from all research data.

Merges:
1. Player rankings (backbone: name, team, positions, overall rank)
2. Projections (stat projections)
3. Relief pitcher data (saves + holds if SV+H league)
4. OF position resolution (LF/CF/RF from generic OF, if applicable)
5. QS estimation for starting pitchers (if QS league)
6. Tier assignment and positional ranks
7. Strategic adjustments (Phase 2)

Usage:
    python research/build_rankings.py
"""

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from research.compiler import create_player, save_ranked_list
from config_loader import LeagueConfig, DerivedConfig


# File paths
RANKINGS_PATH = Path("data/raw/yahoo_rankings.json")
PROJECTIONS_PATH = Path("data/raw/fangraphs_projections.json")
SVH_PATH = Path("data/raw/svh_relievers.json")
OF_POSITIONS_PATH = Path("data/raw/of_positions.json")
STRATEGIC_PATH = Path("research/strategic_adjustments.json")
OUTPUT_PATH = Path("data/ranked_players.json")
CONFIG_PATH = Path("config/league_config.json")
DERIVED_CONFIG_PATH = Path("config/derived_config.json")


def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fuzzy_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    """Find best fuzzy match for a player name."""
    name_lower = name.lower().strip()

    for c in candidates:
        if c.lower().strip() == name_lower:
            return c

    for c in candidates:
        if name_lower in c.lower() or c.lower() in name_lower:
            return c

    best_score = 0.0
    best_match = None
    for c in candidates:
        score = SequenceMatcher(None, name_lower, c.lower()).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = c

    return best_match


def resolve_of_positions(positions: list[str], player_name: str, of_mapping: dict) -> list[str]:
    """Replace generic 'OF' with specific LF/CF/RF where known."""
    if "OF" not in positions:
        return positions

    specific = of_mapping.get(player_name)
    if specific:
        result = [p for p in positions if p != "OF"]
        result.extend(specific)
        if "OF" not in result:
            result.append("OF")
        return result

    return positions


def estimate_qs_rate(ip: float, gs: int, era: float) -> float:
    """Estimate quality start rate from projections."""
    if gs == 0:
        return 0.0

    ip_per_gs = ip / gs

    if ip_per_gs >= 6.0 and era <= 3.50:
        return 0.70
    elif ip_per_gs >= 5.8 and era <= 4.00:
        return 0.55
    elif ip_per_gs >= 5.5 and era <= 4.50:
        return 0.40
    elif ip_per_gs >= 5.0:
        return 0.20
    else:
        return 0.10


def assign_tier(rank: int, tier_boundaries: list[int]) -> int:
    """Assign tier based on overall rank and config-driven boundaries."""
    for i, boundary in enumerate(tier_boundaries):
        if rank <= boundary:
            return i + 1
    return len(tier_boundaries) + 1


def compute_positional_ranks(players: list[dict]) -> dict[str, dict[str, int]]:
    """Compute per-position rank for each player."""
    position_lists: dict[str, list[dict]] = {}
    for p in players:
        for pos in p["positions"]:
            if pos not in position_lists:
                position_lists[pos] = []
            position_lists[pos].append(p)

    for pos in position_lists:
        position_lists[pos].sort(key=lambda x: x["overall_rank"])

    result: dict[str, dict[str, int]] = {}
    for pos, plist in position_lists.items():
        for i, p in enumerate(plist, 1):
            name = p["name"]
            if name not in result:
                result[name] = {}
            result[name][pos] = i

    return result


def compute_category_tags(player, thresholds: dict, scoring_cats: dict) -> list[str]:
    """Compute category tags based on projected stats and config thresholds."""
    tags = []
    stats = player.projected_stats
    batting_cats = scoring_cats.get("batting", [])
    pitching_cats = scoring_cats.get("pitching", [])

    if player.is_hitter and not player.is_pitcher:
        if "SB" in batting_cats and stats.get("SB", 0) >= thresholds.get("elite_SB", 25):
            tags.append("elite_SB")
        if "HR" in batting_cats and stats.get("HR", 0) >= thresholds.get("elite_HR", 35):
            tags.append("elite_HR")
        if "AVG" in batting_cats and stats.get("AVG", 0) >= thresholds.get("elite_AVG", 0.290):
            tags.append("elite_AVG")
        if "OBP" in batting_cats and stats.get("OBP", 0) >= thresholds.get("elite_OBP", 0.370):
            tags.append("elite_OBP")

        # Multi-cat contributor
        above_avg = 0
        for cat in batting_cats:
            threshold_key = f"above_avg_{cat}"
            # Use base thresholds for multi-cat check
            base = {"R": 80, "HR": 22, "RBI": 75, "SB": 12, "AVG": 0.265, "OBP": 0.340}
            thresh = base.get(cat, 0)
            if thresh and stats.get(cat, 0) >= thresh:
                above_avg += 1
        if above_avg >= 4:
            tags.append("5cat")

    if player.is_pitcher:
        if "QS" in pitching_cats and stats.get("proj_QS", 0) >= thresholds.get("QS_workhorse", 18):
            tags.append("QS_workhorse")
        if "K" in pitching_cats and stats.get("K", 0) >= thresholds.get("high_K", 200):
            tags.append("high_K")
        if stats.get("ERA", 0) > 0 and stats.get("WHIP", 0) > 0:
            era_thresh = thresholds.get("elite_ratios_ERA", 3.00)
            whip_thresh = thresholds.get("elite_ratios_WHIP", 1.05)
            if stats["ERA"] <= era_thresh and stats["WHIP"] <= whip_thresh:
                tags.append("elite_ratios")
        if "SV+H" in pitching_cats:
            svh_thresh = thresholds.get("SVH_value", 25)
            if stats.get("proj_SVH", 0) >= svh_thresh and stats.get("proj_HLD", 0) >= 15:
                tags.append("SVH_value")
        if "HLD" in pitching_cats:
            hld_thresh = thresholds.get("HLD_value", 20)
            if stats.get("proj_HLD", 0) >= hld_thresh:
                tags.append("HLD_value")
        if "SV" in pitching_cats and "SV+H" not in pitching_cats:
            if stats.get("SV", 0) >= thresholds.get("elite_SV", 30):
                tags.append("elite_SV")

    return tags


def compute_value_tiers(players: list, tier_boundaries: list[int]) -> list:
    """Assign tiers using config-driven boundaries."""
    if len(players) < len(tier_boundaries):
        for p in players:
            p.tier = 1
        return players

    sorted_players = sorted(players, key=lambda p: p.overall_rank)
    for p in sorted_players:
        p.tier = assign_tier(p.overall_rank, tier_boundaries)

    return sorted_players


def apply_strategic_adjustments(players: list, tier_boundaries: list[int],
                                 tag_thresholds: dict, scoring_cats: dict) -> list:
    """Apply strategic adjustments from research data."""
    try:
        with open(STRATEGIC_PATH, "r", encoding="utf-8") as f:
            adjustments = json.load(f)
        print("\nApplying strategic adjustments...")
    except FileNotFoundError:
        print("\nNo strategic_adjustments.json found, skipping.")
        return players

    rank_adj = adjustments.get("rank_adjustments", {})
    player_flags = adjustments.get("player_flags", {})
    cliffs = adjustments.get("positional_cliffs", {})
    boost_config = adjustments.get("boost_config", {})

    name_map = {p.name: p for p in players}
    adjusted_up = 0
    adjusted_down = 0

    pitching_cats = scoring_cats.get("pitching", [])
    has_qs = "QS" in pitching_cats
    has_svh = "SV+H" in pitching_cats

    for player in players:
        stats = player.projected_stats
        total_adj = 0

        # QS adjustments (only if league uses QS)
        if has_qs and player.is_pitcher and "SP" in player.positions:
            qs_rate = stats.get("QS_rate", 0)
            ip = stats.get("IP", 0)
            gs = stats.get("GS", 0)
            ip_per_gs = ip / gs if gs > 0 else 0

            if qs_rate >= 0.55 and ip >= 180:
                boost = boost_config.get("qs_workhorse_boost", -3)
                if qs_rate >= 0.70:
                    boost = boost_config.get("qs_elite_boost", -5)
                if ip >= 190:
                    boost -= boost_config.get("high_ip_extra", 2)
                total_adj += boost

            if gs >= 20 and ip_per_gs < 5.5:
                total_adj += boost_config.get("short_outing_penalty", 3)

        # SV+H adjustments (only if league uses SV+H)
        if has_svh and player.is_pitcher and "RP" in player.positions:
            proj_hld = stats.get("proj_HLD", 0)
            proj_svh = stats.get("proj_SVH", 0)

            if proj_hld >= 20 and proj_svh >= 25:
                total_adj += boost_config.get("elite_setup_boost", -15)
            elif proj_hld >= 15 and proj_svh >= 22:
                total_adj += boost_config.get("good_setup_boost", -8)
            elif proj_hld >= 10 and proj_svh >= 20:
                total_adj += boost_config.get("decent_setup_boost", -5)

        # Positional scarcity boost
        for pos in player.positions:
            cliff_info = cliffs.get(pos)
            if not cliff_info:
                continue
            cliff_rank = cliff_info.get("cliff_after_rank", 999)
            depth = cliff_info.get("depth", "moderate")
            if depth in ("very_shallow", "shallow"):
                if player.overall_rank <= cliff_rank and player.overall_rank >= cliff_rank - 10:
                    total_adj -= 2

        # Research-based per-player adjustments
        if player.name in rank_adj:
            research_adj = rank_adj[player.name]["adjustment"]
            total_adj += research_adj

        if total_adj != 0:
            player.overall_rank = max(1, player.overall_rank + total_adj)
            if total_adj < 0:
                adjusted_up += 1
            else:
                adjusted_down += 1

    # Re-sort and re-number
    players.sort(key=lambda p: p.overall_rank)
    for i, p in enumerate(players, 1):
        p.overall_rank = i

    # Re-tier
    compute_value_tiers(players, tier_boundaries)

    # Recompute positional ranks
    pos_ranks = compute_positional_ranks(
        [{"name": p.name, "positions": p.positions, "overall_rank": p.overall_rank}
         for p in players]
    )
    for p in players:
        p.positional_rank = pos_ranks.get(p.name, {})

    # Add category tags
    tagged_count = 0
    for player in players:
        tags = compute_category_tags(player, tag_thresholds, scoring_cats)
        if tags:
            player.projected_stats["category_tags"] = tags
            tagged_count += 1

    # Append player flags
    flag_count = 0
    for player in players:
        flag_info = player_flags.get(player.name)
        if flag_info:
            flag_str = f"[{flag_info['flag'].upper()}] {flag_info['note']}"
            for pos in player.positions:
                cliff_info = cliffs.get(pos)
                if cliff_info and cliff_info.get("depth") in ("very_shallow", "shallow"):
                    cliff_rank = cliff_info.get("cliff_after_rank", 999)
                    if player.overall_rank <= cliff_rank + 5 and player.overall_rank >= cliff_rank - 5:
                        flag_str += f" | CLIFF WARNING: {pos} thins out here"
            if player.notes:
                player.notes = f"{player.notes} | {flag_str}"
            else:
                player.notes = flag_str
            flag_count += 1
        else:
            cliff_warnings = []
            for pos in player.positions:
                cliff_info = cliffs.get(pos)
                if cliff_info and cliff_info.get("depth") in ("very_shallow", "shallow"):
                    cliff_rank = cliff_info.get("cliff_after_rank", 999)
                    if player.overall_rank <= cliff_rank + 5 and player.overall_rank >= cliff_rank - 5:
                        cliff_warnings.append(f"CLIFF WARNING: {pos} thins out here")
            if cliff_warnings:
                warning_str = " | ".join(cliff_warnings)
                if player.notes:
                    player.notes = f"{player.notes} | {warning_str}"
                else:
                    player.notes = warning_str

    print(f"  Adjusted up: {adjusted_up} players")
    print(f"  Adjusted down: {adjusted_down} players")
    print(f"  Category tags assigned: {tagged_count} players")
    print(f"  Player flags added: {flag_count} players")

    return players


def build_rankings():
    """Main build pipeline."""
    # Load configs
    print("Loading configuration...")
    try:
        config = LeagueConfig(CONFIG_PATH)
        derived = DerivedConfig(DERIVED_CONFIG_PATH)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Run 'python setup.py' first to generate configuration.")
        sys.exit(1)

    scoring_cats = config.scoring_categories
    tier_boundaries = derived.tier_boundaries
    tag_thresholds = derived.category_tag_thresholds
    has_qs = "QS" in scoring_cats.get("pitching", [])
    has_svh = "SV+H" in scoring_cats.get("pitching", [])
    has_lf_cf_rf = all(pos in config.roster_slots for pos in ("LF", "CF", "RF"))

    print("Loading data sources...")

    # 1. Load rankings (backbone)
    rankings = load_json(RANKINGS_PATH)
    print(f"  Rankings: {len(rankings)} players")

    # 2. Load projections
    try:
        projections = load_json(PROJECTIONS_PATH)
        fg_hitters = {h["name"]: h for h in projections.get("hitters", [])}
        fg_pitchers = {p["name"]: p for p in projections.get("pitchers", [])}
        fg_all_names = list(fg_hitters.keys()) + list(fg_pitchers.keys())
        print(f"  Projections: {len(fg_hitters)} hitters, {len(fg_pitchers)} pitchers")
    except FileNotFoundError:
        fg_hitters = {}
        fg_pitchers = {}
        print("  Projections: not found (skipping)")

    # 3. Load SV+H data (only if relevant)
    svh_map = {}
    if has_svh:
        try:
            svh_data = load_json(SVH_PATH)
            svh_map = {r["name"]: r for r in svh_data}
            print(f"  SV+H relievers: {len(svh_data)}")
        except FileNotFoundError:
            print("  SV+H data: not found (skipping)")

    # 4. Load OF position mapping (only if LF/CF/RF slots)
    of_mapping = {}
    if has_lf_cf_rf:
        try:
            of_mapping = load_json(OF_POSITIONS_PATH)
            print(f"  OF positions: {len(of_mapping)} mappings")
        except FileNotFoundError:
            print("  OF positions: not found (generic OF will be used)")

    # Merge
    print("\nMerging data...")
    players_data = []
    matched_fg = 0
    matched_svh = 0

    for entry in rankings:
        name = entry["name"]
        team = entry["team"]
        positions = entry["positions"]
        rank = entry["overall_rank"]

        # Resolve OF positions if needed
        if has_lf_cf_rf:
            positions = resolve_of_positions(positions, name, of_mapping)

        is_pitcher = any(p in ("SP", "RP") for p in positions)
        is_hitter = any(p not in ("SP", "RP", "P") for p in positions)

        projected_stats = {}

        # Match projections
        if is_hitter and not is_pitcher:
            fg_match = fuzzy_match(name, list(fg_hitters.keys()))
            if fg_match:
                fg = fg_hitters[fg_match]
                for stat in ("R", "HR", "RBI", "SB", "AVG", "OBP", "SLG", "OPS", "H", "TB", "BB"):
                    if stat in fg:
                        projected_stats[stat] = fg[stat]
                matched_fg += 1
        elif is_pitcher:
            fg_match = fuzzy_match(name, list(fg_pitchers.keys()))
            if fg_match:
                fg = fg_pitchers[fg_match]
                for stat in ("IP", "GS", "K", "ERA", "WHIP", "SV", "W"):
                    if stat in fg:
                        projected_stats[stat] = fg[stat]
                # Estimate QS for starters if league uses QS
                if has_qs and fg.get("GS", 0) > 0:
                    qs_rate = estimate_qs_rate(fg["IP"], fg["GS"], fg["ERA"])
                    projected_stats["QS_rate"] = round(qs_rate, 2)
                    projected_stats["proj_QS"] = round(qs_rate * fg["GS"])
                matched_fg += 1

        # Merge SV+H data
        notes = ""
        if svh_map:
            svh_match = fuzzy_match(name, list(svh_map.keys()))
            if svh_match:
                svh = svh_map[svh_match]
                projected_stats["proj_SV"] = svh["proj_sv"]
                projected_stats["proj_HLD"] = svh["proj_hld"]
                projected_stats["proj_SVH"] = svh["proj_svh"]
                notes = svh.get("notes", "")
                matched_svh += 1

        tier = assign_tier(rank, tier_boundaries)

        players_data.append({
            "name": name,
            "team": team,
            "positions": positions,
            "overall_rank": rank,
            "tier": tier,
            "projected_stats": projected_stats,
            "notes": notes,
        })

    print(f"  Projections matched: {matched_fg}/{len(rankings)}")
    if svh_map:
        print(f"  SV+H matched: {matched_svh}")

    # Compute positional ranks
    print("Computing positional ranks...")
    pos_ranks = compute_positional_ranks(players_data)

    # Build final Player objects
    print("Building player objects...")
    players = []
    for pd in players_data:
        player = create_player(
            name=pd["name"],
            team=pd["team"],
            positions=pd["positions"],
            overall_rank=pd["overall_rank"],
            tier=pd["tier"],
            positional_rank=pos_ranks.get(pd["name"], {}),
            projected_stats=pd["projected_stats"],
            notes=pd["notes"],
        )
        players.append(player)

    players.sort(key=lambda p: p.overall_rank)

    # Apply strategic adjustments (Phase 2)
    players = apply_strategic_adjustments(players, tier_boundaries, tag_thresholds, scoring_cats)

    # Save
    print(f"\nSaving {len(players)} players...")
    save_ranked_list(players, OUTPUT_PATH)

    # Summary
    print("\n--- Summary ---")
    hitters = [p for p in players if p.is_hitter and not p.is_pitcher]
    pitchers = [p for p in players if p.is_pitcher]
    print(f"Total: {len(players)}")
    print(f"Hitters: {len(hitters)}, Pitchers: {len(pitchers)}")
    print(f"With projections: {sum(1 for p in players if p.projected_stats)}")

    from collections import Counter
    tier_counts = Counter(p.tier for p in players)
    print(f"Tiers: {dict(sorted(tier_counts.items()))}")


if __name__ == "__main__":
    build_rankings()
