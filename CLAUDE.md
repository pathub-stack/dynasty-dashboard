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

**Stage 3 — Polished UI**
Stages 1, 1.5, and 2 are done (local scripts, SQLite database layer,
Flask app deployed live on Render.com). The design direction is decided
and built (dark theme, Oswald headings, leaderboard-styled tables) and
approved as a solid first pass. Only optional item left is charts, not
requested for v1. Once that's settled the documented v1 roadmap is
complete except swapping `TEST_LEAGUE_ID` -> `LEAGUE_ID` (Pre-Release
Checklist below). Full status in the Database Layer section below.

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
- `faab_transactions` — transaction_id, player, roster_id, week, amount_spent
  (keyed by transaction_id + player, not roster_id — a plain autoincrement id
  would've made every re-run duplicate the whole season's rows, and
  transaction_id is Sleeper's own globally-unique id for the claim, so it
  doubles as the natural key)
- `start_sit` — roster_id, week, pf, max_pf, percentage
- `page_visits` — id (autoincrement), route, visited_at. Unlike every
  table above, this one genuinely wants a surrogate key: it's an
  append-only event log (one row per request), not something that gets
  re-derived and replaced on refresh, so there's no natural key to key
  off of.

### Key rules for survivor logic
- Lowest scorer each week is eliminated
- **Ties = both teams eliminated**
- Survivor pot ends after Week 14 (playoffs start Week 15)

### Updated build order
Stage 1 — Local scripts (sleeper.py, calculations.py) ✅
Stage 1.5 — Database layer (database.py):
- `create_tables()`, `insert_teams()`, `insert_weekly_scores()`,
  `insert_survivor_status()`, `insert_start_sit()`, `insert_faab_transactions()` ✅
  (needed two new pieces of groundwork: `sleeper.py`'s
  `get_league_transactions()` for the `/transactions/{week}` endpoint, and
  `get_all_players()`/`get_player_names()` for resolving player_ids to real
  names, caching Sleeper's ~15 MB `/players/nfl` response to
  `players_cache.json` and refetching at most once a day — confirmed
  2026-08-23. Only `type == "waiver"` + `status == "complete"` transactions
  count as spend; free agent adds are $0, failed waiver claims never had
  their bid deducted, and FAAB moved via trades doesn't fit this table's
  per-player shape.)
- Stage 1.5 is now fully complete.
Stage 2 — Flask web app (app.py):
- Basic app + routes for weekly scoreboard (`/scoreboard`), survivor
  standings (`/survivor`), start/sit % (`/start-sit`) ✅ 2026-08-23 —
  plain unstyled HTML/Jinja templates, reads dynasty.db directly, never
  calls the Sleeper API itself
- Error logging around sleeper.py's API calls (Python's `logging` module —
  log failures instead of crashing the page) — confirmed for v1 2026-08-22,
  built 2026-08-23 ✅. `sleeper.py`'s `_get_json()` is now the one place
  every API call goes through; on failure it logs the URL and re-raises.
  Each `database.py` insert function catches that, logs a
  refresh-was-skipped message, and rolls back rather than committing
  partial data — verified against both a real successful run and a
  deliberately-broken league ID.
- Simple traffic monitoring: a `page_visits` table (route, timestamp)
  written via a Flask `before_request` hook — confirmed for v1 2026-08-22,
  built 2026-08-23 ✅, no third-party analytics needed at this scale
- Deploy to Render.com ✅ 2026-08-23. Live at
  https://dynasty-dashboard-ijio.onrender.com — Starter instance (needed
  for a persistent disk, since the free tier's disk is wiped on every
  redeploy/spin-down), disk mounted at `/var/data`, `DB_PATH` env var
  pointing `database.py`'s `DB_NAME` at `/var/data/dynasty.db`. Verified
  persistence for real: ran `python database.py` via Render's Shell,
  confirmed the live pages matched, triggered a Manual Deploy, and
  confirmed the same data was still there afterward without re-running
  anything. `players_cache.json` was deliberately NOT put on the disk —
  it's not league data, just a cache that's harmless to refetch after
  each redeploy.
- Stage 2 is now fully complete.
Stage 3 — Polished UI:
- Deliberate design direction ✅ decided and built 2026-08-23. Dark
  theme, single green accent (gold/silver/bronze for top-3 ranks, red
  for "eliminated"), Oswald for headings/nav, system-ui for body text.
  Home page is now a real hub with card links instead of a paragraph.
  Reviewed live, approved as a "solid first pass." Full reasoning and
  reference points in Obsidian's `Dynasty Dashboard Feature.md`. Lives
  in `static/style.css` + `templates/*.html`.
- Tables and leaderboards ✅ (leaderboard-styled tables, status pills on
  survivor). Charts still optional, not built — not requested for v1.

Power rankings (weekly subjective 1-12 rank + week-over-week change
indicator) considered and intentionally deferred to "someday," not v1 —
full scoping notes in Obsidian's `Dynasty Dashboard Feature.md`.

---

## Pre-Release Checklist

**Before switching from `TEST_LEAGUE_ID` to the real `LEAGUE_ID`** (in
`sleeper.py`, and anywhere it's passed into `database.py`'s insert
functions): delete the database file and re-run `database.py` (via its
`create_tables()`/insert functions) to rebuild it fresh from the real
league's data. **Do this in both places** — they're separate files:

- **Locally:** `dynasty.db` in the project folder.
- **On Render:** `/var/data/dynasty.db` on the persistent disk, via the
  service's Shell tab. Local and production are two independent files —
  fixing one doesn't touch the other.

**Why:** the database is fully regenerable from the Sleeper API — nothing
in it is hand-entered. Its tables (other than `page_visits`) are keyed by
`roster_id`, which Sleeper only guarantees is unique *within one league*,
not globally. Test league and real league data happening to share
`roster_id` numbers means old test rows would mostly get silently
overwritten by `INSERT OR REPLACE` when pointed at the real league, but
if the team counts ever differ, leftover test-league rows could stick
around unnoticed — and since `database.py` never turns on SQLite's
`PRAGMA foreign_keys`, that wouldn't even error, just silently display
wrong data joined against the wrong team. Deleting the file and
rebuilding removes that risk entirely rather than relying on it working
out.

Deleting the whole file also wipes `page_visits` (traffic history),
even though that table has nothing to do with `roster_id` or league
data — decided 2026-08-23 that's an acceptable, low-stakes trade-off for
the simplicity of one clean wipe-and-rebuild step, rather than writing a
more surgical "delete these tables, keep that one" script.

```bash
# Locally:
rm dynasty.db          # or delete it manually in the file explorer
python database.py     # rebuilds all tables fresh, from LEAGUE_ID's data

# On Render, via the service's Shell tab:
rm /var/data/dynasty.db
python database.py
```

---

## Cross-Project Notes Live in Obsidian

Vault path: `C:\Users\patri\Documents\pats-synced-vault`

- **`Dynasty Dashboard Feature.md`** — feature roadmap: ideas, context, and
  "someday" features for this project specifically. This is separate from
  `LEARNING_NOTES.md` below — add an idea here when one comes up, even if
  it's not something to build right now. Read it at the start of a session
  too, since ideas get added ad hoc outside of Claude Code sessions.
  (`fantasy-football-rankings` has its own equivalent file,
  `Dynasty Rankings Feature.md`.)
- **`Learning Notes/Python.md`** — for Python concepts general enough to
  reuse outside this one project. `LEARNING_NOTES.md` (below, in this
  repo) stays the primary session-by-session Python journal for this
  project specifically — nothing about that workflow changes.
- **`Learning Notes/Git & GitHub.md`** — git/GitHub reference, shared
  across both projects.
