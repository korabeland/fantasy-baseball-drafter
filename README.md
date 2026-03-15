# Fantasy Baseball Draft Assistant

A configurable fantasy baseball draft assistant designed for use with [Claude Code](https://claude.ai/code). Supports any league format, scoring categories, and roster configuration.

## Features

- **Config-driven**: One setup flow configures everything for your league
- **Three-agent recommendation engine**: Analyzes roster needs, positional scarcity, and category balance to suggest optimal picks
- **Draft-day CLI**: Interactive and non-interactive modes for live draft tracking
- **Round-by-round cheat sheet**: Pre-computed targets based on your draft position
- **Data pipeline**: Merges rankings, projections, and research into unified player rankings

## Prerequisites

| Tool | Required | Install |
|------|----------|---------|
| Python 3.11+ | Yes | [python.org/downloads](https://python.org/downloads) |
| Claude Code | Recommended | [claude.ai/code](https://claude.ai/code) |

Python packages (installed automatically or via `pip install -r requirements.txt`):
- `pandas`, `numpy`

Optional (for charts): `pip install -r requirements-optional.txt`

## Quick Start

### 1. Clone and setup

```bash
git clone <repo-url>
cd fantasy-baseball-drafter
pip install -r requirements.txt
python setup.py
```

The setup wizard walks you through:
- League platform (Yahoo/ESPN/CBS/Fantrax)
- Team count, scoring categories, roster slots
- Draft type and position

### 2. Import player data

```bash
# From Fangraphs CSV export
python import_data.py --csv ~/Downloads/fangraphs_projections.csv

# From JSON rankings
python import_data.py --rankings rankings.json
```

Or ask Claude Code to help extract data from screenshots.

### 3. Build rankings

```bash
python research/build_rankings.py
python research/verify_rankings.py  # Optional validation
```

### 4. Draft day

**Interactive CLI:**
```bash
python cli.py
```

**With Claude Code (recommended):**
```bash
python draft_helper.py init 6    # Your draft position
python draft_helper.py rec       # Get pick recommendation
```

**Cheat sheet:**
```bash
python draft_cheat_sheet.py                      # All rounds
python draft_cheat_sheet.py gameplan --position 6 # Opening 4 rounds
```

## Architecture

```
setup.py  -->  config/league_config.json  -->  config/derived_config.json
                                                        |
data/raw/*.json  -->  research/build_rankings.py  -->  data/ranked_players.json
                                                        |
                                              cli.py / draft_helper.py
                                                        |
                                              Orchestrator (3 agents)
                                                        |
                                              Pick recommendation
```

### Configuration Layers

1. **`league_config.json`** -- Your league settings (team count, categories, roster)
2. **`derived_config.json`** -- Auto-computed constants (season targets, thresholds, flex rules)
3. **`data/raw/*.json`** -- Player data (rankings, projections, reliever data)
4. **`strategic_adjustments.json`** -- Optional research-based adjustments

### Supported League Formats

- **Scoring**: H2H Categories, Roto, H2H Points
- **Categories**: Any combination (standard 5x5, QS, SV+H, OBP, custom)
- **Roster**: Standard OF, LF/CF/RF, MI/CI, any slot configuration
- **Draft**: Snake, auction, keeper

## Using with Claude Code

Claude Code is the primary interface for this tool. It can:

1. **Run setup** interactively
2. **Import data** from screenshots, CSVs, or web sources
3. **Generate strategic adjustments** via research (with Perplexity MCP) or targeted questions
4. **Track your live draft** via the non-interactive `draft_helper.py`
5. **Make pick recommendations** using the three-agent system

See `CLAUDE.md` for detailed Claude Code instructions.

## License

MIT
