"""
fetch_netflix.py
Fetches Netflix US new releases for the current week using the
Streaming Availability API (via RapidAPI) /changes endpoint.
All languages included — no language filtering.
Writes output to netflix.json grouped by type, sorted newest first.
Runs once daily via GitHub Actions.
"""

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ─── Configuration ────────────────────────────────────────────────────────────

TIMEZONE = ZoneInfo("America/New_York")
API_HOST = "streaming-availability.p.rapidapi.com"
API_KEY  = os.environ.get("RAPIDAPI_KEY", "")

TYPE_ORDER = ["series", "movie", "documentary", "short_film", "special"]
TYPE_LABELS = {
    "series":      "TV Series",
    "movie":       "Movies",
    "documentary": "Documentaries",
    "short_film":  "Short Films",
    "special":     "Specials",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def week_bounds():
    today = datetime.now(TIMEZONE).date()
    days_since_sunday = (today.weekday() + 1) % 7
    sunday   = today - timedelta(days=days_since_sunday)
    saturday = sunday + timedelta(days=6)
    return sunday, saturday


def week_label(sunday, saturday):
    return f"Week of {sunday.strftime('%B %-d')} \u2013 {saturday.strftime('%B %-d')}"


def api_request(path: str, params: dict) -> dict:
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url   = f"https://{API_HOST}{path}?{query}"
    req   = urllib.request.Request(url, headers={
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key":  API_KEY,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ─── Fetch ────────────────────────────────────────────────────────────────────

def fetch_netflix_releases(from_ts: int, to_ts: int) -> list:
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set.")
        return []

    all_shows = []
    cursor    = None
    seen_ids  = set()

    while True:
        params = {
            "country":         "us",
            "service":         "netflix",
            "change_type":     "new",
            "item_type":       "show",
            "order_direction": "desc",
            "from":            from_ts,
            "to":              to_ts,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            data = api_request("/changes", params)
        except urllib.error.HTTPError as e:
            print(f"  HTTP error: {e.code} {e.reason}")
            try:
                print(f"  Body: {e.read().decode('utf-8')[:500]}")
            except Exception:
                pass
            break
        except Exception as e:
            print(f"  API error: {e}")
            break

        # Debug — show raw response
        print(f"  [DEBUG] Response keys: {list(data.keys())}")
        print(f"  [DEBUG] Raw: {str(data)[:500]}")

        changes  = data.get("changes", [])
        has_more = data.get("hasMore", False)
        cursor   = data.get("nextCursor", None)

        print(f"  Got {len(changes)} changes (hasMore={has_more})")

        for change in changes:
            show = change.get("show", {})
            if not show:
                continue

            # Deduplicate by show id
            show_id = show.get("id") or show.get("imdbId") or show.get("tmdbId")
            if show_id and show_id in seen_ids:
                continue
            if show_id:
                seen_ids.add(show_id)

            show_type  = show.get("showType", "movie").lower()
            title      = show.get("title", "Unknown")
            overview   = show.get("overview", "")
            genres     = [g.get("name", "") for g in show.get("genres", [])]
            added_ts   = change.get("timestamp", 0)
            added_date = datetime.fromtimestamp(added_ts, tz=TIMEZONE).strftime("%B %-d")

            # Get Netflix deep link
            link = ""
            streaming_options = show.get("streamingOptions", {}).get("us", [])
            netflix_option = next(
                (s for s in streaming_options
                 if isinstance(s, dict) and s.get("service", {}).get("id") == "netflix"),
                None
            )
            if netflix_option:
                link = netflix_option.get("link", "")

            all_shows.append({
                "type":       show_type,
                "title":      title,
                "overview":   overview[:200] + "..." if len(overview) > 200 else overview,
                "genres":     genres,
                "added_date": added_date,
                "added_ts":   added_ts,
                "link":       link,
            })

        if not has_more or not cursor:
            break

    return all_shows


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    sunday, saturday = week_bounds()
    label = week_label(sunday, saturday)
    print(f"Fetching Netflix releases for: {label}")

    from_ts = int(datetime(sunday.year, sunday.month, sunday.day,
                           tzinfo=TIMEZONE).timestamp())
    to_ts   = int(datetime(saturday.year, saturday.month, saturday.day,
                           23, 59, 59, tzinfo=TIMEZONE).timestamp())

    shows = fetch_netflix_releases(from_ts, to_ts)
    print(f"  Total: {len(shows)} releases found")

    # Group by type
    grouped = {}
    for show in shows:
        t = show["type"]
        if t not in grouped:
            grouped[t] = []
        grouped[t].append(show)

    # Sort each group newest first
    for t in grouped:
        grouped[t].sort(key=lambda s: s["added_ts"], reverse=True)

    # Order groups by TYPE_ORDER
    ordered_groups = {}
    for t in TYPE_ORDER:
        label_key = TYPE_LABELS.get(t, t.title())
        if t in grouped:
            ordered_groups[label_key] = grouped[t]
    # Any unlisted types go at the end
    for t, items in grouped.items():
        label_key = TYPE_LABELS.get(t, t.title())
        if label_key not in ordered_groups:
            ordered_groups[label_key] = items

    output = {
        "updated":    datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M %Z"),
        "week_label": label,
        "groups":     ordered_groups,
    }

    with open("netflix.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in ordered_groups.values())
    print(f"Done! {total} releases written to netflix.json")


if __name__ == "__main__":
    main()
