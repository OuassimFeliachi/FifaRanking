# FIFA Elo — Internal Competition Manager

A lightweight Flask web app to manage an internal FIFA competition between colleagues, using an **Elo rating system** for fair rankings regardless of the number of games played.

---

## Features

- **Elo ranking** — ratings computed from scratch on every change, processed chronologically
- **Classic table** — points (W×3 + D×1), goal difference, win rate
- **Add players** — with accent-aware deduplication (Loïc = Loic)
- **Record matches** — with validation
- **Match history** — sorted by date then insertion order
- **Player profiles** — stats + rating evolution chart (Chart.js)
- **CSV import** — bulk-import historical matches via web UI or CLI

---

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
flask --app app.py run
```

Open http://127.0.0.1:5000 in your browser.

The SQLite database (`elo.db`) is created automatically on first run.

---

## CSV Import

### Via the web UI
Go to **Import CSV** in the navigation bar and upload your file.

### Via CLI
```bash
python scripts/import_history.py path/to/matches.csv
```

### Expected CSV format
```
Date,Joueur 1,Score J1,Score J2,Joueur 2
01/09/2024,Alice,3,1,Bob
02/09/2024,Loïc,2,2,Charlie
```

- Date format: `dd/mm/yyyy`
- Missing players are created automatically

---

## Elo System

| Parameter | Value |
|---|---|
| Initial rating | 1500 |
| K factor | 32 |
| Win | 1.0 |
| Draw | 0.5 |
| Loss | 0.0 |

Formula: `E = 1 / (1 + 10^((opp - rating) / 400))`

Ratings are **fully recomputed from scratch** on every match insertion or import, ensuring consistency.

---

## Project Structure

```
remi-elo/
├── app.py                  # Entry point
├── requirements.txt
├── README.md
├── app/
│   ├── __init__.py         # App factory
│   ├── models.py           # SQLAlchemy models
│   ├── routes.py           # Flask routes (thin)
│   ├── rating.py           # Pure Elo logic
│   ├── services.py         # Business logic / DB mutations
│   ├── utils.py            # Name normalization helper
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html          # Ranking
│   │   ├── players.html
│   │   ├── add_match.html
│   │   ├── matches.html
│   │   ├── player_detail.html
│   │   └── import_csv.html
│   └── static/
│       └── style.css
└── scripts/
    └── import_history.py   # CLI import tool
```
