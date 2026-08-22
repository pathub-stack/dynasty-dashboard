# Database setup and write functions live here.
# app.py will eventually read FROM this database instead of calling the
# Sleeper API directly -- database.py is what fills it in the first place.

import sqlite3

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


if __name__ == "__main__":
    create_tables()
    print(f"Tables created in {DB_NAME}")
