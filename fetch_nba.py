"""
fetch_nba.py
Fetches NBA schedules using ESPN's JSON API.
Mirrors the structure of fetch_ncaa_basketball.py.
Writes output to nba.json.
"""

import json
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ─── Configuration ────────────────────────────────────────────────────────────

DAYS_AHEAD   = 5
TIMEZONE     = ZoneInfo("America/New_York")
WINDOW_HOURS = 4

ESPN_NBA_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/nba/scoreboard?dates={date_str}"
)

# National broadcasters only — regional networks are excluded
ESPN_SOURCE_MAP = {
    "ESPN":       "ESPN+",
    "ESPN+":      "ESPN+",
    "ESPN2":      "ESPN+",
    "ESPNU":      "ESPN+",
    "ESPNEWS":    "ESPN+",
    "ABC":        "ABC / ESPN+",
    "CBS":        "CBS / Paramount+",
    "Paramount+": "CBS / Paramount+",
    "Peacock":    "Peacock",
    "NBC":        "USA Network",
    "USA Net":    "USA Network",
    "TNT":        "TBS / TNT",
    "TBS":        "TBS / TNT",
    "truTV":      "TBS / TNT",
    "TruTV":      "TBS / TNT",
    "NBA TV":     "NBA TV",
}

# Regional network keywords to exclude
REGIONAL_EXCLUDE = {
    "fanduel", "spectrum", "bally", "yes", "nesn", "msg", "nbc sports",
    "root sports", "altitude", "fox sports", "space city", "jazz+",
    "blazervision", "chsn", "sportsnet", "kjzz", "kunp",
}

SPANISH_EXCLUDE = {
    "universo", "telemundo", "espn deportes", "univision", "tudn",
}

NON_STATUSES = {
    "STATUS_POSTPONED": "Postponed",
    "STATUS_CANCELED":  "Canceled",
    "STATUS_DELAYED":   "Delayed",
    "STATUS_SUSPENDED": "Suspended",
}

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


def is_regional(name: str) -> bool:
    n = name.lower()
    for kw in REGIONAL_EXCLUDE:
        if kw in n:
            return True
    return False


def fetch_nba_day(date_str: str) -> list:
    url = ESPN_NBA_URL.format(date_str=date_str)
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"    API error for NBA on {date_str}: {e}")
        return []

    games = []
    for event in data.get("events", []):
        try:
            competition = event["competitions"][0]
            competitors = competition.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
            home_name = home["team"]["displayName"]
            away_name = away["team"]["displayName"]
            match_title = f"{home_name} vs {away_name}"

            raw_date = event.get("date", "")
            if not raw_date:
                continue
            utc_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            et_dt  = utc_dt.astimezone(TIMEZONE)

            if et_dt.strftime("%Y%m%d") != date_str:
                continue

            time_str = et_dt.strftime("%-I:%M %p")

            status_name = event.get("status", {}).get("type", {}).get("name", "")
            if status_name in NON_STATUSES:
                games.append({
                    "group":     "Regular Season",
                    "time":      NON_STATUSES[status_name],
                    "match":     match_title,
                    "source":    "",
                    "kick_utc":  raw_date,
                    "home_logo": home["team"].get("logo", ""),
                    "away_logo": away["team"].get("logo", ""),
                })
                continue

            # Broadcaster — national only
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
                if is_regional(short):
                    continue
                mapped = ESPN_SOURCE_MAP.get(short)
                if mapped and mapped not in source_names:
                    source_names.append(mapped)

            source = " · ".join(source_names) if source_names else ""

            games.append({
                "group":     "Regular Season",
                "time":      time_str,
                "match":     match_title,
                "source":    source,
                "kick_utc":  raw_date,
                "home_logo": home["team"].get("logo", ""),
                "away_logo": away["team"].get("logo", ""),
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

    print("Fetching NBA...")
    for date_obj, date_str in dates:
        games = fetch_nba_day(date_str)
        if games:
            print(f"  {date_str}: {len(games)} games")
        schedule[date_str]["games"].extend(games)

    ordered = {}
    for _, date_str in dates:
        day = schedule[date_str]
        if date_str == today_str:
            day["games"] = prune_today_games(day["games"])
        day["games"].sort(key=lambda g: g["time"])
        ordered[date_str] = day

    output = {
        "updated": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M %Z"),
        "days":    ordered,
    }

    with open("nba.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(d["games"]) for d in ordered.values())
    print(f"\nDone! {total} games written to nba.json")


if __name__ == "__main__":
    main()
