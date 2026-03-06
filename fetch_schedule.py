"""
fetch_schedule.py
Fetches soccer schedules from ESPN+ and CBS Sports for the next 5 days.
Filters out Spanish-language broadcasts and pre/post show programs.
Removes past games from Today based on a 4-hour window after kickoff.
Writes output to schedule.json.
"""

import json
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    raise

# ─── Configuration ────────────────────────────────────────────────────────────

DAYS_AHEAD = 5
TIMEZONE = ZoneInfo("America/New_York")

# ESPN Soccer category ID
ESPN_SOCCER_CATEGORY = "119cfa41-71d4-39bf-a790-6273a52b0259"

# ESPN league section headers mapped to friendly names
ESPN_LEAGUE_MAP = {
    "German Bundesliga":  "German Bundesliga",
    "Spanish Laliga":     "La Liga",
    "Usl Championship":   "USL Championship",
    "Dutch Eredivisie":   "Dutch Eredivisie",
    "English Fa Cup":     "English FA Cup",
}

# CBS Sports schedule URLs per league
CBS_LEAGUE_URLS = {
    "UEFA Champions League":         "https://www.cbssports.com/soccer/champions-league/schedule/",
    "UEFA Europa League":            "https://www.cbssports.com/soccer/europa-league/schedule/",
    "UEFA Europa Conference League": "https://www.cbssports.com/watch/uefa-conference-league",
    "Premier League":                "https://www.cbssports.com/soccer/premier-league/schedule/",
    "EFL Championship":              "https://www.cbssports.com/watch/efl",
    "Serie A":                       "https://www.cbssports.com/soccer/serie-a/schedule/",
}

# Hours after kickoff before a game is removed from Today's tab
WINDOW_HOURS = 4

# Keywords that mark a program as a non-match show
SHOW_KEYWORDS = [
    "golazo", "espn fc", "futbol picante", "fútbol picante",
    "goal arena", "konferenz", "pre-show", "post-show",
    "halftime", "studio", "preview", "analysis", "highlights",
    "noche",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_real_match(title: str) -> bool:
    t = title.lower()
    if "en español" in t or "en espanol" in t:
        return False
    for kw in SHOW_KEYWORDS:
        if kw in t:
            return False
    if " vs " not in t and " v " not in t:
        return False
    return True


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def convert_to_12h(time_str: str) -> str:
    time_str = time_str.strip().upper().replace("\u202f", " ")
    m = re.match(r"^(\d{1,2}:\d{2})\s*(AM|PM)$", time_str)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return time_str


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
            kickoff = kickoff.replace(year=now.year, month=now.month, day=now.day, tzinfo=TIMEZONE)
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


# ─── ESPN Scraper ─────────────────────────────────────────────────────────────

def fetch_espn_day(page, date_str: str) -> list:
    """
    ESPN page text format:
    ...
    Dutch Eredivisie
    10:25 am
    FC Groningen vs. Ajax
    ...
    """
    url = (
        f"https://www.espn.com/watch/schedule/_/type/upcoming"
        f"/categoryId/{ESPN_SOCCER_CATEGORY}/startDate/{date_str}"
    )
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    content = page.inner_text("main") or ""
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    games = []
    current_league = None
    time_re = re.compile(r"^(\d{1,2}:\d{2}\s*[ap]m)$", re.IGNORECASE)

    i = 0
    while i < len(lines):
        line = lines[i]
        title = line.title()

        if title in ESPN_LEAGUE_MAP:
            current_league = ESPN_LEAGUE_MAP[title]
            i += 1
            continue

        tm = time_re.match(line)
        if tm and current_league:
            time_str = convert_to_12h(tm.group(1))
            if i + 1 < len(lines):
                match_title = lines[i + 1]
                if is_real_match(match_title):
                    games.append({
                        "league": current_league,
                        "time": time_str,
                        "match": match_title,
                        "source": "ESPN+",
                    })
            i += 2
            continue

        i += 1

    return games


# ─── CBS Sports Scraper ───────────────────────────────────────────────────────

def fetch_cbs_league(page, league: str, target_dates: set) -> dict:
    """
    CBS page text format:
    Tuesday, March 10, 2026 Home Away Time/TV Streaming Venue
    Galatasaray Liverpool 1:45 pm Paramount+ Rams Global Stadium
    ...
    Returns dict: YYYYMMDD -> [game dicts]
    """
    url = CBS_LEAGUE_URLS[league]
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    content = page.inner_text("main") or page.inner_text("body") or ""
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    full_date_re = re.compile(
        r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
        r"(\w+ \d{1,2},\s*\d{4})",
        re.IGNORECASE,
    )

    # Match lines like: "Team A Team B 1:45 pm Paramount+ Stadium"
    row_re = re.compile(
        r"^(.+?)\s+(\d{1,2}:\d{2}\s*[ap]m)\s+(?:Paramount\+|CBS|—|-)",
        re.IGNORECASE,
    )

    results = {}
    current_date_str = None

    for line in lines:
        dm = full_date_re.match(line)
        if dm:
            try:
                parsed = datetime.strptime(dm.group(1).strip(), "%B %d, %Y")
                current_date_str = parsed.strftime("%Y%m%d")
            except Exception:
                pass
            continue

        if current_date_str not in target_dates:
            continue

        rm = row_re.match(line)
        if rm:
            teams_part = rm.group(1).strip()
            time_str = convert_to_12h(rm.group(2).strip())

            # Split teams roughly in half
            words = teams_part.split()
            if len(words) >= 2:
                mid = len(words) // 2
                home = " ".join(words[:mid])
                away = " ".join(words[mid:])
                match_title = f"{home} vs {away}"

                if is_real_match(match_title):
                    if current_date_str not in results:
                        results[current_date_str] = []
                    results[current_date_str].append({
                        "league": league,
                        "time": time_str,
                        "match": match_title,
                        "source": "CBS / Paramount+",
                    })

    return results


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    dates = list(date_range(DAYS_AHEAD))
    target_date_strs = {d_str for _, d_str in dates}
    today_str = dates[0][1]

    schedule = {}
    for date_obj, date_str in dates:
        schedule[date_str] = {
            "date": date_obj.strftime("%A, %B %-d"),
            "games": [],
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        print("Fetching ESPN schedule...")
        for date_obj, date_str in dates:
            print(f"  ESPN {date_str}...")
            try:
                games = fetch_espn_day(page, date_str)
                print(f"    Found {len(games)} ESPN games")
                schedule[date_str]["games"].extend(games)
            except Exception as e:
                print(f"  ESPN error on {date_str}: {e}")

        print("Fetching CBS Sports schedule...")
        for league in CBS_LEAGUE_URLS:
            print(f"  CBS: {league}...")
            try:
                day_map = fetch_cbs_league(page, league, target_date_strs)
                for date_str, games in day_map.items():
                    if date_str in schedule:
                        print(f"    {league}: {len(games)} games on {date_str}")
                        schedule[date_str]["games"].extend(games)
            except Exception as e:
                print(f"  CBS error for {league}: {e}")

        browser.close()

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
