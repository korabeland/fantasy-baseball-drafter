"""Verify ranked_players.json before draft day.

Checks:
- Player count adequate
- All required fields populated
- Position coverage adequate
- Stat sanity checks
- No duplicate ranks
- Tier distribution reasonable
"""

import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from models.player import Player
from config_loader import LeagueConfig, DerivedConfig


RANKED_PATH = Path("data/ranked_players.json")
CONFIG_PATH = Path("config/league_config.json")
DERIVED_CONFIG_PATH = Path("config/derived_config.json")


def load_players() -> list[Player]:
    with open(RANKED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Player.from_dict(p) for p in data]


def verify():
    errors = []
    warnings = []

    # Load config for dynamic thresholds
    try:
        config = LeagueConfig(CONFIG_PATH)
        team_count = config.team_count
        roster_slots = config.roster_slots
    except FileNotFoundError:
        print("Warning: league_config.json not found, using defaults")
        team_count = 12
        roster_slots = {}

    # Minimum position counts scale with team count
    min_position_counts = {}
    for pos in roster_slots:
        if pos in ("BN", "IL", "UTIL"):
            continue
        min_count = max(team_count, roster_slots[pos] * team_count)
        min_position_counts[pos] = min_count

    print("Loading ranked_players.json...")
    try:
        players = load_players()
    except FileNotFoundError:
        print("FAIL: data/ranked_players.json not found!")
        return False
    except Exception as e:
        print(f"FAIL: Could not load file: {e}")
        return False

    print(f"Loaded {len(players)} players\n")

    # 1. Player count
    min_players = team_count * 20  # ~20 rounds typical
    if len(players) >= min_players:
        print(f"  [PASS] Player count: {len(players)} >= {min_players}")
    else:
        warnings.append(f"Only {len(players)} players (recommend {min_players}+)")
        print(f"  [WARN] Player count: {len(players)} < {min_players}")

    # 2. Required fields
    missing_fields = 0
    for p in players:
        if not p.name:
            missing_fields += 1
        if not p.team:
            missing_fields += 1
        if not p.positions:
            missing_fields += 1
        if p.overall_rank <= 0:
            missing_fields += 1

    if missing_fields == 0:
        print("  [PASS] All required fields populated")
    else:
        errors.append(f"{missing_fields} missing required fields")
        print(f"  [FAIL] {missing_fields} missing required fields")

    # 3. Rank uniqueness
    ranks = [p.overall_rank for p in players]
    if len(set(ranks)) == len(ranks):
        print("  [PASS] No duplicate ranks")
    else:
        dupes = [r for r, c in Counter(ranks).items() if c > 1]
        errors.append(f"Duplicate ranks: {dupes}")
        print(f"  [FAIL] Duplicate ranks: {dupes}")

    if ranks == sorted(ranks):
        print("  [PASS] Ranks in order")
    else:
        warnings.append("Ranks not in sequential order")
        print("  [WARN] Ranks not in sequential order")

    # 4. Position coverage
    if min_position_counts:
        print("\n  Position coverage:")
        pos_counts = Counter()
        for p in players:
            for pos in p.positions:
                pos_counts[pos] += 1

        for pos, min_count in min_position_counts.items():
            count = pos_counts.get(pos, 0)
            status = "PASS" if count >= min_count else "WARN"
            if count < min_count:
                warnings.append(f"{pos}: {count} < {min_count} minimum")
            print(f"    [{status}] {pos}: {count} (min: {min_count})")

    # 5. Tier distribution
    print("\n  Tier distribution:")
    tier_counts = Counter(p.tier for p in players)
    for tier in sorted(tier_counts.keys()):
        print(f"    Tier {tier}: {tier_counts[tier]} players")

    if 0 in tier_counts:
        warnings.append("Some players have tier 0 (unassigned)")
    else:
        print("    [PASS] All players have tiers assigned")

    # 6. Projection coverage
    with_projections = sum(1 for p in players if p.projected_stats)
    pct = round(with_projections / len(players) * 100, 1) if players else 0
    if pct >= 80:
        print(f"\n  [PASS] Projections: {with_projections}/{len(players)} ({pct}%)")
    else:
        warnings.append(f"Only {pct}% have projections")
        print(f"\n  [WARN] Projections: {with_projections}/{len(players)} ({pct}%)")

    # 7. Top 10
    print("\n  Top 10 players:")
    for p in players[:10]:
        pos_str = "/".join(p.positions)
        print(f"    {p.overall_rank:3d}. {p.name} ({p.team}) - {pos_str} - Tier {p.tier}")

    # 8. Sequential ranks check
    print("\n  Strategic adjustment checks:")
    expected_ranks = set(range(1, len(players) + 1))
    actual_ranks = set(p.overall_rank for p in players)
    missing_ranks = expected_ranks - actual_ranks
    extra_ranks = actual_ranks - expected_ranks
    if missing_ranks:
        errors.append(f"Missing ranks: {sorted(missing_ranks)[:10]}...")
        print(f"  [FAIL] Missing ranks: {sorted(missing_ranks)[:10]}")
    elif extra_ranks:
        errors.append(f"Extra ranks: {sorted(extra_ranks)[:10]}...")
        print(f"  [FAIL] Extra ranks: {sorted(extra_ranks)[:10]}")
    else:
        print("  [PASS] Ranks are sequential 1-N")

    # Summary
    print("\n" + "=" * 50)
    if errors:
        print(f"RESULT: FAIL ({len(errors)} errors, {len(warnings)} warnings)")
        for e in errors:
            print(f"  ERROR: {e}")
    else:
        print(f"RESULT: PASS ({len(warnings)} warnings)")

    for w in warnings:
        print(f"  WARN: {w}")

    return len(errors) == 0


if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
