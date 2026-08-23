# All calls to the Sleeper API live in this file.
# Every other script (calculations.py, app.py) will import functions from here
# instead of calling requests.get() directly — one place to change if the API changes.

import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

# Before swapping calls over from TEST_LEAGUE_ID to LEAGUE_ID: delete
# dynasty.db and re-run database.py to rebuild it fresh (see CLAUDE.md's
# Pre-Release Checklist for why -- roster_id isn't unique across leagues).
LEAGUE_ID = "1364983086189649920"
TEST_LEAGUE_ID = "1195237157114392576"
BASE_URL = "https://api.sleeper.app/v1"

# Sleeper's /players/nfl endpoint returns ~15 MB (every NFL player, not just
# ours) and their docs ask that it not be called more than ~once a day, so
# it gets cached to this file instead of being fetched fresh every call.
PLAYERS_CACHE_FILE = "players_cache.json"
PLAYERS_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def _get_json(url):
    """Shared GET + error handling for every Sleeper API call in this file.

    Every function below calls this instead of requests.get() directly, so
    error handling exists in exactly one place instead of being copy-pasted
    into every function -- same reason get_team_names_by_roster() is the
    one place the users/rosters join happens.

    On failure, logs which URL failed and why, then re-raises. This function
    only handles *logging* the failure -- deciding what to do about it
    (skip this table's refresh, let the whole script stop, etc.) is left to
    the caller, since that's a business decision this file shouldn't make.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        logger.error("Sleeper API call failed: %s", url, exc_info=True)
        raise


def get_league_info(league_id):
    """Return top-level league info, including settings like current week and status."""
    url = f"{BASE_URL}/league/{league_id}"
    return _get_json(url)


def get_league_users(league_id):
    """Return the list of team owners (users) in a Sleeper league."""
    url = f"{BASE_URL}/league/{league_id}/users"
    return _get_json(url)


def get_league_matchups(league_id, week):
    """Return all matchup entries for a given week (one entry per roster)."""
    url = f"{BASE_URL}/league/{league_id}/matchups/{week}"
    return _get_json(url)


def get_league_rosters(league_id):
    """Return all rosters in a league — the roster_id -> owner_id mapping."""
    url = f"{BASE_URL}/league/{league_id}/rosters"
    return _get_json(url)


def get_league_transactions(league_id, week):
    """Return all transactions (waivers, free agent adds, trades) for a given week."""
    url = f"{BASE_URL}/league/{league_id}/transactions/{week}"
    return _get_json(url)


def get_all_players():
    """Return Sleeper's full NFL player dictionary (player_id -> player info).

    Every other function in this file hits the API fresh every call -- this
    one is the exception, because the payload is huge and Sleeper explicitly
    asks callers not to hammer it. So instead of a plain requests.get(), this
    checks a local JSON file first (like a cached materialized view) and
    only refetches from the API when that file is missing or older than
    PLAYERS_CACHE_MAX_AGE_SECONDS.
    """
    cache_is_fresh = (
        os.path.exists(PLAYERS_CACHE_FILE)
        and time.time() - os.path.getmtime(PLAYERS_CACHE_FILE) < PLAYERS_CACHE_MAX_AGE_SECONDS
    )

    if cache_is_fresh:
        with open(PLAYERS_CACHE_FILE, "r") as cache_file:
            return json.load(cache_file)

    url = f"{BASE_URL}/players/nfl"
    players = _get_json(url)

    with open(PLAYERS_CACHE_FILE, "w") as cache_file:
        json.dump(players, cache_file)

    return players


def get_player_names():
    """Return a dict mapping player_id -> full name.

    Kept separate from get_all_players() because every caller so far only
    needs the name, not the other ~40 fields (team, position, injury
    status, etc.) Sleeper returns per player.
    """
    players = get_all_players()
    return {
        player_id: player_info.get("full_name", "Unknown Player")
        for player_id, player_info in players.items()
    }


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
