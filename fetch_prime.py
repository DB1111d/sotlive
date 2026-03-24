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
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
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


# ─── TMDb enrichment ──────────────────────────────────────────────────────────

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE    = "https://api.themoviedb.org/3"
TMDB_IMG     = "https://image.tmdb.org/t/p/w342"


def tmdb_request(path: str, params: dict) -> dict:
    params["api_key"] = TMDB_API_KEY
    query = urllib.parse.urlencode(params)
    url   = f"{TMDB_BASE}{path}?{query}"
    req   = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  TMDb error ({path}): {e}")
        return {}


# ── Manual TMDb overrides ─────────────────────────────────────────────────────
# For titles TMDb can't find automatically, specify the exact TMDb ID and
# media type here. Find IDs at themoviedb.org — it's in the URL of the title page.
# Format: "Exact Title As In prime.json": {"id": 123456, "media_type": "movie"/"tv"}
TMDB_OVERRIDES = {
    "Scarpetta": {"id": 974262, "media_type": "movie"},
}


def enrich_with_tmdb(shows: list) -> list:
    """
    For each show, search TMDb by title and show type, then fill in
    overview, genres, thumbnail, and rating if they are missing.
    The existing Amazon data (title, added_date, link, season, etc.)
    is never overwritten.
    """
    if not TMDB_API_KEY:
        print("  TMDB_API_KEY not set — skipping enrichment.")
        return shows

    print(f"  Enriching {len(shows)} shows via TMDb...")

    for show in shows:
        title     = show["title"]
        is_series = show["type"] == "series"
        media     = "tv" if is_series else "movie"

        # Check manual overrides first
        if title in TMDB_OVERRIDES:
            override   = TMDB_OVERRIDES[title]
            tmdb_id    = override["id"]
            media_type = override["media_type"]
            print(f"    [override] {title}")
        else:
            # Strip subtitle after colon, season ordinals, and trailing season info
            # e.g. "The Silent Service Season Two: The Battle of Arctic Ocean" -> "The Silent Service"
            search_title = re.sub(r'\s*:.*$', '', title).strip()
            search_title = re.sub(r'\s+Season\s+\w+.*$', '', search_title, flags=re.IGNORECASE).strip()
            search_title = re.sub(r'\s+S\d+.*$', '', search_title, flags=re.IGNORECASE).strip()
            if not search_title:
                search_title = title

            # Search TMDb — try cleaned title first, fall back to full title if no match
            data = tmdb_request("/search/multi", {"query": search_title, "language": "en-US", "page": 1})
            results = data.get("results", [])

            if not results and search_title != title:
                data = tmdb_request("/search/multi", {"query": title, "language": "en-US", "page": 1})
                results = data.get("results", [])

            # Prefer exact media_type match, fall back to first result
            match = next(
                (r for r in results if r.get("media_type") == media),
                next((r for r in results if r.get("media_type") in ("tv", "movie")), None)
            )

            if not match:
                print(f"    No TMDb match for: {title} (searched: {search_title})")
                time.sleep(0.25)
                continue

            tmdb_id    = match.get("id")
            media_type = match.get("media_type", media)

        # Fetch full details for genres + overview
        details = tmdb_request(f"/{media_type}/{tmdb_id}", {"language": "en-US"})

        # Overview — only fill if empty
        if not show["overview"]:
            show["overview"] = details.get("overview") or match.get("overview") or ""

        # Genres — only fill if empty
        if not show["genres"]:
            show["genres"] = [g["name"] for g in details.get("genres", [])]

        # Thumbnail — only fill if empty
        if not show["thumbnail"]:
            poster = details.get("poster_path") or match.get("poster_path") or ""
            show["thumbnail"] = f"{TMDB_IMG}{poster}" if poster else ""

        # Rating — only fill if None
        if show["rating"] is None:
            vote = details.get("vote_average") or match.get("vote_average")
            if vote:
                # Normalise to 0–100 scale to match Netflix rating format
                show["rating"] = round(float(vote) * 10)

        print(f"    ✓ {title}")
        time.sleep(0.25)  # be polite to TMDb

    return shows


# ─── Main ─────────────────────────────────────────────────────────────────────

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

    # ── Enrich with TMDb (thumbnail, overview, genres, rating) ───────────────
    shows = enrich_with_tmdb(shows)

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
