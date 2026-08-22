# Database setup and write functions live here.
# app.py will eventually read FROM this database instead of calling the
# Sleeper API directly -- database.py is what fills it in the first place.

import sqlite3

from sleeper import (
    get_league_users,
    get_league_rosters,
    get_league_info,
    get_league_matchups,
    TEST_LEAGUE_ID,
)
from calculations import get_survivor_results, get_start_sit_percentages

DB_NAME = "dynasty.db"


def get_connection():
    """Open a connection to the SQLite database file.

    SQLite is just a single file on disk (dynasty.db) -- there's no server
    to log into like a real SQL Server instance. This connection is our
    "session" against that file, same idea as connecting to a database
    before you can run any queries.
    """
    return sqlite3.connect(DB_NAME)


def create_tables():
    """Create all tables if they don't already exist.

    Safe to run every time the app starts -- IF NOT EXISTS means it's a
    no-op if the tables are already there, instead of erroring out.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            roster_id INTEGER PRIMARY KEY,
            team_name TEXT,
            owner_name TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_scores (
            roster_id INTEGER,
            week INTEGER,
            points REAL,
            PRIMARY KEY (roster_id, week),
            FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS survivor_status (
            roster_id INTEGER PRIMARY KEY,
            week_eliminated INTEGER,
            FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faab_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roster_id INTEGER,
            week INTEGER,
            player TEXT,
            amount_spent INTEGER,
            FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS start_sit (
            roster_id INTEGER,
            week INTEGER,
            pf REAL,
            max_pf REAL,
            percentage REAL,
            PRIMARY KEY (roster_id, week),
            FOREIGN KEY (roster_id) REFERENCES teams(roster_id)
        )
    """)

    # Nothing is actually saved to the file until you commit -- same idea
    # as COMMIT in SQL Server. Everything above happens inside one
    # transaction.
    connection.commit()
    connection.close()


def insert_teams(league_id):
    """Pull team + owner info from Sleeper and write it into the teams table.

    Uses INSERT OR REPLACE so this is safe to re-run any time (e.g. once a
    week) -- each roster_id just gets overwritten with fresh data instead
    of erroring because the row already exists. Same idea as a SQL
    MERGE/upsert.
    """
    users = get_league_users(league_id)
    rosters = get_league_rosters(league_id)

    # Same "chase the id through a lookup table" pattern as sleeper.py's
    # get_team_names_by_roster(), except we need TWO things off each user
    # (team name AND owner display name), so we build both dicts here
    # instead of reusing that function.
    team_name_by_owner = {}
    owner_name_by_owner = {}
    for user in users:
        owner_name_by_owner[user["user_id"]] = user["display_name"]
        team_name_by_owner[user["user_id"]] = user["metadata"].get(
            "team_name", user["display_name"]
        )

    connection = get_connection()
    cursor = connection.cursor()

    for roster in rosters:
        roster_id = roster["roster_id"]
        owner_id = roster["owner_id"]

        cursor.execute(
            """
            INSERT OR REPLACE INTO teams (roster_id, team_name, owner_name)
            VALUES (?, ?, ?)
            """,
            (roster_id, team_name_by_owner[owner_id], owner_name_by_owner[owner_id]),
        )

    connection.commit()
    connection.close()


def insert_weekly_scores(league_id):
    """Pull every played week's matchup scores and write them into weekly_scores.

    Sleeper's matchups endpoint is per-week (get_league_matchups needs a
    week number), so unlike insert_teams this has to loop and make one API
    call per week instead of one call total.
    """
    league_info = get_league_info(league_id)

    # "leg" is Sleeper's field name for the most recent completed/current
    # week -- same field calculations.py uses for this.
    last_played_week = league_info["settings"]["leg"]

    connection = get_connection()
    cursor = connection.cursor()

    for week in range(1, last_played_week + 1):
        matchups = get_league_matchups(league_id, week)

        for matchup in matchups:
            cursor.execute(
                """
                INSERT OR REPLACE INTO weekly_scores (roster_id, week, points)
                VALUES (?, ?, ?)
                """,
                (matchup["roster_id"], week, matchup["points"]),
            )

    connection.commit()
    connection.close()


def insert_survivor_status(league_id):
    """Run the survivor pot simulation and write each team's status.

    Reuses get_survivor_results() from calculations.py instead of
    re-implementing the elimination/tie logic here -- that logic already
    has a subtle rule (ties eliminate everyone tied, not just one team),
    so it should only exist in one place.

    week_eliminated is left NULL for teams still alive, matching the
    schema comment in the table itself.
    """
    eliminations, survivors = get_survivor_results(league_id)

    connection = get_connection()
    cursor = connection.cursor()

    for week, roster_id, _team_name, _points in eliminations:
        cursor.execute(
            """
            INSERT OR REPLACE INTO survivor_status (roster_id, week_eliminated)
            VALUES (?, ?)
            """,
            (roster_id, week),
        )

    for roster_id, _team_name in survivors:
        cursor.execute(
            """
            INSERT OR REPLACE INTO survivor_status (roster_id, week_eliminated)
            VALUES (?, NULL)
            """,
            (roster_id,),
        )

    connection.commit()
    connection.close()


def insert_start_sit(league_id):
    """Snapshot each team's season-to-date PF / Max PF / start-sit % and
    write it into start_sit, tagged with the most recently played week.

    Sleeper only exposes PF/Max PF as running season totals, not a
    per-week history, so each call here writes ONE row per team for
    "as of this week." Since start_sit's primary key is (roster_id, week),
    re-running this every week (rather than overwriting the same row)
    naturally builds up a real week-by-week history over the season.
    """
    league_info = get_league_info(league_id)
    current_week = league_info["settings"]["leg"]

    start_sit_results = get_start_sit_percentages(league_id)

    connection = get_connection()
    cursor = connection.cursor()

    for roster_id, _team_name, percentage, pf, max_pf in start_sit_results:
        cursor.execute(
            """
            INSERT OR REPLACE INTO start_sit (roster_id, week, pf, max_pf, percentage)
            VALUES (?, ?, ?, ?, ?)
            """,
            (roster_id, current_week, pf, max_pf, percentage),
        )

    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_tables()
    print(f"Tables created in {DB_NAME}")

    insert_teams(TEST_LEAGUE_ID)
    print("Teams inserted")

    # Quick sanity check -- read back what actually landed in the table.
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT roster_id, team_name, owner_name FROM teams")
    for row in cursor.fetchall():
        print(row)
    connection.close()

    insert_weekly_scores(TEST_LEAGUE_ID)
    print("Weekly scores inserted")

    # Sanity check -- just week 1, so the output stays readable.
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT roster_id, week, points FROM weekly_scores WHERE week = 1"
    )
    for row in cursor.fetchall():
        print(row)
    connection.close()

    insert_start_sit(TEST_LEAGUE_ID)
    print("Start/sit % inserted")

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT teams.team_name, start_sit.week, start_sit.pf,
               start_sit.max_pf, start_sit.percentage
        FROM start_sit
        JOIN teams ON teams.roster_id = start_sit.roster_id
        ORDER BY start_sit.percentage DESC
    """)
    for row in cursor.fetchall():
        print(row)
    connection.close()

    insert_survivor_status(TEST_LEAGUE_ID)
    print("Survivor status inserted")

    # Sanity check -- JOIN back to teams so this prints team names instead
    # of raw roster_ids. "week_eliminated IS NULL" as a sort key sorts
    # False (0) before True (1), so eliminated teams show in elimination
    # order and the still-alive survivor(s) print last.
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT teams.team_name, survivor_status.week_eliminated
        FROM survivor_status
        JOIN teams ON teams.roster_id = survivor_status.roster_id
        ORDER BY survivor_status.week_eliminated IS NULL, survivor_status.week_eliminated
    """)
    for row in cursor.fetchall():
        print(row)
    connection.close()
