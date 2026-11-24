# Business logic that runs on top of the raw data from sleeper.py:
# survivor pot, start/sit %, high score tracking.

from datetime import datetime
from zoneinfo import ZoneInfo

from sleeper import (
    get_league_info,
    get_league_matchups,
    get_league_rosters,
    get_team_names_by_roster,
    get_traded_picks,
    get_draft,
    get_winners_bracket,
    LEAGUE_ID,
)


def draft_priority_key(wins, max_pf, pf):
    """Sort key for rookie draft order between teams in the same group.

    Sorting ascending by this key puts the EARLIEST pick first. Per
    BYLAWS.md (Rookie Supplemental Drafts):
    1. Worse record picks earlier (fewer wins first).
    2. Tied record: lower Max PF picks earlier.
    3. Tied record AND Max PF: HIGHER total PF picks earlier (so the team
       that set better lineups isn't the one punished).

    Rules 1 and 2 are ascending, but rule 3 runs the other way. In SQL
    that's just ORDER BY wins ASC, max_pf ASC, pf DESC, since every column
    gets its own direction. Python's sort only has one reverse flag for
    the whole key, so the trick is to negate the column that goes the
    other way: sorting -pf ascending is the same as sorting pf descending.
    """
    return (wins, max_pf, -pf)


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
    tiebreakers (see the draft order table under BYLAWS.md's Rookie
    Supplemental Drafts):
    - All 12 teams: wins, then PF (total points scored) -- this decides
      who's in the top 6 playoff spots, so a tie straddling the 6/7 line
      is always settled by PF.
    - Bottom 6 only, re-sorted: wins, then Max PF, then PF, using
      draft_priority_key(). Lower Max PF ranks LOWER here, which means
      that team picks EARLIER in the rookie draft (the draft reads
      non-playoff teams bottom-up). If record and Max PF are both tied,
      the team with HIGHER PF ranks lower and picks earlier.
      draft_priority_key() sorts earliest pick first, so reverse=True
      flips it to "best to worst" like the rest of the list.
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
    # result[2] = wins, result[5] = max_pf, result[4] = pf. reverse=True
    # turns "earliest pick first" into "best team first", so the LAST row
    # here (rank 12) is the team that picks 1.01.
    bottom_six.sort(
        key=lambda result: draft_priority_key(result[2], result[5], result[4]),
        reverse=True,
    )
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


def get_target_draft_season(league_id):
    """Return the season of the next rookie draft to show on the board."""

    # 1. Get the league info (function already exists)
    league_info = get_league_info(league_id)

    # 2. Pull out two things from it: the season, and the main draft's id
    #    (keys: "season" and "draft_id")
    season = int(league_info["season"])
    draft_id = league_info["draft_id"]

    # 3. Fetch that draft with your new get_draft()
    current_draft = get_draft(draft_id)

    # 4. If the draft's "status" is "complete", the target is next season.
    #    Otherwise it's this season.
    status = current_draft["status"]

    if status == "complete":
        target_draft = season + 1 
        return target_draft

    else:
        target_draft = season
        return target_draft


def get_pick_ownership(league_id, season):
    """Return (season, round, original_roster_id, owner_roster_id) for every pick in one draft."""

    # 1. Get the list of rosters (hint: a function that already exists in sleeper.py)

    rosters = get_league_rosters(league_id)

    # 2. Get the number of draft rounds from the league info
    #    (it lives at league_info["settings"]["draft_rounds"])

    league_info = get_league_info(league_id)
    draft_rounds = league_info["settings"]["draft_rounds"]

    # 3. Make an empty dict for the grid
    grid = {} 

    # 4. Loop over every round, and inside that, loop over every roster.
    #    Put each pick in the grid: key = (round, roster_id), value = roster_id
    #    (everyone owns their own picks to start)
    for round_number in range(1, draft_rounds + 1):
        for roster in rosters:
            roster_id = roster["roster_id"]
            grid[(round_number, roster_id)] = roster_id
    # 5. Get the traded picks
    traded_picks = get_traded_picks(league_id)

    # 6. Loop over the traded picks. Skip any whose season isn't ours
    #    (remember: '2027' vs 2027). For the rest, overwrite the grid
    #    entry with the new owner_id.
    for pick in traded_picks:
        if int(pick["season"]) == season:
            grid[(pick["round"], pick["roster_id"])] = pick["owner_id"]

    # 7. Build the list of tuples from the grid and return it
    picks = []
    for key, owner in grid.items():
        round_number, original_roster_id = key 
        picks.append((season, round_number, original_roster_id, owner))
    return picks


def build_draft_order(standings, bracket, regular_season_over, playoff_teams=6):
    """Turn standings + the playoff bracket into rookie draft slots.

    This is the pure "math" half of get_draft_order(): it never calls the
    Sleeper API, it only works on what's passed in. That split is what
    makes it testable, since you can hand it a made-up bracket (say, only
    round 1 finished) and check the answer without waiting for real games.

    standings: get_standings() output, best to worst, rows of
        (roster_id, team_name, wins, losses, pf, max_pf).
    bracket: get_winners_bracket() output (a list of game dicts).
    regular_season_over: True once no regular season week is left to play.
    playoff_teams: how many teams make the playoffs (6 in this league).

    Returns a list of (roster_id, slot, projected) tuples sorted by slot,
    where slot 1 is pick 1.01. projected is True when that slot can still
    change, False when it's locked in.
    """
    num_teams = len(standings)
    first_playoff_slot = num_teams - playoff_teams + 1  # 7 in a 12 team, 6 playoff league

    # Like building a lookup table keyed on roster_id, so the tiebreak
    # stats can be fetched for any team without re-scanning standings.
    priority_by_roster = {
        roster_id: draft_priority_key(wins, max_pf, pf)
        for roster_id, team_name, wins, losses, pf, max_pf in standings
    }

    draft_order = []

    # Non-playoff teams (ranks 7-12): get_standings() already sorted them
    # in bylaws draft order, so the slot is just 13 - rank. They're locked
    # once the regular season is over, since nothing after that changes
    # their record.
    for rank, row in enumerate(standings, start=1):
        if rank > playoff_teams:
            roster_id = row[0]
            draft_order.append((roster_id, num_teams + 1 - rank, not regular_season_over))

    # Playoff teams (ranks 1-6), best first. The set version is for fast
    # "is this team a playoff team?" checks, like WHERE roster_id IN (...).
    playoff_ids = [row[0] for row in standings[:playoff_teams]]
    playoff_id_set = set(playoff_ids)

    # Walk the bracket and sort every decided loser into the round they
    # were knocked out in. losers_by_round is like a GROUP BY round:
    # {1: [9, 3], 2: [7, 10]}.
    losers_by_round = {}
    final_loser = None
    champion = None
    for game in bracket:
        loser = game.get("l")
        if loser is None or loser not in playoff_id_set:
            # Not played yet (or, defensively, a team the bracket and our
            # standings disagree on, so it can't get two slots).
            continue
        if game.get("p") == 1:
            # The championship game: loser picks 11, winner picks 12.
            final_loser = loser
            champion = game.get("w")
        elif "p" in game:
            # 3rd and 5th place games don't affect the draft (bylaws), and
            # their losers were already counted when they were knocked out.
            continue
        else:
            losers_by_round.setdefault(game["r"], []).append(loser)

    # Eliminated teams in slot order: earlier rounds first, and within a
    # round, the same tiebreak as the non-playoff teams (worst record
    # first, then lower Max PF, then higher PF).
    eliminated = []
    for round_number in sorted(losers_by_round):
        eliminated += sorted(losers_by_round[round_number], key=lambda rid: priority_by_roster[rid])
    if final_loser is not None:
        eliminated.append(final_loser)
    if champion is not None:
        eliminated.append(champion)

    # Teams still alive take whatever slots are left, as a projection:
    # worst seed first, so the 1 seed is projected to pick last (1.12).
    eliminated_set = set(eliminated)
    still_alive = [rid for rid in reversed(playoff_ids) if rid not in eliminated_set]

    slot = first_playoff_slot
    for roster_id in eliminated:
        draft_order.append((roster_id, slot, False))
        slot += 1
    for roster_id in still_alive:
        draft_order.append((roster_id, slot, True))
        slot += 1

    draft_order.sort(key=lambda row: row[1])
    return draft_order


def get_draft_order(league_id):
    """Return the rookie draft order as (roster_id, slot, projected) tuples.

    Always 12 rows (one per team), sorted by slot, slot an int 1-12 where
    1 means pick 1.01. projected is True while that team's slot can still
    move, False once it's final. Per BYLAWS.md (Rookie Supplemental Drafts):
    - Slots 1-6: non-playoff teams, worst record first (tiebreaks in
      draft_priority_key()). Projected until the regular season ends.
    - Slots 7-12: playoff teams, by how far they got in the main bracket.
      The consolation and 3rd/5th place games don't count.

    This function only gathers the data (API calls); the actual logic lives
    in build_draft_order() so it can be tested with a made-up bracket.
    The 1.13 compensatory pick isn't included here, it's a separate thing.
    """
    standings = get_standings(league_id)
    league_info = get_league_info(league_id)
    bracket = get_winners_bracket(league_id) or []  # None before the bracket exists

    settings = league_info["settings"]
    # Read from league settings instead of hardcoding 6, in case the
    # league ever votes to change the playoff size.
    playoff_teams = settings.get("playoff_teams", 6)

    # The regular season is over once the "current" week is a playoff
    # week. get_effective_current_week() is "leg" adjusted for Sleeper's
    # Tuesday lag (see its docstring). The status check covers the
    # offseason, when "leg" may no longer mean anything useful.
    regular_season_over = (
        league_info["status"] in ("post_season", "complete")
        or get_effective_current_week(league_info) >= settings["playoff_week_start"]
    )

    return build_draft_order(standings, bracket, regular_season_over, playoff_teams)

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

    print("\n--- 2027 Pick Ownership ---")
    for season, round_number, original, owner in get_pick_ownership(LEAGUE_ID, 2027):
        print(round_number, original, owner)

    print("\n--- Upcoming Draft ---")
    print(get_target_draft_season(LEAGUE_ID))

    print("\n--- Rookie Draft Order ---")
    team_names_by_roster = get_team_names_by_roster(LEAGUE_ID)
    for roster_id, slot, projected in get_draft_order(LEAGUE_ID):
        projected_note = " (projected)" if projected else ""
        print(f"1.{slot:02d}: {team_names_by_roster[roster_id]}{projected_note}")
    
