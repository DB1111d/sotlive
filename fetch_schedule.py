"""
fetch_schedule.py
Fetches Bundesliga (ESPN) and Serie A (CBS Sports) schedules for the next 5 days.
Filters out Spanish-language broadcasts and pre/post show programs.
Writes output to schedule.json.
"""

import json
import re
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

# ESPN category ID for Soccer (used in Watch ESPN schedule URL)
ESPN_SOCCER_CATEGORY = "119cfa41-71d4-39bf-a790-6273a52b0259"

# Leagues to include from ESPN (exact section header text on the page)
ESPN_LEAGUES = {"German Bundesliga", "Spanish LALIGA", "USL Championship", "Dutch Eredivisie", "English FA Cup"}

# Leagues to include from CBS Sports
CBS_LEAGUES = {"Serie A", "UEFA Champions League", "UEFA Europa League", "Premier League"}

# Keywords that indicate a non-match program to skip
SHOW_KEYWORDS = [
    "golazo", "espn fc", "fútbol picante", "futbol picante",
    "goal arena", "konferenz", "pre-show", "post-show",
    "halftime", "studio", "preview", "analysis", "highlights",
]

# Hours after kickoff before a game is removed from Today's tab — 4 hours for all leagues
WINDOW_HOURS = 4

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_real_match(title: str) -> bool:
    """Return True if the title looks like a real match, not a show."""
    t = title.lower()
    # Skip Spanish language
    if "en español" in t or "en espanol" in t:
        return False
    # Skip known show keywords
    for kw in SHOW_KEYWORDS:
        if kw in t:
            return False
    # Must contain " vs " or " v " to be a match
    if " vs " not in t and " v " not in t:
        return False
    return True


def date_range(days: int):
    """Yield (date_obj, date_str YYYYMMDD) for today + next N days."""
    today = datetime.now(TIMEZONE).date()
    for i in range(days):
        d = today + timedelta(days=i)
        yield d, d.strftime("%Y%m%d")


def prune_today_games(games: list[dict]) -> list[dict]:
    """
    For TODAY's games only: remove any game whose kickoff time has passed
    the allowed window (4 hours for all leagues).
    If a game's time can't be parsed it is kept.
    """
    now = datetime.now(TIMEZONE)
    kept = []
    for g in games:
        try:
            # Parse kickoff time (e.g. "9:20 AM") against today's date
            kickoff = datetime.strptime(g["time"].strip(), "%I:%M %p")
            kickoff = kickoff.replace(year=now.year, month=now.month, day=now.day,
                                      tzinfo=TIMEZONE)
            window_hrs = WINDOW_HOURS
            cutoff = kickoff + timedelta(hours=window_hrs)
            if now <= cutoff:
                kept.append(g)
            else:
                print(f"  🕐 Removed past game: [{g['league']}] {g['time']} {g['match']}")
        except Exception:
            kept.append(g)  # keep if time can't be parsed
    return kept


# ─── ESPN Scraper ─────────────────────────────────────────────────────────────

# Map ESPN section headers to friendly names
ESPN_LEAGUE_LABELS = {
    "German Bundesliga": "German Bundesliga",
    "Spanish Laliga":    "La Liga",
    "Usl Championship":  "USL Championship",
    "Dutch Eredivisie":  "Dutch Eredivisie",
    "English Fa Cup":    "English FA Cup",
}

def fetch_espn_day(page, date_str: str) -> list[dict]:
    """Scrape ESPN Watch schedule for a single date, return matching games."""
    url = (
        f"https://www.espn.com/watch/schedule/_/type/upcoming"
        f"/categoryId/{ESPN_SOCCER_CATEGORY}/startDate/{date_str}"
    )
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    games = []
    current_league = None

    # Walk all schedule rows
    rows = page.query_selector_all(".scheduleGrid__item, .ScheduleGrid__item, [class*='scheduleGrid']")

    # Fallback: parse text content if structured selectors don't work
    content = page.inner_text("main") or ""
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect league section headers (all caps, no "vs")
        if line.isupper() and "VS" not in line and len(line) > 3:
            current_league = line.title()
            i += 1
            continue

        # Detect time pattern like "9:20 AM" or "12:20 PM"
        time_match = re.match(r"^(\d{1,2}:\d{2}\s*[AP]M)$", line, re.IGNORECASE)
        if time_match and current_league in ESPN_LEAGUES:
            time_str = time_match.group(1)
            # Next line should be the match title
            if i + 1 < len(lines):
                title = lines[i + 1]
                if is_real_match(title):
                    games.append({
                        "league": current_league,
                        "time": time_str,
                        "match": title,
                        "source": "ESPN+",
                    })
                i += 2
                continue

        i += 1

    return games


# ─── CBS Sports Scraper ───────────────────────────────────────────────────────

CBS_LEAGUE_PATHS = {
    "UEFA Conference League": "https://www.cbssports.com/watch/uefa-conference-league",
    "EFL Championship":       "https://www.cbssports.com/watch/efl",
    "Serie A":              "https://www.cbssports.com/soccer/serie-a/schedule/",
    "UEFA Champions League":"https://www.cbssports.com/soccer/champions-league/schedule/",
    "UEFA Europa League":   "https://www.cbssports.com/soccer/europa-league/schedule/",
    "Premier League":       "https://www.cbssports.com/soccer/premier-league/schedule/",
}

def fetch_cbs_league(page, league: str, target_dates: set[str]) -> list[dict]:
    """Scrape CBS Sports schedule page for a league, filter by target dates."""
    url = CBS_LEAGUE_PATHS[league]
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    games = []
    content = page.inner_text("main") or page.inner_text("body") or ""
    lines = [l.strip() for l in content.splitlines() if l.strip()]

    current_date_str = None

    # Date pattern: "Sat, Mar 7" or "Saturday, March 7"
    date_pattern = re.compile(
        r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*[,.]?\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})",
        re.IGNORECASE,
    )
    # Time pattern
    time_pattern = re.compile(r"(\d{1,2}:\d{2}\s*[ap]m)", re.IGNORECASE)

    year = datetime.now(TIMEZONE).year

    for i, line in enumerate(lines):
        # Try to detect a date header
        dm = date_pattern.match(line)
        if dm:
            # Parse the date to get YYYYMMDD
            try:
                parsed = datetime.strptime(f"{line.split(',')[-1].strip()} {year}", "%B %d %Y")
                current_date_str = parsed.strftime("%Y%m%d")
            except Exception:
                try:
                    # Short month e.g. "Mar 7"
                    short = re.search(r"([A-Za-z]+ \d+)", line)
                    if short:
                        parsed = datetime.strptime(f"{short.group(1)} {year}", "%b %d %Y")
                        current_date_str = parsed.strftime("%Y%m%d")
                except Exception:
                    pass
            continue

        if current_date_str not in target_dates:
            continue

        tm = time_pattern.search(line)
        if tm:
            time_str = tm.group(1).upper()
            # Look ahead for match title
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j]
                if is_real_match(candidate):
                    games.append({
                        "league": league,
                        "time": time_str,
                        "match": candidate,
                        "source": "CBS Sports / Paramount+",
                    })
                    break

    return games


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    dates = list(date_range(DAYS_AHEAD))
    target_date_strs = {d_str for _, d_str in dates}

    schedule = {}  # keyed by YYYYMMDD

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

        # ESPN — one request per day
        print("Fetching ESPN schedule...")
        for date_obj, date_str in dates:
            print(f"  ESPN {date_str}...")
            try:
                games = fetch_espn_day(page, date_str)
            except Exception as e:
                print(f"  ESPN error on {date_str}: {e}")
                games = []
            if date_str not in schedule:
                schedule[date_str] = {"date": date_obj.strftime("%A, %B %-d"), "games": []}
            schedule[date_str]["games"].extend(games)

        # CBS Sports — one request per league (covers all dates)
        print("Fetching CBS Sports schedule...")
        for league in CBS_LEAGUES:
            print(f"  CBS {league}...")
            try:
                games = fetch_cbs_league(page, league, target_date_strs)
            except Exception as e:
                print(f"  CBS error for {league}: {e}")
                games = []
            # Distribute games to the right day
            # (CBS scraper already knows the date — but we stored them without date key above)
            # Re-run with date tracking:
            pass

        # Re-run CBS with date tracking built in
        for league in CBS_LEAGUES:
            url = CBS_LEAGUE_PATHS[league]
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                content = page.inner_text("main") or page.inner_text("body") or ""
                lines = [l.strip() for l in content.splitlines() if l.strip()]

                current_date_str = None
                date_pattern = re.compile(
                    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*[,.]?\s+"
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})",
                    re.IGNORECASE,
                )
                time_pattern = re.compile(r"(\d{1,2}:\d{2}\s*[ap]m)", re.IGNORECASE)
                year = datetime.now(TIMEZONE).year

                for i, line in enumerate(lines):
                    dm = date_pattern.match(line)
                    if dm:
                        try:
                            short = re.search(r"([A-Za-z]+ \d+)", line)
                            if short:
                                parsed = datetime.strptime(f"{short.group(1)} {year}", "%b %d %Y")
                                current_date_str = parsed.strftime("%Y%m%d")
                        except Exception:
                            pass
                        continue

                    if current_date_str not in target_date_strs:
                        continue

                    tm = time_pattern.search(line)
                    if tm:
                        time_str = tm.group(1).upper()
                        for j in range(i + 1, min(i + 4, len(lines))):
                            candidate = lines[j]
                            if is_real_match(candidate):
                                if current_date_str not in schedule:
                                    # Find the date label
                                    d_obj = datetime.strptime(f"{current_date_str}", "%Y%m%d")
                                    schedule[current_date_str] = {
                                        "date": d_obj.strftime("%A, %B %-d"),
                                        "games": [],
                                    }
                                schedule[current_date_str]["games"].append({
                                    "league": league,
                                    "time": time_str,
                                    "match": candidate,
                                    "source": "CBS Sports / Paramount+",
                                })
                                break
            except Exception as e:
                print(f"  CBS error for {league}: {e}")

        browser.close()

    # Sort days and games within each day, deduplicating cross-source duplicates
    def normalize(s):
        import unicodedata
        s = unicodedata.normalize('NFD', s.lower())
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return ' '.join(s.split())

    def dedup_games(games):
        seen = {}
        result = []
        for g in games:
            key = normalize(g['match']) + '|' + g['time']
            if key in seen:
                existing = seen[key]
                if g['source'] not in existing['source']:
                    existing['source'] += ' · ' + g['source']
            else:
                clone = dict(g)
                seen[key] = clone
                result.append(clone)
        return result
    ordered = {}
    today_str = dates[0][1]  # first date is always today
    for _, date_str in dates:
        if date_str in schedule:
            day = schedule[date_str]
            # Sort games by time
            def sort_key(g):
                try:
                    return datetime.strptime(g["time"].strip(), "%I:%M %p")
                except Exception:
                    return datetime.min
            day["games"] = dedup_games(day["games"])
            # Prune past games from TODAY only
            if date_str == today_str:
                day["games"] = prune_today_games(day["games"])
            day["games"].sort(key=sort_key)
            ordered[date_str] = day
        else:
            d_obj = datetime.strptime(date_str, "%Y%m%d")
            ordered[date_str] = {
                "date": d_obj.strftime("%A, %B %-d"),
                "games": [],
            }

    output = {
        "updated": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M %Z"),
        "days": ordered,
    }

    with open("schedule.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(d["games"]) for d in ordered.values())
    print(f"\n✅ Done! {total} games written to schedule.json")


if __name__ == "__main__":
    main()
