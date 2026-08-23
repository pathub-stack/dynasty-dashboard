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
*Last updated: 2026-08-23*
