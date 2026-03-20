"""
fetch_prime.py
Fetches Prime Video US new original releases using Amazon's official press API.
No RapidAPI needed — completely free with no quota limits.

Source: https://press.amazonmgmstudios.com/api/whatson/get-whatson-schedules/{month-year}
Only fetches "Original" schedule type to avoid bulk library re-uploads.
Covers the last 30 days (current month + previous month if needed).
Writes output to prime.json grouped by type, sorted newest first.
Runs as part of the Netflix GitHub Actions job.
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/New_York")
API_BASE = "https://press.amazonmgmstudios.com/api/whatson/get-whatson-schedules"

INCLUDE_TYPES = {"Original"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://press.amazonmgmstudios.com/us/en/whatson/",
    "Origin": "https://press.amazonmgmstudios.com",
    "Connection": "keep-alive",
}


def month_slug(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B-%Y").lower()


def fetch_month(year: int, month: int) -> list:
    slug = month_slug(year, month)
    url  = f"{API_BASE}/{slug}"
    req  = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            # Handle gzip
            if resp.info().get('Content-Encoding') == 'gzip':
                import gzip
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
            print(f"  [{slug}] got {len(data)} entries")
            return data
    except urllib.error.HTTPError as e:
        print(f"  HTTP error [{slug}]: {e.code} {e.reason}")
        try:
            print(f"  Body: {e.read().decode('utf-8')[:200]}")
        except Exception:
            pass
        return []
    except Exception as e:
        print(f"  Error [{slug}]: {e}")
        return []


def parse_date(date_str: str):
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=TIMEZONE)
    except Exception:
        return None


def main():
    today = datetime.now(TIMEZONE)
    thirty_days_ago = today - timedelta(days=30)
    label = f"{thirty_days_ago.strftime('%B %-d')} \u2013 {today.strftime('%B %-d, %Y')}"
    print(f"Fetching Prime Video originals for: {label}")

    months_to_fetch = [(today.year, today.month)]
    if (thirty_days_ago.month != today.month or thirty_days_ago.year != today.year):
        months_to_fetch.insert(0, (thirty_days_ago.year, thirty_days_ago.month))

    all_entries = []
    for year, month in months_to_fetch:
        entries = fetch_month(year, month)
        all_entries.extend(entries)

    print(f"  Total entries fetched: {len(all_entries)}")

    cutoff_ts = thirty_days_ago.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    end_ts    = today.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()

    seen_titles = set()
    shows = []

    for entry in all_entries:
        if entry.get("scheduleTypeText") not in INCLUDE_TYPES:
            continue
        if not entry.get("isActive", True):
            continue

        dt = parse_date(entry.get("date", ""))
        if not dt:
            continue

        ts = dt.timestamp()
        if ts < cutoff_ts or ts > end_ts:
            continue

        title = entry.get("show", "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        clean_title = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()
        season = entry.get("season") or ""
        link   = entry.get("showUrl") or ""

        shows.append({
            "type":       "series" if season else "movie",
            "title":      clean_title,
            "overview":   "",
            "genres":     [],
            "added_date": dt.strftime("%B %-d"),
            "added_ts":   int(ts),
            "link":       link,
            "thumbnail":  "",
            "rating":     None,
            "season":     season,
        })

    shows.sort(key=lambda s: s["added_ts"], reverse=True)
    print(f"  Originals in window: {len(shows)}")

    grouped = {}
    for show in shows:
        t = show["type"]
        grouped.setdefault(t, []).append(show)

    TYPE_ORDER  = ["series", "movie"]
    TYPE_LABELS = {"series": "TV Series", "movie": "Movies"}

    ordered_groups = {}
    for t in TYPE_ORDER:
        if t in grouped:
            ordered_groups[TYPE_LABELS[t]] = grouped[t]
    for t, items in grouped.items():
        lbl = TYPE_LABELS.get(t, t.title())
        if lbl not in ordered_groups:
            ordered_groups[lbl] = items

    output = {
        "updated":    today.strftime("%Y-%m-%d %H:%M %Z"),
        "week_label": label,
        "groups":     ordered_groups,
    }

    with open("prime.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in ordered_groups.values())
    print(f"Done! {total} originals written to prime.json")


if __name__ == "__main__":
    main()
