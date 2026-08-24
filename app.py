# The Flask web app -- turns dynasty.db's tables into pages a browser can
# load. This queries the database directly; it never calls the Sleeper API
# itself. Keeping data refresh (sleeper.py -> database.py) and data serving
# (this file) separate means a slow/down Sleeper API can't slow down or
# crash a page load -- the dashboard just serves whatever's already in
# dynasty.db until the next refresh happens.

import os
import sqlite3
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request

from database import DB_NAME, create_tables, refresh_all_data
from sleeper import LEAGUE_ID

app = Flask(__name__)

# From README's documented league settings, not a live API call -- Flask
# never touches Sleeper's API, only dynasty.db, so this can't be pulled
# from league_info["settings"]["waiver_budget"] the way calculations.py
# does it.
WAIVER_BUDGET = 200

# One color per team instead of every bar/card sharing a single green --
# every dashboard card looked identical regardless of which team it was,
# which read as more "spreadsheet" than "fantasy football."
TEAM_COLOR_PALETTE = [
    "#3fb950", "#58a6ff", "#bc8cff", "#f778ba", "#ffa657", "#56d4dd",
    "#e3b341", "#ff7b72", "#79c0ff", "#7ee787", "#d2a8ff", "#ffab70",
]


def get_team_colors(cursor):
    """Return a dict mapping team_name -> a hex color, one per team.

    Assigned by roster_id, not by insertion order in whatever query calls
    this -- that's what keeps a team's color the same across every card
    and every page load, instead of shifting around based on how a
    particular query happened to sort its rows.
    """
    cursor.execute("SELECT roster_id, team_name FROM teams")
    return {
        row["team_name"]: TEAM_COLOR_PALETTE[row["roster_id"] % len(TEAM_COLOR_PALETTE)]
        for row in cursor.fetchall()
    }

# create_tables() is IF NOT EXISTS, so this is safe every time the app
# starts (dev reload, or a fresh process on Render) -- it's what actually
# makes sure page_visits (and every other table) exists before any route
# or the before_request hook below tries to write to it.
create_tables()

# Background refresh: pulls fresh data from Sleeper on a timer (hourly) so
# the dashboard doesn't go stale between manual `python database.py` runs
# -- same idea as a scheduled SQL Agent job, except it runs as a
# background thread inside this same process instead of a separate
# scheduler service, since Render's Starter tier stays running anyway.
#
# Guarded so it only ever starts once. Flask's debug reloader
# (app.run(debug=True), used locally) actually launches two processes --
# a watcher and the real worker -- and without this check the scheduler
# would start in both, doubling every Sleeper API call. WERKZEUG_RUN_MAIN
# is only set to "true" inside the real worker process. In production
# (gunicorn, where app.debug is False) the first half of the condition
# alone is enough.
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: refresh_all_data(LEAGUE_ID),
        trigger="interval",
        hours=1,
        next_run_time=datetime.now(),
    )
    scheduler.start()


def get_db_connection():
    """Open a connection to dynasty.db for this app's own queries.

    Separate from database.py's get_connection() because this one sets
    row_factory = sqlite3.Row -- that makes each row behave like a dict
    (row["team_name"]) instead of a plain tuple (row[1]), which is what
    Jinja templates need to read columns by name. database.py's own
    connection stays plain tuples since its code already unpacks by
    position everywhere.
    """
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


@app.before_request
def log_page_visit():
    """Write one row per request into page_visits -- route + timestamp.

    Flask runs this before every route handler below, so it doesn't need
    to be called manually in each one. Unlike every table in database.py,
    this one really does want a plain autoincrement id: those other
    tables get REPLACED on every refresh (same roster_id, fresher data),
    but a page visit is a one-time event -- there's nothing to overwrite,
    every request is a genuinely new row.
    """
    connection = get_db_connection()
    connection.execute(
        "INSERT INTO page_visits (route, visited_at) VALUES (?, ?)",
        (request.path, datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()
    connection.close()


@app.route("/")
def home():
    """The real dashboard -- a dense, at-a-glance summary of every payout
    category, each as a bar-chart-style card instead of a plain table.
    Full detail for scoreboard/survivor/start-sit still lives on their own
    pages (linked from each card); this just pulls the same data plus two
    new aggregations (season high score, weekly high score win tally) that
    don't have a dedicated route of their own.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    team_colors = get_team_colors(cursor)

    # ---- Standings: placeholder only -- win/loss records aren't tracked
    # anywhere yet (that's a real feature, not built), so this just lists
    # real team names with the "Coming Soon" columns left blank.
    cursor.execute("SELECT team_name FROM teams ORDER BY team_name")
    standings_teams = [row["team_name"] for row in cursor.fetchall()]

    # ---- Scoreboard: latest week, same query as /scoreboard ----
    cursor.execute("SELECT MAX(week) AS latest_week FROM weekly_scores")
    latest_week = cursor.fetchone()["latest_week"]

    cursor.execute(
        """
        SELECT teams.team_name, weekly_scores.points
        FROM weekly_scores
        JOIN teams ON teams.roster_id = weekly_scores.roster_id
        WHERE weekly_scores.week = ?
        ORDER BY weekly_scores.points DESC
        """,
        (latest_week,),
    )
    scoreboard_rows = cursor.fetchall()
    max_score = max((row["points"] for row in scoreboard_rows), default=1)
    scoreboard_bars = [
        {
            "team_name": row["team_name"],
            "points": row["points"],
            "width_pct": row["points"] / max_score * 100,
        }
        for row in scoreboard_rows
    ]

    # ---- Survivor: same as /survivor, plus each elimination's points via
    # a join to weekly_scores -- survivor_status only stores WHICH week a
    # team was eliminated, not how many points they scored that week.
    cursor.execute("""
        SELECT teams.team_name, survivor_status.week_eliminated, weekly_scores.points
        FROM survivor_status
        JOIN teams ON teams.roster_id = survivor_status.roster_id
        LEFT JOIN weekly_scores
            ON weekly_scores.roster_id = survivor_status.roster_id
            AND weekly_scores.week = survivor_status.week_eliminated
        ORDER BY survivor_status.week_eliminated IS NULL, survivor_status.week_eliminated
    """)
    survivor_rows = cursor.fetchall()

    # A "leader" only exists once exactly one team is left standing -- with
    # everyone still alive (e.g. before the season starts) or several teams
    # alive at once, there's no single winner to declare yet.
    still_alive = [row for row in survivor_rows if row["week_eliminated"] is None]
    survivor_leader = still_alive[0] if len(still_alive) == 1 else None
    eliminated_count = sum(1 for row in survivor_rows if row["week_eliminated"] is not None)

    # ---- Season High Score: every week's top scorer(s), ranked across the
    # whole season. Same "greatest-n-per-group" subquery as /start-sit uses
    # (max value per group), just grouped by week instead of by roster_id.
    cursor.execute("""
        SELECT weekly_scores.week, teams.team_name, weekly_scores.points
        FROM weekly_scores
        JOIN teams ON teams.roster_id = weekly_scores.roster_id
        WHERE weekly_scores.points = (
            SELECT MAX(w2.points) FROM weekly_scores AS w2 WHERE w2.week = weekly_scores.week
        )
        ORDER BY weekly_scores.points DESC
    """)
    season_high_rows = cursor.fetchall()
    max_season_high = max((row["points"] for row in season_high_rows), default=1)
    season_high_bars = [
        {
            "team_name": row["team_name"],
            "week": row["week"],
            "points": row["points"],
            "width_pct": row["points"] / max_season_high * 100,
        }
        for row in season_high_rows
    ]
    season_high_leader = season_high_rows[0] if season_high_rows else None
    season_high_tied = bool(
        season_high_leader
        and len(season_high_rows) > 1
        and season_high_rows[1]["points"] == season_high_leader["points"]
    )

    # ---- Weekly High Score win tally: how many times has each team posted
    # that week's top score? Reuses the exact same per-week-max subquery
    # above, just GROUPed by team to count wins instead of listing each one.
    cursor.execute("""
        SELECT teams.team_name, COUNT(*) AS wins
        FROM weekly_scores
        JOIN teams ON teams.roster_id = weekly_scores.roster_id
        WHERE weekly_scores.points = (
            SELECT MAX(w2.points) FROM weekly_scores AS w2 WHERE w2.week = weekly_scores.week
        )
        GROUP BY teams.roster_id
        ORDER BY wins DESC
    """)
    weekly_high_tally = cursor.fetchall()

    # ---- Start/Sit %: same query as /start-sit ----
    cursor.execute("""
        SELECT teams.team_name, start_sit.percentage
        FROM start_sit
        JOIN teams ON teams.roster_id = start_sit.roster_id
        WHERE start_sit.week = (
            SELECT MAX(week) FROM start_sit AS latest
            WHERE latest.roster_id = start_sit.roster_id
        )
        ORDER BY start_sit.percentage DESC
    """)
    start_sit_bars = [
        {
            "team_name": row["team_name"],
            "percentage": row["percentage"],
            "width_pct": row["percentage"] * 100,
        }
        for row in cursor.fetchall()
    ]

    # ---- FAAB: season-to-date spend per team. LEFT JOIN (not JOIN) so a
    # team with zero waiver claims still shows up as $0 spent instead of
    # disappearing from the list entirely.
    # Sorted by spent ASC (== remaining DESC) so rank 1 has the longest bar
    # here too -- same "rank 1 = fullest bar" convention as every other card.
    cursor.execute("""
        SELECT teams.team_name, COALESCE(SUM(faab_transactions.amount_spent), 0) AS spent
        FROM teams
        LEFT JOIN faab_transactions ON faab_transactions.roster_id = teams.roster_id
        GROUP BY teams.roster_id
        ORDER BY spent ASC
    """)
    # remaining is clamped at 0: a team that received FAAB via a trade can
    # genuinely spend past the flat $200 base budget (trades that move FAAB
    # aren't tracked in faab_transactions -- see insert_faab_transactions()'s
    # docstring), so "spent" can exceed WAIVER_BUDGET without it being a bug.
    #
    # width_pct is based on REMAINING, not spent -- every other bar on this
    # page uses "longer bar = more of the good thing" (more points, higher
    # %), so a bar based on spent would make $0-left teams look the fullest,
    # backwards from what a glance at the bar should tell you.
    faab_bars = [
        {
            "team_name": row["team_name"],
            "spent": row["spent"],
            "remaining": max(0, WAIVER_BUDGET - row["spent"]),
            "width_pct": max(0, min(100, (WAIVER_BUDGET - row["spent"]) / WAIVER_BUDGET * 100)),
        }
        for row in cursor.fetchall()
    ]

    connection.close()

    return render_template(
        "index.html",
        week=latest_week,
        scoreboard_bars=scoreboard_bars,
        survivor_rows=survivor_rows,
        survivor_leader=survivor_leader,
        eliminated_count=eliminated_count,
        season_high_bars=season_high_bars,
        season_high_leader=season_high_leader,
        season_high_tied=season_high_tied,
        weekly_high_tally=weekly_high_tally,
        start_sit_bars=start_sit_bars,
        faab_bars=faab_bars,
        waiver_budget=WAIVER_BUDGET,
        team_colors=team_colors,
        standings_teams=standings_teams,
    )


@app.route("/scoreboard")
def scoreboard():
    connection = get_db_connection()
    cursor = connection.cursor()

    # No week was requested, so default to whichever week was most
    # recently written into weekly_scores.
    cursor.execute("SELECT MAX(week) AS latest_week FROM weekly_scores")
    latest_week = cursor.fetchone()["latest_week"]

    cursor.execute(
        """
        SELECT teams.team_name, weekly_scores.points
        FROM weekly_scores
        JOIN teams ON teams.roster_id = weekly_scores.roster_id
        WHERE weekly_scores.week = ?
        ORDER BY weekly_scores.points DESC
        """,
        (latest_week,),
    )
    scores = cursor.fetchall()
    connection.close()

    return render_template("scoreboard.html", week=latest_week, scores=scores)


@app.route("/survivor")
def survivor():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT teams.team_name, survivor_status.week_eliminated
        FROM survivor_status
        JOIN teams ON teams.roster_id = survivor_status.roster_id
        ORDER BY survivor_status.week_eliminated IS NULL, survivor_status.week_eliminated
    """)
    standings = cursor.fetchall()
    connection.close()

    return render_template("survivor.html", standings=standings)


@app.route("/start-sit")
def start_sit():
    connection = get_db_connection()
    cursor = connection.cursor()

    # start_sit's primary key is (roster_id, week), so re-running
    # insert_start_sit() every week builds up real history per team --
    # this "greatest-n-per-group" subquery pulls just each team's most
    # recent row instead of every week they've ever had.
    cursor.execute("""
        SELECT teams.team_name, start_sit.pf, start_sit.max_pf, start_sit.percentage
        FROM start_sit
        JOIN teams ON teams.roster_id = start_sit.roster_id
        WHERE start_sit.week = (
            SELECT MAX(week) FROM start_sit AS latest
            WHERE latest.roster_id = start_sit.roster_id
        )
        ORDER BY start_sit.percentage DESC
    """)
    leaderboard = cursor.fetchall()
    connection.close()

    return render_template("start_sit.html", leaderboard=leaderboard)


@app.route("/history")
def history():
    return render_template(
        "coming_soon.html",
        title="League History",
        message="Past-season history isn't tracked yet. Logged as a future idea in the project roadmap.",
    )


@app.route("/draft-picks")
def draft_picks():
    """Placeholder page for draft pick tracking.

    "2027" is hardcoded for now rather than computed from the current NFL
    season. The real feature (tracking completed rookie drafts plus who
    holds which future picks) needs its own session to scope properly;
    this route just exists so the nav link has somewhere real to go.
    """
    return render_template(
        "coming_soon.html",
        title="2027 Draft Picks",
        message="Draft pick tracking isn't built yet. Logged as a future idea in the project roadmap.",
    )


@app.route("/power-rankings")
def power_rankings():
    return render_template(
        "coming_soon.html",
        title="Power Rankings",
        message="Weekly subjective 1-12 rankings aren't built yet. Logged as a future idea in the project roadmap.",
    )


if __name__ == "__main__":
    app.run(debug=True)
