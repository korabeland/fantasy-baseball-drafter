"""Pre-computed round-by-round cheat sheet for draft day.

Fast -- no orchestrator, no agents. Uses position-aware strategy logic
to recommend the right player at the right time.

Called via: python draft_cheat_sheet.py [round] [--position N]
"""

import json
import sys
from pathlib import Path

from config_loader import LeagueConfig, DerivedConfig

PLAYERS_PATH = Path("data/ranked_players.json")
STATE_PATH = Path("data/draft_state.json")
CONFIG_PATH = Path("config/league_config.json")
DERIVED_CONFIG_PATH = Path("config/derived_config.json")

# Position groups for eligibility checking
HITTER_POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF"}
PITCHER_POSITIONS = {"SP", "RP"}


def load_config():
    """Load league and derived configs."""
    config = LeagueConfig(CONFIG_PATH)
    derived = DerivedConfig(DERIVED_CONFIG_PATH)
    return config, derived


def load_players():
    with open(PLAYERS_PATH) as f:
        return json.load(f)


def get_draft_position():
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            state = json.load(f)
            pos = state.get("draft_position")
            if pos:
                return pos
    with open(CONFIG_PATH) as f:
        config = json.load(f)
        return config.get("draft_position")


def get_drafted_names():
    if not STATE_PATH.exists():
        return set()
    with open(STATE_PATH) as f:
        state = json.load(f)
    return {p["name"] for p in state.get("picks", [])}


def pick_number_for_round(position, round_num, team_count):
    if round_num % 2 == 1:
        return (round_num - 1) * team_count + position
    else:
        return (round_num - 1) * team_count + (team_count - position + 1)


def classify_draft_position(pos, team_count):
    """early / mid / late based on team count."""
    third = team_count / 3
    if pos <= third:
        return "early"
    elif pos <= third * 2:
        return "mid"
    return "late"


def player_is_position(player, pos):
    positions = set(player["positions"])
    if pos == "OF":
        return bool(positions & {"LF", "CF", "RF", "OF"})
    return pos in positions


def player_is_hitter(player):
    return bool(set(player["positions"]) & HITTER_POSITIONS)


def player_is_sp(player):
    return "SP" in player["positions"]


def player_is_rp(player):
    return "RP" in player["positions"]


def has_tag(player, tag):
    tags = player.get("projected_stats", {}).get("category_tags", [])
    return tag in tags


def get_notes(player):
    return player.get("notes", "")


def build_round_strategy(draft_pos, team_count, total_rounds, scarcity_deadlines, scoring_cats):
    """Build position priority lists per round based on draft position bracket.

    Uses scarcity deadlines from derived config to determine when positions
    need to be targeted.
    """
    bracket = classify_draft_position(draft_pos, team_count)

    # Determine if league uses SV+H (setup men matter) or SV (just closers)
    pitching_cats = scoring_cats.get("pitching", [])
    has_svh = "SV+H" in pitching_cats
    has_qs = "QS" in pitching_cats
    closer_label = "setup" if has_svh else "closer"

    # Sort positions by deadline urgency
    urgent_positions = sorted(
        [(pos, rnd) for pos, rnd in scarcity_deadlines.items()],
        key=lambda x: x[1],
    )

    strategy = {}

    if bracket == "early":
        strategy[1] = ["hitter_bpa"]
        for rnd in range(2, total_rounds + 1):
            priorities = []
            # Add positions approaching their deadlines
            for pos, deadline in urgent_positions:
                if rnd <= deadline and rnd >= deadline - 2:
                    if pos in ("SP",):
                        priorities.append("SP")
                    elif pos in ("RP",):
                        priorities.append("closer")
                    else:
                        priorities.append(pos)
            if rnd >= 4 and "SP" not in priorities:
                priorities.append("SP")
            if rnd >= total_rounds * 0.6:
                if has_svh:
                    priorities.append("setup")
                priorities.append("sleeper")
            priorities.append("hitter_bpa")
            strategy[rnd] = priorities

    elif bracket == "mid":
        strategy[1] = ["hitter_bpa"]
        for rnd in range(2, total_rounds + 1):
            priorities = []
            for pos, deadline in urgent_positions:
                if rnd <= deadline and rnd >= deadline - 2:
                    if pos in ("SP",):
                        priorities.append("SP")
                    elif pos in ("RP",):
                        priorities.append("closer")
                    else:
                        priorities.append(pos)
            if rnd >= 4 and "SP" not in priorities:
                priorities.append("SP")
            if rnd >= total_rounds * 0.6:
                if has_svh:
                    priorities.append("setup")
                priorities.append("sleeper")
            priorities.append("hitter_bpa")
            strategy[rnd] = priorities

    else:  # late
        strategy[1] = ["hitter_bpa"]
        strategy[2] = ["SP", "hitter_bpa"]  # THE TURN: double-dip
        for rnd in range(3, total_rounds + 1):
            priorities = []
            for pos, deadline in urgent_positions:
                if rnd <= deadline and rnd >= deadline - 2:
                    if pos in ("SP",):
                        priorities.append("SP")
                    elif pos in ("RP",):
                        priorities.append("closer")
                    else:
                        priorities.append(pos)
            if rnd >= 3 and "SP" not in priorities:
                priorities.append("SP")
            if rnd >= total_rounds * 0.6:
                if has_svh:
                    priorities.append("setup")
                priorities.append("sleeper")
            priorities.append("hitter_bpa")
            strategy[rnd] = priorities

    return strategy


def _windowed(candidates, pick_num, count):
    """Return up to `count` candidates near the pick number."""
    if not candidates:
        return []
    tight = [c for c in candidates
             if max(1, pick_num - 8) <= c["overall_rank"] <= pick_num + 15]
    if tight:
        tight.sort(key=lambda p: p["overall_rank"])
        return tight[:count]
    candidates.sort(key=lambda p: p["overall_rank"])
    return candidates[:count]


def find_candidates(available, priority_type, pick_num):
    """Find up to 3 candidates for a given priority type near the pick."""
    if priority_type == "hitter_bpa":
        pool = [p for p in available if player_is_hitter(p)]
    elif priority_type == "SP":
        pool = [p for p in available if player_is_sp(p)]
    elif priority_type == "closer":
        pool = []
        for p in available:
            if not player_is_rp(p):
                continue
            sv = p.get("projected_stats", {}).get("SV", 0)
            if sv and sv >= 15:
                pool.append(p)
    elif priority_type == "setup":
        pool = []
        for p in available:
            if not player_is_rp(p):
                continue
            if has_tag(p, "SVH_value") or has_tag(p, "HLD_value"):
                pool.append(p)
                continue
            hld = p.get("projected_stats", {}).get("HLD", 0) or p.get("projected_stats", {}).get("proj_HLD", 0)
            svh = p.get("projected_stats", {}).get("SVH", 0) or p.get("projected_stats", {}).get("proj_SVH", 0)
            if (hld and hld >= 15) or (svh and svh >= 20):
                pool.append(p)
        if not pool:
            for p in available:
                if player_is_rp(p):
                    sv = p.get("projected_stats", {}).get("SV", 0)
                    if not sv or sv < 15:
                        pool.append(p)
    elif priority_type == "sleeper":
        pool = [p for p in available
                if "[SLEEPER]" in get_notes(p) or "[BREAKOUT]" in get_notes(p)]
    elif priority_type in HITTER_POSITIONS:
        pool = [p for p in available if player_is_position(p, priority_type)]
    else:
        return []

    return _windowed(pool, pick_num, 3)


def select_targets(available, priorities, pick_num):
    """Select primary target + 2 slip candidates from priority list."""
    window_lo = max(1, pick_num - 10)
    window_mid = max(1, pick_num - 4)
    window_hi = pick_num + 12

    all_candidates = []
    primary = None
    primary_category = None

    for ptype in priorities:
        candidates = find_candidates(available, ptype, pick_num)
        for c in candidates:
            if c not in all_candidates:
                all_candidates.append(c)

        if primary is None and candidates:
            reachable = [c for c in candidates
                         if window_mid <= c["overall_rank"] <= window_hi]
            if reachable:
                primary = reachable[0]
                primary_category = ptype

    if primary is None:
        for ptype in priorities:
            candidates = find_candidates(available, ptype, pick_num)
            reachable = [c for c in candidates if c["overall_rank"] <= window_hi]
            if reachable:
                primary = min(reachable, key=lambda p: abs(p["overall_rank"] - pick_num))
                primary_category = ptype
                break

    if primary is None and all_candidates:
        primary = min(all_candidates, key=lambda p: abs(p["overall_rank"] - pick_num))
        primary_category = priorities[0] if priorities else "BPA"

    if primary is None:
        return None, [], None

    slips = [c for c in all_candidates
             if c != primary
             and c["overall_rank"] < primary["overall_rank"]
             and c["overall_rank"] >= window_lo]
    slips.sort(key=lambda p: p["overall_rank"])
    slips = slips[:2]

    if len(slips) < 2:
        for ptype in priorities:
            extras = find_candidates(available, ptype, pick_num)
            for c in extras:
                if c != primary and c not in slips and c["overall_rank"] >= window_lo and c["overall_rank"] < primary["overall_rank"]:
                    slips.append(c)
                    if len(slips) >= 2:
                        break
            if len(slips) >= 2:
                break

    if len(slips) < 2:
        alts = [c for c in all_candidates if c != primary and c not in slips]
        alts.sort(key=lambda p: abs(p["overall_rank"] - pick_num))
        slips.extend(alts[:2 - len(slips)])

    return primary, slips, primary_category


def category_label(ptype):
    labels = {
        "hitter_bpa": "Best hitter",
        "SP": "Starting pitcher",
        "closer": "Closer",
        "setup": "Setup man",
        "sleeper": "Sleeper/breakout",
    }
    return labels.get(ptype, ptype)


def _print_player(label, p):
    pos = "/".join(p["positions"])
    tags = p.get("projected_stats", {}).get("category_tags", [])
    tag_str = f" [{', '.join(tags)}]" if tags else ""
    notes = f" {p['notes']}" if p.get("notes") else ""
    print(f"  {label:8s}: {p['name']} ({pos}) -- Rank {p['overall_rank']}, Tier {p['tier']}{tag_str}{notes}")


def generate_cheat_sheet(target_round=None, position=None):
    config, derived = load_config()
    team_count = config.team_count
    total_rounds = config.total_draft_rounds - config.roster_slots.get("IL", 0)
    scarcity_deadlines = derived.scarcity_deadlines

    players = load_players()
    draft_pos = position or get_draft_position()
    drafted = get_drafted_names()

    if not draft_pos:
        print("Error: Draft position not set. Run: draft_helper.py init <position>")
        sys.exit(1)

    available = [p for p in players if p["name"] not in drafted]
    strategy = build_round_strategy(draft_pos, team_count, total_rounds, scarcity_deadlines, config.scoring_categories)
    bracket = classify_draft_position(draft_pos, team_count)

    rounds = range(1, total_rounds + 1) if target_round is None else [target_round]

    print(f"Draft Position: {draft_pos} ({bracket.upper()}) | Snake {team_count}-team")
    print()

    for rnd in rounds:
        pick_num = pick_number_for_round(draft_pos, rnd, team_count)
        priorities = strategy.get(rnd, ["hitter_bpa"])

        primary, slips, category = select_targets(available, priorities, pick_num)

        if primary is None:
            continue

        focus = category_label(category)
        print(f"{'='*60}")
        print(f"ROUND {rnd} | Pick #{pick_num} | Focus: {focus}")
        print(f"{'='*60}")
        _print_player("TARGET", primary)
        for i, s in enumerate(slips, 1):
            _print_player(f"SLIP {i}", s)

        warnings = []
        for pos, deadline in scarcity_deadlines.items():
            if rnd == deadline:
                warnings.append(f"{pos} cliff -- last chance for value")
        if warnings:
            print(f"  {'':8s}  ** {'; '.join(warnings)} **")
        print()


def generate_gameplan(position):
    """Generate a 4-round opening sequence based on draft position and scarcity."""
    config, derived = load_config()
    team_count = config.team_count
    scarcity_deadlines = derived.scarcity_deadlines

    players = load_players()
    drafted = get_drafted_names()
    available = [p for p in players if p["name"] not in drafted]
    bracket = classify_draft_position(position, team_count)

    # Sort positions by scarcity deadline to determine opening priorities
    urgent = sorted(
        [(pos, rnd) for pos, rnd in scarcity_deadlines.items() if rnd <= 6],
        key=lambda x: x[1],
    )

    # Build 4-round sequence: R1 is always BPA hitter, then scarce positions
    sequence = [
        ("hitter_bpa", "Best available hitter -- take the best bat on the board"),
    ]

    # Add the 2-3 most urgent positions
    for pos, deadline in urgent[:3]:
        if pos == "SP":
            sequence.append(("SP", f"Starting pitcher -- scarcity deadline round {deadline}"))
        elif pos == "RP":
            sequence.append(("closer", f"Closer -- scarcity deadline round {deadline}"))
        else:
            sequence.append((pos, f"{pos} scarcity -- must draft by round {deadline}"))

    # Late picks: exploit the turn
    if bracket == "late" and len(sequence) >= 2:
        # Swap R2 to SP for the turn exploitation
        sequence.insert(1, ("SP", "THE TURN -- double-dip with back-to-back picks"))
        sequence = sequence[:4]

    # Pad to 4 rounds if needed
    while len(sequence) < 4:
        sequence.append(("hitter_bpa", "Best available hitter"))

    sequence = sequence[:4]

    print(f"{'='*60}")
    print(f"  OPENING GAMEPLAN -- Pick {position} ({bracket.upper()})")
    print(f"{'='*60}")
    print()

    for rnd_idx, (ptype, rationale) in enumerate(sequence, 1):
        pick_num = pick_number_for_round(position, rnd_idx, team_count)
        candidates = find_candidates(available, ptype, pick_num)

        pos_label = category_label(ptype)
        print(f"  ROUND {rnd_idx} | Pick #{pick_num} | Target: {pos_label}")
        print(f"  Why: {rationale}")
        print(f"  Names:")
        for c in candidates[:3]:
            _print_player("   ", c)
        print()

    print(f"{'='*60}")
    print("  SCARCITY REMINDERS")
    print(f"{'='*60}")
    for pos, deadline in sorted(scarcity_deadlines.items(), key=lambda x: x[1]):
        print(f"  {pos}: draft by round {deadline}")
    print()


if __name__ == "__main__":
    target_round = None
    pos_override = None
    mode = "cheatsheet"

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--position":
            pos_override = int(args[i + 1])
            i += 2
        elif args[i] == "gameplan":
            mode = "gameplan"
            i += 1
        else:
            target_round = int(args[i])
            i += 1

    if mode == "gameplan":
        if not pos_override:
            pos_override = get_draft_position()
        if not pos_override:
            print("Error: Draft position required. Use: draft_cheat_sheet.py gameplan --position N")
            sys.exit(1)
        generate_gameplan(pos_override)
    else:
        generate_cheat_sheet(target_round, pos_override)
