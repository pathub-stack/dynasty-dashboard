# Database setup and write functions live here.
# app.py will eventually read FROM this database instead of calling the
# Sleeper API directly -- database.py is what fills it in the first place.

import sqlite3

from sleeper import get_league_users, get_league_rosters, TEST_LEAGUE_ID

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
