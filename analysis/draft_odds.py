"""Monte Carlo projection of the rest of the regular season, and what it
means for rookie draft position.

Run from the project root:
    python analysis/draft_odds.py
    python analysis/draft_odds.py --trade "Player Name" --to "team or owner"
    python analysis/draft_odds.py --trade "Player A" --to "bmc3377" --receive "Player B"

The idea in one paragraph: for every remaining regular-season week, each
player on every roster gets a projected score (Sleeper's own weekly
projection, which already knows about byes and injuries). Each team starts
its best projected lineup. We then "play" the week by giving every player a
random actual score built from how wrong projections have been so far this
season, and the higher team score wins. Do that for all remaining weeks,
rank the final standings using the bylaws rules, note where my team's pick
landed, and repeat 10,000 times. The percentages are just
COUNT(*) GROUP BY draft_slot over those 10,000 fake seasons.

This file never writes to dynasty.db and is not used by the Flask app.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import zlib

import numpy as np
import pandas as pd
import requests

# This script lives in analysis/, but sleeper.py and calculations.py live
# one folder up. Python only looks for imports in the script's own folder
# by default, so add the project root to the search path first.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import sleeper  # noqa: E402
from calculations import get_standings  # noqa: E402

LEAGUE_ID = sleeper.LEAGUE_ID
MY_TEAM_DEFAULT = "Poop Island"
POSITIONS = ["QB", "RB", "WR", "TE"]
# Starting lineup: 1 QB, 2 RB, 3 WR, 1 TE, then 3 FLEX from RB/WR/TE.
SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
FLEX_SLOTS = 3
PLAYOFF_TEAMS = 6
# Only use projections at least this big when measuring "how wrong are
# projections". A player projected for 0.5 who scores 8 is a 16x miss,
# and a few of those would blow up the whole distribution.
MIN_PROJ_FOR_CALIBRATION = 5.0

CACHE_DIR = os.path.join(PROJECT_ROOT, "analysis", "cache")
CACHE_MAX_AGE_SECONDS = 6 * 60 * 60


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def cached_get(name, url, params=None):
    """GET a URL, but reuse a saved copy if it's less than 6 hours old.

    Same idea as players_cache.json in sleeper.py. One run of this script
    makes about 30 API calls, and rerunning it for a few trade scenarios
    back to back would otherwise flirt with Sleeper's 90/minute limit.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name + ".json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_MAX_AGE_SECONDS:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def get_projections(season, week):
    """Sleeper's projected half-PPR points for every QB/RB/WR/TE in a week.

    Returns {player_id: projected_points}. Players on bye (or with no
    projection at all) simply aren't in the dict, so .get(pid, 0) treats
    them as 0. That's how byes get handled for free.

    Note: this is an unofficial endpoint (it's what Sleeper's own app uses,
    but it isn't in their public docs), so it could change without notice.
    """
    rows = cached_get(
        f"proj_{season}_{week}",
        f"https://api.sleeper.app/projections/nfl/{season}/{week}",
        params={"season_type": "regular", "position[]": POSITIONS},
    )
    projections = {}
    for row in rows:
        points = (row.get("stats") or {}).get("pts_half_ppr")
        if points is None:
            continue
        status = (row.get("player") or {}).get("injury_status")
        # Players already ruled out get nothing, whatever the projection says.
        if status in ("Out", "IR", "PUP", "Sus", "NA"):
            points = 0.0
        projections[row["player_id"]] = points
    return projections


def get_matchups(week):
    return cached_get(f"matchups_{week}", f"{sleeper.BASE_URL}/league/{LEAGUE_ID}/matchups/{week}")


def get_nfl_state():
    return cached_get("state", f"{sleeper.BASE_URL}/state/nfl")


# ---------------------------------------------------------------------------
# Step 1: how wrong are projections? (calibration)
# ---------------------------------------------------------------------------

def build_calibration(season, completed_weeks, positions_by_id):
    """Compare every past projection to what the player actually scored.

    Builds one row per (week, player) that was on a league roster, like:
        SELECT m.week, m.player_id, p.projected, m.actual
        FROM matchup_player_points m
        JOIN projections p ON p.week = m.week AND p.player_id = m.player_id

    Then keeps the ratio actual / projected per position. A ratio of 1.4
    means "scored 40% more than projected". The simulation later picks
    random ratios out of this pool, which is called bootstrapping: instead
    of assuming scores follow a neat bell curve, we reuse the real misses
    this league's players have actually had this season.
    """
    rows = []
    for week in completed_weeks:
        projections = get_projections(season, week)
        for team in get_matchups(week):
            for pid, actual in (team.get("players_points") or {}).items():
                if pid in projections:
                    rows.append({
                        "week": week,
                        "player_id": pid,
                        "position": positions_by_id.get(pid),
                        "projected": projections[pid],
                        "actual": actual,
                    })

    df = pd.DataFrame(rows)
    df = df[df["projected"] >= MIN_PROJ_FOR_CALIBRATION].copy()
    df["ratio"] = df["actual"] / df["projected"]

    # {position: numpy array of ratios}, the pool each draw comes from.
    pools = {pos: group["ratio"].to_numpy() for pos, group in df.groupby("position")}
    # Fallback for oddballs whose listed position isn't QB/RB/WR/TE (e.g. a
    # "FB" who still gets a projection). Like COALESCE(position_pool, all_pool).
    pools["ALL"] = df["ratio"].to_numpy()
    summary = df.groupby("position").agg(
        samples=("ratio", "size"),
        avg_projected=("projected", "mean"),
        avg_actual=("actual", "mean"),
        median_ratio=("ratio", "median"),
        ratio_spread=("ratio", "std"),
    )
    return pools, summary


# ---------------------------------------------------------------------------
# Step 2: lineups
# ---------------------------------------------------------------------------

def choose_starters(player_ids, projections, positions_by_id):
    """Pick the best projected lineup: what a manager paying attention does.

    Fill QB, RB, RB, WR, WR, WR, TE with the highest projected players at
    each position, then the 3 FLEX spots with the best leftovers. Players
    on bye or ruled out project to 0, so they naturally fall to the bench.
    This is also why the bylaws matter here: benching obvious starters to
    tank isn't allowed, so every team, mine included, gets its best lineup.
    """
    by_position = {pos: [] for pos in POSITIONS}
    for pid in player_ids:
        pos = positions_by_id.get(pid)
        if pos in by_position:
            by_position[pos].append(pid)

    starters, leftovers = [], []
    for pos, count in SLOTS.items():
        ranked = sorted(by_position[pos], key=lambda p: projections.get(p, 0.0), reverse=True)
        starters += ranked[:count]
        if pos != "QB":  # FLEX is RB/WR/TE only, a backup QB can't start there
            leftovers += ranked[count:]
    leftovers.sort(key=lambda p: projections.get(p, 0.0), reverse=True)
    starters += leftovers[:FLEX_SLOTS]
    return starters


def best_possible_total(scores, positions):
    """Max PF for one week: best lineup in hindsight, for every sim at once.

    scores is a 2D array: one row per simulation, one column per player.
    np.sort works down every row at the same time, which is the numpy
    version of a set-based UPDATE instead of a cursor loop.
    """
    n_sims = scores.shape[0]
    total = np.zeros(n_sims)
    leftovers = []
    for pos, count in SLOTS.items():
        cols = scores[:, positions == pos]
        if cols.shape[1] < count:  # not enough players at a position: empty slot = 0
            cols = np.hstack([cols, np.zeros((n_sims, count - cols.shape[1]))])
        ranked = -np.sort(-cols, axis=1)  # sort each row descending
        total += ranked[:, :count].sum(axis=1)
        if pos != "QB":
            leftovers.append(ranked[:, count:])
    flex = np.hstack(leftovers + [np.zeros((n_sims, FLEX_SLOTS))])
    total += (-np.sort(-flex, axis=1))[:, :FLEX_SLOTS].sum(axis=1)
    return total


# ---------------------------------------------------------------------------
# Step 3: simulate
# ---------------------------------------------------------------------------

def simulated_player_scores(pid, week, projection, position, pools, n_sims, seed):
    """n_sims random actual scores for one player in one week.

    Each player-week gets its own random number generator, seeded from the
    player id and week. That means a player's 10,000 simulated games are
    identical whether he's on my roster or traded away, so when comparing
    the "no trade" and "trade" runs, the ONLY thing that differs is which
    team he plays for. (Statisticians call this common random numbers. It
    keeps random noise from looking like a trade effect.)
    """
    if projection <= 0:
        return np.zeros(n_sims)
    rng = np.random.default_rng([seed, week, zlib.crc32(pid.encode())])
    pool = pools.get(position, pools["ALL"])
    return projection * rng.choice(pool, size=n_sims)


def simulate(rosters, standings, schedule, projections_by_week, positions_by_id, pools,
             n_sims, seed):
    """Play out every remaining week n_sims times.

    rosters:  {roster_id: [player_id, ...]} (startable players only)
    standings: {roster_id: {"wins", "losses", "pf", "max_pf"}} as of today
    schedule: {week: [(roster_a, roster_b), ...]}

    Returns three 2D arrays (sims x teams): final wins, pf, max_pf, plus
    the roster_id that each column belongs to.
    """
    team_ids = sorted(rosters)
    col = {rid: i for i, rid in enumerate(team_ids)}
    n_teams = len(team_ids)

    wins = np.tile([standings[r]["wins"] for r in team_ids], (n_sims, 1)).astype(float)
    pf = np.tile([standings[r]["pf"] for r in team_ids], (n_sims, 1)).astype(float)
    max_pf = np.tile([standings[r]["max_pf"] for r in team_ids], (n_sims, 1)).astype(float)

    for week, games in schedule.items():
        projections = projections_by_week[week]
        week_points = np.zeros((n_sims, n_teams))
        for rid in team_ids:
            players = rosters[rid]
            if not players:
                continue
            positions = np.array([positions_by_id.get(p) for p in players])
            scores = np.column_stack([
                simulated_player_scores(p, week, projections.get(p, 0.0),
                                        positions_by_id.get(p), pools, n_sims, seed)
                for p in players
            ])
            starters = set(choose_starters(players, projections, positions_by_id))
            is_starter = np.array([p in starters for p in players])
            week_points[:, col[rid]] = scores[:, is_starter].sum(axis=1)
            max_pf[:, col[rid]] += best_possible_total(scores, positions)

        pf += week_points
        for a, b in games:
            a_won = week_points[:, col[a]] > week_points[:, col[b]]
            wins[:, col[a]] += a_won
            wins[:, col[b]] += ~a_won

    return team_ids, wins, pf, max_pf


# ---------------------------------------------------------------------------
# Step 4: final standings -> draft slot (bylaws rules)
# ---------------------------------------------------------------------------

def draft_slots(team_ids, wins, pf, max_pf):
    """For each simulated season, where does every team pick?

    Bylaws, two different sorts (same two passes as get_standings()):
      1. Playoffs: top 6 by wins, tiebreak higher PF.
      2. Picks 1.01-1.06: the other 6, worst record first, tiebreak LOWER
         Max PF picks earlier.
    Playoff teams get slot 0 here, meaning "1.07-1.12, decided by the
    bracket", since the simulation doesn't play out the playoffs.

    np.lexsort is ORDER BY with several keys. It sorts by the LAST key
    first, so lexsort((pf, wins)) means ORDER BY wins, pf.
    """
    n_sims, n_teams = wins.shape
    slots = np.zeros((n_sims, n_teams), dtype=int)
    for s in range(n_sims):
        playoff_order = np.lexsort((-pf[s], -wins[s]))  # wins DESC, pf DESC
        out = playoff_order[PLAYOFF_TEAMS:]
        pick_order = out[np.lexsort((max_pf[s, out], wins[s, out]))]  # wins ASC, max_pf ASC
        for pick, team_col in enumerate(pick_order, start=1):
            slots[s, team_col] = pick
    return slots


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def find_player(name, names_by_id, player_ids):
    """Case-insensitive name lookup, limited to rostered players."""
    matches = [p for p in player_ids if names_by_id.get(p, "").lower() == name.lower()]
    if not matches:
        matches = [p for p in player_ids if name.lower() in names_by_id.get(p, "").lower()]
    if len(matches) != 1:
        found = ", ".join(names_by_id.get(p, p) for p in matches) or "nobody"
        sys.exit(f"Couldn't pin down one player for '{name}' (matched: {found}).")
    return matches[0]


def find_team(text, teams):
    """Match a team by team name or owner name, case-insensitive."""
    text = text.lower()
    for rid, info in teams.items():
        if text in (info["team_name"].lower(), info["owner_name"].lower()):
            return rid
    for rid, info in teams.items():
        if text in info["team_name"].lower() or text in info["owner_name"].lower():
            return rid
    sys.exit(f"No team matches '{text}'.")


def apply_trade(rosters, my_id, partner_id, send_ids, receive_ids):
    """Return a copy of rosters with players swapped. Original is untouched."""
    new = {rid: list(players) for rid, players in rosters.items()}
    for pid in send_ids:
        new[my_id].remove(pid)
        if partner_id is not None:
            new[partner_id].append(pid)
    for pid in receive_ids:
        owner = next(rid for rid, players in new.items() if pid in players)
        new[owner].remove(pid)
        new[my_id].append(pid)
    return new


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def record_odds(team_ids, wins, team_id, standings, games_left):
    """SELECT final_record, COUNT(*) / total FROM sims GROUP BY final_record"""
    final_wins = wins[:, team_ids.index(team_id)].astype(int)
    counts = pd.Series(final_wins).value_counts(normalize=True).sort_index()
    total_games = standings[team_id]["wins"] + standings[team_id]["losses"] + games_left
    return pd.DataFrame({
        "record": [f"{w}-{total_games - w}" for w in counts.index],
        "chance": counts.to_numpy(),
    })


def slot_odds(team_ids, slots, team_id):
    """Where does this team's pick land? Same GROUP BY idea, on draft slot."""
    counts = pd.Series(slots[:, team_ids.index(team_id)]).value_counts(normalize=True)
    # ORDER BY slot, but with 0 ("made the playoffs") last instead of first.
    counts = counts.sort_index(key=lambda idx: idx.where(idx != 0, 99))
    return pd.DataFrame({
        "slot": ["7-12 (playoffs)" if s == 0 else f"{s}" for s in counts.index],
        "chance": counts.to_numpy(),
    })


def get_owned_picks(my_id):
    """Which picks do I own in the upcoming rookie draft?

    Returns {original_roster_id: [rounds]}. Every round uses the round 1
    order (linear draft, per bylaws), so one slot projection per original
    team covers all of that team's picks I hold.
    """
    with sqlite3.connect(os.path.join(PROJECT_ROOT, "dynasty.db")) as conn:
        rows = conn.execute(
            """SELECT original_roster_id, round FROM draft_picks
               WHERE owner_roster_id = ? AND season = (SELECT MAX(season) FROM draft_picks)
               ORDER BY round""",
            (my_id,),
        ).fetchall()
    owned = {}
    for original, rnd in rows:
        owned.setdefault(original, []).append(rnd)
    return owned


def league_table(team_ids, wins, slots, teams, standings):
    """Everyone's projected wins and odds at the top picks, for context."""
    rows = []
    for i, rid in enumerate(team_ids):
        rows.append({
            "team": teams[rid]["team_name"],
            "now": f'{standings[rid]["wins"]}-{standings[rid]["losses"]}',
            "proj_wins": wins[:, i].mean(),
            "playoffs": (slots[:, i] == 0).mean(),
            "1.01": (slots[:, i] == 1).mean(),
            "top_3_pick": ((slots[:, i] >= 1) & (slots[:, i] <= 3)).mean(),
        })
    return pd.DataFrame(rows).sort_values("proj_wins", ascending=False)


def pct(x):
    return f"{x:6.1%}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Project the rest of the season and my draft slot.")
    parser.add_argument("--team", default=MY_TEAM_DEFAULT, help="team or owner name to report on")
    parser.add_argument("--sims", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--trade", nargs="+", default=[], metavar="PLAYER",
                        help="player(s) I send away")
    parser.add_argument("--to", help="team receiving them (leave off to just remove them)")
    parser.add_argument("--receive", nargs="+", default=[], metavar="PLAYER",
                        help="player(s) I get back")
    parser.add_argument("--show-calibration", action="store_true")
    args = parser.parse_args()

    league = sleeper.get_league_info(LEAGUE_ID)
    season = league["season"]
    playoff_start = league["settings"]["playoff_week_start"]
    current_week = get_nfl_state()["week"]
    remaining_weeks = list(range(current_week, playoff_start))
    completed_weeks = list(range(1, current_week))
    if not remaining_weeks:
        sys.exit("Regular season is over, nothing left to simulate.")

    players = sleeper.get_all_players()
    positions_by_id = {pid: p.get("position") for pid, p in players.items()}
    names_by_id = sleeper.get_player_names()

    # Teams + current standings. get_standings() rows are
    # (roster_id, team_name, wins, losses, pf, max_pf).
    # Owner names only live in dynasty.db's teams table (read-only here), so
    # "--to bmc3377" style lookups work on either team or owner name.
    with sqlite3.connect(os.path.join(PROJECT_ROOT, "dynasty.db")) as conn:
        owners = dict(conn.execute("SELECT roster_id, owner_name FROM teams").fetchall())
    standings = {}
    teams = {}
    for rid, team_name, w, l, team_pf, team_max_pf in get_standings(LEAGUE_ID):
        standings[rid] = {"wins": w, "losses": l, "pf": team_pf, "max_pf": team_max_pf}
        teams[rid] = {"team_name": team_name, "owner_name": owners.get(rid, "")}

    # Startable players only: taxi squad and IR (reserve) can't be in a lineup.
    rosters = {}
    for r in sleeper.get_league_rosters(LEAGUE_ID):
        blocked = set(r.get("taxi") or []) | set(r.get("reserve") or [])
        rosters[r["roster_id"]] = [p for p in (r.get("players") or []) if p not in blocked]

    # Remaining schedule: two rosters sharing a matchup_id in a week play each
    # other. Basically a self-join on (week, matchup_id) where a < b.
    schedule = {}
    for week in remaining_weeks:
        by_matchup = {}
        for m in get_matchups(week):
            by_matchup.setdefault(m["matchup_id"], []).append(m["roster_id"])
        schedule[week] = [tuple(pair) for pair in by_matchup.values() if len(pair) == 2]

    projections_by_week = {w: get_projections(season, w) for w in remaining_weeks}
    pools, calibration = build_calibration(season, completed_weeks, positions_by_id)

    my_id = find_team(args.team, teams)
    my_name = teams[my_id]["team_name"]

    print(f"\n{my_name}: currently {standings[my_id]['wins']}-{standings[my_id]['losses']}, "
          f"simulating weeks {remaining_weeks[0]}-{remaining_weeks[-1]} "
          f"({args.sims:,} seasons)")

    if args.show_calibration:
        print("\nHow projections compared to reality, weeks 1-"
              f"{completed_weeks[-1]} (projections of {MIN_PROJ_FOR_CALIBRATION}+ pts):")
        print(calibration.round(2).to_string())

    # Show my projected lineups so the bye/injury handling is visible.
    print("\nMy projected starters by week (bye/out players fall to the bench):")
    for week in remaining_weeks:
        starters = choose_starters(rosters[my_id], projections_by_week[week], positions_by_id)
        total = sum(projections_by_week[week].get(p, 0.0) for p in starters)
        opponent = next(b if a == my_id else a for a, b in schedule[week] if my_id in (a, b))
        print(f"  Wk {week} vs {teams[opponent]['team_name']}: projected {total:.1f}")

    games_left = len(remaining_weeks)
    owned = get_owned_picks(my_id)

    def run(roster_set):
        team_ids, wins, pf, max_pf = simulate(roster_set, standings, schedule, projections_by_week,
                                              positions_by_id, pools, args.sims, args.seed)
        slots = draft_slots(team_ids, wins, pf, max_pf)
        return team_ids, wins, slots

    base = run(rosters)
    after = None

    if args.trade or args.receive:
        all_rostered = [p for players_list in rosters.values() for p in players_list]
        send_ids = [find_player(n, names_by_id, rosters[my_id]) for n in args.trade]
        receive_ids = [find_player(n, names_by_id, all_rostered) for n in args.receive]
        partner_id = find_team(args.to, teams) if args.to else None
        traded = apply_trade(rosters, my_id, partner_id, send_ids, receive_ids)

        sent = ", ".join(names_by_id.get(p, p) for p in send_ids) or "nothing"
        got = ", ".join(names_by_id.get(p, p) for p in receive_ids) or "nothing"
        where = f" to {teams[partner_id]['team_name']}" if partner_id else " (removed from the league)"
        print(f"\nTrade scenario: send {sent}{where}, receive {got}")
        print("My projected lineup totals AFTER the trade:")
        for week in remaining_weeks:
            starters = choose_starters(traded[my_id], projections_by_week[week], positions_by_id)
            total = sum(projections_by_week[week].get(p, 0.0) for p in starters)
            print(f"  Wk {week}: projected {total:.1f}")
        after = run(traded)

    def show(title, key, before_df, after_df):
        """Print one odds table; with a trade, add 'with trade' + change columns.

        The merge is a FULL OUTER JOIN on the key (record or slot), since a
        trade can create outcomes that had 0% before, or remove some.
        """
        print(f"\n{title}")
        if after_df is None:
            for _, r in before_df.iterrows():
                print(f"  {r[key]:>16}  {pct(r['chance'])}")
            return
        merged = before_df.merge(after_df, on=key, how="outer", suffixes=("_now", "_trade")).fillna(0)
        print(f"  {'':>16}  no trade  with trade  change")
        for _, r in merged.iterrows():
            change = r["chance_trade"] - r["chance_now"]
            print(f"  {r[key]:>16}  {pct(r['chance_now'])}    {pct(r['chance_trade'])}   {change:+6.1%}")

    team_ids = base[0]
    show(f"{my_name} final record odds:", "record",
         record_odds(team_ids, base[1], my_id, standings, games_left),
         record_odds(team_ids, after[1], my_id, standings, games_left) if after else None)

    for original_id, rounds in owned.items():
        label = "my own" if original_id == my_id else f"{teams[original_id]['team_name']}'s"
        round_list = ", ".join(str(r) for r in rounds)
        show(f"Draft slot for {label} picks (rounds {round_list}). Every round uses this slot:",
             "slot",
             slot_odds(team_ids, base[2], original_id),
             slot_odds(team_ids, after[2], original_id) if after else None)

    table = league_table(*base, teams, standings)
    print("\nWhole league (no trade):")
    print(table.to_string(index=False, formatters={
        "proj_wins": "{:.1f}".format, "playoffs": pct, "1.01": pct, "top_3_pick": pct}))


if __name__ == "__main__":
    main()
