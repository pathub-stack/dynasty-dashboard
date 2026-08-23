# The Flask web app -- turns dynasty.db's tables into pages a browser can
# load. This queries the database directly; it never calls the Sleeper API
# itself. Keeping data refresh (sleeper.py -> database.py) and data serving
# (this file) separate means a slow/down Sleeper API can't slow down or
# crash a page load -- the dashboard just serves whatever's already in
# dynasty.db until the next refresh happens.

import sqlite3
from datetime import datetime, timezone

from flask import Flask, render_template, request

from database import DB_NAME, create_tables

app = Flask(__name__)

# create_tables() is IF NOT EXISTS, so this is safe every time the app
# starts (dev reload, or a fresh process on Render) -- it's what actually
# makes sure page_visits (and every other table) exists before any route
# or the before_request hook below tries to write to it.
create_tables()


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
    return render_template("index.html")


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


if __name__ == "__main__":
    app.run(debug=True)
