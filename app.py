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
from flask import Flask, redirect, render_template, request, session, url_for

from database import DB_NAME, create_tables, refresh_all_data
from sleeper import LEAGUE_ID

app = Flask(__name__)

# Needed for Flask's `session` to work at all -- it's the key used to sign
# the session cookie, so a browser can't just edit its own cookie to claim
# is_admin=True. The fallback only covers local dev (nobody else can reach
# localhost); Render's copy needs FLASK_SECRET_KEY set for real, same as
# DB_PATH and ADMIN_PASSWORD below.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-not-for-production")

# No default here on purpose -- unlike DB_NAME, a missing ADMIN_PASSWORD
# should mean "nobody can log in" (fail closed), not "fall back to some
# guessable value baked into a public GitHub repo."
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

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


def get_current_week(cursor):
    """Return the week currently being played, or None if no refresh has
    run yet (e.g. a brand-new database).

    Read from league_status -- written by database.py's
    insert_league_status() -- instead of calling Sleeper directly. This
    file never touches the Sleeper API itself, only dynasty.db (see the
    file header comment above).
    """
    cursor.execute("SELECT current_week FROM league_status WHERE id = 1")
    row = cursor.fetchone()
    return row["current_week"] if row else None


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


@app.context_processor
def inject_current_week():
    """Make current_week and draft_season available in every template automatically --
    same idea as a value every view has access to without each route
    having to fetch and pass it in individually. Runs on every request
    with its own connection, independent of whatever a specific route's
    handler is doing with its own.
    """
    connection = get_db_connection()
    cursor = connection.cursor()
    current_week = get_current_week(cursor)

    # Season for the nav's "Draft Picks" link label, so it rolls over to
    # the next year on its own instead of a hardcoded "2027". [0] pulls
    # the one value out of the one-row result. MAX() on an empty table
    # returns a row holding None (not zero rows), so this never crashes.
    draft_season = cursor.execute("SELECT MAX(season) FROM draft_picks").fetchone()[0]

    connection.close()
    return {"current_week": current_week, "draft_season": draft_season}


@app.after_request
def log_page_visit(response):
    """Write one row per request into page_visits -- route + timestamp.

    after_request (not before_request) specifically because it needs to
    see the response's status code -- more on why below. Flask runs this
    after every route handler, so it doesn't need to be called manually in
    each one. Unlike every table in database.py, this one really does want
    a plain autoincrement id: those other tables get REPLACED on every
    refresh (same roster_id, fresher data), but a page visit is a one-time
    event -- there's nothing to overwrite, every request is a genuinely
    new row. Must return `response` -- that's the contract for an
    after_request function, unlike before_request which returns nothing.

    Skips /static/ requests (CSS, images, etc.) -- those fire on every
    single page load alongside the real page request, so counting them
    here would drown out actual page views with "someone's browser
    fetched style.css again."

    Also skips anything that 404'd. Browsers automatically probe for
    things like /favicon.ico and /apple-touch-icon.png on every visit --
    none of those are real routes in this app, so they'd otherwise get
    logged as if someone visited a page called "/favicon.ico." Checking
    the response status (only available here, in after_request, not in
    before_request) catches this in general rather than hardcoding a list
    of every icon filename a browser might ever ask for.
    """
    if request.path.startswith("/static/") or response.status_code == 404:
        return response

    connection = get_db_connection()
    connection.execute(
        "INSERT INTO page_visits (route, visited_at) VALUES (?, ?)",
        (request.path, datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()
    connection.close()

    return response


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
    current_week = get_current_week(cursor)

    cursor.execute("SELECT rank, team_name, wins, losses, pf, max_pf FROM standings s JOIN teams t on t.roster_id = s.roster_id ORDER BY rank")
    standings_rows = cursor.fetchall()

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
    # `or 1`, not just `default=1` -- default only covers an EMPTY
    # scoreboard_rows. Early in a week, before any games have kicked off,
    # scoreboard_rows is non-empty but every score is still 0.0, so
    # max() legitimately returns 0 -- dividing by that crashed the page
    # (ZeroDivisionError). `or 1` catches that falsy-but-not-missing 0
    # case too.
    max_score = max((row["points"] for row in scoreboard_rows), default=1) or 1
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
    #
    # weekly_scores.week < current_week excludes the week still being
    # played -- its scores in weekly_scores are live/partial (correct for
    # the /scoreboard page, which wants to show games in progress), but
    # not yet a "final" week score, so it shouldn't be eligible to win
    # Season High Score until it's actually over. current_week can be
    # None (no refresh has run yet) -- SQLite treats week < NULL as
    # unknown for every row, so this naturally returns nothing rather
    # than erroring.
    cursor.execute(
        """
        SELECT weekly_scores.week, teams.team_name, weekly_scores.points
        FROM weekly_scores
        JOIN teams ON teams.roster_id = weekly_scores.roster_id
        WHERE weekly_scores.week < ?
          AND weekly_scores.points = (
            SELECT MAX(w2.points) FROM weekly_scores AS w2 WHERE w2.week = weekly_scores.week
        )
        ORDER BY weekly_scores.points DESC
        """,
        (current_week,),
    )
    season_high_rows = cursor.fetchall()
    # Same 0-vs-empty distinction as max_score above -- see that comment.
    max_season_high = max((row["points"] for row in season_high_rows), default=1) or 1
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
    # Same current_week exclusion as Season High Score above -- the
    # in-progress week hasn't produced a decided weekly winner yet.
    cursor.execute(
        """
        SELECT teams.team_name, COUNT(*) AS wins
        FROM weekly_scores
        JOIN teams ON teams.roster_id = weekly_scores.roster_id
        WHERE weekly_scores.week < ?
          AND weekly_scores.points = (
            SELECT MAX(w2.points) FROM weekly_scores AS w2 WHERE w2.week = weekly_scores.week
        )
        GROUP BY teams.roster_id
        ORDER BY wins DESC
        """,
        (current_week,),
    )
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
        standings_rows=standings_rows,
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
    """Who owns every pick in the upcoming rookie draft, grouped by round.

    Reads the draft_picks table (filled by database.py's
    insert_draft_picks() on every refresh), never the Sleeper API. Picks
    are listed by original team, not draft slot: the real 1.01-1.12 order
    is Step 2 of the draft pick roadmap.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    # teams is joined TWICE (owner + orig aliases) to get both names.
    # MAX(season) instead of a hardcoded year: after next summer's draft,
    # the table holds two seasons and this keeps showing the newest one.
    # traded_pick compares roster_ids (keys), not team names (labels that
    # owners rename), and comes back as 1/0 since SQLite has no booleans.
    cursor.execute("""
    SELECT season, 
    round, 
    owner.team_name as owner_team_name,
    orig.team_name as original_team_name,
    dp.original_roster_id != dp.owner_roster_id as traded_pick,
    13 - s.rank as slot
    FROM draft_picks dp 
    JOIN teams owner on owner.roster_id = dp.owner_roster_id
    JOIN teams orig on orig.roster_id = dp.original_roster_id  
    LEFT JOIN standings s on s.roster_id = dp.original_roster_id
    WHERE season = (SELECT MAX(season) from draft_picks)
    ORDER BY round, slot
    """)

    # 3. fetchall() into a variable (catch the return value!), close the connection
    picks = cursor.fetchall()
    connection.close()

    # Every row has the same season (the WHERE above), so read it off the
    # first one. An empty list is falsy, so an empty table gives None
    # instead of crashing on picks[0] (IndexError).
    season = picks[0]["season"] if picks else None

    return render_template(
        "draft_picks.html",
        picks=picks,
        season=season
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    """Password-gated page showing page_visits traffic data.

    Everything else in this app is intentionally public (same as the
    Sleeper API it mirrors) -- this is the one page meant for just the
    developer, not the other 11 leaguemates, so it's the first route that
    needs to check anything before rendering.

    Not logged in yet -> show the login form (and re-show it with an error
    if a submitted password was wrong). Logged in -> skip straight to the
    dashboard queries below. `session["is_admin"]` is what "logged in"
    means here -- Flask signs that cookie with app.secret_key above, so a
    visitor can't just set the cookie themselves to fake it.
    """
    if not session.get("is_admin"):
        if request.method == "POST":
            submitted_password = request.form.get("password", "")
            if ADMIN_PASSWORD and submitted_password == ADMIN_PASSWORD:
                session["is_admin"] = True
                # Redirect back to a plain GET /admin instead of falling
                # through here -- otherwise refreshing the page after
                # login would re-submit the login form (the browser's
                # "confirm form resubmission" prompt).
                return redirect(url_for("admin"))
            return render_template("admin_login.html", error="Wrong password.")
        return render_template("admin_login.html", error=None)

    connection = get_db_connection()
    cursor = connection.cursor()

    # ---- Visits by page: total count per route, most-visited first.
    cursor.execute("""
        SELECT route, COUNT(*) AS visit_count
        FROM page_visits
        GROUP BY route
        ORDER BY visit_count DESC
    """)
    route_rows = cursor.fetchall()
    total_visits = sum(row["visit_count"] for row in route_rows)
    max_route_visits = max((row["visit_count"] for row in route_rows), default=1)
    route_bars = [
        {
            "route": row["route"],
            "visit_count": row["visit_count"],
            "width_pct": row["visit_count"] / max_route_visits * 100,
        }
        for row in route_rows
    ]

    # ---- Last 30 days: total visits per day, most recent first. SQLite's
    # date() understands the ISO timestamps log_page_visit() writes, same
    # as pulling just the date part out of a SQL Server datetime column.
    cursor.execute("""
        SELECT date(visited_at) AS day, COUNT(*) AS visit_count
        FROM page_visits
        WHERE date(visited_at) >= date('now', '-30 days')
        GROUP BY day
        ORDER BY day DESC
    """)
    day_rows = cursor.fetchall()
    max_day_visits = max((row["visit_count"] for row in day_rows), default=1)
    day_bars = [
        {
            "day": row["day"],
            "visit_count": row["visit_count"],
            "width_pct": row["visit_count"] / max_day_visits * 100,
        }
        for row in day_rows
    ]

    connection.close()

    return render_template(
        "admin_dashboard.html",
        total_visits=total_visits,
        route_bars=route_bars,
        day_bars=day_bars,
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin"))


@app.route("/power-rankings")
def power_rankings():
    return render_template(
        "coming_soon.html",
        title="Power Rankings",
        message="Weekly subjective 1-12 rankings aren't built yet. Logged as a future idea in the project roadmap.",
    )


if __name__ == "__main__":
    app.run(debug=True)
