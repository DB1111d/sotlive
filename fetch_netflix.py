"""
fetch_netflix.py
Fetches Netflix US new releases for the current Sunday–Saturday week.
Uses a two-pass approach to eliminate bulk re-upload noise:
  1. Fetch change_type=new  for the full week (what actually appeared)
  2. Fetch change_type=upcoming for the full week (what Netflix announced)
  3. Keep only shows that appear in BOTH lists
Bulk catalogue re-uploads are never announced as upcoming, so they
are automatically filtered out. Genuine new releases are in both.
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
    today = datetime.now(TIMEZONE)
    return today.strftime("%B %Y")


def api_request(path: str, params: dict) -> dict:
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url   = f"https://{API_HOST}{path}?{query}"
    req   = urllib.request.Request(url, headers={
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key":  API_KEY,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ─── Fetch one change_type ────────────────────────────────────────────────────

def fetch_changes(change_type: str, from_ts: int, to_ts: int) -> dict:
    """
    Fetch all changes of a given type within the time window.
    Returns a dict of showId -> show data (with added_ts from the change).
    """
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set.")
        return {}

    results  = {}
    cursor   = None

    while True:
        params = {
            "country":         "us",
            "catalogs":        "netflix",
            "change_type":     change_type,
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
            print(f"  HTTP error ({change_type}): {e.code} {e.reason}")
            try:
                print(f"  Body: {e.read().decode('utf-8')[:500]}")
            except Exception:
                pass
            break
        except Exception as e:
            print(f"  API error ({change_type}): {e}")
            break

        changes  = data.get("changes", [])
        shows    = data.get("shows", {})
        has_more = data.get("hasMore", False)
        cursor   = data.get("nextCursor", None)

        print(f"  [{change_type}] got {len(changes)} changes (hasMore={has_more})")

        for change in changes:
            show_id = change.get("showId")
            if not show_id or show_id in results:
                continue

            show = shows.get(str(show_id), {})
            if not show:
                continue

            added_ts = change.get("timestamp", 0)

            # Prefer the deep link from the change object (guaranteed for upcoming)
            link = change.get("link", "") or ""
            if not link:
                streaming_options = show.get("streamingOptions", {}).get("us", [])
                netflix_option = next(
                    (s for s in streaming_options
                     if isinstance(s, dict) and s.get("service", {}).get("id") == "netflix"),
                    None
                )
                if netflix_option:
                    link = netflix_option.get("link", "")

            results[show_id] = {
                "show":     show,
                "added_ts": added_ts,
                "link":     link,
            }

        if not has_more or not cursor:
            break

    return results


# ─── Build show record ────────────────────────────────────────────────────────

def build_show(show_id: str, entry: dict) -> dict:
    show     = entry["show"]
    added_ts = entry["added_ts"]

    show_type  = show.get("showType", "movie").lower()
    title      = show.get("title", "Unknown")
    overview   = show.get("overview", "")
    genres     = [g.get("name", "") for g in show.get("genres", [])]
    added_date = datetime.fromtimestamp(added_ts, tz=TIMEZONE).strftime("%B %-d") if added_ts else ""
    rating     = show.get("rating", None)
    link       = entry["link"]

    image_set = show.get("imageSet", {})
    thumbnail = (
        image_set.get("verticalPoster", {}).get("w240")
        or image_set.get("verticalPoster", {}).get("w360")
        or image_set.get("horizontalPoster", {}).get("w360")
        or image_set.get("horizontalPoster", {}).get("w480")
        or ""
    )

    return {
        "type":       show_type,
        "title":      title,
        "overview":   overview,
        "genres":     genres,
        "added_date": added_date,
        "added_ts":   added_ts,
        "link":       link,
        "thumbnail":  thumbnail,
        "rating":     rating,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    sunday, saturday = week_bounds()
    label = week_label(sunday, saturday)
    print(f"Fetching Netflix releases for: {label}")

    today = datetime.now(TIMEZONE)
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Last second of the last day of the current month
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        month_end = today.replace(month=today.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = month_end.replace(tzinfo=TIMEZONE) - timedelta(seconds=1)

    week_from_ts = int(month_start.replace(tzinfo=TIMEZONE).timestamp())
    week_to_ts   = int(month_end.timestamp())
    today_ts     = int(today.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    # ── Pass 1: what actually appeared as new this week ──────────────────────
    print("Pass 1: fetching new releases...")
    new_shows = fetch_changes("new", week_from_ts, week_to_ts)
    print(f"  Total new: {len(new_shows)}")

    # ── Pass 2: what Netflix announced as upcoming this week ─────────────────
    # upcoming can only query today → future, so clamp from_ts to today
    upcoming_from = max(week_from_ts, today_ts)
    print("Pass 2: fetching upcoming announcements...")
    upcoming_shows = fetch_changes("upcoming", upcoming_from, week_to_ts)
    print(f"  Total upcoming: {len(upcoming_shows)}")

    # ── Intersect: keep only shows in both lists ──────────────────────────────
    announced_ids = set(upcoming_shows.keys())
    matched = {sid: entry for sid, entry in new_shows.items() if sid in announced_ids}
    print(f"  Matched (in both): {len(matched)}")

    # If upcoming returns nothing (e.g. early in the week before announcements),
    # fall back to new_shows only so the page isn't empty
    if not matched and new_shows:
        print("  No upcoming matches found — falling back to new_shows only")
        matched = new_shows

    # ── Build show records ────────────────────────────────────────────────────
    shows = [build_show(sid, entry) for sid, entry in matched.items()]

    # ── Group by type ─────────────────────────────────────────────────────────
    grouped = {}
    for show in shows:
        t = show["type"]
        grouped.setdefault(t, []).append(show)

    # Sort each group newest first
    for t in grouped:
        grouped[t].sort(key=lambda s: s["added_ts"], reverse=True)

    # Order groups by TYPE_ORDER
    ordered_groups = {}
    for t in TYPE_ORDER:
        label_key = TYPE_LABELS.get(t, t.title())
        if t in grouped:
            ordered_groups[label_key] = grouped[t]
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
