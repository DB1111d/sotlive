"""
fetch_ncaa_basketball.py
Fetches men's college basketball schedules using ESPN's JSON API.
Mirrors the structure and error-handling of fetch_schedule.py.

Sorting behavior:
  - Regular season / conference tournaments → group by conference
  - NCAA Tournament games → group by round (First Round, Sweet 16, etc.)
  Both modes sort by tip-off time within each group.

TBD teams are handled cleanly — unset bracket slots show as "TBD".
Writes output to ncaa_basketball.json.
"""

import json
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ─── Configuration ────────────────────────────────────────────────────────────

DAYS_AHEAD   = 5
TIMEZONE     = ZoneInfo("America/New_York")
WINDOW_HOURS = 4  # Hours after tip-off before a game is removed from Today's tab

# ESPN API endpoint — groups=50 (all D-I), limit=500 (every game)
# Men's only — women's college basketball uses a separate ESPN slug
# (womens-college-basketball) which this script never calls
ESPN_NCAA_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/scoreboard?groups=50&limit=500&dates={date_str}"
)

# Broadcaster → badge label (mirrors ESPN_SOURCE_MAP in fetch_schedule.py)
ESPN_SOURCE_MAP = {
    "ESPN":                    "ESPN",
    "ESPN2":                   "ESPN2",
    "ESPN+":                   "ESPN+",
    "ESPNU":                   "ESPN+",
    "ESPNEWS":                 "ESPN+",
    "Hulu":                    "Hulu",
    "ABC":                     "ABC",
    "CBS":                     "CBS",
    "Paramount+":              "Paramount+",
    "CBS Sports Network":      "CBS",
    "CBSSN":                   "CBS",
    "HBO Max":                 "HBO Max",
    "Max":                     "Max",
    "TNT":                     "TNT",
    "TBS":                     "TBS",
    "truTV":                   "truTV",
    "TruTV":                   "truTV",
    "Peacock":                 "Peacock",
    "NBC":                     "NBC",
    "USA Net":                 "USA Network",
    "NBCSN":                   "NBC",
    "FOX":                     "FOX",
    "FS1":                     "FS1",
    "FS2":                     "FS2",
    "Apple TV":                "Apple TV",
    "YouTube":                 "YouTube",
    "YouTube TV":              "YouTube",
    "NBA TV":                  "NBA TV",
    "NHL Net":                 "NHL Network",
    "NHL Network":             "NHL Network",
}

# Spanish-language broadcasters to always exclude — no exceptions
SPANISH_EXCLUDE = {
    "universo", "telemundo", "tele", "espn deportes",
    "univision", "fox deportes", "tudn", "nbc universo",
    "espn deportes+", "cnn en español", "univision deportes",
}

# Non-time statuses — mirrors fetch_schedule.py
NON_STATUSES = {
    "STATUS_POSTPONED": "Postponed",
    "STATUS_CANCELED":  "Canceled",
    "STATUS_DELAYED":   "Delayed",
    "STATUS_SUSPENDED": "Suspended",
}

# ESPN season type names / slugs that indicate NCAA Tournament or NIT
NCAA_TOURNEY_SEASON_TYPES = {
    "postseason", "post-season", "ncaa tournament",
    "ncaa men's basketball tournament",
}

# Keywords that identify specifically the NCAA Tournament (not NIT)
NCAA_TOURNEY_KEYWORDS = {
    "ncaa tournament", "ncaa men's basketball tournament",
    "march madness",
}

# Keywords that identify the NIT
NIT_KEYWORDS = {
    "nit", "national invitation tournament",
}

# ESPN slugs / headline keywords → clean round label (NCAA Tournament)
TOURNEY_ROUND_MAP = {
    "first-four":            "First Four",
    "first-round":           "First Round",
    "round-of-64":           "First Round",
    "round-of-32":           "Round of 32",
    "second-round":          "Round of 32",
    "sweet-16":              "Sweet 16",
    "sweet16":               "Sweet 16",
    "elite-eight":           "Elite Eight",
    "elite8":                "Elite Eight",
    "final-four":            "Final Four",
    "final4":                "Final Four",
    "semifinal":             "Final Four",
    "semifinals":            "Final Four",
    "national-championship": "National Championship",
    "championship":          "National Championship",
    "final":                 "National Championship",
}

# NIT round keywords → clean round label
NIT_ROUND_MAP = {
    "first-round":    "NIT First Round",
    "first round":    "NIT First Round",
    "second-round":   "NIT Second Round",
    "second round":   "NIT Second Round",
    "quarterfinal":   "NIT Quarterfinals",
    "semifinal":      "NIT Semifinals",
    "final":          "NIT Final",
    "championship":   "NIT Final",
}

# Display order for tournament rounds
TOURNEY_ROUND_ORDER = [
    "First Four",
    "First Round",
    "Round of 32",
    "Sweet 16",
    "Elite Eight",
    "Final Four",
    "National Championship",
]

# ESPN conferenceId → conference name
# These are ESPN's internal numeric IDs for each D-I conference
CONFERENCE_ID_MAP = {
    1:   "ACC",
    2:   "Big East",
    3:   "Big 12",
    4:   "Pac-12",
    5:   "Big Ten",
    6:   "SEC",
    7:   "American Athletic",
    8:   "Mountain West",
    9:   "Missouri Valley",
    10:  "West Coast",
    11:  "Atlantic 10",
    12:  "Conference USA",
    13:  "MAC",
    14:  "Sun Belt",
    15:  "Big Sky",
    16:  "Big South",
    17:  "Big West",
    18:  "CAA",
    19:  "Horizon",
    20:  "Ivy League",
    21:  "MAAC",
    22:  "MEAC",
    23:  "NEC",
    24:  "OVC",
    25:  "Patriot",
    26:  "Pioneer",
    27:  "Southern",
    28:  "Southland",
    29:  "SWAC",
    30:  "Summit",
    31:  "WAC",
    32:  "Big East",
    49:  "America East",
    50:  "Atlantic Sun",
    51:  "Big South",
    52:  "Colonial",
    62:  "WAC",
    63:  "Independent",
}
CONFERENCE_ORDER = [
    "ACC",
    "Big 12",
    "Big Ten",
    "SEC",
    "Pac-12",
    "Big East",
    "American Athletic",
    "Atlantic 10",
    "Mountain West",
    "Missouri Valley",
    "West Coast",
    "Conference USA",
    "MAC",
    "Sun Belt",
    "Big Sky",
    "Big South",
    "Big West",
    "CAA",
    "Horizon",
    "Ivy League",
    "MAAC",
    "MEAC",
    "NEC",
    "OVC",
    "Patriot",
    "Pioneer",
    "Southern",
    "Southland",
    "SWAC",
    "Summit",
    "WAC",
    "Independent",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; SOTLive/1.0)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def date_range(days: int):
    today = datetime.now(TIMEZONE).date()
    for i in range(days):
        d = today + timedelta(days=i)
        yield d, d.strftime("%Y%m%d")


def prune_today_games(games: list) -> list:
    """Remove games that started more than WINDOW_HOURS ago. Mirrors fetch_schedule.py."""
    now  = datetime.now(TIMEZONE)
    kept = []
    for g in games:
        kickoff = None
        if g.get("kick_utc"):
            try:
                kickoff = datetime.fromisoformat(g["kick_utc"].replace("Z", "+00:00"))
                kickoff = kickoff.astimezone(TIMEZONE)
            except Exception:
                pass

        if kickoff is None:
            kept.append(g)
            continue

        cutoff = kickoff + timedelta(hours=WINDOW_HOURS)
        if now <= cutoff:
            kept.append(g)
        else:
            print(f"  Removed past game: {g['time']} {g['match']}")
    return kept


def team_name(competitor: dict) -> str:
    """Return display name, falling back to 'TBD' for unset bracket slots."""
    name = competitor.get("team", {}).get("displayName", "").strip()
    if not name or name.lower() in ("tbd", "tba"):
        return "TBD"
    return name


def conference_sort_key(conf: str) -> int:
    try:
        return CONFERENCE_ORDER.index(conf)
    except ValueError:
        return len(CONFERENCE_ORDER)


def tourney_round_sort_key(round_label: str) -> int:
    try:
        return TOURNEY_ROUND_ORDER.index(round_label)
    except ValueError:
        return len(TOURNEY_ROUND_ORDER)


def parse_tourney_round(event: dict, competition: dict = None) -> str | None:
    """
    Returns 'NIT' or 'NCAA Tournament' for postseason games, None otherwise.
    Uses competition.notes headline — the only reliable ESPN field that
    distinguishes NIT from NCAA Tournament (both have slug='post-season').
    """
    season = event.get("season", {})
    if not isinstance(season, dict):
        season = {}
    if season.get("type") != 3:
        return None
    notes = competition.get("notes", []) if competition else []
    headline = next(
        (n.get("headline", "") for n in notes if isinstance(n, dict)),
        ""
    ).lower()
    if "nit" in headline:
        return "NIT"
    return "NCAA Tournament"


def fetch_ncaa_day(date_str: str) -> list:
    """
    Fetch all D-I men's college basketball games for one date.
    Each game dict includes:
      - conference    (used when tourney_round is None)
      - tourney_round (set only for NCAA Tournament games, None otherwise)
      - time, match, source, kick_utc
    """
    url = ESPN_NCAA_URL.format(date_str=date_str)
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"    API error for NCAA basketball on {date_str}: {e}")
        return []

    games = []
    for event in data.get("events", []):
        try:
            competition = event["competitions"][0]
            competitors = competition.get("competitors", [])
            if len(competitors) < 2:
                continue

            # Teams — TBD for unset bracket slots
            home       = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away       = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
            home_name  = team_name(home)
            away_name  = team_name(away)
            match_title = f"{home_name} vs {away_name}"

            # Skip pure placeholder slots — both TBD with no real time set yet
            if home_name == "TBD" and away_name == "TBD":
                continue

            # NCAA Tournament round detection — None if regular season / conf tourney
            tourney_round = parse_tourney_round(event, competition)


            # Conference — only matters when not in the tournament
            # ESPN stores conference as a numeric conferenceId on the team object
            conference = "Independent"
            if tourney_round is None:
                conf_id = home.get("team", {}).get("conferenceId")
                if conf_id is not None:
                    conference = CONFERENCE_ID_MAP.get(int(conf_id), f"Conference {conf_id}")

            # Time
            raw_date = event.get("date", "")
            if not raw_date:
                continue
            utc_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            et_dt  = utc_dt.astimezone(TIMEZONE)

            # Only include games on the target date
            if et_dt.strftime("%Y%m%d") != date_str:
                continue

            time_str = et_dt.strftime("%-I:%M %p")

            # Non-time statuses — mirrors fetch_schedule.py
            status_name = event.get("status", {}).get("type", {}).get("name", "")
            if status_name in NON_STATUSES:
                games.append({
                    "conference":    conference,
                    "tourney_round": tourney_round,
                    "time":          NON_STATUSES[status_name],
                    "match":         match_title,
                    "source":        "",
                    "kick_utc":      raw_date,
                    "home_logo":     home.get("team", {}).get("logo", ""),
                    "away_logo":     away.get("team", {}).get("logo", ""),
                })
                continue

            # Broadcaster — same dual-fallback logic as fetch_schedule.py
            broadcasts   = competition.get("geoBroadcasts", [])
            source_names = []
            for b in broadcasts:
                if not isinstance(b, dict):
                    continue
                media = b.get("media", {})
                if not isinstance(media, dict):
                    continue
                short = media.get("shortName", "")
                lang  = b.get("lang", "en")
                if lang != "en":
                    continue
                if short.lower() in SPANISH_EXCLUDE:
                    continue
                mapped = ESPN_SOURCE_MAP.get(short)
                if mapped and mapped not in source_names:
                    source_names.append(mapped)

            # Fallback to broadcasts array
            if not source_names:
                for b in competition.get("broadcasts", []):
                    if not isinstance(b, dict):
                        continue
                    for name in b.get("names", []):
                        if name.lower() in SPANISH_EXCLUDE:
                            continue
                        mapped = ESPN_SOURCE_MAP.get(name)
                        if mapped and mapped not in source_names:
                            source_names.append(mapped)

            # Default to ESPN+ if no broadcaster found
            source = " · ".join(source_names) if source_names else "ESPN+"

            games.append({
                "conference":    conference,
                "tourney_round": tourney_round,
                "time":          time_str,
                "match":         match_title,
                "source":        source,
                "kick_utc":      raw_date,
                "home_logo":     home.get("team", {}).get("logo", ""),
                "away_logo":     away.get("team", {}).get("logo", ""),
            })

        except Exception as e:
            print(f"    Error parsing event: {e}")
            continue

    return games


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    dates     = list(date_range(DAYS_AHEAD))
    today_str = dates[0][1]

    schedule = {}
    for date_obj, date_str in dates:
        schedule[date_str] = {
            "date":  date_obj.strftime("%A, %B %-d"),
            "games": [],
        }

    print("Fetching NCAA Men's Basketball...")
    for date_obj, date_str in dates:
        games = fetch_ncaa_day(date_str)
        if games:
            print(f"  {date_str}: {len(games)} games")
        schedule[date_str]["games"].extend(games)

    # Post-process each day
    ordered = {}
    for _, date_str in dates:
        day = schedule[date_str]

        # Prune stale games from today
        if date_str == today_str:
            day["games"] = prune_today_games(day["games"])

        def sort_key(g):
            tr = g.get("tourney_round")
            if tr == "NCAA Tournament":
                group_pos = 0
            elif tr == "NIT":
                group_pos = 1
            elif tr:
                group_pos = 0
            else:
                # Regular season / conference tournament — sort by conference, then time
                group_pos = 2 + conference_sort_key(g["conference"])

            try:
                t = datetime.strptime(g["time"].strip(), "%I:%M %p")
            except Exception:
                t = datetime.max

            return (group_pos, t)

        day["games"].sort(key=sort_key)
        ordered[date_str] = day

    output = {
        "updated": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M %Z"),
        "days":    ordered,
    }

    with open("ncaa_basketball.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(d["games"]) for d in ordered.values())
    print(f"\nDone! {total} games written to ncaa_basketball.json")


if __name__ == "__main__":
    main()
