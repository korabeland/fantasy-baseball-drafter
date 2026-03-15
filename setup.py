"""Interactive setup script for the Fantasy Baseball Draft Assistant.

Two modes:
    python setup.py              # Interactive: prompts for everything, writes both configs
    python setup.py --derive     # Re-derive: reads existing league_config.json, regenerates derived_config.json
"""

import json
import subprocess
import sys
from pathlib import Path


CONFIG_DIR = Path("config")
LEAGUE_CONFIG_PATH = CONFIG_DIR / "league_config.json"
DERIVED_CONFIG_PATH = CONFIG_DIR / "derived_config.json"

# Known stat classifications
STAT_INFO = {
    # Hitting
    "R":    {"type": "counting", "side": "hitting"},
    "HR":   {"type": "counting", "side": "hitting"},
    "RBI":  {"type": "counting", "side": "hitting"},
    "SB":   {"type": "counting", "side": "hitting"},
    "AVG":  {"type": "ratio",    "side": "hitting"},
    "OBP":  {"type": "ratio",    "side": "hitting"},
    "SLG":  {"type": "ratio",    "side": "hitting"},
    "OPS":  {"type": "ratio",    "side": "hitting"},
    "H":    {"type": "counting", "side": "hitting"},
    "TB":   {"type": "counting", "side": "hitting"},
    "BB":   {"type": "counting", "side": "hitting"},
    "XBH":  {"type": "counting", "side": "hitting"},
    "NSB":  {"type": "counting", "side": "hitting"},
    # Pitching
    "K":    {"type": "counting", "side": "pitching"},
    "W":    {"type": "counting", "side": "pitching"},
    "QS":   {"type": "counting", "side": "pitching"},
    "SV":   {"type": "counting", "side": "pitching"},
    "SV+H": {"type": "counting", "side": "pitching"},
    "HLD":  {"type": "counting", "side": "pitching"},
    "ERA":  {"type": "ratio",    "side": "pitching", "inverted": True},
    "WHIP": {"type": "ratio",    "side": "pitching", "inverted": True},
    "IP":   {"type": "counting", "side": "pitching"},
    "L":    {"type": "counting", "side": "pitching", "inverted": True},
    "K/9":  {"type": "ratio",    "side": "pitching"},
    "K/BB": {"type": "ratio",    "side": "pitching"},
    "BB/9": {"type": "ratio",    "side": "pitching", "inverted": True},
}

# Default flex eligibility rules
FLEX_RULES = {
    "IF": ["C", "1B", "2B", "3B", "SS"],
    "OF": ["LF", "CF", "RF", "OF"],
    "MI": ["2B", "SS"],
    "CI": ["1B", "3B"],
    "P":  ["SP", "RP"],
}

# Category presets
CATEGORY_PRESETS = {
    "standard_5x5": {
        "batting": ["R", "HR", "RBI", "SB", "AVG"],
        "pitching": ["W", "K", "ERA", "WHIP", "SV"],
    },
    "standard_5x5_qs": {
        "batting": ["R", "HR", "RBI", "SB", "AVG"],
        "pitching": ["K", "ERA", "WHIP", "QS", "SV"],
    },
    "standard_5x5_qs_svh": {
        "batting": ["R", "HR", "RBI", "SB", "AVG"],
        "pitching": ["K", "ERA", "WHIP", "QS", "SV+H"],
    },
    "standard_6x6": {
        "batting": ["R", "HR", "RBI", "SB", "AVG", "OBP"],
        "pitching": ["W", "K", "ERA", "WHIP", "SV", "QS"],
    },
}

# Roster presets
ROSTER_PRESETS = {
    "yahoo_standard": {
        "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1,
        "OF": 3, "UTIL": 1,
        "SP": 2, "RP": 2, "P": 2,
        "BN": 3, "IL": 2,
    },
    "yahoo_lf_cf_rf": {
        "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "IF": 1,
        "LF": 1, "CF": 1, "RF": 1, "OF": 1,
        "UTIL": 2,
        "SP": 4, "RP": 2, "P": 2,
        "BN": 6, "IL": 4,
    },
    "espn_standard": {
        "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1,
        "OF": 3, "UTIL": 1, "MI": 1, "CI": 1,
        "SP": 5, "RP": 3,
        "BN": 3, "IL": 2,
    },
}

# Historical MLB averages per team (for season target computation)
HISTORICAL_AVERAGES = {
    "R": 720, "HR": 180, "RBI": 690, "SB": 100, "AVG": 0.252,
    "OBP": 0.320, "SLG": 0.410, "OPS": 0.730,
    "H": 1400, "TB": 2200, "BB": 520, "XBH": 440, "NSB": 80,
    "K": 1350, "W": 85, "QS": 85, "SV": 45, "SV+H": 75, "HLD": 50,
    "ERA": 4.15, "WHIP": 1.27, "IP": 1430,
    "K/9": 9.0, "K/BB": 2.8, "BB/9": 3.3,
    "L": 77,
}

# Above-average thresholds per player (for 12-team; scaled by team count)
BASE_ABOVE_AVG = {
    "R": 80, "HR": 22, "RBI": 75, "SB": 12, "AVG": 0.265,
    "OBP": 0.340, "SLG": 0.440, "OPS": 0.780,
    "H": 150, "TB": 240, "BB": 60, "XBH": 50, "NSB": 10,
    "K": 160, "W": 12, "QS": 14, "SV": 25, "SV+H": 20, "HLD": 15,
    "ERA": 3.50, "WHIP": 1.15, "IP": 180,
    "K/9": 9.5, "K/BB": 3.2, "BB/9": 2.8,
    "L": 10,
}

# Category tag mapping templates
TAG_TEMPLATES = {
    "HR":   "elite_HR",
    "SB":   "elite_SB",
    "AVG":  "elite_AVG",
    "OBP":  "elite_OBP",
    "R":    "elite_R",
    "RBI":  "elite_RBI",
    "QS":   "QS_workhorse",
    "K":    "high_K",
    "SV":   "elite_SV",
    "SV+H": "SVH_value",
    "HLD":  "HLD_value",
    "W":    "high_W",
}

# Category tag thresholds (base, for 12-team)
BASE_TAG_THRESHOLDS = {
    "elite_SB": 25, "elite_HR": 35, "elite_AVG": 0.290,
    "elite_OBP": 0.370, "elite_R": 90, "elite_RBI": 90,
    "QS_workhorse": 18, "high_K": 200,
    "elite_SV": 30, "SVH_value": 25, "HLD_value": 20,
    "high_W": 14,
    "elite_ratios_ERA": 3.00, "elite_ratios_WHIP": 1.05,
}


def preflight_check() -> bool:
    """Verify Python version, pip, and required packages."""
    print("=== PREFLIGHT CHECK ===")
    all_ok = True

    # Python version
    v = sys.version_info
    if v.major >= 3 and v.minor >= 11:
        print(f"[OK] Python {v.major}.{v.minor}.{v.micro}")
    else:
        print(f"[FAIL] Python {v.major}.{v.minor}.{v.micro} (need 3.11+)")
        all_ok = False

    # pip
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"],
                       capture_output=True, check=True)
        print("[OK] pip available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[FAIL] pip not available")
        all_ok = False

    # Required packages
    for pkg in ["pandas", "numpy"]:
        try:
            __import__(pkg)
            print(f"[OK] {pkg} installed")
        except ImportError:
            print(f"[FAIL] {pkg} not installed")
            all_ok = False

    # Optional packages
    for pkg in ["matplotlib", "seaborn"]:
        try:
            __import__(pkg)
            print(f"[OK] {pkg} installed (optional)")
        except ImportError:
            print(f"[!!] {pkg} not installed (optional -- charts disabled)")

    print()
    if not all_ok:
        print("Missing required tools. Install them and re-run setup.")
        missing_pkgs = []
        for pkg in ["pandas", "numpy"]:
            try:
                __import__(pkg)
            except ImportError:
                missing_pkgs.append(pkg)
        if missing_pkgs:
            print(f"\n  pip install {' '.join(missing_pkgs)}")
            resp = input("\nInstall missing packages now? [Y/n] ").strip().lower()
            if resp in ("", "y", "yes"):
                subprocess.run([sys.executable, "-m", "pip", "install"] + missing_pkgs, check=True)
                print("Packages installed. Re-running preflight...")
                return preflight_check()
        return False

    print("Required tools: All present. Ready to proceed.\n")
    return True


def prompt_choice(prompt: str, options: list[str], default: str | None = None) -> str:
    """Prompt user to pick from a list."""
    for i, opt in enumerate(options, 1):
        marker = " *" if opt == default else ""
        print(f"  {i}. {opt}{marker}")
    while True:
        raw = input(f"{prompt} [{default or ''}]: ").strip()
        if not raw and default:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        print(f"  Enter 1-{len(options)} or a valid option.")


def prompt_int(prompt: str, default: int | None = None, min_val: int = 1, max_val: int = 999) -> int:
    """Prompt for an integer."""
    while True:
        raw = input(f"{prompt} [{default or ''}]: ").strip()
        if not raw and default is not None:
            return default
        if raw.isdigit() and min_val <= int(raw) <= max_val:
            return int(raw)
        print(f"  Enter a number {min_val}-{max_val}.")


def interactive_setup() -> dict:
    """Walk the user through league configuration."""
    print("=== LEAGUE SETUP ===\n")

    # Platform
    platform = prompt_choice(
        "League platform?",
        ["Yahoo", "ESPN", "CBS", "Fantrax", "Other"],
        default="Yahoo",
    )

    # Team count
    team_count = prompt_int("How many teams?", default=12, min_val=4, max_val=30)

    # Scoring format
    scoring_format = prompt_choice(
        "Scoring format?",
        ["head-to-head-categories", "roto", "head-to-head-points"],
        default="head-to-head-categories",
    )

    # Scoring categories
    print("\nScoring category presets:")
    preset_names = list(CATEGORY_PRESETS.keys()) + ["custom"]
    preset = prompt_choice("Category preset?", preset_names, default="standard_5x5")

    if preset == "custom":
        print("Enter batting categories (comma-separated, e.g. R,HR,RBI,SB,AVG):")
        batting = [c.strip() for c in input("  Batting: ").split(",")]
        print("Enter pitching categories (comma-separated, e.g. K,ERA,WHIP,QS,SV+H):")
        pitching = [c.strip() for c in input("  Pitching: ").split(",")]
        categories = {"batting": batting, "pitching": pitching}
    else:
        categories = CATEGORY_PRESETS[preset]
        print(f"  Batting: {', '.join(categories['batting'])}")
        print(f"  Pitching: {', '.join(categories['pitching'])}")

    # Roster slots
    print("\nRoster slot presets:")
    roster_preset_names = list(ROSTER_PRESETS.keys()) + ["custom"]
    roster_choice = prompt_choice("Roster preset?", roster_preset_names, default="yahoo_standard")

    if roster_choice == "custom":
        print("Enter roster slots as POSITION:COUNT pairs (comma-separated):")
        print("  e.g. C:1,1B:1,2B:1,3B:1,SS:1,OF:3,UTIL:1,SP:2,RP:2,P:2,BN:3,IL:2")
        raw = input("  Roster: ").strip()
        roster_slots = {}
        for pair in raw.split(","):
            pos, count = pair.strip().split(":")
            roster_slots[pos.strip()] = int(count.strip())
    else:
        roster_slots = ROSTER_PRESETS[roster_choice]
        parts = [f"{pos}:{count}" for pos, count in roster_slots.items()]
        print(f"  Slots: {', '.join(parts)}")

    # Draft type
    draft_type = prompt_choice(
        "Draft type?",
        ["snake", "live-standard", "auction"],
        default="snake",
    )

    # Draft position (optional)
    print("\nDraft position (optional, can set later):")
    pos_raw = input(f"  Draft position [skip]: ").strip()
    draft_position = int(pos_raw) if pos_raw.isdigit() else None

    # League name (optional)
    league_name = input("League name [My League]: ").strip() or "My League"

    # Min IP/week (optional)
    min_ip = None
    raw = input("Minimum innings per week (or skip) [skip]: ").strip()
    if raw.isdigit():
        min_ip = int(raw)

    config = {
        "team_count": team_count,
        "roster_slots": roster_slots,
        "scoring_format": scoring_format,
        "scoring_categories": categories,
        "draft_type": draft_type,
        "draft_position": draft_position,
        "my_team_name": "My Team",
        "league_name": league_name,
        "platform": platform,
    }
    if min_ip:
        config["min_innings_per_week"] = min_ip

    return config


def derive_config(league_config: dict) -> dict:
    """Compute all derived constants from league configuration."""
    team_count = league_config["team_count"]
    batting_cats = league_config["scoring_categories"]["batting"]
    pitching_cats = league_config["scoring_categories"]["pitching"]
    all_cats = batting_cats + pitching_cats
    roster_slots = league_config["roster_slots"]

    # Map display categories to internal stat names
    def to_internal(cat: str) -> str:
        if cat == "QS":
            return "proj_QS"
        if cat == "SV+H":
            return "proj_SVH"
        return cat

    internal_batting = [to_internal(c) for c in batting_cats]
    internal_pitching = [to_internal(c) for c in pitching_cats]
    internal_all = internal_batting + internal_pitching

    # Stat classifications
    counting_stats = []
    ratio_stats = []
    inverted_stats = []

    for cat in all_cats:
        info = STAT_INFO.get(cat, {})
        internal = to_internal(cat)
        if info.get("type") == "ratio":
            ratio_stats.append(internal)
        else:
            counting_stats.append(internal)
        if info.get("inverted"):
            inverted_stats.append(internal)

    # Season targets: scale historical averages by team count
    scale_factor = 12 / team_count  # more teams = lower targets per team
    season_targets = {}
    for cat in all_cats:
        internal = to_internal(cat)
        base = HISTORICAL_AVERAGES.get(cat, 0)
        info = STAT_INFO.get(cat, {})
        if info.get("type") == "ratio":
            # Ratio stats don't scale with team count
            season_targets[internal] = base
        else:
            # Counting stats: competitive target is ~top-3 team level
            # Scale from historical MLB per-team average
            season_targets[internal] = round(base * scale_factor * 0.95)

    # Above-average thresholds (per player)
    above_avg = {}
    for cat in all_cats:
        internal = to_internal(cat)
        base = BASE_ABOVE_AVG.get(cat, 0)
        info = STAT_INFO.get(cat, {})
        if info.get("type") == "ratio":
            above_avg[internal] = base
        else:
            # Scale counting stats: fewer teams = higher bar per player
            above_avg[internal] = round(base * scale_factor)

    # Tracked positions: all roster slots except BN, IL, UTIL
    non_tracked = {"BN", "IL", "UTIL"}
    tracked = [pos for pos in roster_slots if pos not in non_tracked]

    # Flex eligibility: only include flex slots that are in the roster
    flex_elig = {}
    for slot, eligible in FLEX_RULES.items():
        if slot in roster_slots:
            flex_elig[slot] = eligible

    # Tag-to-category mapping: only for categories in this league
    tag_to_cat = {}
    for cat in all_cats:
        internal = to_internal(cat)
        tag = TAG_TEMPLATES.get(cat)
        if tag:
            tag_to_cat[tag] = internal
    # Always include elite_ratios if ERA or WHIP present
    if "ERA" in all_cats or "WHIP" in all_cats:
        tag_to_cat["elite_ratios"] = to_internal("ERA")

    # Category tag thresholds: scale counting-based ones
    cat_tag_thresholds = {}
    for tag, base_val in BASE_TAG_THRESHOLDS.items():
        # Ratio-based thresholds don't scale
        if tag.startswith("elite_ratios"):
            cat_tag_thresholds[tag] = base_val
        elif isinstance(base_val, float) and base_val < 1:
            cat_tag_thresholds[tag] = base_val  # ratio stat
        else:
            cat_tag_thresholds[tag] = round(base_val * scale_factor)

    # Tier boundaries: based on team_count
    tc = team_count
    tier_boundaries = [
        tc,          # Tier 1: first round
        tc * 2,      # Tier 2: second round
        tc * 4,      # Tier 3
        tc * 6,      # Tier 4
        tc * 9,      # Tier 5
        tc * 13,     # Tier 6
        tc * 17,     # Tier 7
        tc * 21,     # Tier 8
                      # Tier 9: everything after
    ]

    # Target counts: how many of each position to draft
    target_counts = {}
    for pos, count in roster_slots.items():
        if pos in ("BN", "IL"):
            continue
        if pos == "UTIL":
            continue
        if pos == "P":
            # P slots can be SP or RP; don't set specific targets
            continue
        target_counts[pos] = count
    # SP typically gets bench streaming slots
    sp_count = roster_slots.get("SP", 0) + roster_slots.get("P", 0)
    if sp_count > 0:
        target_counts["SP"] = sp_count + min(roster_slots.get("BN", 0), 2)
    # RP gets P flex slots
    rp_count = roster_slots.get("RP", 0) + roster_slots.get("P", 0)
    if rp_count > 0:
        target_counts["RP"] = min(rp_count, 4)

    # Scarcity deadlines: generic defaults based on position depth
    scarcity_deadlines = {}
    shallow_positions = {"C", "2B", "3B"}
    mid_positions = {"1B", "LF", "CF", "RF", "SP", "RP"}
    deep_positions = {"SS", "OF"}
    total_rounds = sum(roster_slots.values()) - roster_slots.get("IL", 0)

    for pos in tracked:
        if pos in FLEX_RULES:
            continue  # flex slots don't have scarcity deadlines
        if pos in shallow_positions:
            scarcity_deadlines[pos] = min(5, total_rounds)
        elif pos in mid_positions:
            scarcity_deadlines[pos] = min(8, total_rounds)
        elif pos in deep_positions:
            scarcity_deadlines[pos] = min(10, total_rounds)

    return {
        "team_count": team_count,
        "season_targets": season_targets,
        "counting_stats": counting_stats,
        "ratio_stats": ratio_stats,
        "inverted_stats": inverted_stats,
        "hitting_cats": internal_batting,
        "pitching_cats": internal_pitching,
        "tracked_positions": tracked,
        "tag_to_category": tag_to_cat,
        "above_avg_thresholds": above_avg,
        "flex_eligibility": flex_elig,
        "tier_boundaries": tier_boundaries,
        "category_tag_thresholds": cat_tag_thresholds,
        "target_counts": target_counts,
        "scarcity_deadlines": scarcity_deadlines,
    }


def generate_claude_md(league_config: dict) -> None:
    """Append league-specific section to CLAUDE.md."""
    claude_md_path = Path("CLAUDE.md")
    if not claude_md_path.exists():
        return

    content = claude_md_path.read_text(encoding="utf-8")

    # Remove existing generated section if present
    marker = "<!-- GENERATED: League-Specific Context -->"
    if marker in content:
        idx = content.index(marker)
        content = content[:idx].rstrip() + "\n"

    batting = ", ".join(league_config["scoring_categories"]["batting"])
    pitching = ", ".join(league_config["scoring_categories"]["pitching"])
    slots = ", ".join(f"{k} x{v}" for k, v in league_config["roster_slots"].items())
    team_count = league_config["team_count"]

    section = f"""
{marker}

## League-Specific Context

This league uses the following configuration:
- **Teams**: {team_count}
- **Format**: {league_config["scoring_format"]}
- **Batting categories**: {batting}
- **Pitching categories**: {pitching}
- **Roster slots**: {slots}
- **Draft type**: {league_config["draft_type"]}
"""

    # Add category-specific notes
    if "QS" in league_config["scoring_categories"]["pitching"]:
        section += "- **QS** (Quality Starts) instead of W -- favors durable starters with low ERA over guys on winning teams\n"
    if "SV+H" in league_config["scoring_categories"]["pitching"]:
        section += "- **SV+H** (Saves + Holds) instead of SV -- makes high-leverage setup men draftable, not just closers\n"

    has_lf_cf_rf = all(pos in league_config["roster_slots"] for pos in ("LF", "CF", "RF"))
    if has_lf_cf_rf:
        section += "- **LF/CF/RF** roster slots instead of generic OF -- position eligibility matters for outfielders\n"

    content += section
    claude_md_path.write_text(content, encoding="utf-8")
    print(f"Updated CLAUDE.md with league-specific context.")


def save_config(config: dict, path: Path) -> None:
    """Write config dict to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")


def main():
    args = sys.argv[1:]

    if "--derive" in args:
        # Re-derive mode: read existing league_config, regenerate derived
        if not LEAGUE_CONFIG_PATH.exists():
            print(f"Error: {LEAGUE_CONFIG_PATH} not found. Run setup.py without --derive first.")
            sys.exit(1)
        with open(LEAGUE_CONFIG_PATH, "r", encoding="utf-8") as f:
            league_config = json.load(f)
        derived = derive_config(league_config)
        save_config(derived, DERIVED_CONFIG_PATH)
        print("Derived config regenerated.")
        return

    # Interactive mode
    if not preflight_check():
        sys.exit(1)

    league_config = interactive_setup()

    print("\n=== SAVING ===")
    save_config(league_config, LEAGUE_CONFIG_PATH)

    derived = derive_config(league_config)
    save_config(derived, DERIVED_CONFIG_PATH)

    generate_claude_md(league_config)

    print("\nSetup complete! Next steps:")
    print("  1. Import player data: python import_data.py --csv projections.csv")
    print("  2. Build rankings: python research/build_rankings.py")
    print("  3. Run the draft CLI: python cli.py")


if __name__ == "__main__":
    main()
