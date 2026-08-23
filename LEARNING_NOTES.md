# Python Learning Notes 🐍
### Project: Dynasty Dashboard — "This Is Never Going To Work"
*Started: August 2026*

> These are my personal notes as I learn Python through a real project.
> I'm coming in with strong SQL experience but Python is new to me.
> Notes are written casually — like I'm explaining things to myself.

---

## Background

I'm building a web dashboard for my dynasty fantasy football league that pulls
live data from the Sleeper API. The goal is to track weekly scores, the survivor
pot, start/sit %, and FAAB spending — stuff I'd otherwise track manually.

Using this project to learn Python properly rather than just following tutorials.
Claude Code (in VS Code) helps me build and explains everything as we go.
This file stays the session-by-session journal for this project specifically;
general Python concepts also get added to `Learning Notes/Python.md` in my
Obsidian vault so they're reusable outside this one project.

---

## Environment Setup ✅

**What I learned:** Before writing any code you need a virtual environment.
Think of it like a schema isolated to just this project — packages installed
here don't affect anything else on my machine.

```bash
# Create the virtual environment (one time only)
python -m venv venv

# Activate it (run this every time you open the project)
.\venv\Scripts\activate

# You know it worked when you see (venv) in your terminal:
# (venv) PS C:\Users\patri\Desktop\dynasty-dashboard>
```

**Windows gotcha:** Had to run this first because Windows blocks scripts by default:
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
`RemoteSigned` = local scripts can run, downloaded ones need to be signed. Safe.
`CurrentUser` = only affects my account, not the whole machine.

---

## Packages Installed ✅

```bash
pip install requests flask
```

**requests** — handles API calls. When I ask "give me week 3 scores" this is
what actually sends that request to Sleeper's servers and brings back the answer.
SQL analogy: like a linked server query pulling from an external database.

**flask** — lightweight web framework. Eventually turns my Python scripts into
something that renders in a browser instead of just printing to the terminal.
SQL analogy: like the reporting layer on top of your queries.

**What is pip?** Python's package manager. Like an app store for code libraries.
`pip install X` downloads package X and makes it available in my project.

---

## Sessions

## Session 2026-08-08 — Built sleeper.py and calculations.py (Stage 1)

### What we built

**`sleeper.py`** — all the raw Sleeper API calls live here:
- `get_league_info(league_id)` — league status, current week, playoff start week
- `get_league_users(league_id)` — team owners
- `get_league_rosters(league_id)` — roster_id → owner_id, plus season totals (fpts/ppts)
- `get_league_matchups(league_id, week)` — one week's scores
- `get_team_names_by_roster(league_id)` — the reusable "join" that turns a roster_id
  into an actual team name, built from users + rosters together

**`calculations.py`** — logic that sits on top of the raw data:
- `get_survivor_results(league_id, last_week)` — simulates the survivor pot week by
  week, eliminating the lowest scorer(s) until one team's left
- `get_start_sit_percentages(league_id)` — PF ÷ Max PF leaderboard for the
  compensatory pick race

Also learned our real league (`LEAGUE_ID`) hasn't started its season yet, so there's
no matchup data for it. Added `TEST_LEAGUE_ID` pointing at last year's completed
league so there's actual data to build and test against in the meantime.

### New concepts learned

**Functions = stored procedures.** `def get_league_users(league_id):` takes a
parameter and returns a value, same shape as `CREATE PROCEDURE ... @LeagueID`.

**Dictionaries = a row with named columns.** A single user record like
`{'display_name': 'CJSpillerTruther', 'metadata': {...}}` is a row you access by
key instead of by position. Nested dicts (`metadata.team_name`) are just a column
that happens to hold structured data instead of a plain value.

**Building lookup dictionaries = building a small indexed table to join against.**
Instead of scanning a whole list every time you need a name, you build a dict once
keyed by the id you'll look up (`{user_id: team_name}`), then every future lookup
is instant instead of a scan. This is the pattern basically every calculation in
this project uses — Sleeper's data almost never links directly to a human-readable
name, so you're always chaining `id -> id -> name` through 2+ of these.

```python
# roster_id -> team name, built by chaining two lookup dicts together
team_names_by_owner = {}
for user in users:
    team_names_by_owner[user["user_id"]] = user["metadata"].get("team_name", user["display_name"])

team_names_by_roster = {}
for roster in rosters:
    team_names_by_roster[roster["roster_id"]] = team_names_by_owner[roster["owner_id"]]
```

**List comprehensions = a compact SELECT...WHERE.**
```python
alive_scores = [
    (matchup["roster_id"], matchup["points"])
    for matchup in matchups
    if matchup["roster_id"] in alive
]
```
Reads like `SELECT roster_id, points FROM matchups WHERE roster_id IN (alive)` —
builds a full list in memory. A **generator expression** (same thing without the
`[ ]`) does the same job but hands out values one at a time instead of building the
whole list up front — used it for a quick `min()` pass where I didn't need to keep
the list around after.

**Sets = a table with a unique constraint and no ordering.** Used a set (`alive`)
to track which roster_ids are still in the survivor pot, because all we ever do
with it is check membership (`if x in alive`) or remove one entry — no sorting
needed, and duplicates shouldn't be possible anyway.

**`sort()`/`min()` with `key=lambda`.** Both need to know *what part* of each item
to compare. `key=lambda team_score: team_score[1]` = "compare by the second item
in the tuple," basically a one-line anonymous function used only in that one spot.
SQL analogy: like specifying `ORDER BY` on a computed expression instead of a raw
column.

**Tuple unpacking + `enumerate()`.**
```python
for rank, (team_name, points) in enumerate(scores, start=1):
```
`enumerate()` hands back both the index and the item as it loops; `(team_name,
points)` unpacks a tuple straight into two named variables instead of `pair[0]` /
`pair[1]`. `start=1` so ranks read `1, 2, 3...` instead of starting at 0.

**Format spec `:.2%`.** `f"{pct:.2%}"` auto-multiplies a decimal by 100 and adds a
`%` sign — `0.9294` → `92.94%` — no manual math needed.

**Importing between your own files.** `from sleeper import get_league_users, TEST_LEAGUE_ID`
works because `calculations.py` sits in the same folder — Python treats any `.py`
file as an importable module by its filename. This is *why* we split raw API calls
(sleeper.py) from business logic (calculations.py) — calculations.py never touches
`requests` directly, it just asks sleeper.py for what it needs, like a report
querying a view instead of hitting raw tables.

### Mistakes & fixes

**Parameter name shadowing a constant.** Wrote `def get_league_users(TEST_LEAGUE_ID):`
— reusing the constant's name as the parameter name. It still *ran* fine (parameter
names are just local placeholders), but it was misleading: the function looked like
it only accepted the test league, when the whole point of a parameter is that it
accepts *any* value passed in. Fixed by renaming the parameter back to the generic
`league_id`. SQL analogy: you wouldn't name a stored proc parameter after one
specific value you plan to pass — `@LeagueID`, not `@TestLeagueID`.

**Silent tie bug in survivor logic.** First version used `min(alive_scores,
key=...)` to find the lowest scorer to eliminate. `min()` on a tie just returns
the *first* match it finds — meaning if two teams tied for last, one got
eliminated and the other didn't, based purely on API response order, not a real
rule. Caught this before it became a real-money problem. Fixed by finding the
lowest value first, then collecting *every* roster_id that matches it, and
eliminating all of them (per league decision: ties = simultaneous elimination).
Also had to guard against eliminating literally everyone left (if the whole
remaining field ties on the final relevant week) — that's a split pot, not a wipe.

### Questions / still confused about ❓

- `lambda` syntax still feels a little unnatural coming from SQL — need more reps
  before `key=lambda x: x[1]` reads instantly instead of requiring a beat to parse.
- Generator expressions vs list comprehensions — got *when* to use which in the
  moment (build a list I need to keep vs. just feed straight into `min()`/`sum()`),
  but want to see a case where the memory difference actually matters before it
  fully clicks.
- Haven't yet tested `get_survivor_results` against a real tie scenario (this
  year's test league data had none) — logic is confident but untested on real
  tied data.

### Code snippets worth remembering

```python
# The "chase the id through two lookup tables" pattern -- used constantly
team_names_by_roster = get_team_names_by_roster(league_id)
team_name = team_names_by_roster[some_matchup["roster_id"]]
```

```python
# dict.get() with a fallback = COALESCE
team_name = user["metadata"].get("team_name", user["display_name"])
```

```python
# Sleeper splits points into whole + decimal (hundredths) fields
pf = settings["fpts"] + settings["fpts_decimal"] / 100
```

---

## Session 2026-08-22 — Built database.py (Stage 1.5, database layer)

### What we built

**`database.py`** — the SQLite layer sitting between the Sleeper API and
(eventually) Flask:
- `get_connection()` — opens `dynasty.db`
- `create_tables()` — creates all 5 tables from the schema, safe to
  re-run (`IF NOT EXISTS`)
- `insert_teams()` — writes roster_id/team_name/owner_name, one API call
- `insert_weekly_scores()` — loops every played week, one API call each,
  writes roster_id/week/points
- `insert_survivor_status()` — reuses `calculations.py`'s existing
  elimination logic instead of re-implementing it, writes
  `week_eliminated` (NULL = still alive)
- `insert_start_sit()` — snapshots season-to-date PF/Max PF/% per team,
  tagged with the current week
- `insert_faab_transactions()` — **not built yet, next session.** Real
  per-transaction data (player name + amount per waiver claim) needs a
  new `sleeper.py` function hitting `/transactions/{week}` plus resolving
  player_ids to names via `/players/nfl` — neither exists yet, and it's
  a fair amount of new ground, so we scoped it out rather than force a
  quick placeholder that didn't match the table's actual design.

Also had to touch `calculations.py`: `get_survivor_results()` and
`get_start_sit_percentages()` only returned `team_name`, but the database
writes need `roster_id` (that's the actual foreign key / primary key —
team names aren't unique-safe to key off of). Added `roster_id` to both
functions' return tuples instead of re-deriving the same lookup logic
inside `database.py`.

### New concepts learned

**`sqlite3` is built into Python** — no `pip install` needed, unlike
`requests`/`flask`. First package we've used that didn't need installing.

**Connection / cursor, mapped to what I already know:**
`sqlite3.connect("dynasty.db")` = connecting to an instance (except the
"instance" is just a file — SQLite creates it on connect if it doesn't
exist yet). `connection.cursor()` = the thing that actually runs SQL and
holds results. `connection.commit()` = `COMMIT` — nothing's saved to the
file until you call it; everything since the connection opened is one
uncommitted transaction.

**`IF NOT EXISTS` = idempotency.** Makes `create_tables()` safe to call
every time the app starts, instead of erroring on tables that already
exist. This is going to matter once Flask calls it on every startup.

**`?` placeholders instead of f-strings in SQL.**
```python
cursor.execute(
    "INSERT OR REPLACE INTO teams (roster_id, team_name, owner_name) VALUES (?, ?, ?)",
    (roster_id, team_name, owner_name),
)
```
Same reason you'd never concatenate raw values into a SQL string on a
real database — avoids SQL injection. Low risk here since it's just API
data, but built the habit anyway since it costs nothing.

**`INSERT OR REPLACE` = upsert.** Since `roster_id` (or `roster_id, week`
for the composite-key tables) is the primary key, a plain `INSERT` would
error the second time a function ran — `OR REPLACE` overwrites instead.
Same idea as a SQL `MERGE`. This is what makes every insert function safe
to re-run on a schedule as the season progresses.

**Composite primary keys** (`PRIMARY KEY (roster_id, week)`) work exactly
like in SQL — `weekly_scores` and `start_sit` both use this so
`(roster_id=1, week=1)` and `(roster_id=1, week=2)` are correctly treated
as different rows, not a duplicate-key error.

**One connection reused across a whole loop, not reopened per row.**
`insert_weekly_scores()` loops 17 weeks × 12 teams but opens the
connection once, outside the loop, and commits once at the end — same as
not reconnecting to SQL Server for every single row you insert.

**A real SQL `JOIN`, first one in this project:**
```sql
SELECT teams.team_name, survivor_status.week_eliminated
FROM survivor_status
JOIN teams ON teams.roster_id = survivor_status.roster_id
```
`survivor_status`/`start_sit` only store `roster_id` — team names live in
`teams` and shouldn't be duplicated — so reading them back in a
human-readable way needs an actual join, same as SQL Server.

**`ORDER BY x IS NULL, x` — the NULLS-LAST trick.**
`x IS NULL` evaluates to `0`/`1`, so sorting by that first pushes NULL
rows to the end, then the second `x` sorts everyone else normally.
Without it, SQLite puts NULLs *first* by default — which would've shown
the survivor at the top of the elimination list instead of the bottom.
✅ Good one to remember, comes up any time NULL means "hasn't happened
yet."

**Reusing existing logic instead of duplicating it across files.**
Rather than re-writing the survivor tie-elimination rule (the one with
the bug we already caught once) inside `database.py`, changed
`calculations.py`'s function to return what both files need and imported
it. One source of truth for that rule.

**Changing a function's return shape is a breaking change for every
caller.** Adding `roster_id` to `get_survivor_results()`'s output meant
`calculations.py`'s own `__main__` block broke until updated to match —
had to fix the unpacking there too, twice (once for survivor, once for
start_sit). Same as changing a stored proc's result columns — every
caller needs to know.

**Sleeper only exposes PF/Max PF as running season totals, not
historical per-week snapshots.** `insert_start_sit()` can't reconstruct
"what was the % after week 3" retroactively — it can only capture "as of
right now." Since `start_sit`'s primary key is `(roster_id, week)`
though, re-running this function every week (rather than always
overwriting the same row) naturally builds up a real week-by-week history
over the season anyway. ✅ Nice case where the schema design does the
work for you.

**`roster_id` is only unique within one league, not globally.** Test
league and next season's real league will both hand out `roster_id`
1–12, but they refer to completely different teams. Nothing broke from
this since every lookup dict gets rebuilt fresh per `league_id` passed
in, but it's the reason we added a Pre-Release Checklist to `CLAUDE.md`:
delete `dynasty.db` and rebuild fresh before switching from
`TEST_LEAGUE_ID` to the real `LEAGUE_ID`, rather than relying on
`INSERT OR REPLACE` to sort it out silently.

### Mistakes & fixes

No actual crashes this session, but a "gotcha avoided by testing
immediately": every time a function's return tuple shape changed
(`get_survivor_results`, `get_start_sit_percentages`), I ran
`calculations.py` right after to confirm its own `__main__` block still
worked — it didn't, until the unpacking there was updated too. ✅ Good
habit: re-run a file immediately after changing what a function returns,
don't assume other callers are fine just because the function itself
runs.

### Questions / still confused about ❓

- None new this session — the FAAB gap isn't confusion, just genuinely
  unbuilt work (new endpoint + player-id resolution) scoped into next
  session instead of rushed.

### Code snippets worth remembering

```python
# The upsert pattern -- reused for every insert function in database.py
cursor.execute(
    "INSERT OR REPLACE INTO teams (roster_id, team_name, owner_name) VALUES (?, ?, ?)",
    (roster_id, team_name, owner_name),
)
connection.commit()
```

```sql
-- JOIN back to teams to read roster_id-keyed tables in a human-readable way
SELECT teams.team_name, start_sit.percentage
FROM start_sit
JOIN teams ON teams.roster_id = start_sit.roster_id
ORDER BY start_sit.percentage DESC;
```

```sql
-- NULLS-LAST trick -- x IS NULL sorts 0/1, so NULL rows go last
ORDER BY survivor_status.week_eliminated IS NULL, survivor_status.week_eliminated;
```

---

## Session 2026-08-23 — Built insert_faab_transactions() (finishing Stage 1.5)

### What we built

Closed out the one gap left in the database layer:

**`sleeper.py`:**
- `get_league_transactions(league_id, week)` — hits `/transactions/{week}`,
  same one-call-per-week shape as `get_league_matchups`
- `get_all_players()` — hits `/players/nfl` (returns *every* NFL player,
  ~15 MB), but caches the result to `players_cache.json` and only refetches
  if that file is missing or older than 24 hours, since Sleeper's docs say
  not to hit this one casually
- `get_player_names()` — thin wrapper around `get_all_players()` that
  trims it down to just `{player_id: full_name}`, since that's all any
  caller actually needs

**`database.py`:**
- `insert_faab_transactions()` — loops every played week's transactions,
  keeps only `type == "waiver"` + `status == "complete"` ones (see below
  for why), and writes one row per player added

Also had to change `faab_transactions`' schema before writing any of this
— see Mistakes & fixes, this one's a real design decision, not a bug.

### New concepts learned

**Exploring an API response's actual shape before writing code against it.**
Instead of guessing what `/transactions/{week}` returns, I ran it against
the test league first and printed the raw JSON. Turned out there are 3
transaction `type`s (`waiver`, `free_agent`, `trade`) and 2 `status`es
(`complete`, `failed`) — none of that was obvious from the endpoint name
alone. SQL analogy: this is like running `SELECT TOP 5 * FROM table` on a
linked server table you've never queried before you write real logic
against it, instead of assuming you know its columns.

**Caching a large, mostly-static API response to a local file.**
```python
cache_is_fresh = (
    os.path.exists(PLAYERS_CACHE_FILE)
    and time.time() - os.path.getmtime(PLAYERS_CACHE_FILE) < PLAYERS_CACHE_MAX_AGE_SECONDS
)
```
`os.path.getmtime()` reads a file's last-modified timestamp straight off
the filesystem — no need to store "when did I fetch this" separately,
the file's own metadata already answers that. This is the first function
in the project that *isn't* a plain `requests.get()` — every other
`sleeper.py` function hits the API fresh every time, but Sleeper's own
docs ask callers not to hammer this specific 15 MB endpoint, so it needed
an actual caching layer instead of just following the existing pattern.

**Natural key vs. surrogate key, for real this time.** `faab_transactions`
originally had a plain `id INTEGER PRIMARY KEY AUTOINCREMENT` — fine for
just defining the table, but useless for making inserts safe to re-run,
since every other insert function's "safe to re-run" trick
(`INSERT OR REPLACE` keyed on something real, like `roster_id, week`)
needs a key that's actually *derived from the data*, not a counter that
just goes up forever. Sleeper's own `transaction_id` is already a unique
id for each waiver claim, so pairing it with `player` (in case one
transaction ever adds more than one player) gives a real composite key —
swapped it in for the autoincrement id.

```sql
-- Old: no real key, every re-run would've doubled the whole season
CREATE TABLE faab_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ...
);

-- New: keyed by data Sleeper already guarantees is unique
CREATE TABLE faab_transactions (
    transaction_id TEXT,
    player TEXT,
    ...
    PRIMARY KEY (transaction_id, player)
);
```

**Filtering on more than one column before trusting a total.** Sleeper
tracks `waiver_bid` on every waiver attempt, win or lose — so filtering
only on `type == "waiver"` would've counted *failed* claims as spent
money too. Had to filter on both `type` AND `status` together. Same idea
as forgetting a second `WHERE` clause and quietly overcounting a total.

### Mistakes & fixes

**Caught a schema flaw before writing any data into it — not a crash,
a design gap.** `faab_transactions` was created back on 2026-08-22 with
just an autoincrement `id`, before we knew what Sleeper's transaction data
even looked like. Once `get_league_transactions()` showed a real
`transaction_id` was available, it was clear the original schema had no
way to avoid duplicating rows on re-run. Table was still empty (never
populated), so fixed it by dropping and recreating it with the composite
key above instead of working around the bad key later. ✅ Worth remembering:
"the API hasn't been explored yet" is a good reason to leave a schema
detail unresolved rather than guess at it.

Verified the fix actually worked by re-running `insert_faab_transactions()`
twice and checking the row count didn't change (67 both times) — didn't
just trust that `INSERT OR REPLACE` would behave, actually checked.

### Questions / still confused about ❓

- None new — this session closed out exactly the gap scoped at the end of
  last session, no surprises.

### Code snippets worth remembering

```python
# Cache a big/rarely-changing API response to disk instead of refetching
# every call -- checks the file's own last-modified time, no separate
# "when did I fetch this" bookkeeping needed
cache_is_fresh = (
    os.path.exists(PLAYERS_CACHE_FILE)
    and time.time() - os.path.getmtime(PLAYERS_CACHE_FILE) < PLAYERS_CACHE_MAX_AGE_SECONDS
)
```

```python
# Filtering on two conditions before trusting a "spent" number --
# waiver_bid exists on failed claims too, so type alone isn't enough
if transaction["type"] != "waiver" or transaction["status"] != "complete":
    continue
```

---

## Session 2026-08-23 (cont'd) — Built app.py (Stage 2, minus deployment)

### What we built

**`app.py`** — the actual Flask web app, reading `dynasty.db` directly
(never calls the Sleeper API itself):
- `/` — home page
- `/scoreboard` — latest week's scores, ranked
- `/survivor` — who's still alive / eliminated and when
- `/start-sit` — PF/Max PF % leaderboard, using each team's *most recent*
  row (start_sit has one row per team per week)
- A `before_request` hook that logs every request into a new
  `page_visits` table (route + timestamp) — simple traffic monitoring,
  no third-party analytics
- Calls `create_tables()` on startup so the schema (including the new
  `page_visits` table) always exists before any route runs

**`templates/`** — `base.html` (nav + layout every page extends) plus
one template per route. Deliberately plain/unstyled — Stage 3 is the
actual design pass, so this stays focused on data/routes.

**`sleeper.py` + `database.py`** — added the error logging Stage 2 also
called for: `sleeper.py` now has one `_get_json()` helper every API call
goes through, which logs failures and re-raises; `database.py`'s insert
functions catch that, log a "skipped this refresh" message, and roll
back instead of committing partial data or crashing.

### New concepts learned

**Routes = a stored procedure triggered by a URL instead of a call.**
`@app.route("/scoreboard")` above a function means "when a browser asks
for this path, run this function and send back whatever it returns" —
same shape as a stored proc, just invoked by an HTTP request instead of
`EXEC`.

**Jinja templates = parameterized views.** `render_template("scoreboard.html", week=latest_week, scores=scores)`
hands data to an HTML file the same way you'd pass parameters into a
view/report — the template just displays what it's given, same
separation as "the query decides the data, the report decides the
layout."

**Two different connections to the same database, on purpose.**
`app.py` has its own `get_db_connection()` instead of reusing
`database.py`'s, because it sets `row_factory = sqlite3.Row` — that
makes a row behave like a dict (`row["team_name"]`) instead of a plain
tuple (`row[1]`), which is what templates need to read columns by name.
`database.py`'s connection stays plain tuples since its code already
unpacks by position everywhere. ✅ Good pattern: the same underlying
resource can have more than one "flavor" of connection depending on who's
using it and how they need the data shaped.

**Greatest-n-per-group, in real SQL.** `/start-sit` needed each team's
*most recent* row from `start_sit`, not every week they've ever had:
```sql
SELECT teams.team_name, start_sit.pf, start_sit.max_pf, start_sit.percentage
FROM start_sit
JOIN teams ON teams.roster_id = start_sit.roster_id
WHERE start_sit.week = (
    SELECT MAX(week) FROM start_sit AS latest
    WHERE latest.roster_id = start_sit.roster_id
)
ORDER BY start_sit.percentage DESC
```
The subquery re-finds `MAX(week)` *per roster_id*, correlated to the
outer row via `latest.roster_id = start_sit.roster_id` — same pattern as
SQL Server's classic "latest record per group" problem, just without
window functions (`ROW_NUMBER() OVER (PARTITION BY ...)`), which SQLite
does actually support but this was simple enough not to need it.

**Centralizing error handling in one function.** `sleeper.py`'s
`_get_json()` is now the only place `requests.get()` gets called from —
every public function (get_league_info, get_league_users, etc.) is just
`return _get_json(url)`. One function decides how to log a failure
instead of that logic getting copy-pasted into 6 different functions.
Same instinct as `get_team_names_by_roster()` being the one place the
users/rosters join happens.

**Log, then re-raise vs. log and swallow.** `_get_json()` logs the
failed URL *and then re-raises* the exception instead of returning
`None` — the reasoning: sleeper.py is the layer closest to the actual
failure (it knows *which URL* broke), but deciding what to *do* about a
broken refresh (skip it? abort everything?) is a business decision that
belongs to `database.py`, not to the API layer. Swallowing the error in
sleeper.py and returning `None` would've meant every caller had to
remember to check for `None`, and forgetting even once would just
convert a clear network error into a confusing `TypeError` somewhere
else.

**`try/except/finally` with a variable initialized before the `try`.**
```python
connection = None
try:
    ...
    connection = get_connection()
    ...
    connection.commit()
except requests.exceptions.RequestException:
    logging.error(...)
    if connection:
        connection.rollback()
finally:
    if connection:
        connection.close()
```
Setting `connection = None` up front means the `except`/`finally` blocks
can safely check "did we even get this far?" without crashing on an
undefined variable if the API call failed *before* a connection was ever
opened. `finally` runs whether the `try` succeeded or the `except` fired
— that's what guarantees the connection always gets closed either way.

**Catching a specific exception type, not bare `except:`.** `except
requests.exceptions.RequestException` only catches actual network/API
failures — a real bug elsewhere in the function (a typo, a bad
assumption about the API's shape) still crashes loudly instead of
silently getting swallowed and logged as if it were a network problem.
Catching everything with a bare `except:` would've hidden real bugs
during development, not just handled the intended failure case.

**Two different reasons a table needs a primary key.** `page_visits`
uses a plain `id INTEGER PRIMARY KEY AUTOINCREMENT` — and unlike
`faab_transactions` (fixed last session specifically *because*
autoincrement was wrong there), this is the right call here: every
other table gets `INSERT OR REPLACE`d with fresher data on each refresh,
but a page visit is a one-time event with nothing to overwrite. ✅ The
lesson isn't "autoincrement bad" — it's "pick the key based on whether
re-running the write should overwrite something or create something new."

**`app.py` calling `create_tables()` at import time, not inside
`if __name__ == "__main__":`.** A production server (gunicorn on Render,
later) imports `app.py` as a module rather than running it as a script,
so code inside `if __name__ == "__main__":` wouldn't execute at all in
that setup. Putting `create_tables()` at the top level means it runs
every time the app starts, regardless of how it's launched.

### Mistakes & fixes

**Broad `taskkill` killed more than intended.** After testing the app,
shut down the dev server with `taskkill /F /IM python.exe` — that kills
*every* Python process on the machine by name, not just the one Flask
server that was started, since the flag doesn't take a specific PID.
Caught immediately after and switched to finding the actual PID
listening on port 5000 (`Get-NetTCPConnection -LocalPort 5000`) and
stopping just that one. ❓ Still tripped up once more right after
switching approaches: Flask's debug-mode reloader actually runs as
*two* processes (a parent + a child it spawns to do the real serving),
so killing only the first PID left the port still bound — had to find
and kill both with `Get-CimInstance Win32_Process` to see the real
parent/child relationship. Worth remembering for next time: stopping a
Flask dev server started with `debug=True` means killing 2 processes,
not 1.

### Questions / still confused about ❓

- Exactly why Flask's debug reloader needs two OS processes instead of
  one (something about the parent watching files for changes and
  restarting the child) — works fine in practice, just don't have the
  full mental model of *why* it's built that way yet.

### Code snippets worth remembering

```python
# The "safe try/except/finally" shape used in every database.py insert
# function now -- initialize the resource variable to None before the
# try so except/finally can check "did we get this far?" safely
connection = None
try:
    connection = get_connection()
    ...
    connection.commit()
except requests.exceptions.RequestException:
    logging.error("...: Sleeper API call failed, skipping this refresh")
    if connection:
        connection.rollback()
finally:
    if connection:
        connection.close()
```

```sql
-- Greatest-n-per-group: latest row per roster_id from a table with
-- (roster_id, week) history
SELECT * FROM start_sit
WHERE week = (SELECT MAX(week) FROM start_sit AS latest
              WHERE latest.roster_id = start_sit.roster_id)
```

---

## Session 2026-08-23 (cont'd again) — Deployed to Render.com (Stage 2 done)

### What we built

Nothing new in the codebase itself beyond three small changes to make
deployment possible:
- `requirements.txt` — added `gunicorn` (the production WSGI server
  Flask's own dev server warns you not to use in production) by hand,
  not via local `pip install` — gunicorn depends on Unix-only modules
  and can't even run on Windows. Render's build runs
  `pip install -r requirements.txt` inside its own Linux container, so
  it installs and works fine there despite never running locally.
- `database.py` — `DB_NAME` now reads `os.environ.get("DB_PATH", "dynasty.db")`
  instead of being hardcoded, so it can point at Render's persistent
  disk in production while still defaulting to the local file for dev.
- Render dashboard config (no repo file for this): a Starter-tier web
  service, a 1 GB disk mounted at `/var/data`, `DB_PATH` set to
  `/var/data/dynasty.db`, build command `pip install -r requirements.txt`,
  start command `gunicorn app:app`.

Live at https://dynasty-dashboard-ijio.onrender.com, running on
`TEST_LEAGUE_ID` data for now.

### New concepts learned

**Why the free tier wasn't an option.** Render's free web service tier
has *ephemeral* disk — wiped on every redeploy, and can reset when the
service spins down after 15 min of inactivity. Most of this project's
tables are fully re-derivable from Sleeper's API (just re-run
`database.py`), but `start_sit` isn't — it only has history because we
snapshot it over time, and Sleeper never exposes that history itself.
Losing it on every redeploy would be a real, permanent data loss, not
just an inconvenience. A small paid "Starter" instance was needed
specifically because Render's persistent Disks aren't available on the
free tier at all.

**A platform's build environment isn't your local environment.**
`gunicorn` can't run on Windows, so it was never going to be
`pip install`ed locally or show up via `pip freeze` — it was added to
`requirements.txt` by hand. This only works because Render's build step
runs entirely inside its own Linux container: "install this project's
dependencies" doesn't mean "using my machine," it means "using whatever
OS the deploy target actually is." ✅ First time a dependency existed
that the dev environment itself couldn't touch.

**`os.environ.get(key, default)` as an environment-aware config
switch.** Same `?? COALESCE`-style pattern as `dict.get()` with a
fallback, just reading from the *environment* instead of a dictionary —
no `DB_PATH` set (local machine) falls back to `"dynasty.db"`; `DB_PATH`
set (Render) overrides it. This is *the* standard way an app tells the
difference between "running locally" and "running in production"
without needing separate code paths or config files per environment.

**A production WSGI server never runs your `if __name__ == "__main__":`
block at all.** `gunicorn app:app` imports `app.py` as a module and
talks to the `app` object directly — it never executes the file as a
script, so `app.run(debug=True)` inside that guard simply never runs in
production. This is *why* `create_tables()` had to be called at the top
level of `app.py` instead of inside that block (see last entry) — it's
also why Flask's `debug=True` mode (which you'd never want live, since
it can expose a debugger console) automatically isn't a production
concern at all, with zero extra code needed to disable it.

**Verifying persistence by actually testing it, not just trusting the
setup.** Confirmed the disk was really wired up by: checking the env var
existed (`echo $DB_PATH`), checking the *app itself* resolved the same
path (`python -c "from database import DB_NAME; print(DB_NAME)"` — this
is the one that actually proves it, since it uses the real code path
instead of just the shell's environment), running the real
population script, then **triggering an actual redeploy and confirming
the same data was still there afterward** without re-running anything.
✅ That last step is the one that actually proves persistence — anything
before it could still be true even if the disk wasn't really mounted
(the container's own temporary filesystem would "work" too, right up
until it gets wiped).

**SQLite doesn't enforce `FOREIGN KEY` constraints by default.** Came up
while reasoning through what happens if `TEST_LEAGUE_ID` and `LEAGUE_ID`
rows ever mixed in the same table without a clean rebuild — the
schema *declares* `FOREIGN KEY (roster_id) REFERENCES teams(roster_id)`,
but SQLite only actually checks that if a connection runs
`PRAGMA foreign_keys = ON`, which `database.py` never does. So a stale
row referencing a `roster_id` that no longer matches the right team
wouldn't error — it'd just silently join against the wrong team's name.
❓ Worth deciding at some point whether to turn this pragma on for real
enforcement, or leave it as documentation-only like it is now — no
decision made this session, just flagged.

### Mistakes & fixes

No mistakes this session — deployment went cleanly because each piece
was verified as we went (env var, then app-level path resolution, then
population, then the actual redeploy-survival test) instead of doing
everything at once and hoping it worked.

### Questions / still confused about ❓

- Whether to turn on `PRAGMA foreign_keys = ON` for real constraint
  enforcement (see above) — not urgent, just noted.
- Haven't yet done the actual `TEST_LEAGUE_ID` → `LEAGUE_ID` swap (real
  draft context: `BYLAWS.md` has the real draft as 2026-08-23, i.e.
  around now) — Pre-Release Checklist in `CLAUDE.md` is updated to cover
  both the local *and* Render copies of the database, but the swap
  itself hasn't happened yet.

### Code snippets worth remembering

```python
# Environment-aware config default -- same idea as dict.get()'s fallback,
# just reading from the environment instead of a dict. No env var set
# (local dev) falls back to the default; set (production) overrides it.
DB_NAME = os.environ.get("DB_PATH", "dynasty.db")
```

---

## Session 2026-08-23 (cont'd yet again) — Stage 3 design pass

### What we built

**`static/style.css`** — the first real CSS in the project, built around
CSS custom properties (variables) for the whole palette/typography
instead of repeating raw values everywhere:
```css
:root {
    --color-bg: #0d1117;
    --color-accent: #3fb950;
    --font-heading: "Oswald", "Arial Narrow", sans-serif;
}
```
Grounded in the design direction already logged in Obsidian back on
2026-08-22 (simple/modern/clean, Sleeper's app + 440andfriends.com as
references) but the actual colors/fonts/spacing were picked this
session, since that gap had been explicitly left open. Reviewed live and
approved as a "solid first pass."

**Templates** — `base.html` got a real nav bar (brand name + section
links) and now links the stylesheet plus a Google Fonts import for
Oswald. `index.html` became a real hub page with card links instead of
a paragraph of text. `scoreboard.html`/`start_sit.html` got rank-based
styling (gold/silver/bronze for top 3). `survivor.html` got colored
status pills instead of plain text, plus a payout blurb matching the one
already on start/sit % (small follow-up after first review).

### New concepts learned

**CSS custom properties (variables) = named constants for design
values.** `--color-accent: #3fb950;` defined once in `:root`, then used
everywhere as `var(--color-accent)`. Same reason you'd never hardcode a
magic number in five different queries — change the value in one place,
every use of it updates. This is what makes a "theme" a real thing
instead of a color repeated by hand in a dozen places.

**Conditional CSS classes from Jinja, built as a string.**
```jinja
<td class="rank{% if loop.index <= 3 %} rank-{{ loop.index }}{% endif %}">
```
This builds the `class` attribute's value piece by piece -- always
`"rank"`, then conditionally appends `" rank-1"` / `" rank-2"` /
`" rank-3"` only for the top 3 rows. Same idea as string concatenation
in Python, just inline in the template instead of in a `.py` file.

**`box-sizing: border-box` as a near-universal reset.** `* { box-sizing: border-box; }`
makes padding and border count *inside* an element's declared width
instead of adding to it -- without this, a table cell with padding ends
up wider than expected and things misalign in ways that are annoying to
debug. Basically every real stylesheet starts with this.

**CSS Grid with `auto-fit` + `minmax()` for a responsive card layout,
with zero media queries.**
```css
grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
```
Reads as "fit as many 220px-or-wider columns as will comfortably fit,
and stretch them evenly to fill the row" -- the home page's 3 cards sit
side-by-side on a wide screen and stack automatically on a narrow one,
without writing a single `@media` rule for it.

**Verifying a UI change without a browser, honestly.** This environment
doesn't have a headless browser set up, so instead of claiming the
design was "done," checked what *could* be verified without eyes on
it -- routes return 200, the right CSS classes actually show up in the
rendered HTML, no template errors -- and was upfront that the actual
visual judgment call still needed a real person looking at a real
browser. ✅ Good instinct to remember: "I tested the plumbing" and "I
tested how it looks" are two different claims, don't blur them together.

### Mistakes & fixes

**Killed the dev server mid-review by reflex.** After verifying the
markup via `curl`, shut the Flask dev server down the same way as every
previous test -- except this time the developer was about to actually
look at it in a browser, and the "site can't be reached" was just the
server being off, not a real bug. ✅ Lesson: a UI change being reviewed
by an actual person needs the server left running, not cleaned up the
instant automated checks pass.

### Questions / still confused about ❓

- None new -- this was a fairly mechanical CSS + template session, no
  surprises.

### Code snippets worth remembering

```css
/* Design tokens as CSS custom properties -- change the palette in one
   place instead of hunting down every hardcoded color */
:root {
    --color-bg: #0d1117;
    --color-accent: #3fb950;
    --font-heading: "Oswald", "Arial Narrow", sans-serif;
}
body {
    background: var(--color-bg);
    font-family: var(--font-heading);
}
```

```css
/* Responsive card grid with no media queries */
.hub-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
}
```

---

## Session 2026-08-23 (cont'd once more) — Debugging "the CSS isn't showing up"

### What happened

After the Stage 3 design pass, the live page kept showing the *old*
plain layout even after a hard refresh and an incognito window. Spent a
while ruling things out in order:

1. **Was the server actually serving the new code?** Checked server
   logs + `curl` from the terminal -- confirmed 200s, confirmed the
   *actual* HTML being returned had the new hub-card markup. Server was
   never the problem.
2. **View page source in the browser** -- confirmed the browser really
   was receiving the new HTML. So it wasn't a caching issue on the HTML
   itself either.
3. **Checked `style.css`'s response headers via curl** -- correct
   `Content-Type: text/css`, right file size. Ruled out a MIME-type
   mismatch (a real thing that silently breaks stylesheets in some
   setups, just wasn't this one).
4. **DevTools Network tab, searched for "style"** -- found the real
   clue: the request wasn't just failing, it wasn't happening *at all*.
   Not even as a cached or blocked entry -- completely absent.
5. **Navigated directly to the `style.css` URL** -- loaded fine as raw
   text. So the file and the URL were both completely fine; only
   loading it *as a linked stylesheet* was the problem.
6. That combination (works standalone, invisible when loaded via
   `<link>`) pointed at a browser extension intercepting the request
   before Chrome's network layer ever logged it. Checked
   `chrome://extensions`, disabled everything, and the page rendered
   correctly with `style.css` now showing up (as a real request, status
   304) in the Network tab.

**Turned out to be one of the installed extensions** (Dark Reader alone
wasn't it, despite being the obvious suspect for a dark-themed page --
disabling *all* extensions was what actually fixed it). Not worth fully
bisecting which one specifically, since this only matters for local dev
on `localhost` -- extensions can just stay off for that.

### New concepts learned

**A request that's silently *absent* from Network tab is a different
bug than a request that's *failed*.** A 404 or blocked request still
shows up as a row (usually red). A resource interception happening
*before* the browser's network stack ever logs anything shows up as
nothing at all -- no row, no error, no trace. That specific
symptom (not "failed," just "never attempted") is the tell for a
browser extension or content-script intercepting the request early,
not a server-side or code problem.

**Isolating "works standalone" vs. "works as a linked resource" as a
diagnostic split.** Navigating directly to `/static/style.css` proved
the URL and file were fine on their own. The only difference between
that and the broken case was *how* it was being loaded (typed into the
address bar vs. fetched automatically by a `<link>` tag) -- which
narrowed the problem down to something browser-side reacting
specifically to it being loaded as a stylesheet resource, not to
anything about the file or server at all.

**When to stop debugging your own code.** Every check on the app side
(server logs, curl, response headers, page source) came back clean.
At that point the responsible move was to stop assuming the bug was in
`app.py`/`style.css` and start checking the browser environment itself
instead -- extensions, in this case. ✅ Worth remembering: once you've
verified the same thing works correctly from multiple independent
angles (server logs *and* curl *and* direct navigation), the bug
probably isn't where you're looking.

### Questions / still confused about ❓

- Never pinned down *which specific* extension was blocking it (7TV,
  Reddit Enhancement Suite, LastPass, Okta Browser Plugin, and a couple
  others were all still on the suspect list when we stopped, since
  disabling everything at once was enough to confirm the fix without
  needing to bisect further).

---

## Session 2026-08-23 (cont'd, final) -- Design refinement and the real league switch

### What we built

Iterated on the dashboard home page based on live feedback (survivor
table alignment, FAAB bar direction, per-team colors, icons, pill nav,
a placeholder Standings section, two "Coming Soon" nav items), then did
the actual `TEST_LEAGUE_ID` -> `LEAGUE_ID` switch: updated
`database.py`'s `__main__` block, deleted the local `dynasty.db`, and
rebuilt it fresh against the real league.

### New concepts learned

**A bug that only shows up once real (not sample) data hits the code.**
Every calculation function worked fine all season against
`TEST_LEAGUE_ID`'s fully-completed 17-week season, because there was
always at least one score to call `min()`/`max()` on. The moment they
ran against a `pre_draft` league with zero games played,
`get_survivor_results()` and `get_season_high_scores()` both crashed
calling `min()`/`max()` on an empty list, and `get_start_sit_percentages()`
crashed on a roster settings dict that didn't even have the
`fpts_decimal` key yet (not just zero -- genuinely absent). ✅ Good
reminder: code that's only ever been tested against "the happy path"
data can hide bugs that only a genuinely different real-world case
(brand new league, empty season) will expose. Caught this by explicitly
checking the real league's actual state via the API before touching any
database, not by assuming last session's test-league behavior would
carry over.

**`dict.get(key, default)` for a key that might not exist at all.**
```python
pf = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100
```
Different from the earlier `dict.get()` pattern (falling back when a
value is present but empty) -- here the key itself might not exist in
the dict yet pre-season, so `settings["fpts_decimal"]` would raise a
`KeyError`, not just return something falsy. `.get()` handles "missing
entirely" and "present but zero" the exact same way.

**An empty result isn't always an error -- sometimes it's the correct
answer.** Adding `if not alive_scores: break` to
`get_survivor_results()` isn't "handling an error," it's recognizing
that an empty week genuinely means "nothing happened yet," and the
correct response is "no eliminations this week," not a crash.

**A logic bug distinct from a crash bug.** `survivor_leader` never
raised an exception with 12 teams still alive -- it just silently
picked whichever team's row happened to come back first from the query
and displayed them as if they'd already won the pot. Fixed by only
declaring a leader when exactly one team is left standing
(`len(still_alive) == 1`), not just "found a row with no elimination."
Nothing crashed, so nothing would have flagged this without actually
looking at what the home page displayed once real data was there.

### Mistakes & fixes

**Grid column math didn't actually add up.** The payout tiles grid was
declared as `repeat(5, 1fr)` at wide screens, but the tiles inside it
needed 6 columns worth of space (the wide Weekly High tile spanning 2,
plus 4 more singles) -- so the 6th tile (2nd Place) had nowhere left in
that row and wrapped to a lonely row by itself. Fixed by stacking 1st
and 2nd Place into one shared column instead of trying to force a 6th
track into a 5-column grid.

**Used my own "avoid em dashes" reminder's connector as an em dash,
while writing it.** Caught immediately on review, but a good example of
how automatic a habit can be -- worth reading back over anything meant
to correct a habit, since the habit can sneak into the correction itself.

### Questions / still confused about ❓

- None new this session.

### Code snippets worth remembering

```python
# .get() with a default handles "key is missing entirely" the same way
# as "key exists but is zero" -- useful before a season/data source has
# fully populated yet
pf = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100
```

```python
# A "leader" only exists once exactly one option remains -- checking
# "is there a row with no elimination" isn't the same question as
# "has exactly one team survived"
still_alive = [row for row in survivor_rows if row["week_eliminated"] is None]
survivor_leader = still_alive[0] if len(still_alive) == 1 else None
```

---
*Last updated: 2026-08-23*
