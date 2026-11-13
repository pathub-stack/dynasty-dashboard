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

## Session 2026-08-23 (cont'd, wrap-up) -- Render platform Q&A

### What we learned

Not code changes -- infrastructure/platform questions that came up after
sharing the live link with leaguemates.

**Renaming a Render service does NOT change its `.onrender.com` URL.**
Tested this directly: changed the service's Name field from
"dynasty-dashboard" to "thisisnevergoingtowork" in Render's Settings.
The Name field itself saved correctly, but the live URL stayed
`dynasty-dashboard-ijio.onrender.com`, and the "expected" new URL
(`thisisnevergoingtowork.onrender.com`) 404'd. Render's own docs don't
explicitly document this either way -- they only say the name generates
the subdomain *at initial setup*. ✅ Good example of confirming a
platform's actual behavior empirically instead of trusting what a
Settings field name implies it should do. The real path to a
name-matching URL is a custom domain, which the developer is setting up
instead.

**Custom domains on Render are free, not a paid add-on.** Corrected an
earlier wrong guess in this same conversation -- verified against
Render's actual docs: the Hobby plan (what this project is already on,
for the persistent disk) includes 2 custom domains at no extra cost.
Only the domain registration itself (roughly $10-15/year for a `.com`)
costs anything.

**Render's Logs and Metrics tabs, and how they relate to our own
`page_visits` table.** Render automatically captures stdout/stderr
(which is exactly what `database.py`'s `logging.basicConfig()` and
Flask's own request logging already feed into, no extra setup needed)
plus CPU/memory/bandwidth/request-volume metrics, both free on Hobby
with a 7-day retention window. That's infrastructure-level visibility;
it's a different thing from `page_visits`, which is our own
application-level table tracking route visits indefinitely (no 7-day
limit, since it's just rows in `dynasty.db`) -- the two complement each
other rather than one replacing the other.

### Questions / still confused about ❓

- None new -- straightforward platform research, verified against
  Render's own docs rather than assumed.

---

## Session 2026-08-24 — Built the scheduled data refresh (APScheduler)

### What we built

Closed the gap flagged back on 2026-08-22: nothing was actually re-running
`database.py`'s insert functions, so the dashboard could go stale (found
this for real when a leaguemate's team-name change never showed up on the
site). Built:

- `refresh_all_data()` in `database.py` -- one function that calls
  `create_tables()` + every `insert_*()` function in order. Same idea as
  bundling several stored-proc calls into one job step.
- Wired that into `app.py` with `APScheduler`'s `BackgroundScheduler`,
  running hourly, with the first run firing immediately on startup
  instead of waiting a full hour.

Chose APScheduler-inside-Flask over an OS-level scheduler (cron / Windows
Task Scheduler) because Render's Starter tier never spins down, so there's
already a process sitting there to run it in -- no second Render service
(a paid Cron Job) or separate local Task Scheduler setup needed. Same
"no extra infrastructure" call already made for error logging and traffic
tracking back in Stage 2.

### New concepts learned

**A background scheduler running *inside* the app process, not next to
it.** `BackgroundScheduler` spins up its own thread and just calls a
Python function on a timer -- no separate service, no OS involved at all.
✅ Clicked once I saw it's really just "start a thread, sleep between
calls" with a nicer API bolted on.

**Flask's debug reloader secretly runs two processes.** `app.run(debug=True)`
(what `python app.py` uses locally) launches a watcher process that
restarts a second, real worker process whenever a file changes. Code that
runs at import time -- like starting a scheduler -- would run in BOTH
processes if not guarded, silently doubling every Sleeper API call. Fixed
with a check on `WERKZEUG_RUN_MAIN`, an env var Flask only sets to
`"true"` inside the real worker:

```python
# app.debug is False under gunicorn (Render/production), so the first
# half alone covers prod. Locally, app.debug is True, so it falls through
# to checking WERKZEUG_RUN_MAIN -- only "true" in the real worker process,
# not the reloader's watcher -- so the scheduler still starts exactly once.
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: refresh_all_data(LEAGUE_ID),
        trigger="interval",
        hours=1,
        next_run_time=datetime.now(),  # also run once immediately on startup
    )
    scheduler.start()
```

**A `lambda` as a quick one-line function.** `scheduler.add_job` needs a
function it can call later with zero arguments, but `refresh_all_data`
needs a `league_id` passed in. `lambda: refresh_all_data(LEAGUE_ID)`
is a throwaway, unnamed function that takes no arguments and just calls
`refresh_all_data(LEAGUE_ID)` when invoked -- same idea as wrapping a
parameterized query in a no-arg stored proc so a caller that can't pass
arguments still has something it can just execute.

### Mistakes & fixes

Tried testing with the real dev server (`python app.py`) and hit
`An attempt was made to access a socket in a way forbidden by its access
permissions` -- a Windows socket-binding error from *this specific sandbox
environment* refusing to open a network port, unrelated to the scheduler
code itself. Worked around it for testing by importing `app.py` directly
in a script instead of calling `app.run()` -- that still runs all the
same startup code (including the scheduler), just without needing to bind
a port. Confirmed it actually worked by checking `dynasty.db` before and
after: `roster_id 2` really did update from `"barttt"` to `"bart"`,
pulled live from Sleeper. If the real socket error shows up again outside
this sandbox, that's a separate thing to debug (probably a Windows
Firewall / port-already-in-use issue), not a scheduler bug.

### Code snippets worth remembering

```python
# database.py -- one function that bundles every table's refresh together,
# reused by both the scheduler (app.py) and manual runs (database.py's
# own __main__ block).
def refresh_all_data(league_id=LEAGUE_ID):
    create_tables()
    insert_teams(league_id)
    insert_weekly_scores(league_id)
    insert_start_sit(league_id)
    insert_faab_transactions(league_id)
    insert_survivor_status(league_id)
```

**Also flagged, not fixed this session:** `insert_weekly_scores()` and
`insert_faab_transactions()` both loop `range(1, last_played_week + 1)`
every single time they run -- re-fetching *every* past week from Sleeper,
not just new ones. Harmless today (well under the rate limit even at
week 17), but wasteful, and worth fixing separately from this scheduling
work. Logged in the Obsidian roadmap doc.

---

## Session 2026-08-24 (cont'd) — Built the /admin traffic page

### What we built

Picked the next roadmap item: a password-gated `/admin` page showing
`page_visits` data (visits per route, last-30-days trend), instead of
querying it by hand in Render's Shell. First route in the whole app that
needs to check anything before rendering -- everything else is
intentionally public, same as the Sleeper API it mirrors.

- `ADMIN_PASSWORD` env var (no local fallback -- more on why below) plus
  `app.secret_key` (falls back to a dev-only value locally, must be set
  for real on Render) so Flask's `session` can sign a cookie proving
  someone already logged in.
- `/admin` (GET shows the login form or the dashboard depending on
  `session["is_admin"]`; POST checks the submitted password) and
  `/admin/logout` (clears the session flag).
- Two new queries: total visits per route (`GROUP BY route`), and total
  visits per day for the last 30 days (`GROUP BY date(visited_at)`).
- Two new templates (`admin_login.html`, `admin_dashboard.html`) that
  reuse the existing `.dash-card` / `.bar-row` CSS classes from the home
  page -- no new chart/bar CSS needed, just a small `.admin-login-form` /
  `.btn` addition for the one thing the site didn't have yet: a form.

### New concepts learned

**"Fail closed," not "fail open."** `DB_NAME` has a friendly local
fallback (`os.environ.get("DB_PATH", "dynasty.db")`) because a missing
value there just means "use the default database" -- harmless. Did the
*opposite* for `ADMIN_PASSWORD`
(`os.environ.get("ADMIN_PASSWORD")`, no second argument): if it's not
set, `ADMIN_PASSWORD` is `None`, and `None` can never equal a submitted
password string, so login is simply impossible until someone deliberately
sets it. ✅ The two situations look identical in code (an env var lookup
with `os.environ.get`), but which way you let it fail is a real security
decision, not a style choice.

**Sessions vs. just remembering something server-side.** `session` in
Flask isn't a database table Claude Code manages -- it's a cookie in the
*user's own browser*, cryptographically signed with `app.secret_key` so
they can't forge it (e.g. hand-editing the cookie to say
`is_admin: true`). Closest SQL analogy: like a signed auth token a client
presents on every request, except Flask handles the signing/verifying for
us. ❓ Still fuzzy on exactly what "signed" is doing mechanically (some
kind of hash so tampering is detectable?) -- worth digging into next time
sessions come up.

**The Post/Redirect/Get pattern.** First instinct was to have a
successful login just render the dashboard directly in the same POST
response. Problem: hitting refresh afterward would resubmit the login
form (the browser's "confirm form resubmission" warning) because the
browser remembers the last request was a POST. Fixed by having a
successful POST `redirect()` to a plain `GET /admin` instead of rendering
inline -- now the *last* request in the browser's history is a harmless
GET, so refreshing just reloads the dashboard. ✅ This clicked once I saw
it's the same reason online forms often land you on a different
confirmation-page URL after submitting, not the form page again.

### Mistakes & fixes

Building this surfaced a real, unrelated data-quality bug in the
*existing* traffic-logging code (Stage 2, `before_request` hook): it was
recording a row for **every** request, including `/static/style.css`
fetches -- so "Visits by Page" showed the CSS file as if it were a page
someone visited, growing every single page load. Fixed by skipping
`/static/` paths in `log_page_visit()` before the insert. Confirmed with
a before/after row count instead of just eyeballing the page -- caught
this myself in testing because the admin page's own output looked wrong,
not because it errored.

**Round two of the same bug class, found after actually deploying and
looking at real production data:** `/admin` on the live site showed
`/favicon.ico` and five different `/apple-touch-icon*.png` variants as
top "pages" -- browsers automatically probe for those on every visit, and
none of them are real routes in this app, so they 404. `before_request`
runs *before* Flask knows a request is about to 404, so it logged them
anyway. Fixed properly this time instead of adding those five filenames
to a blocklist: switched `log_page_visit()` from `@app.before_request` to
`@app.after_request`, which runs *after* the response is built and can
check `response.status_code`. Skip logging on any 404, not just these
specific icon files -- so this also covers robots.txt, sitemap.xml, or
anything else a browser/crawler probes for automatically in the future,
not just today's list. ✅ Good example of "find the general rule, not
just today's symptom" -- a hardcoded filename list would've needed
editing again the next time a browser adds a new auto-probed file.

### Questions / still confused about ❓

- How Flask's session-cookie signing actually works under the hood (noted
  above too) -- know *that* it prevents tampering, not exactly *how*.

**Q: Can I just make up my own string for `FLASK_SECRET_KEY`?**
A: Technically yes, but `ADMIN_PASSWORD` and `FLASK_SECRET_KEY` want
different things even though both are "just a string in an env var."
`ADMIN_PASSWORD` gets typed in by a human (me) every login, so it needs
to be memorable. `FLASK_SECRET_KEY` is never typed by anyone -- it only
exists so Flask can cryptographically sign the login cookie -- so it
should be long and random instead, generated rather than made up:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
✅ Good rule of thumb going forward: if a value gets typed by a human,
optimize for memorable; if a value only gets read by code, optimize for
random/unguessable. Side effect worth remembering: changing this value
later logs everyone out of `/admin` (their old cookie's signature stops
matching) -- not a bug if that ever happens.

### Code snippets worth remembering

```python
# Fail-closed pattern: no fallback value means "nobody gets in" until
# it's deliberately configured, instead of silently allowing something.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if ADMIN_PASSWORD and submitted_password == ADMIN_PASSWORD:
    session["is_admin"] = True
    return redirect(url_for("admin"))  # Post/Redirect/Get, not render() here
```

---

## Session 2026-09-08 — Fixing a live site outage (ZeroDivisionError on the home page)

### What we built

The live site (dynasty-dashboard-ijio.onrender.com) was throwing "Internal
Server Error" on the home page. Tracked it down and shipped a fix, then
walked through the actual git commands (I ran them myself this time
instead of Claude Code doing it) to get it deployed.

### New concepts learned

**"Empty" and "zero" are two different problems, and `default=` in
`max()` only solves one of them.** The buggy line was:
```python
max_score = max((row["points"] for row in scoreboard_rows), default=1)
```
`default=1` only kicks in if `scoreboard_rows` is an empty list (no
matchups at all). It does *nothing* to protect against the list having
real rows where every score is legitimately `0.0` -- which is exactly
what happens in the window after matchups are created for the week but
before any games have actually kicked off. `max()` of a list of zeros is
`0`, not "missing," so `default` never fires, and `row["points"] /
max_score` divides by that real `0`. ✅ Lesson: a `default=` on an
aggregate function guards against *no data*, not against *data that
happens to equal a falsy value*. Those are different failure modes and
need different guards.

**Fix used: `or 1` layered on top of `default=1`.**
```python
max_score = max((row["points"] for row in scoreboard_rows), default=1) or 1
```
`or 1` catches anything falsy that comes out the other side -- `0`
specifically here -- and swaps in `1` instead, same as `COALESCE`, except
`COALESCE` only catches `NULL` while Python's `or` catches *any* falsy
value (`0`, `None`, `""`, `[]`, `False`). That's a double-edged tool: fine
here since `points` can't legitimately be a negative-but-still-falsy
number, but worth remembering `or` is broader than `COALESCE` before
reusing this pattern somewhere a real `0` *should* survive.

**Reproducing a prod-only bug locally.** Rather than guessing from
reading the code, ran the actual Flask dev server locally
(`python app.py`) against the same `dynasty.db` and hit `/` with
`Invoke-WebRequest` -- got the exact same traceback Render would've
logged, with Werkzeug's debugger pinpointing the exact line. Confirmed
the fix the same way afterward: reran, got a 200 instead of a 500. ✅
Much faster than reasoning about it in the abstract, and it's the same
instinct as reproducing a bug against a real query in SSMS before trusting
a fix.

### Mistakes & fixes

Not a mistake made *this* session, but the bug itself is worth noting as
a category: it was a latent bug sitting in the Stage 3 home-page code
since it was written, invisible the whole time because every score
happened to be non-zero whenever it was tested. It only surfaced once the
real season actually started and there was a genuine 0-0 moment. Same
shape as the pre-season `min()`/`max()`-on-empty bugs from the
2026-08-23 session (logged earlier in this file) -- another case of code
that was fine for every state I'd actually tested, but not for a state
that hadn't happened yet.

### Questions / still confused about ❓

None new this session -- straightforward once reproduced.

### Code snippets worth remembering

```python
# Guard against BOTH "no rows" and "rows, but the aggregate is falsy" --
# default= alone only covers the first case.
max_score = max((row["points"] for row in scoreboard_rows), default=1) or 1
```

Full git workflow for shipping a fix (ran manually this session):
```bash
git status              # see what changed
git diff app.py         # review the actual diff before staging
git add app.py           # stage it -- like building a transaction before COMMIT
git commit -m "..."      # COMMIT -- saved to local history, not remote yet
git push                 # send commits to GitHub -- this is what triggers
                          # Render's auto-deploy, nothing before this step does
```

---

## Session 2026-09-17 — Fixed survivor/Best Single Week jumping the gun mid-week

### What we built

Caught a real logic bug from actually using the live site once the real
season started: Survivor was marking someone "Eliminated" and the home
page's Best Single Week card could show a score from a week that was
still being *played*, not actually over yet. Root cause was the same
one thing in four different places: `league_info["settings"]["leg"]` is
Sleeper's name for the week **currently being played**, not the last one
that finished -- but `calculations.py` and `database.py` were both
treating it as "last played week" and looping `range(1, leg + 1)`,
which includes that still-in-progress week.

Fixed it in two layers:
- **`calculations.py`** -- `get_survivor_results()` and
  `get_season_high_scores()` now use `leg - 1` ("last *decided* week")
  instead of `leg`.
- **`app.py`** -- the home page's Season High / Weekly High queries read
  straight from `weekly_scores` via SQL, bypassing `calculations.py`
  entirely, so they needed their own fix. But `app.py` deliberately
  never calls the Sleeper API itself (it only ever reads `dynasty.db`),
  so it had no way to know "which week is in progress" -- which is the
  actual reason we added a new single-row `league_status` table,
  written by a new `insert_league_status()` in `database.py` on every
  refresh, plus a `current_week` badge in the nav (`base.html`) so it's
  not just invisible plumbing.

Important thing this *didn't* touch: `weekly_scores` itself still gets
written for the in-progress week (that's what makes the live
`/scoreboard` page work) -- only the "who won" *determinations*
(survivor, season high, weekly high) needed to stop short of it.

### New concepts learned

**A field name can lie about what it actually means.** `leg` sounds
like it'd mean "the leg that's been completed" but it's really "the leg
currently being played" -- nothing in the field name itself tells you
that, only actually reading Sleeper's real behavior (this league sitting
at `leg = 2` with Week 2 mid-game) proved it. ✅ Same lesson as last
month's transaction `type`/`status` exploration: don't assume a field
means what its name suggests, check what it actually holds.

**Flask's `@app.context_processor`.**
```python
@app.context_processor
def inject_current_week():
    connection = get_db_connection()
    cursor = connection.cursor()
    current_week = get_current_week(cursor)
    connection.close()
    return {"current_week": current_week}
```
Runs before *every* template render and merges whatever dict it returns
into that template's variables automatically -- so `base.html`'s nav
(shared by every page) can use `{{ current_week }}` without every single
route handler having to query for it and pass it into `render_template()`
by hand. SQL analogy: closest thing I know is a view that's implicitly
joined onto every query without each query having to write the join
itself.

**A single-row table, enforced by the schema itself, not just convention.**
```sql
CREATE TABLE league_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_week INTEGER
)
```
Every write is `INSERT OR REPLACE INTO league_status (id, current_week)
VALUES (1, ?)` -- always the same `id`, so it always overwrites the one
row instead of accumulating history (this is "what's true right now,"
not something we want a week-by-week history of, unlike `weekly_scores`).
The `CHECK (id = 1)` isn't just documentation either -- SQLite would
actually reject an insert that tried to use any other id. First time
we've used `CHECK` for real in this project.

**`week < NULL` in SQL is neither true nor false -- it's unknown, and
unknown rows just don't match.** `current_week` can be `None` (a brand
new database, no refresh has run yet). Passing that straight in as a
query parameter --
```sql
WHERE weekly_scores.week < ?  -- param = None
```
-- doesn't error and doesn't need a special case. SQLite (like SQL
Server) treats any comparison against `NULL` as unknown, so the `WHERE`
just matches zero rows -- which is exactly the right answer ("we don't
know what's decided yet") without writing an explicit `if current_week
is None` branch.

### Mistakes & fixes

No crashes or wrong turns this session -- this one was caught by
reasoning about what `leg` actually represents *before* writing any
code (confirmed against the real league actually sitting at Week 2 mid-
game), rather than shipping something and finding the bug later. Verified
it worked by running `database.py` for real afterward: Week 1 (finished)
correctly eliminated `bart`, Week 2 (in progress) wasn't touched at all,
and Best Single Week correctly still points at Week 1's top score even
though Week 2 already has live partial scores sitting in `weekly_scores`.

### Questions / still confused about ❓

- None new -- this was a clean root-cause fix, not a debugging session.

### Code snippets worth remembering

```python
# "leg" is the week CURRENTLY being played, not the last one that
# finished -- leg - 1 is the last week whose scores are actually final.
last_decided_week = league_info["settings"]["leg"] - 1
```

```python
# context_processor makes a value available in every template
# automatically, without every route passing it in by hand
@app.context_processor
def inject_current_week():
    connection = get_db_connection()
    cursor = connection.cursor()
    current_week = get_current_week(cursor)
    connection.close()
    return {"current_week": current_week}
```

```sql
-- CHECK enforces "this table only ever has one row" at the schema
-- level, not just by convention
CREATE TABLE league_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_week INTEGER
)
```

---

## Session 2026-11-07: Standings on the home page (I wrote most of the code this time)

### What we built

Took `get_standings()` (already written, returns all 12 teams in bylaws
order) and wired it all the way through to the website, same pipeline as
every other feature:

Sleeper API → `calculations.py` → `database.py` insert → `dynasty.db` →
`app.py` query → template

- New `standings` table in `create_tables()`: roster_id, wins, losses,
  pf, max_pf, rank
- New `insert_standings()` in `database.py`, added to `refresh_all_data()`
  so the hourly refresh keeps it current
- Home page query now JOINs `standings` to `teams`, `ORDER BY rank`
- Home page table shows Rank / Team / Record / PF / Max PF, with a green
  line under rank 6 (the playoff cutoff), gold/silver/bronze for the top 3
- 1st/2nd Place payout tiles now say "decided in Week 17" instead of
  "Needs a standings feature" (those come from the playoffs, not standings)
- Bylaws link in the top nav, pointing at the league's Google Doc

### New concepts learned

✅ **Store the rank, don't recompute it in SQL.** The bylaws sort is two
passes (all 12 by wins then PF, then the bottom 6 re-sorted by wins then
Max PF). That's awkward to write as one `ORDER BY`. So Python works out the
order once, I save the position as a `rank` column, and the website query
is just `ORDER BY rank`. The bylaws logic lives in exactly one place.

✅ **`enumerate()` is Python's `ROW_NUMBER()`.** It numbers rows by their
position in an already-sorted list. The rank isn't IN the data, it's
generated:
```python
for rank, (roster_id, _team_name, wins, losses, pf, max_pf) in enumerate(standings, start=1):
#   ^ the number enumerate adds   ^ the original 6-item row, unpacked
```
`start=1` matters, otherwise first place is rank 0.

✅ **Tuple unpacking has to match the shape exactly.** `get_standings()`
returns 6 items per row. I have to name all 6, even ones I don't use.
`_team_name` (leading underscore) is the convention for "unpacking this
because I have to, not using it." Too few names = "too many values to
unpack", too many names = "not enough values to unpack."

✅ **A parameterized INSERT has three lists that must line up:** the
column list, the `?` placeholders, and the Python values tuple. Same count,
same order. Adding a column means touching all three in one edit.

✅ **"It compiles" doesn't mean "it works."** `py_compile` only checks
syntax (is this shaped like Python). A wrong variable name or a column
that doesn't exist only blows up when that line actually runs. Like a SQL
query that parses but fails on an invalid column name at execution.

✅ **A `try:` with no `except`/`finally` breaks the WHOLE file**, not just
that function. Python checks the entire file's syntax before running any
of it, so `app.py` couldn't even import `database.py`.

✅ **Jinja fails silently on unknown variable names.** If the template
loops over a name `app.py` didn't send (an old name, a typo, a leftover
`___`), it's treated as empty: the table just shows no rows, no error. If a
table is ever mysteriously empty, check the variable names first.

✅ **`cursor.fetchall()` vs a list comprehension.** The old placeholder
did `[row["team_name"] for row in cursor.fetchall()]`, which keeps only
one column (like wrapping the query in `SELECT team_name FROM (...)`).
The template needs every column now, so it's just `cursor.fetchall()`.

✅ **SQLite is looser than SQL Server about column types.** An `INTEGER`
column will quietly keep a decimal like 1342.56. I'd get away with it, but
`REAL` is the honest type for PF.

### Mistakes & fixes

Lots this time, since I was writing it myself. Every one was a real lesson:
- **CREATE TABLE with no commas between columns.** SQLite read the whole
  thing as one column with a giant multi-word type name, then choked at
  `PRIMARY KEY (`. Error was the unhelpful `near "(": syntax error`.
- **`FOREIGN KEY (roster_id)` with nothing after it.** Needs
  `REFERENCES teams(roster_id)`.
- **`pf`/`max_pf` as `INTEGER`.** Changed to `REAL` (see above).
- **`try:` with no `except`.** SyntaxError pointing at the NEXT function,
  which was confusing. Copied the except/finally from `insert_start_sit()`.
- **Put `team_name` in the INSERT**, but the `standings` table doesn't have
  that column (it's in `teams`, I JOIN for it).
- **Unpacking mismatches, both directions.** Dropped `_team_name` (5 names
  for 6 values), then added `rank` at the end (7 names for 6 values). The
  fix was `enumerate`, since rank isn't in the tuple at all.
- **6 `?` placeholders but 5 columns and 5 values.** "6 values for 5 columns."
- **Home page query had no JOIN**, so `team_name` didn't exist. That would
  have 500'd the whole home page, not just the table.
- **Edits not saved in VS Code** a couple of times. Checked for the dot on
  the tab. Turning on Auto Save would prevent this.
- **Bylaws:** started building a `/bylaws` page from `BYLAWS.md`, then
  realized the Google Doc is the real version (and the two had drifted,
  e.g. 1 IR slot vs 2). Switched to just linking the Doc instead of
  keeping two copies in sync.

### Questions / still confused about ❓

- ❓ The two-level unpacking with `enumerate` (`rank, (a, b, c)`) took a
  few tries to get. I get it now, but it's not automatic yet.
- ❓ `BYLAWS.md` in the repo is behind the Google Doc. Need to sync it at
  some point, since Claude Code still reads it for rules.

### Code snippets worth remembering

```python
# insert pattern: try / except / finally, same shape as T-SQL TRY/CATCH + ROLLBACK
connection = None                                   # so finally can check it even if connecting fails
try:
    standings = get_standings(league_id)            # API calls happen here, can raise
    connection = get_connection()
    cursor = connection.cursor()
    for rank, (roster_id, _team_name, wins, losses, pf, max_pf) in enumerate(standings, start=1):
        cursor.execute(
            "INSERT OR REPLACE INTO standings (roster_id, wins, losses, pf, max_pf, rank) VALUES (?, ?, ?, ?, ?, ?)",
            (roster_id, wins, losses, pf, max_pf, rank),   # 6 columns, 6 ?, 6 values
        )
    connection.commit()                             # nothing is saved until this
except requests.exceptions.RequestException:
    logging.error("insert_standings: Sleeper API call failed, skipping this refresh")
    if connection:
        connection.rollback()                       # don't keep half a refresh
finally:
    if connection:
        connection.close()                          # always runs, error or not
```

```html
<!-- Jinja: loop the rows app.py sent, print columns by name -->
{% for row in standings_rows %}                     <!-- like a cursor over the result set -->
<tr{% if row["rank"] == 6 %} class="playoff-cutoff"{% endif %}>  <!-- green line under the last playoff spot -->
    <td>{{ row["rank"] }}</td>                       <!-- {{ }} = print this value -->
    <td>{{ row["wins"] }}-{{ row["losses"] }}</td>    <!-- two columns in one cell: 6-2 -->
    <td>{{ "%.2f"|format(row["pf"]) }}</td>          <!-- always 2 decimals -->
</tr>
{% endfor %}
```

⚠️ **Don't run `pip freeze > requirements.txt` blindly.** `gunicorn` is
only installed on Render, not on my machine, so freeze leaves it out, and
overwriting the file would break the next deploy. Add new packages to
`requirements.txt` by hand.

---

## Session 2026-11-12: Draft pick ownership grid (I wrote all of it)

### What we built

Step 1 of draft pick tracking: who currently owns each 2027 rookie pick.
Only the data part, no database or website yet.

- `sleeper.py`: `get_traded_picks(league_id)`, a raw fetch of
  `/league/{id}/traded_picks` through `_get_json()`
- `calculations.py`: `get_pick_ownership(league_id, season)`, returns 60
  tuples of `(season, round, original_roster_id, owner_roster_id)`
- A `--- 2027 Pick Ownership ---` section in `calculations.py`'s
  `__main__` block

Matched the expected live numbers exactly: 60 picks, 6 traded, roster 1
owns 7, roster 2 owns 6, rosters 5/9/11 own 4, everyone else 5.

Also decided how the 1.13 compensatory pick will look on the board
(13th row in round 1 with a "COMP" pill, start/sit leader shown as
"projected"). Logged in Obsidian under Step 3.

### New concepts learned

✅ **Write it in English first, then translate.** I could read code fine
but froze on a blank page. What worked: write every step as a comment
first, then turn ONE comment into code, run it, print, check, repeat. Same
as building a big SQL query one join at a time.

✅ **The whole function is a CROSS JOIN + LEFT JOIN/COALESCE.**
- Default grid = every round x every roster (nested loops = CROSS JOIN)
- Trades overwrite the owner for the picks that moved (= COALESCE(trade owner, original))

✅ **A dict with a tuple key is a table with a composite primary key.**
`grid[(round, roster_id)] = owner`. Writing to a key that already exists
REPLACES the value, it doesn't add a row. That's why the grid stayed at 60
after the trades. Like `UPDATE ... WHERE pk = ...`.

✅ **`=` puts the right side INTO the left side.** Like `SET target = source`.
I had it backwards once and wrote into the pick instead of the grid.

✅ **A function call or lookup on its own line does nothing useful.**
`get_league_rosters(league_id)` alone runs and throws the result away.
Needs `rosters = ...` to catch it. Same as a SELECT with no INTO. I did
this three separate times (rosters, `roster["roster_id"]`, and calling
`get_pick_ownership()` in `__main__` without looping over what it returned).

✅ **`print(my_function)` vs `print(my_function())`.** No parentheses =
the function itself (`<function ... at 0x...>`), not its result. Like
`sp_helptext` vs `EXEC`.

✅ **`'2027' == 2027` is False in Python.** No error, no automatic
conversion like SQL Server does. The API sends season as a string, so I
convert the API side: `int(pick["season"]) == season`. Never hardcode the
year, that's what the `season` parameter is for.

✅ **`.items()` loops over a dict's keys AND values together.**
`for key, owner in grid.items():`

✅ **`append()` takes exactly ONE thing.** For a row, that one thing is a
tuple, so it needs double parentheses: `picks.append((a, b, c, d))`.
Like `INSERT ... VALUES (a, b, c, d)` being one row.

✅ **Unpacking goes by position, not name.** The `for` line needs exactly
as many names as the tuple has values, in the same order. Swap two names
and Python won't complain, the data will just be silently wrong.

✅ **Reading a traceback:** start at the bottom. Last line = what went
wrong. The bottom `File ... line N` = where to fix it. Lines above that
are just the chain of calls that got there.

✅ **Test one function without running the whole file:**
`python -c "from calculations import get_pick_ownership, LEAGUE_ID; get_pick_ownership(LEAGUE_ID, 2027)"`.
Importing skips the `if __name__ == "__main__":` block.

✅ **Label debug prints** (`print("grid size:", len(grid))`) so they're
findable in a wall of output. Then delete them once the function returns
real data.

### Mistakes & fixes

- **Put `get_pick_ownership` in `sleeper.py`.** That file is only for raw
  API fetches. Moved it to `calculations.py`, then had to delete the copy
  I'd left behind.
- **Forgot the `season` parameter** at first.
- **`IndentationError: unexpected indent`.** Indented the `grid[...]` line
  under a line that didn't end in `:`. Only indent further after a colon.
- **Filter compared the wrong things.** First `season == int('2027')`
  (always True, let all 14 trades through, including 2026 and 2028), then
  `pick["season"] == int('2027')` (string vs int, always False, 0 trades).
  The count of `traded:` lines is what caught both.
- **Backwards assignment**, then a bare tuple on the left side with no
  `grid[...]` around it. That one never errored because the broken filter
  meant the line never ran. "No error" doesn't mean "correct."
- **`append()` with 0 args, then 4 args.** Needed 1 tuple.
- **Dropped `original` from the `for` line**, got "too many values to
  unpack (expected 3)".
- **Edits not saved**, several times again. Then once it WAS saved but
  the edit wasn't in the file. Check the tab for the dot, turn on Auto Save.

### Questions / still confused about ❓

- ❓ Getting started on a blank function is still the hard part. The
  comment skeleton helped a lot, try writing my own skeleton next time.
- ❓ Catching return values in a variable isn't automatic yet (3 misses
  this session).

### Code snippets worth remembering

```python
grid = {}                                                   # empty "table", key = (round, roster_id)
for round_number in range(1, draft_rounds + 1):             # 1..5 (range stops BEFORE the end number)
    for roster in rosters:                                  # inner loop runs fully for each round = CROSS JOIN
        roster_id = roster["roster_id"]                     # catch the value in a variable
        grid[(round_number, roster_id)] = roster_id         # everyone owns their own pick to start

for pick in traded_picks:
    if int(pick["season"]) == season:                       # WHERE season = 2027 (convert the string side)
        grid[(pick["round"], pick["roster_id"])] = pick["owner_id"]   # overwrite = UPDATE owner

picks = []
for key, owner in grid.items():                             # key and value together
    round_number, original_roster_id = key                  # split the (round, roster) tuple
    picks.append((season, round_number, original_roster_id, owner))  # double () = one row
return picks                                                # lined up with the for, not inside it
```

---
*Last updated: 2026-11-12*
