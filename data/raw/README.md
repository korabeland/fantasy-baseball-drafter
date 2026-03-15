# Raw Data Directory

This directory holds the input data files consumed by `research/build_rankings.py`.

## Expected Files

### `yahoo_rankings.json` (required)
Player rankings backbone. List of objects:
```json
[
    {
        "name": "Aaron Judge",
        "team": "NYY",
        "positions": ["RF"],
        "overall_rank": 1
    }
]
```

### `fangraphs_projections.json` (recommended)
Stat projections. Object with `hitters` and `pitchers` arrays:
```json
{
    "source": "Fangraphs Steamer 2026",
    "hitters": [
        {"name": "Aaron Judge", "team": "NYY", "R": 109, "HR": 42, "RBI": 102, "SB": 9, "AVG": 0.283}
    ],
    "pitchers": [
        {"name": "Tarik Skubal", "team": "DET", "IP": 199.2, "GS": 32, "K": 243, "ERA": 2.79, "WHIP": 1.01, "SV": 0, "W": 14}
    ]
}
```

### `svh_relievers.json` (only for SV+H leagues)
Saves + Holds projections for relievers:
```json
[
    {"name": "Andres Munoz", "team": "SEA", "role": "CL", "proj_sv": 30, "proj_hld": 3, "proj_svh": 33, "notes": "Elite closer"}
]
```

### `of_positions.json` (only for LF/CF/RF leagues)
Maps generic "OF" to specific outfield positions:
```json
{
    "Aaron Judge": ["RF"],
    "Juan Soto": ["RF"],
    "Kyle Tucker": ["LF"]
}
```

## How to Populate

1. **CSV import**: `python import_data.py --csv projections.csv`
2. **Screenshots**: Send screenshots of your league's rankings to Claude Code
3. **Manual**: Create the JSON files directly following the formats above
