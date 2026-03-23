"""
fetch_schedule.py
Fetches soccer schedules using ESPN's JSON API (no browser required).
Fast, reliable, no Playwright needed.
Writes output to schedule.json.
"""

import json
import re
import unicodedata
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# If ESPN returns one of these instead of a kickoff time, show it as-is with no broadcaster
NON_TIME_STATUSES = {"postponed", "canceled", "cancelled", "suspended", "tbd", "delayed"}

# ─── Configuration ────────────────────────────────────────────────────────────

DAYS_AHEAD = 5
TIMEZONE = ZoneInfo("America/New_York")

# Hours after kickoff before a game is removed from Today's tab
WINDOW_HOURS = 4

# ESPN API league slugs mapped to friendly names
# Format: https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates=YYYYMMDD
ESPN_LEAGUES = {
    "fifa.worldq.uefa":            "World Cup Qualifying",
    "fifa.worldq.concacaf":        "World Cup Qualifying",
    "fifa.worldq.conmebol":        "World Cup Qualifying",
    "fifa.worldq.afc":             "World Cup Qualifying",
    "fifa.worldq.caf":             "World Cup Qualifying",
    "fifa.worldq.ofc":             "World Cup Qualifying",
    "fifa.worldq.concacaf.ofc":    "World Cup Qualifying",
    "fifa.worldq.afc.conmebol":    "World Cup Qualifying",
    "fifa.friendly":               "International Friendly",
    "eng.1":          "Premier League",
    "eng.2":          "EFL Championship",
    "eng.fa":         "English FA Cup",
    "eng.league_cup": "Carabao Cup",
    "esp.1":          "La Liga",
    "ger.1":          "German Bundesliga",
    "ita.1":          "Serie A",
    "ned.1":          "Dutch Eredivisie",
    "usa.1":          "MLS",
    "concacaf.champions": "CONCACAF Champions Cup",
    "usa.open":           "US Open Cup",
    "usa.usl.1":      "USL Championship",
    "usa.usl.l1":     "USL League One",
    "mex.1":          "Liga MX",
    "uefa.champions": "UEFA Champions League",
    "uefa.europa":    "UEFA Europa League",
    # uefa.conference returns 400 — Conference League is fetched via scoreboard scraper
}

# ESPN broadcaster names to map to our badges
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

# Spanish-language broadcasters to always exclude
SPANISH_EXCLUDE = {
    "universo", "telemundo", "tele", "espn deportes",
    "univision", "fox deportes", "tudn"
}

# Leagues where games with NO English broadcaster should be dropped entirely (not defaulted)
ENGLISH_ONLY_LEAGUES = {"Liga MX"}

# Broadcaster names for Premier League (scraped from ESPN scoreboard page)
PL_SOURCE_MAP = {
    "Peacock":   "Peacock",
    "USA Net":   "USA Network",
    "NBC":       "USA Network",
    "NBCSN":     "USA Network",
}

# Spanish-language broadcasters to exclude from PL results
PL_SPANISH_EXCLUDE = {"universo", "telemundo", "tele", "espn deportes", "univision"}

# Broadcaster names for MLS (scraped from ESPN scoreboard page)
MLS_SOURCE_MAP = {
    "Apple TV": "Apple TV",
    "FOX":      "FOX",
    "FS1":      "FS1",
    "FS2":      "FS2",
}

# Spanish-language broadcasters to exclude from MLS results
MLS_SPANISH_EXCLUDE = {"universo", "telemundo", "tele", "espn deportes", "univision", "fox deportes"}

# Keywords to skip (shows, not matches)
SHOW_KEYWORDS = [
    "golazo", "espn fc", "futbol picante", "fútbol picante",
    "goal arena", "konferenz", "pre-show", "post-show",
    "halftime", "studio", "preview", "analysis", "highlights",
]

LEAGUE_ORDER = [
    "World Cup Qualifying",
    "International Friendly",
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Europa Conference League",
    "Premier League",
    "MLS",
    "Carabao Cup",
    "CONCACAF Champions Cup",
    "US Open Cup",
    "English FA Cup",
    "EFL Championship",
    "Serie A",
    "German Bundesliga",
    "La Liga",
    "Dutch Eredivisie",
    "USL Championship",
    "USL League One",
    "Liga MX",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_time_value(s: str) -> bool:
    """Returns True if the string looks like a kickoff time (e.g. '7:30 PM'), False if it's a status."""
    return bool(re.match(r'^\d{1,2}:\d{2}\s*(AM|PM)$', s.strip(), re.IGNORECASE))


STATUS_DISPLAY = {
    "postponed": "Postponed",
    "canceled":  "Canceled",
    "cancelled": "Canceled",
    "suspended": "Suspended",
    "delayed":   "Delayed",
    "tbd":       "TBD",
}

def normalize_status(s: str) -> str:
    """Normalize a non-time status string to a clean display label."""
    return STATUS_DISPLAY.get(s.strip().lower(), s.strip())


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def is_real_match(title: str) -> bool:
    t = title.lower()
    for kw in SHOW_KEYWORDS:
        if kw in t:
            return False
    return True


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


def lookback_date_range(days: int):
    """Yields date strings for the past N days (not including today)."""
    today = datetime.now(TIMEZONE).date()
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        yield d.strftime("%Y%m%d")


def prune_today_games(games: list) -> list:
    now = datetime.now(TIMEZONE)
    kept = []
    for g in games:
        # Try parsing the display time first
        kickoff = None
        try:
            kickoff = datetime.strptime(g["time"].strip(), "%I:%M %p")
            kickoff = kickoff.replace(
                year=now.year, month=now.month, day=now.day, tzinfo=TIMEZONE
            )
        except Exception:
            pass

        # Fall back to stored UTC kickoff (e.g. for postponed games)
        if kickoff is None and g.get("kick_utc"):
            try:
                kickoff = datetime.fromisoformat(g["kick_utc"].replace("Z", "+00:00"))
                kickoff = kickoff.astimezone(TIMEZONE)
            except Exception:
                pass

        if kickoff is None:
            # No time info at all — keep it
            kept.append(g)
            continue

        cutoff = kickoff + timedelta(hours=WINDOW_HOURS)
        if now <= cutoff:
            kept.append(g)
        else:
            print(f"  Removed past game: [{g['league']}] {g['time']} {g['match']}")
    return kept


def dedup_games(games: list) -> list:
    seen = {}
    result = []
    for g in games:
        key = normalize(g["match"]) + "|" + g["time"]
        if key in seen:
            existing = seen[key]
            if g["source"] not in existing["source"]:
                existing["source"] += " · " + g["source"]
        else:
            clone = dict(g)
            seen[key] = clone
            result.append(clone)
    return result


# ─── Round label helper ───────────────────────────────────────────────────────

def slug_to_round_label(slug: str) -> str:
    """Convert an ESPN season slug to a clean round label."""
    if not slug:
        return "Group"
    SLUG_MAP = {
        "group-stage":    "Group",
        "groups":         "Group",
        "league-phase":   "Group",
        "playoff-round":  "Playoff Round",
        "round-one":      "Round One",
        "round-of-32":    "Round of 32",
        "round-of-16":    "Round of 16",
        "quarter-final":  "Quarter-final",
        "quarterfinals":  "Quarter-final",
        "semi-final":     "Semi-final",
        "semifinals":     "Semi-final",
        "final":          "Final",
    }
    if slug in SLUG_MAP:
        return SLUG_MAP[slug]
    # Fallback: title-case and replace hyphens
    return slug.replace("-", " ").title()


# ─── ESPN API Scraper ─────────────────────────────────────────────────────────

def fetch_espn_league_day(league_slug: str, league_name: str, date_str: str) -> list:
    """Fetch games for one league on one date via ESPN's scoreboard API."""
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/soccer"
        f"/{league_slug}/scoreboard?dates={date_str}"
    )
    try:
        data = fetch_json(url)
    except Exception as e:
        if "400" not in str(e):
            print(f"    API error for {league_slug} on {date_str}: {e}")
        return []

    ROUND_LABEL_LEAGUES = {
        "UEFA Champions League", "UEFA Europa League",
        "UEFA Europa Conference League", "CONCACAF Champions Cup"
    }

    games = []
    for event in data.get("events", []):
        try:
            # Get competitors
            competition = event["competitions"][0]
            competitors = competition.get("competitors", [])
            if len(competitors) < 2:
                continue

            # Home/away
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
            home_name = home["team"]["displayName"]
            away_name = away["team"]["displayName"]
            match_title = f"{home_name} vs {away_name}"

            if not is_real_match(match_title):
                continue

            # Get kickoff time in ET
            raw_date = event.get("date", "")
            if not raw_date:
                continue
            utc_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            et_dt = utc_dt.astimezone(TIMEZONE)

            # Only include games on the target date
            if et_dt.strftime("%Y%m%d") != date_str:
                continue

            time_str = et_dt.strftime("%-I:%M %p")

            # Check game status — postponed/cancelled games get no broadcaster
            status_name = event.get("status", {}).get("type", {}).get("name", "")
            non_scheduled = {
                "STATUS_POSTPONED": "Postponed",
                "STATUS_CANCELED":  "Canceled",
                "STATUS_DELAYED":   "Delayed",
                "STATUS_SUSPENDED": "Suspended",
            }
            if status_name in non_scheduled:
                # Skip non-time statuses entirely for International Friendly
                if league_name == "International Friendly":
                    continue
                games.append({
                    "league":    league_name,
                    "time":      non_scheduled[status_name],
                    "match":     match_title,
                    "source":    "",
                    "kick_utc":  raw_date,
                })
                continue

            # Get broadcaster — guard against media being an int (ESPN API quirk on knockout games)
            broadcasts = competition.get("geoBroadcasts", [])
            source_names = []
            for b in broadcasts:
                if not isinstance(b, dict):
                    continue
                media = b.get("media", {})
                if not isinstance(media, dict):
                    continue
                short = media.get("shortName", "")
                lang = b.get("lang", "en")
                if lang != "en":
                    continue
                if short.lower() in SPANISH_EXCLUDE:
                    continue
                mapped = ESPN_SOURCE_MAP.get(short)
                if mapped and mapped not in source_names:
                    source_names.append(mapped)

            if not source_names:
                # Fall back to broadcasts array
                for b in competition.get("broadcasts", []):
                    if not isinstance(b, dict):
                        continue
                    for name in b.get("names", []):
                        if name.lower() in SPANISH_EXCLUDE:
                            continue
                        mapped = ESPN_SOURCE_MAP.get(name)
                        if mapped and mapped not in source_names:
                            source_names.append(mapped)

            # Default source per league if none found
            if not source_names:
                if league_name in ENGLISH_ONLY_LEAGUES:
                    continue
                elif league_name == "MLS":
                    source_names = ["Apple TV"]
                elif league_name == "Premier League":
                    source_names = ["Peacock"]
                elif league_name in {"US Open Cup", "USL Championship", "USL League One", "EFL Championship", "International Friendly", "World Cup Qualifying"}:
                    # No known broadcaster — skip the game entirely
                    continue
                else:
                    source_names = ["ESPN+"]

            source = " · ".join(source_names) if source_names else ""

            # Round/leg label for knockout competitions
            round_label = None
            if league_name in ROUND_LABEL_LEAGUES:
                season = event.get("season", {})
                if not isinstance(season, dict):
                    season = {}
                slug = season.get("slug", "")
                base_label = slug_to_round_label(slug)

                if base_label == "Group":
                    round_label = "Group"
                elif base_label == "Final":
                    round_label = "Final"
                else:
                    # Store base label only — leg number assigned in main() second pass
                    round_label = base_label

            game = {
                "league":     league_name,
                "time":       time_str,
                "match":      match_title,
                "source":     source,
                "kick_utc":   raw_date,
                "home_logo":  home["team"].get("logo", ""),
                "away_logo":  away["team"].get("logo", ""),
            }
            if round_label:
                game["round_label"] = round_label

            games.append(game)

        except Exception as e:
            print(f"    Error parsing event: {e}")
            continue

    return games


# ─── Premier League Scraper (ESPN Scoreboard Page) ───────────────────────────


def fetch_scoreboard_league(date_str: str, header_text: str, league_name: str,
                            source_map: dict, spanish_exclude: set,
                            default_source: str) -> list:
    """
    Generic ESPN scoreboard page scraper for a named league section.
    Finds the section by its h3 header text, extracts games with broadcaster info.
    """
    url = f"https://www.espn.com/soccer/scoreboard/_/date/{date_str}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SOTLive/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        print(f"    Scrape error for {league_name} on {date_str}: {e}")
        return []

    games = []
    try:
        section_start = html.find(f'>{header_text}<')
        if section_start == -1:
            return []

        next_league = html.find('Card__Header__Title', section_start + 100)
        section = html[section_start:next_league] if next_league != -1 else html[section_start:section_start + 50000]

        cell_marker = 'ScoreboardScoreCell__Overview'
        pos = 0
        while True:
            idx = section.find(cell_marker, pos)
            if idx == -1:
                break

            div_start = section.rfind('<div', 0, idx)
            next_idx = section.find(cell_marker, idx + len(cell_marker))
            chunk = section[div_start: next_idx if next_idx != -1 else div_start + 3000]
            parent_chunk = section[div_start: next_idx if next_idx != -1 else len(section)]

            # Time
            time_val = ""
            t_idx = chunk.find('ScoreCell__Time')
            if t_idx != -1:
                t_close = chunk.find('>', t_idx)
                t_end = chunk.find('<', t_close + 1)
                time_val = chunk[t_close + 1:t_end].strip()

            # Networks
            raw_networks = []
            n_pos = 0
            while True:
                n_idx = chunk.find('ScoreCell__NetworkItem', n_pos)
                if n_idx == -1:
                    break
                n_close = chunk.find('>', n_idx)
                n_end = chunk.find('<', n_close + 1)
                net_name = chunk[n_close + 1:n_end].strip()
                if net_name:
                    raw_networks.append(net_name)
                n_pos = n_idx + len('ScoreCell__NetworkItem')

            # Teams
            teams = []
            tp = 0
            while len(teams) < 2:
                t_idx2 = parent_chunk.find('ScoreCell__TeamName--shortDisplayName', tp)
                if t_idx2 == -1:
                    break
                t_close2 = parent_chunk.find('>', t_idx2)
                t_end2 = parent_chunk.find('<', t_close2 + 1)
                team = parent_chunk[t_close2 + 1:t_end2].strip()
                if team:
                    teams.append(team)
                tp = t_idx2 + len('ScoreCell__TeamName--shortDisplayName')

            pos = next_idx if next_idx != -1 else len(section)

            if not time_val or len(teams) < 2:
                continue

            if is_time_value(time_val):
                mapped = []
                for net in raw_networks:
                    if net.lower() in spanish_exclude:
                        continue
                    label = source_map.get(net)
                    if label and label not in mapped:
                        mapped.append(label)
                source = " · ".join(mapped) if mapped else default_source
            else:
                time_val = normalize_status(time_val)
                source = ""

            games.append({
                "league": league_name,
                "time": time_val,
                "match": f"{teams[0]} vs {teams[1]}",
                "source": source,
            })

    except Exception as e:
        print(f"    Parse error for {league_name} on {date_str}: {e}")

    return games


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    dates = list(date_range(DAYS_AHEAD))
    today_str = dates[0][1]

    schedule = {}
    for date_obj, date_str in dates:
        schedule[date_str] = {
            "date": date_obj.strftime("%A, %B %-d"),
            "games": [],
        }

    for slug, league_name in ESPN_LEAGUES.items():
        print(f"Fetching {league_name}...")
        # First pass: collect all games across forward-looking dates
        all_league_games = []  # list of (date_str, game)
        for date_obj, date_str in dates:
            games = fetch_espn_league_day(slug, league_name, date_str)
            if games:
                print(f"  {date_str}: {len(games)} games")
            for g in games:
                all_league_games.append((date_str, g))

        # For knockout leagues, look back 30 days to find rounds already played
        # This tells us if games in our window are Leg 1 or Leg 2
        knockout_slugs_seen = set()
        if league_name in {"UEFA Champions League", "UEFA Europa League",
                           "UEFA Europa Conference League", "CONCACAF Champions Cup"}:
            for past_date_str in lookback_date_range(30):
                past_games = fetch_espn_league_day(slug, league_name, past_date_str)
                for g in past_games:
                    rl = g.get("round_label", "")
                    if rl and rl not in ("Group", "Final"):
                        knockout_slugs_seen.add(rl)

        # Second pass: assign leg numbers
        # If a round slug was already seen in the lookback, current games are Leg 2
        for date_str, g in all_league_games:
            rl = g.get("round_label", "")
            if rl and rl not in ("Group", "Final") and "·" not in rl:
                leg = 2 if rl in knockout_slugs_seen else 1
                g["round_label"] = f"{rl} · Leg {leg}"

            schedule[date_str]["games"].append(g)

    # Conference League via scoreboard scraper (no valid JSON API slug exists)
    print("Fetching UEFA Europa Conference League (scoreboard scrape)...")
    for date_obj, date_str in dates:
        games = fetch_scoreboard_league(
            date_str,
            "UEFA Europa Conference League",
            "UEFA Europa Conference League",
            {"CBS": "CBS / Paramount+", "Paramount+": "CBS / Paramount+", "ESPN+": "ESPN+"},
            SPANISH_EXCLUDE,
            "CBS / Paramount+",
        )
        if games:
            print(f"  {date_str}: {len(games)} games")
        schedule[date_str]["games"].extend(games)

    def sort_key(g, order, first_game_times):
        league_pos = order.index(g["league"]) if g["league"] in order else len(order)
        league_first_time = first_game_times.get(g["league"], datetime.max)
        try:
            game_time = datetime.strptime(g["time"].strip(), "%I:%M %p")
        except Exception:
            game_time = datetime.max
        return (league_pos, league_first_time, game_time)

    ordered = {}
    for _, date_str in dates:
        day = schedule[date_str]
        day["games"] = dedup_games(day["games"])

        # Fix: ESPN's eng.1 (Premier League) endpoint sometimes returns FA Cup games.
        # If the same match appears under both Premier League and English FA Cup,
        # remove the Premier League entry — FA Cup is correct.
        fa_cup_matches = {normalize(g["match"]) for g in day["games"] if g["league"] == "English FA Cup"}
        day["games"] = [
            g for g in day["games"]
            if not (g["league"] == "Premier League" and normalize(g["match"]) in fa_cup_matches)
        ]

        if date_str == today_str:
            day["games"] = prune_today_games(day["games"])
        # Compute the earliest kickoff time per league for ordering
        first_game_times = {}
        for g in day["games"]:
            try:
                t = datetime.strptime(g["time"].strip(), "%I:%M %p")
            except Exception:
                t = datetime.max
            if g["league"] not in first_game_times or t < first_game_times[g["league"]]:
                first_game_times[g["league"]] = t

        day["games"].sort(key=lambda g: sort_key(g, LEAGUE_ORDER, first_game_times))
        ordered[date_str] = day

    output = {
        "updated": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M %Z"),
        "days": ordered,
    }

    with open("schedule.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(d["games"]) for d in ordered.values())
    print(f"\nDone! {total} games written to schedule.json")


if __name__ == "__main__":
    main()
