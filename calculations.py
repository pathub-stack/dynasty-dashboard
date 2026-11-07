# Business logic that runs on top of the raw data from sleeper.py:
# survivor pot, start/sit %, high score tracking.

from datetime import datetime
from zoneinfo import ZoneInfo

from sleeper import (
    get_league_info,
    get_league_matchups,
    get_league_rosters,
    get_team_names_by_roster,
    LEAGUE_ID,
)


def get_effective_current_week(league_info):
    """Return the week that's still "in progress" -- i.e. the first week
    NOT yet safe to use for survivor eliminations or high score winners.

    You'd think Sleeper's own "leg" setting (the week currently being
    played) would already be this. It mostly is, except for one gap:
    Monday Night Football is the last game of any week, but Sleeper
    doesn't roll "leg" forward to the next week until Wednesday morning --
    a full day after that week is actually decided. That's not a stat-
    correction safeguard on Sleeper's part either (corrections trickle in
    Tuesday regardless of what "leg" says); it's just Sleeper's own fixed
    weekly cycle running one day behind what the schedule allows.

    So every day except Tuesday, "leg" is already correct as-is. On
    Tuesday specifically, the week "leg" points at has already finished
    (MNF was the night before) even though Sleeper hasn't rolled the
    number forward yet -- so the cutoff gets nudged a week early.

    This is a day-of-week check, not a stat-correction check -- a real
    correction landing Tuesday into Wednesday could still, rarely, flip
    something decided on this dashboard a day before Sleeper itself would
    have shown it. Acceptable for a friends' league dashboard; not
    something to lean on if real money depended on same-day certainty.

    One known edge case this doesn't account for: a handful of weeks
    (Thanksgiving, Christmas) move the "last game of the week" off Monday
    entirely. Not worth special-casing for a 12-team dynasty league --
    worst case those specific weeks are briefly a day later than ideal,
    same as every week was before this fix.
    """
    leg = league_info["settings"]["leg"]
    today_eastern = datetime.now(ZoneInfo("America/New_York"))
    is_tuesday = today_eastern.weekday() == 1  # Monday=0, Tuesday=1
    return leg + 1 if is_tuesday else leg


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

    # get_effective_current_week() is the week NOT yet safe to call final
    # (see its own docstring -- it's "leg", nudged a day early on
    # Tuesdays). One week before that is the last one we can actually
    # call final. Early in the season this can go to 0 (or even negative
    # pre-draft) -- the loop below just won't run, same as before.
    league_info = get_league_info(league_id)
    last_decided_week = get_effective_current_week(league_info) - 1

    # A set of roster_ids still in the running. Sets are like a table with
    # a unique constraint and no ordering — perfect for "who's still alive,"
    # since we only ever check membership or remove entries, never sort it.
    alive = set(team_names_by_roster.keys())

    eliminations = []

    for week in range(1, last_decided_week + 1):
        if len(alive) <= 1:
            break

        matchups = get_league_matchups(league_id, week)

        # Only consider scores from rosters still alive this week.
        alive_scores = [
            (matchup["roster_id"], matchup["points"])
            for matchup in matchups
            if matchup["roster_id"] in alive
        ]

        if not alive_scores:
            # No matchup data for this week yet (the season hasn't reached
            # it, or "leg" points at a week still in progress). Nothing to
            # eliminate, so stop here instead of crashing on an empty min().
            break

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
        # Before the season starts, these keys may not exist on the roster
        # at all yet (not just be zero), so .get() with a 0 fallback covers
        # both cases the same way.
        pf = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100
        max_pf = settings.get("ppts", 0) + settings.get("ppts_decimal", 0) / 100

        roster_id = roster["roster_id"]
        team_name = team_names_by_roster[roster_id]
        # No games played yet means max_pf is 0. There's no meaningful
        # percentage yet, so use 0% instead of dividing by zero.
        start_sit_pct = pf / max_pf if max_pf else 0
        results.append((roster_id, team_name, start_sit_pct, pf, max_pf))

    results.sort(key=lambda result: result[2], reverse=True)
    return results

def get_standings(league_id):
    """Return all teams as standings, best to worst.

    Each row is (roster_id, team_name, wins, losses, pf, max_pf).

    Same pattern as start/sit % -- Sleeper already tracks season-to-date
    wins, losses, PF, and Max PF on each roster's settings, so no need to
    re-derive records from weekly matchups.

    Sorted in two passes, because the top 6 and bottom 6 follow different
    tiebreakers (see BYLAWS.md's Rookie Draft Order):
    - All 12 teams: wins, then PF (total points scored) -- this decides
      who's in the top 6 playoff spots, so a tie straddling the 6/7 line
      is always settled by PF.
    - Bottom 6 only, re-sorted: wins, then Max PF. Lower Max PF ranks
      LOWER here, which means that team picks EARLIER in the rookie draft
      (the draft reads non-playoff teams bottom-up). That's why both sorts
      use reverse=True -- descending on every key, no mixed directions.
    """
    rosters = get_league_rosters(league_id)
    team_names_by_roster = get_team_names_by_roster(league_id)

    results = []
    for roster in rosters:
        settings = roster["settings"]
        wins = settings.get("wins", 0)
        losses = settings.get("losses", 0)
        pf = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100
        max_pf = settings.get("ppts", 0) + settings.get("ppts_decimal", 0) / 100

        roster_id = roster["roster_id"]
        team_name = team_names_by_roster[roster_id]
        results.append((roster_id, team_name, wins, losses, pf, max_pf))

    results.sort(key=lambda result: (result[2], result[4]), reverse=True)
    top_six = results[:6]
    bottom_six = results[6:]
    bottom_six.sort(key=lambda result: (result[2], result[5]), reverse=True)
    return top_six + bottom_six


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

    # Same reasoning as get_survivor_results() -- see
    # get_effective_current_week()'s docstring for why this isn't simply
    # "leg - 1".
    league_info = get_league_info(league_id)
    last_decided_week = get_effective_current_week(league_info) - 1

    weekly_highs = []
    for week in range(1, last_decided_week + 1):
        matchups = get_league_matchups(league_id, week)

        if not matchups:
            # Same reasoning as get_survivor_results(): no data for this
            # week yet, so stop instead of crashing on an empty max().
            break

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
    eliminations, survivors = get_survivor_results(LEAGUE_ID)

    print("--- Survivor Pot ---")
    for week, roster_id, team_name, points in eliminations:
        print(f"Week {week}: {team_name} eliminated ({points} pts)")

    survivor_names = [team_name for roster_id, team_name in survivors]
    if len(survivor_names) == 1:
        print(f"\nSurvivor: {survivor_names[0]}")
    else:
        print(f"\nSurvivor pot split between: {', '.join(survivor_names)}")

    print("\n--- Start/Sit % Leaderboard ---")
    start_sit_results = get_start_sit_percentages(LEAGUE_ID)
    for rank, (roster_id, team_name, pct, pf, max_pf) in enumerate(start_sit_results, start=1):
        print(f"{rank}. {team_name} - {pct:.2%} ({pf} / {max_pf})")

    print("\n--- Season High Score Leaderboard ---")
    season_high_scores = get_season_high_scores(LEAGUE_ID)
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
    faab_results = get_faab_spending(LEAGUE_ID)
    for rank, (team_name, spent, remaining) in enumerate(faab_results, start=1):
        print(f"{rank}. {team_name} - ${spent} spent, ${remaining} remaining")

    print("\n--- Standings ---")
    standings = get_standings(LEAGUE_ID)
    for rank, (roster_id, team_name, wins, losses, pf, max_pf) in enumerate(standings, start=1):
        print(f"{rank}. {team_name} - {wins}-{losses} - {pf} PF - {max_pf} max PF")
