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
*Last updated: 2026-08-08*
