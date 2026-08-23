# Dynasty Dashboard 🏈

A web dashboard for **"This Is Never Going To Work"** — a 12-team dynasty fantasy football league on Sleeper. Pulls live data from the Sleeper API and displays league stats in a browser for all leaguemates to access.

> **Developer note:** This project is being built as a Python learning exercise. The developer has strong SQL experience but is new to Python. Explain concepts clearly, use SQL analogies where helpful, and walk through the *why* behind decisions, not just the *what*.

---

## Project Goals

Build a browser-accessible dashboard that tracks:

1. **Weekly Scores** — full league scoreboard each week, ranked 1–12
2. **Weekly High Score** — who wins the $25 weekly payout
3. **Survivor Pot Tracker** — who's been eliminated, who's still alive ($5/week, $85 total pot)
4. **Season High Score Leaderboard** — running tracker for the $60 end-of-season payout
5. **Start/Sit % Leaderboard** — compensatory pick race (PF ÷ Max PF), winner gets pick 1.13 in rookie draft
6. **FAAB Spending Tracker** — how each team is spending their $200 waiver budget

---

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.13 | Core language |
| requests | API calls to Sleeper |
| Flask | Web framework — serves dashboard in browser |
| Render.com | Free hosting for leaguemates to access |
| VS Code | Code editor |
| Claude Code | AI coding assistant (you!) |

---

## League Info

| Setting | Value |
|---|---|
| League Name | This Is Never Going To Work |
| League ID | `1364983086189649920` |
| Platform | Sleeper |
| Teams | 12 |
| Scoring | Half PPR |
| Roster | 1 QB, 2 RB, 3 WR, 1 TE, 3 FLEX, 15 BN |
| No K or DEF | Correct |
| Taxi Squad | 4 rookies only |
| Playoffs | 6 teams, Weeks 15–17 |
| Trade Deadline | None (up until playoffs) |

---

## Payout Structure

| Payout | Amount | Notes |
|---|---|---|
| 1st Place | $870 | Paid end of season |
| 2nd Place | $300 | Paid end of season |
| Season High Score | $60 | Paid end of season |
| Weekly High Score | $25/week × 17 = $425 | Paid end of season |
| Survivor Pot | $85 total | Last team standing wins, paid end of season |
| **Total** | **$1,800** | 12 teams × $150 buy-in |

**Survivor Rules:** Lowest scorer each week is eliminated. $5/week accumulates. Last team standing takes the pot. Eliminated teams still compete for all other payouts.

---

## Compensatory Pick — Start/Sit %

Each year, the team with the highest **start/sit %** earns pick **1.13** (end of round 1) in the rookie draft.

**Formula:** `Start/Sit % = PF ÷ Max PF`
- `PF` = actual points scored across the season
- `Max PF` = maximum possible points if the perfect lineup had been set every week
- Higher % = better roster management

This needs to be tracked weekly and displayed as a live leaderboard.

---

## Sleeper API Reference

- **Base URL:** `https://api.sleeper.app/v1/`
- **Authentication:** None required (fully public, read-only)
- **Rate Limit:** 90 requests/minute per IP
- **Format:** All responses are JSON
- **Docs:** https://docs.sleeper.com

### Key Endpoints

```
# League info
GET /league/{league_id}

# All rosters in the league
GET /league/{league_id}/rosters

# All users/teams in the league
GET /league/{league_id}/users

# Matchups for a specific week
GET /league/{league_id}/matchups/{week}

# Transactions (trades, waivers, drops)
GET /league/{league_id}/transactions/{week}

# Traded picks
GET /league/{league_id}/traded_picks

# NFL state (current week, season, etc.)
GET /v1/state/nfl
```

---

## Project Structure

```
dynasty-dashboard/
│
├── venv/                   ← virtual environment (never edit this)
├── README.md               ← this file
├── app.py                  ← Flask web app (Stage 2)
├── sleeper.py              ← all Sleeper API calls live here
├── calculations.py         ← logic: survivor, start/sit %, high score
├── templates/              ← HTML templates for Flask
│   └── index.html
├── static/                 ← CSS and any static assets
│   └── style.css
└── requirements.txt        ← list of packages (generated with pip freeze)
```

> **Note:** This structure will be built incrementally. Start with `sleeper.py` first.

---

## Build Order

### Stage 1 — Local Python Scripts
Get data flowing from the Sleeper API and print results to the terminal. No web stuff yet.

- [ ] `sleeper.py` — functions that call the API and return data
- [ ] Pull league info and print team names
- [ ] Pull weekly matchup scores
- [ ] Calculate weekly high score
- [ ] Build survivor tracker logic
- [ ] Calculate start/sit % per team
- [ ] Track FAAB usage per team

### Stage 2 — Flask Web App
Wrap Stage 1 scripts in Flask so they render in a browser.

- [ ] Set up basic Flask app in `app.py`
- [ ] Create route for weekly scoreboard
- [ ] Create route for survivor standings
- [ ] Create route for start/sit % leaderboard
- [ ] Deploy to Render.com

### Stage 3 — Polished UI
Make it look like an actual dashboard.

- [ ] Style with CSS
- [ ] Add tables and leaderboards
- [ ] Add charts if needed

---

## Environment Setup (already done)

```bash
# Create virtual environment (one time only)
python -m venv venv

# Activate virtual environment (every session)
.\venv\Scripts\activate

# Install packages (one time only)
pip install requests flask

# Generate requirements.txt (run after installing any new package)
pip freeze > requirements.txt
```

> **Important:** Always activate `(venv)` before working. You'll see `(venv)` at the start of your terminal line when it's active.

---

## Developer Notes

- Owner is learning Python through this project — SQL background, new to Python
- Explain the *why* behind every decision, not just the *what*
- Use SQL analogies where helpful (API = source tables, functions = stored procedures, etc.)
- Build incrementally — get something working before adding complexity
- Cross-project learning notes are maintained in Obsidian (see CLAUDE.md) and updated after each session
- League bylaws Google Doc: shared separately

---

## LEARNING_NOTES.md — How to Maintain It

A file called `LEARNING_NOTES.md` lives in this project folder. After every meaningful coding session, update it with what was built and learned.

**Writing style rules:**
- Write in first person, casual tone — like personal notes, not documentation
- Explain the *why* behind every concept, not just the *what*
- Use SQL analogies wherever they help ("this is like a JOIN because...")
- Note any mistakes made and how they were fixed — that's part of learning
- Keep code snippets short and annotated with comments explaining each line
- Flag anything confusing with a ❓ so it can be revisited
- Flag anything that clicked with a ✅ so the pattern can be reused

**When to update it:**
- After installing a new package
- After writing a new function
- After hitting and fixing an error
- After any concept that needed explanation
- At the end of every coding session with a short summary

**Format per session:**
```
## Session [date] — [what we worked on]

### What we built
### New concepts learned
### Mistakes & fixes
### Questions / still confused about
### Code snippets worth remembering
```

---

## Database Layer

### Why
Instead of hitting the Sleeper API every page load, we pull data on a schedule and store it locally. Faster dashboard, historical data, and SQL querying practice.

### Stack
- **SQLite** to start (single file, built into Python, no setup)
- **PostgreSQL** later if needed (Supabase or Railway, free tier)

### Pipeline
```
Sleeper API → Python script (scheduled) → SQLite database → Flask → Browser
```

### Schema

```sql
CREATE TABLE teams (
    roster_id INTEGER PRIMARY KEY,
    team_name TEXT,
    owner_name TEXT
);

CREATE TABLE weekly_scores (
    roster_id INTEGER,
    week INTEGER,
    points REAL,
    PRIMARY KEY (roster_id, week),
    FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
);

CREATE TABLE survivor_status (
    roster_id INTEGER PRIMARY KEY,
    week_eliminated INTEGER, -- NULL means still alive
    FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
);

CREATE TABLE faab_transactions (
    transaction_id TEXT,
    player TEXT,
    roster_id INTEGER,
    week INTEGER,
    amount_spent INTEGER,
    PRIMARY KEY (transaction_id, player),
    FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
);

CREATE TABLE start_sit (
    roster_id INTEGER,
    week INTEGER,
    pf REAL,
    max_pf REAL,
    percentage REAL,
    PRIMARY KEY (roster_id, week),
    FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
);
```

### Updated project structure
```
dynasty-dashboard/
│
├── venv/
├── CLAUDE.md
├── README.md
├── BYLAWS.md
├── LEARNING_NOTES.md
├── STARTUP_CHECKLIST.md
├── dynasty.db              ← SQLite database (auto-created)
├── sleeper.py              ← Sleeper API calls
├── calculations.py         ← business logic
├── database.py             ← database setup and write functions (NEW)
├── app.py                  ← Flask web app
├── templates/
│   └── index.html
├── static/
│   └── style.css
└── requirements.txt
```
