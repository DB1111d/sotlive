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

# ─── Configuration ────────────────────────────────────────────────────────────

DAYS_AHEAD = 5
TIMEZONE = ZoneInfo("America/New_York")

# Hours after kickoff before a game is removed from Today's tab
WINDOW_HOURS = 4

# ESPN API league slugs mapped to friendly names
# Format: https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates=YYYYMMDD
ESPN_LEAGUES = {
    "eng.1":        "Premier League",
    "eng.2":        "EFL Championship",
    "eng.fa":       "English FA Cup",
    "esp.1":        "La Liga",
    "ger.1":        "German Bundesliga",
    "ita.1":        "Serie A",
    "ned.1":        "Dutch Eredivisie",
    "usa.usl.1":    "USL Championship",
    "uefa.champions": "UEFA Champions League",
    "uefa.europa":    "UEFA Europa League",
    "uefa.conference": "UEFA Europa Conference League",
}

# ESPN broadcaster names to map to our badges
ESPN_SOURCE_MAP = {
    "ESPN+":        "ESPN+",
    "ESPN":         "ESPN+",
    "ESPN2":        "ESPN+",
    "ESPNU":        "ESPN+",
    "Paramount+":   "CBS / Paramount+",
    "CBS":          "CBS / Paramount+",
    "CBS Sports Network": "CBS / Paramount+",
    "CBSSN":        "CBS / Paramount+",
}

# Keywords to skip (shows, not matches)
SHOW_KEYWORDS = [
    "golazo", "espn fc", "futbol picante", "fútbol picante",
    "goal arena", "konferenz", "pre-show", "post-show",
    "halftime", "studio", "preview", "analysis", "highlights",
]

LEAGUE_ORDER = [
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Europa Conference League",
    "Premier League",
    "English FA Cup",
    "EFL Championship",
    "Serie A",
    "German Bundesliga",
    "La Liga",
    "Dutch Eredivisie",
    "USL Championship",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

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


def prune_today_games(games: list) -> list:
    now = datetime.now(TIMEZONE)
    kept = []
    for g in games:
        try:
            kickoff = datetime.strptime(g["time"].strip(), "%I:%M %p")
            kickoff = kickoff.replace(
                year=now.year, month=now.month, day=now.day, tzinfo=TIMEZONE
            )
            cutoff = kickoff + timedelta(hours=WINDOW_HOURS)
            if now <= cutoff:
                kept.append(g)
            else:
                print(f"  Removed past game: [{g['league']}] {g['time']} {g['match']}")
        except Exception:
            kept.append(g)
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
        print(f"    API error for {league_slug} on {date_str}: {e}")
        return []

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

            # Get broadcaster
            broadcasts = competition.get("geoBroadcasts", [])
            source_names = []
            for b in broadcasts:
                short = b.get("media", {}).get("shortName", "")
                lang = b.get("lang", "en")
                if lang != "en":
                    continue
                mapped = ESPN_SOURCE_MAP.get(short)
                if mapped and mapped not in source_names:
                    source_names.append(mapped)

            if not source_names:
                # Fall back to broadcasts array
                for b in competition.get("broadcasts", []):
                    for name in b.get("names", []):
                        mapped = ESPN_SOURCE_MAP.get(name)
                        if mapped and mapped not in source_names:
                            source_names.append(mapped)

            source = " · ".join(source_names) if source_names else "ESPN+"

            games.append({
                "league": league_name,
                "time": time_str,
                "match": match_title,
                "source": source,
            })

        except Exception as e:
            print(f"    Error parsing event: {e}")
            continue

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
        for date_obj, date_str in dates:
            games = fetch_espn_league_day(slug, league_name, date_str)
            if games:
                print(f"  {date_str}: {len(games)} games")
            schedule[date_str]["games"].extend(games)

    def sort_key(g):
        try:
            return datetime.strptime(g["time"].strip(), "%I:%M %p")
        except Exception:
            return datetime.min

    ordered = {}
    for _, date_str in dates:
        day = schedule[date_str]
        day["games"] = dedup_games(day["games"])
        if date_str == today_str:
            day["games"] = prune_today_games(day["games"])
        day["games"].sort(key=sort_key)
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
