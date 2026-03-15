"""Fantasy Baseball Draft Assistant -- CLI entry point."""

import sys
from pathlib import Path

from config_loader import LeagueConfig, DerivedConfig
from models.roster import Roster
from models.draft_board import DraftBoard
from agents.orchestrator import Orchestrator


CONFIG_PATH = Path("config/league_config.json")
DERIVED_CONFIG_PATH = Path("config/derived_config.json")
PLAYERS_PATH = Path("data/ranked_players.json")
DRAFT_LOG_PATH = Path("data/draft_log.json")


def main():
    # Load config
    print("Loading league config...", end=" ")
    try:
        config = LeagueConfig(CONFIG_PATH)
    except (FileNotFoundError, ValueError) as e:
        print(f"\nError: {e}")
        sys.exit(1)
    print("done")

    # Load derived config
    print("Loading derived config...", end=" ")
    try:
        derived = DerivedConfig(DERIVED_CONFIG_PATH)
    except FileNotFoundError:
        print(f"\nError: {DERIVED_CONFIG_PATH} not found. Run 'python setup.py --derive' first.")
        sys.exit(1)
    print("done")

    # Load player pool
    print("Loading ranked players...", end=" ")
    try:
        board = DraftBoard.from_json(PLAYERS_PATH)
    except FileNotFoundError:
        print(f"\nError: {PLAYERS_PATH} not found. Run pre-draft research first.")
        sys.exit(1)
    print(f"done ({len(board.players)} players)")

    # Initialize roster and orchestrator
    roster = Roster(config.roster_slots, derived.flex_eligibility_sets)
    orchestrator = Orchestrator(config, derived)

    # Get draft position if not set
    if config.draft_position is None:
        while True:
            pos = input("Draft position? ").strip()
            if pos.isdigit() and 1 <= int(pos) <= config.team_count:
                config.draft_position = int(pos)
                break
            print(f"Enter a number 1-{config.team_count}")

    current_round = 1
    print(f"\nReady. Draft position: {config.draft_position}/{config.team_count}")
    print("Commands: pick <name>, me <name>, rec, roster, board, status, round <n>, undo, save, quit")
    print(f"Round {current_round}")
    print("-" * 50)

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "quit" or cmd == "exit":
                board.save_draft_log(DRAFT_LOG_PATH)
                print(f"Draft log saved to {DRAFT_LOG_PATH}. Goodbye!")
                break

            elif cmd == "pick":
                if not arg:
                    print("Usage: pick <player name>")
                    continue
                player_name = arg.split(",")[0].strip()
                player = board.record_pick(player_name, drafter="opponent", round_number=current_round)
                print(f"  Drafted: {player.name} ({'/'.join(player.positions)}) [opponent]")

            elif cmd == "me":
                if not arg:
                    print("Usage: me <player name>")
                    continue
                player_name = arg.split(",")[0].strip()
                player = board.record_pick(player_name, drafter="me", round_number=current_round)
                slot = roster.best_slot_for(player)
                if slot:
                    roster.add_player(player, slot)
                    print(f"  Drafted: {player.name} ({'/'.join(player.positions)}) -> {slot}")
                else:
                    print(f"  Drafted: {player.name} ({'/'.join(player.positions)}) [no open slot!]")

            elif cmd == "rec":
                recommendations = orchestrator.recommend(roster, board)
                print("-" * 50)
                print(orchestrator.display_recommendations(recommendations))
                print("-" * 50)

            elif cmd == "roster":
                print(roster.summary())

            elif cmd == "board":
                pos = arg.upper() if arg else None
                best = board.best_available(15, position=pos)
                header = f"Best available" + (f" at {pos}" if pos else "")
                print(header)
                for i, p in enumerate(best, 1):
                    positions = "/".join(p.positions)
                    print(f"  {i:2}. {p.name} ({positions}) - Rank {p.overall_rank}, Tier {p.tier}")

            elif cmd == "status":
                print(orchestrator.display_status(roster, board))

            elif cmd == "round":
                if arg.isdigit():
                    current_round = int(arg)
                    print(f"Round {current_round}")
                else:
                    current_round += 1
                    print(f"Round {current_round}")

            elif cmd == "undo":
                if board.draft_log:
                    last_pick = board.draft_log.pop()
                    last_pick.player.drafted = False
                    last_pick.player.drafted_by = None
                    last_pick.player.draft_round = None
                    last_pick.player.draft_pick = None
                    board._pick_counter -= 1
                    if last_pick.drafter == "me":
                        for slot in roster.slots.values():
                            if last_pick.player in slot.filled:
                                slot.filled.remove(last_pick.player)
                                break
                    print(f"  Undone: {last_pick.player.name}")
                else:
                    print("  Nothing to undo.")

            elif cmd == "save":
                board.save_draft_log(DRAFT_LOG_PATH)
                print(f"  Saved to {DRAFT_LOG_PATH}")

            elif cmd == "help":
                print("Commands:")
                print("  pick <name>    - Record opponent pick")
                print("  me <name>      - Record my pick")
                print("  rec            - Get pick recommendations")
                print("  roster         - Show my roster")
                print("  board [POS]    - Show best available (optionally by position)")
                print("  status         - Quick status summary")
                print("  round [n]      - Set round number (or advance by 1)")
                print("  undo           - Undo last pick")
                print("  save           - Save draft log")
                print("  quit           - Save and exit")

            else:
                print(f"  Unknown command: {cmd}. Type 'help' for commands.")

        except ValueError as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    main()
