"""Non-interactive draft helper for Claude Code mobile workflow.

Each invocation loads state from disk, executes a command, saves state, prints output.
Called via: python draft_helper.py <command> [args]
"""

import argparse
import sys
from pathlib import Path

from config_loader import LeagueConfig, DerivedConfig
from models.roster import Roster
from models.draft_board import DraftBoard
from agents.orchestrator import Orchestrator


CONFIG_PATH = Path("config/league_config.json")
DERIVED_CONFIG_PATH = Path("config/derived_config.json")
PLAYERS_PATH = Path("data/ranked_players.json")
STATE_PATH = Path("data/draft_state.json")
DRAFT_LOG_PATH = Path("data/draft_log.json")


class DraftHelper:
    """Stateless draft helper -- loads from disk, acts, saves."""

    def __init__(self):
        self.config = LeagueConfig(CONFIG_PATH)
        self.derived = DerivedConfig(DERIVED_CONFIG_PATH)
        self.board = DraftBoard.from_json(PLAYERS_PATH)
        self.roster = Roster(self.config.roster_slots, self.derived.flex_eligibility_sets)
        self.current_round = 1
        self.draft_position = self.config.draft_position

        if STATE_PATH.exists():
            state = self.board.load_state(STATE_PATH)
            self.draft_position = state.get("draft_position", self.draft_position)
            self.current_round = state.get("current_round", 1)
            if self.draft_position is not None:
                self.config.draft_position = self.draft_position

            for pick in self.board.draft_log:
                if pick.drafter == "me":
                    slot = self.roster.best_slot_for(pick.player)
                    if slot:
                        self.roster.add_player(pick.player, slot)

    def save(self):
        self.board.save_state(STATE_PATH, self.draft_position, self.current_round)

    def cmd_init(self, position: int):
        if STATE_PATH.exists():
            STATE_PATH.unlink()

        self.board = DraftBoard.from_json(PLAYERS_PATH)
        self.roster = Roster(self.config.roster_slots, self.derived.flex_eligibility_sets)
        self.current_round = 1
        self.draft_position = position
        self.config.draft_position = position

        self.save()
        print(f"Draft initialized. Position: {position}/{self.config.team_count}")
        print(f"Players loaded: {len(self.board.players)}")

    def cmd_pick(self, names: list[str]):
        results = []
        for name in names:
            try:
                player = self.board.record_pick(name, drafter="opponent", round_number=self.current_round)
                results.append(f"  Drafted: {player.name} ({'/'.join(player.positions)}) [opponent]")
            except ValueError as e:
                results.append(f"  Error: {e}")

        self.save()
        print(f"Recorded {len(names)} pick(s):")
        print("\n".join(results))

    def cmd_me(self, name: str):
        player = self.board.record_pick(name, drafter="me", round_number=self.current_round)
        slot = self.roster.best_slot_for(player)
        if slot:
            self.roster.add_player(player, slot)
            print(f"My pick: {player.name} ({'/'.join(player.positions)}) -> {slot}")
        else:
            print(f"My pick: {player.name} ({'/'.join(player.positions)}) [no open slot!]")

        self.save()
        self._print_needs_and_targets()

    def _print_needs_and_targets(self):
        needs = self.roster.needs()
        urgency = self.roster.urgency()
        critical = [p for p in needs if urgency.get(p) == "critical"]
        moderate = [p for p in needs if urgency.get(p) == "moderate"]

        print(f"\n--- NEEDS ---")
        if critical:
            print(f"  Critical: {', '.join(critical)}")
        if moderate:
            print(f"  Moderate: {', '.join(moderate)}")
        other = [p for p in needs if p not in critical and p not in moderate]
        if other:
            print(f"  Open: {', '.join(other)}")

        next_round = self.current_round + 1
        team_count = self.config.team_count
        if next_round % 2 == 1:
            pick_in_round = self.draft_position
        else:
            pick_in_round = team_count - self.draft_position + 1
        next_pick_number = (next_round - 1) * team_count + pick_in_round

        available = self.board.available()
        picks_before_us = next_pick_number - len(self.board.draft_log)
        adp_cutoff = next_pick_number - int(picks_before_us * 0.7)

        scored = []
        for p in available:
            if p.overall_rank < adp_cutoff:
                continue

            fills_need = False
            need_level = "none"
            for pos in p.positions:
                if pos in critical or any(
                    pos in self.roster.slots[n].position
                    for n in critical
                    if n in self.roster.slots
                ):
                    fills_need = True
                    need_level = "critical"
                    break
            if not fills_need:
                test_slot = self.roster.best_slot_for(p)
                if test_slot and test_slot not in ("BN",):
                    fills_need = True
                    need_level = "moderate"

            scored.append({
                "player": p,
                "fills_need": fills_need,
                "need_level": need_level,
            })

        def sort_key(s):
            need_priority = {"critical": 0, "moderate": 1, "none": 2}
            return (need_priority.get(s["need_level"], 2), s["player"].overall_rank)

        scored.sort(key=sort_key)
        targets = scored[:5]
        print(f"\n--- TARGETS (Round {next_round}, Pick ~{next_pick_number}) ---")
        for i, t in enumerate(targets, 1):
            p = t["player"]
            positions = "/".join(p.positions)
            tag = ""
            if t["need_level"] == "critical":
                tag = " [FILLS CRITICAL NEED]"
            elif t["need_level"] == "moderate":
                tag = " [fills need]"
            print(f"  {i}. {p.name} ({positions}) - Rank {p.overall_rank}, Tier {p.tier}{tag}")

    def cmd_rec(self):
        if self.draft_position is None:
            print("Error: Draft position not set. Run: draft_helper.py init <position>")
            return

        orchestrator = Orchestrator(self.config, self.derived)
        recommendations = orchestrator.recommend(self.roster, self.board)

        if not recommendations:
            print("No recommendations available.")
            return

        best = recommendations[0]
        positions = "/".join(best.player.positions)
        print(f">>> PICK: {best.player.name} ({positions}) -- Rank {best.player.overall_rank}, Tier {best.player.tier}")
        print(f"    Why: {best.rationale}")

    def cmd_board(self, position: str | None = None):
        best = self.board.best_available(15, position=position)
        header = "Best available" + (f" at {position}" if position else "")
        print(header)
        for i, p in enumerate(best, 1):
            positions = "/".join(p.positions)
            print(f"  {i:2}. {p.name} ({positions}) - Rank {p.overall_rank}, Tier {p.tier}")

    def cmd_roster(self):
        print(self.roster.summary())

    def cmd_status(self):
        available = len(self.board.available())
        drafted = len(self.board.draft_log)
        my_picks = sum(1 for p in self.board.draft_log if p.drafter == "me")
        needs = self.roster.needs()

        print(f"Round: {self.current_round} | Position: {self.draft_position or 'not set'}")
        print(f"Picks: {drafted} total, {my_picks} mine | Available: {available}")
        print(f"Roster: {self.roster.total_filled}/{self.roster.total_slots} filled | Open needs: {len(needs)}")

        urgency = self.roster.urgency()
        critical = [p for p, l in urgency.items() if l == "critical"]
        if critical:
            print(f"Critical needs: {', '.join(critical)}")

    def cmd_resume(self):
        if not STATE_PATH.exists():
            print("No draft in progress. Run: draft_helper.py init <position>")
            return

        print("=" * 50)
        print("DRAFT RESUME")
        print("=" * 50)
        self.cmd_status()

        print(f"\n{'=' * 50}")
        print("MY ROSTER")
        print("=" * 50)
        self.cmd_roster()

        recent = self.board.draft_log[-12:]
        if recent:
            print(f"\n{'=' * 50}")
            print(f"LAST {len(recent)} PICKS")
            print("=" * 50)
            for pick in recent:
                tag = "ME" if pick.drafter == "me" else "opp"
                positions = "/".join(pick.player.positions)
                print(f"  [{tag}] {pick.player.name} ({positions}) - Rd {pick.round_number}")

        print(f"\n{'=' * 50}")
        print("RECOMMENDATION")
        print("=" * 50)
        self.cmd_rec()

    def cmd_round(self, n: int):
        self.current_round = n
        self.save()
        print(f"Round set to {n}")

    def cmd_undo(self, count: int = 1):
        undone = []
        for _ in range(count):
            if not self.board.draft_log:
                break
            last_pick = self.board.draft_log.pop()
            last_pick.player.drafted = False
            last_pick.player.drafted_by = None
            last_pick.player.draft_round = None
            last_pick.player.draft_pick = None
            self.board._pick_counter -= 1

            if last_pick.drafter == "me":
                for slot in self.roster.slots.values():
                    if last_pick.player in slot.filled:
                        slot.filled.remove(last_pick.player)
                        break

            undone.append(last_pick.player.name)

        self.save()
        if undone:
            print(f"Undone {len(undone)} pick(s): {', '.join(undone)}")
        else:
            print("Nothing to undo.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fantasy Baseball Draft Helper (non-interactive)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    init_p = subparsers.add_parser("init", help="Initialize draft with position")
    init_p.add_argument("position", type=int, help="Draft position")

    pick_p = subparsers.add_parser("pick", help="Record opponent picks")
    pick_p.add_argument("names", nargs="+", help="Player name(s)")

    me_p = subparsers.add_parser("me", help="Record my pick")
    me_p.add_argument("name", help="Player name")

    subparsers.add_parser("rec", help="Get pick recommendations")

    board_p = subparsers.add_parser("board", help="Show best available")
    board_p.add_argument("position", nargs="?", default=None, help="Filter by position")

    subparsers.add_parser("roster", help="Show my roster")
    subparsers.add_parser("status", help="Quick summary")
    subparsers.add_parser("resume", help="Full context dump for new session")

    round_p = subparsers.add_parser("round", help="Set current round")
    round_p.add_argument("n", type=int, help="Round number")

    undo_p = subparsers.add_parser("undo", help="Undo last N picks")
    undo_p.add_argument("count", nargs="?", type=int, default=1, help="Number of picks to undo")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        helper = DraftHelper()
    except FileNotFoundError as e:
        print(f"Error loading data: {e}")
        sys.exit(1)

    try:
        if args.command == "init":
            helper.cmd_init(args.position)
        elif args.command == "pick":
            helper.cmd_pick(args.names)
        elif args.command == "me":
            helper.cmd_me(args.name)
        elif args.command == "rec":
            helper.cmd_rec()
        elif args.command == "board":
            pos = args.position.upper() if args.position else None
            helper.cmd_board(pos)
        elif args.command == "roster":
            helper.cmd_roster()
        elif args.command == "status":
            helper.cmd_status()
        elif args.command == "resume":
            helper.cmd_resume()
        elif args.command == "round":
            helper.cmd_round(args.n)
        elif args.command == "undo":
            helper.cmd_undo(args.count)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
