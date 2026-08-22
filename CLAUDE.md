# Claude Code Instructions — Dynasty Dashboard

Read this file and README.md and LEARNING_NOTES.md before doing anything else.

---

## About This Project

Building a browser-accessible fantasy football dashboard for a 12-team dynasty
league called "This Is Never Going To Work" on Sleeper. Pulls live data from
the Sleeper API and displays league stats for all leaguemates.

Full project details, league info, API endpoints, and build roadmap are in README.md.

---

## About the Developer

- **SQL background** — strong experience with queries, aggregations, joins
- **Python experience** — beginner, learning through this project
- **Goal** — understand what the code is doing and why, not just copy/paste solutions

---

## How to Work With Me

**Always explain the why, not just the what.**
Don't just write code — explain what each part does and why we're doing it that way.

**Use SQL analogies.**
Whenever a Python concept maps to something in SQL, call it out explicitly.
Examples:
- A Python function → like a stored procedure
- A list → like a result set
- A dictionary → like a row with named columns
- Iterating a list → like a cursor or row-by-row operation
- An API call → like a linked server query
- A package → like a built-in SQL function you didn't have to write

**Go step by step.**
Don't build everything at once. Get one thing working, explain it, then move on.

**Call out mistakes.**
If something errors, explain what went wrong and why before fixing it.
Mistakes are learning opportunities — don't just silently fix them.

**Flag patterns worth remembering.**
If we write something that will be reused later, say so explicitly.

---

## After Every Session — Update LEARNING_NOTES.md

At the end of every coding session, update `LEARNING_NOTES.md` with a new entry.

**Writing style:**
- First person, casual tone — like personal notes, not documentation
- Explain concepts like I'm writing to my future self
- Use SQL analogies where helpful
- Keep code snippets short with comments on every line explaining what it does
- Note mistakes made and how they were fixed
- Flag anything still confusing with ❓
- Flag anything that clicked with ✅

**Format for each session entry:**
```
## Session [DATE] — [what we worked on]

### What we built

### New concepts learned

### Mistakes & fixes

### Questions / still confused about ❓

### Code snippets worth remembering
```

---

## Project Files

| File | Purpose |
|---|---|
| `README.md` | Full project context, league info, API reference, build roadmap |
| `CLAUDE.md` | This file — auto-read by Claude Code every session |
| `LEARNING_NOTES.md` | Running learning journal — update after every session |
| `STARTUP_CHECKLIST.md` | Step-by-step guide for starting VS Code correctly |
| `sleeper.py` | All Sleeper API calls (build this first) |
| `calculations.py` | Logic for survivor, start/sit %, high score |
| `app.py` | Flask web app |
| `templates/index.html` | HTML for the dashboard |
| `requirements.txt` | Package list (run `pip freeze > requirements.txt` after installs) |

---

## Current Build Stage

**Stage 1 — Local Python Scripts**
Getting data flowing from the Sleeper API and printing to terminal.
Start with `sleeper.py` — first task is pulling league info and printing team names.

---

## Key Info

- **League ID:** `1364983086189649920`
- **Sleeper API base URL:** `https://api.sleeper.app/v1/`
- **No auth required** — fully public read-only API
- **Rate limit:** 90 requests/minute

---

## Database Layer

A SQLite database (`dynasty.db`) stores data pulled from the Sleeper API. All database setup and write functions live in `database.py`. Flask queries the database rather than hitting the API directly on each page load.

### Tables
- `teams` — roster_id, team_name, owner_name
- `weekly_scores` — roster_id, week, points
- `survivor_status` — roster_id, week_eliminated (NULL = still alive)
- `faab_transactions` — roster_id, week, player, amount_spent
- `start_sit` — roster_id, week, pf, max_pf, percentage

### Key rules for survivor logic
- Lowest scorer each week is eliminated
- **Ties = both teams eliminated**
- Survivor pot ends after Week 14 (playoffs start Week 15)

### Updated build order
Stage 1 — Local scripts (sleeper.py, calculations.py) ✅
Stage 1.5 — Database layer (database.py) ← next
Stage 2 — Flask web app (app.py)
Stage 3 — Polished UI
