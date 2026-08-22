# Business logic that runs on top of the raw data from sleeper.py:
# survivor pot, start/sit %, high score tracking.

from sleeper import (
    get_league_info,
    get_league_matchups,
    get_league_rosters,
    get_team_names_by_roster,
    TEST_LEAGUE_ID,
)


def get_survivor_results(league_id):
    """Simulate the survivor pot week by week.

    Each week, whoever has the lowest score *among teams still alive* is
    eliminated. If multiple teams tie for lowest, ALL of them are
    eliminated that week (per league rule). The pot resolves naturally
    whenever only one team remains -- could be week 8, could run all the
    way through the playoffs, however long it takes. It's the payout
    that happens at end of season, not the elimination process itself.

    Returns a list of (week, roster_id, team_name, points) in the order
    teams were eliminated, plus a list of (roster_id, team_name) for
    whoever's left standing — usually one, but more if the pot ends up
    split. roster_id is included alongside team_name because database.py
    needs it to write rows into survivor_status, which is keyed by
    roster_id, not team name.
    """
    team_names_by_roster = get_team_names_by_roster(league_id)

    # How many weeks this league has actually played -- "leg" is Sleeper's
    # name for the most recent completed/current week.
    league_info = get_league_info(league_id)
    last_played_week = league_info["settings"]["leg"]

    # A set of roster_ids still in the running. Sets are like a table with
    # a unique constraint and no ordering — perfect for "who's still alive,"
    # since we only ever check membership or remove entries, never sort it.
    alive = set(team_names_by_roster.keys())

    eliminations = []

    for week in range(1, last_played_week + 1):
        if len(alive) <= 1:
            break

        matchups = get_league_matchups(league_id, week)

        # Only consider scores from rosters still alive this week.
        alive_scores = [
            (matchup["roster_id"], matchup["points"])
            for matchup in matchups
            if matchup["roster_id"] in alive
        ]

        lowest_points = min(points for roster_id, points in alive_scores)

        # Everyone who matched that lowest score, not just the first one found.
        tied_lowest = [
            roster_id for roster_id, points in alive_scores if points == lowest_points
        ]

        if len(tied_lowest) == len(alive):
            # Every remaining team tied for last -- eliminating "all of them"
            # would leave nobody standing, so treat this as a split pot
            # among whoever's left instead of eliminating anyone.
            break

        for roster_id in tied_lowest:
            alive.remove(roster_id)
            team_name = team_names_by_roster[roster_id]
            eliminations.append((week, roster_id, team_name, lowest_points))

    survivors = [(roster_id, team_names_by_roster[roster_id]) for roster_id in alive]

    return eliminations, survivors


def get_start_sit_percentages(league_id):
    """Return each team's start/sit % (PF / Max PF), highest first.

    Sleeper already tracks season-to-date fpts (points scored) and ppts
    (possible points -- what you'd have scored with a perfect lineup every
    week) on each roster's settings, so no need to re-derive this from
    individual matchups.
    """
    rosters = get_league_rosters(league_id)
    team_names_by_roster = get_team_names_by_roster(league_id)

    results = []
    for roster in rosters:
        settings = roster["settings"]

        # Sleeper splits points into whole-number + decimal (hundredths)
        # fields to avoid floating-point rounding issues in their database.
        pf = settings["fpts"] + settings["fpts_decimal"] / 100
        max_pf = settings["ppts"] + settings["ppts_decimal"] / 100

        roster_id = roster["roster_id"]
        team_name = team_names_by_roster[roster_id]
        start_sit_pct = pf / max_pf
        results.append((roster_id, team_name, start_sit_pct, pf, max_pf))

    results.sort(key=lambda result: result[2], reverse=True)
    return results


def get_season_high_scores(league_id):
    """Return every week's top score, ranked season-wide, highest first.

    This is for the $60 Season High Score payout -- whoever's single best
    week was the highest of the entire season. Weekly High Score ($25/week)
    is a separate, simpler thing: just that week's top scorer.

    If multiple teams tie for the top score *within a week*, all of them
    are included for that week -- BYLAWS.md flags weekly-high ties as still
    undecided, so this surfaces ties instead of silently picking one.

    Returns a list of (week, points, team_names) tuples, sorted so the
    single best week of the season is first.
    """
    team_names_by_roster = get_team_names_by_roster(league_id)

    league_info = get_league_info(league_id)
    last_played_week = league_info["settings"]["leg"]

    weekly_highs = []
    for week in range(1, last_played_week + 1):
        matchups = get_league_matchups(league_id, week)

        top_points = max(matchup["points"] for matchup in matchups)

        # Everyone who hit that week's top score, not just the first one found.
        top_teams = [
            team_names_by_roster[matchup["roster_id"]]
            for matchup in matchups
            if matchup["points"] == top_points
        ]

        weekly_highs.append((week, top_points, top_teams))

    weekly_highs.sort(key=lambda weekly_high: weekly_high[1], reverse=True)
    return weekly_highs


def get_faab_spending(league_id):
    """Return each team's FAAB spending, biggest spender first.

    Same pattern as start/sit % -- Sleeper already tracks season-to-date
    waiver_budget_used directly on each roster, so no need to loop through
    weekly transactions to get a spending total. Total budget is pulled
    from the league's own settings rather than hardcoded, in case it ever
    changes season to season.
    """
    rosters = get_league_rosters(league_id)
    team_names_by_roster = get_team_names_by_roster(league_id)

    league_info = get_league_info(league_id)
    total_budget = league_info["settings"]["waiver_budget"]

    results = []
    for roster in rosters:
        spent = roster["settings"]["waiver_budget_used"]
        remaining = total_budget - spent

        team_name = team_names_by_roster[roster["roster_id"]]
        results.append((team_name, spent, remaining))

    results.sort(key=lambda result: result[1], reverse=True)
    return results


if __name__ == "__main__":
    eliminations, survivors = get_survivor_results(TEST_LEAGUE_ID)

    print("--- Survivor Pot ---")
    for week, roster_id, team_name, points in eliminations:
        print(f"Week {week}: {team_name} eliminated ({points} pts)")

    survivor_names = [team_name for roster_id, team_name in survivors]
    if len(survivor_names) == 1:
        print(f"\nSurvivor: {survivor_names[0]}")
    else:
        print(f"\nSurvivor pot split between: {', '.join(survivor_names)}")

    print("\n--- Start/Sit % Leaderboard ---")
    start_sit_results = get_start_sit_percentages(TEST_LEAGUE_ID)
    for rank, (roster_id, team_name, pct, pf, max_pf) in enumerate(start_sit_results, start=1):
        print(f"{rank}. {team_name} - {pct:.2%} ({pf} / {max_pf})")

    print("\n--- Season High Score Leaderboard ---")
    season_high_scores = get_season_high_scores(TEST_LEAGUE_ID)
    for rank, (week, points, team_names) in enumerate(season_high_scores, start=1):
        teams_display = " & ".join(team_names)
        tie_note = " (TIE)" if len(team_names) > 1 else ""
        print(f"{rank}. Week {week}: {teams_display} - {points}{tie_note}")

    top_week, top_points, top_teams = season_high_scores[0]
    if len(top_teams) == 1:
        print(f"\nSeason High Score winner: {top_teams[0]} (Week {top_week}, {top_points} pts)")
    else:
        print(
            f"\nSeason High Score TIED between {', '.join(top_teams)} "
            f"(Week {top_week}, {top_points} pts) - tiebreaker not decided in BYLAWS.md"
        )

    print("\n--- FAAB Spending Tracker ---")
    faab_results = get_faab_spending(TEST_LEAGUE_ID)
    for rank, (team_name, spent, remaining) in enumerate(faab_results, start=1):
        print(f"{rank}. {team_name} - ${spent} spent, ${remaining} remaining")
