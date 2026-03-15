"""Import player data from CSV or other formats.

Auto-detects CSV column headers to determine source format.
Writes to data/raw/ in expected JSON format.

Usage:
    python import_data.py --csv projections.csv          # Auto-detect format
    python import_data.py --format fangraphs --csv f.csv  # Explicit format
    python import_data.py --rankings rankings.json        # JSON rankings
"""

import argparse
import csv
import json
import sys
from pathlib import Path


OUTPUT_DIR = Path("data/raw")


# Column header patterns for auto-detection
FORMAT_SIGNATURES = {
    "fangraphs": {"Name", "Team", "HR", "RBI", "ERA"},
    "fantasypros": {"Player", "Team", "ADP", "AVG"},
    "espn": {"PLAYER", "POS", "R", "HR"},
}


def detect_format(headers: list[str]) -> str:
    """Detect CSV format from column headers."""
    header_set = set(headers)
    best_match = None
    best_score = 0

    for fmt, signature in FORMAT_SIGNATURES.items():
        overlap = len(header_set & signature)
        if overlap > best_score:
            best_score = overlap
            best_match = fmt

    return best_match or "unknown"


def parse_fangraphs_csv(filepath: Path) -> dict:
    """Parse Fangraphs projection CSV into hitters and pitchers."""
    hitters = []
    pitchers = []

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", row.get("name", "")).strip()
            team = row.get("Team", row.get("team", "")).strip()

            if not name:
                continue

            # Detect hitter vs pitcher
            gs = int(row.get("GS", 0) or 0)
            ip = float(row.get("IP", 0) or 0)

            if gs > 0 or ip > 30:
                # Pitcher
                pitcher = {
                    "name": name,
                    "team": team,
                    "IP": float(row.get("IP", 0) or 0),
                    "GS": int(row.get("GS", 0) or 0),
                    "K": int(row.get("SO", row.get("K", 0)) or 0),
                    "ERA": float(row.get("ERA", 0) or 0),
                    "WHIP": float(row.get("WHIP", 0) or 0),
                    "SV": int(row.get("SV", 0) or 0),
                    "W": int(row.get("W", 0) or 0),
                }
                pitchers.append(pitcher)
            else:
                # Hitter
                hitter = {
                    "name": name,
                    "team": team,
                    "R": int(row.get("R", 0) or 0),
                    "HR": int(row.get("HR", 0) or 0),
                    "RBI": int(row.get("RBI", 0) or 0),
                    "SB": int(row.get("SB", 0) or 0),
                    "AVG": float(row.get("AVG", 0) or 0),
                }
                # Optional stats
                for stat in ("OBP", "SLG", "OPS", "H", "TB", "BB"):
                    if stat in row and row[stat]:
                        try:
                            hitter[stat] = float(row[stat])
                        except ValueError:
                            pass
                hitters.append(hitter)

    return {
        "source": "Fangraphs CSV import",
        "hitters": hitters,
        "pitchers": pitchers,
    }


def parse_generic_csv(filepath: Path) -> dict:
    """Parse a generic CSV -- best effort mapping."""
    hitters = []
    pitchers = []

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Try to map columns
        name_col = next((h for h in headers if h.lower() in ("name", "player", "playername")), None)
        team_col = next((h for h in headers if h.lower() in ("team", "tm")), None)

        if not name_col:
            print(f"Error: Could not find name column. Headers: {headers}")
            sys.exit(1)

        for row in reader:
            name = row.get(name_col, "").strip()
            team = row.get(team_col, "").strip() if team_col else ""

            if not name:
                continue

            # Check if pitcher
            is_pitcher = False
            for key in ("IP", "ERA", "GS", "WHIP"):
                val = row.get(key, "")
                if val and float(val or 0) > 0:
                    is_pitcher = True
                    break

            if is_pitcher:
                pitcher = {"name": name, "team": team}
                for stat in ("IP", "GS", "K", "SO", "ERA", "WHIP", "SV", "W"):
                    if stat in row and row[stat]:
                        try:
                            pitcher[stat] = float(row[stat])
                        except ValueError:
                            pass
                if "SO" in pitcher and "K" not in pitcher:
                    pitcher["K"] = pitcher.pop("SO")
                pitchers.append(pitcher)
            else:
                hitter = {"name": name, "team": team}
                for stat in ("R", "HR", "RBI", "SB", "AVG", "OBP", "SLG", "OPS", "H", "TB", "BB"):
                    if stat in row and row[stat]:
                        try:
                            hitter[stat] = float(row[stat])
                        except ValueError:
                            pass
                hitters.append(hitter)

    return {
        "source": "CSV import",
        "hitters": hitters,
        "pitchers": pitchers,
    }


def parse_rankings_json(filepath: Path) -> list[dict]:
    """Load rankings from JSON (expected format: list of {name, team, positions, overall_rank})."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Import player data")
    parser.add_argument("--csv", help="Path to CSV file with projections")
    parser.add_argument("--rankings", help="Path to JSON rankings file")
    parser.add_argument("--format", choices=["fangraphs", "fantasypros", "espn", "auto"],
                        default="auto", help="CSV format (default: auto-detect)")
    args = parser.parse_args()

    if not args.csv and not args.rankings:
        parser.print_help()
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.rankings:
        filepath = Path(args.rankings)
        data = parse_rankings_json(filepath)
        output = OUTPUT_DIR / "yahoo_rankings.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(data)} rankings to {output}")
        return

    if args.csv:
        filepath = Path(args.csv)
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)

        # Auto-detect or use specified format
        fmt = args.format
        if fmt == "auto":
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
            fmt = detect_format(headers)
            print(f"Auto-detected format: {fmt}")

        if fmt == "fangraphs":
            data = parse_fangraphs_csv(filepath)
        else:
            data = parse_generic_csv(filepath)

        output = OUTPUT_DIR / "fangraphs_projections.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Saved {len(data['hitters'])} hitters and {len(data['pitchers'])} pitchers to {output}")


if __name__ == "__main__":
    main()
