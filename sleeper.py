# All calls to the Sleeper API live in this file.
# Every other script (calculations.py, app.py) will import functions from here
# instead of calling requests.get() directly — one place to change if the API changes.

import requests

# Before swapping calls over from TEST_LEAGUE_ID to LEAGUE_ID: delete
# dynasty.db and re-run database.py to rebuild it fresh (see CLAUDE.md's
# Pre-Release Checklist for why -- roster_id isn't unique across leagues).
LEAGUE_ID = "1364983086189649920"
TEST_LEAGUE_ID = "1195237157114392576"
BASE_URL = "https://api.sleeper.app/v1"


def get_league_info(league_id):
    """Return top-level league info, including settings like current week and status."""
    url = f"{BASE_URL}/league/{league_id}"
    response = requests.get(url)
    return response.json()


def get_league_users(league_id):
    """Return the list of team owners (users) in a Sleeper league."""
    url = f"{BASE_URL}/league/{league_id}/users"
    response = requests.get(url)
    return response.json()


def get_league_matchups(league_id, week):
    """Return all matchup entries for a given week (one entry per roster)."""
    url = f"{BASE_URL}/league/{league_id}/matchups/{week}"
    response = requests.get(url)
    return response.json()


def get_league_rosters(league_id):
    """Return all rosters in a league — the roster_id -> owner_id mapping."""
    url = f"{BASE_URL}/league/{league_id}/rosters"
    response = requests.get(url)
    return response.json()


def get_team_names_by_roster(league_id):
    """Return a dict mapping roster_id -> team name, joined across users + rosters.

    Every other calculation (scores, survivor, start/sit %) needs to turn a
    roster_id into a human-readable team name, so this join lives here once
    instead of getting rebuilt in every script that needs it.
    """
    users = get_league_users(league_id)
    rosters = get_league_rosters(league_id)

    team_names_by_owner = {}
    for user in users:
        team_names_by_owner[user["user_id"]] = user["metadata"].get(
            "team_name", user["display_name"]
        )

    team_names_by_roster = {}
    for roster in rosters:
        owner_id = roster["owner_id"]
        team_names_by_roster[roster["roster_id"]] = team_names_by_owner[owner_id]

    return team_names_by_roster


if __name__ == "__main__":
    week = 1
    team_names_by_roster = get_team_names_by_roster(TEST_LEAGUE_ID)
    matchups = get_league_matchups(TEST_LEAGUE_ID, week)

    scores = []
    for matchup in matchups:
        team_name = team_names_by_roster[matchup["roster_id"]]
        scores.append((team_name, matchup["points"]))

    scores.sort(key=lambda team_score: team_score[1], reverse=True)

    print(f"--- Week {week} Scores ---")
    for rank, (team_name, points) in enumerate(scores, start=1):
        print(f"{rank}. {team_name} - {points}")
