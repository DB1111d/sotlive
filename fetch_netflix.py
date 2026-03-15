"""
fetch_netflix.py
Fetches Netflix new releases for the current week using the
Streaming Availability API (via RapidAPI).
Writes output to netflix.json, grouped by type (TV Series, Movie, etc.)
sorted by release date descending within each group.
Runs once daily via GitHub Actions.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ─── Configuration ────────────────────────────────────────────────────────────

TIMEZONE   = ZoneInfo("America/New_York")
API_HOST   = "streaming-availability.p.rapidapi.com"
API_KEY    = os.environ.get("RAPIDAPI_KEY", "")

# Type display order and labels
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
    """Returns (sunday, saturday) as date objects for the current week."""
    today = datetime.now(TIMEZONE).date()
    days_since_sunday = (today.weekday() + 1) % 7
    sunday    = today - timedelta(days=days_since_sunday)
    saturday  = sunday + timedelta(days=6)
    return sunday, saturday


def week_label(sunday, saturday):
    """Returns a string like 'Week of March 15 – March 21'."""
    start = sunday.strftime("%B %-d")
    end   = saturday.strftime("%B %-d")
    return f"Week of {start} – {end}"


def fetch_netflix_releases(from_date, to_date) -> list:
    """
    Fetch Netflix US new releases between two dates using the
    Streaming Availability API /shows/search/filters endpoint.
    Paginates through all results.
    """
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set.")
        return []

    from_ts = int(datetime(from_date.year, from_date.month, from_date.day,
                           tzinfo=TIMEZONE).timestamp())
    to_ts   = int(datetime(to_date.year, to_date.month, to_date.day,
                           23, 59, 59, tzinfo=TIMEZONE).timestamp())

    all_shows = []
    cursor    = None

    while True:
        params = {
            "country":           "us",
            "catalogs":          "netflix",
            "order_by":          "new_addition_timestamp",
            "order_direction":   "desc",
            "show_original_language": "en",
            "output_language":   "en",
        }

        if cursor:
            params["cursor"] = cursor

        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url   = f"https://{API_HOST}/shows/search/filters?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "x-rapidapi-host": API_HOST,
                "x-rapidapi-key":  API_KEY,
                "Content-Type":    "application/json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"  API HTTP error: {e.code} {e.reason}")
            break
        except Exception as e:
            print(f"  API error: {e}")
            break

        shows    = data.get("shows", [])
        has_more = data.get("hasMore", False)
        cursor   = data.get("nextCursor", None)

        for show in shows:
            # Find the Netflix US streaming option
            streaming_options = show.get("streamingOptions", {}).get("us", [])
            netflix_option = next(
                (s for s in streaming_options if s.get("service", {}).get("id") == "netflix"),
                None
            )
            if not netflix_option:
                continue

            added_ts = netflix_option.get("availableSince", 0)
            if not (from_ts <= added_ts <= to_ts):
                continue

            show_type   = show.get("showType", "movie").lower()
            title       = show.get("title", "Unknown")
            overview    = show.get("overview", "")
            genres      = [g.get("name", "") for g in show.get("genres", [])]
            added_date  = datetime.fromtimestamp(added_ts, tz=TIMEZONE).strftime("%B %-d")
            link        = netflix_option.get("link", "")

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
    import urllib.parse  # needed for quote inside fetch function

    sunday, saturday = week_bounds()
    label = week_label(sunday, saturday)
    print(f"Fetching Netflix releases for: {label}")

    shows = fetch_netflix_releases(sunday, saturday)
    print(f"  Found {len(shows)} releases")

    if not shows:
        # Write empty state — same pattern as other scripts
        output = {
            "updated":    datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M %Z"),
            "week_label": label,
            "groups":     {},
        }
        with open("netflix.json", "w") as f:
            json.dump(output, f, indent=2)
        print("Done! 0 releases written to netflix.json")
        return

    # Group by type
    grouped = {}
    for show in shows:
        t = show["type"]
        if t not in grouped:
            grouped[t] = []
        grouped[t].append(show)

    # Sort each group by added_ts descending (newest first)
    for t in grouped:
        grouped[t].sort(key=lambda s: s["added_ts"], reverse=True)

    # Build ordered output respecting TYPE_ORDER
    ordered_groups = {}
    for t in TYPE_ORDER:
        if t in grouped:
            ordered_groups[TYPE_LABELS.get(t, t.title())] = grouped[t]
    # Any types not in TYPE_ORDER go at the end
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
    import urllib.parse
    main()
