"""
fetch_disney.py
Fetches Disney+ US new releases for the last 30 days.
Writes output to disney.json grouped by type, sorted newest first.

Disney+ bulk-uploads large library batches, so change_type=new returns
hundreds of results including old catalogue content. We filter these out
by comparing the streaming option's availableSince timestamp to the
change timestamp: if availableSince is within 3 days of the change event,
the content is genuinely new. If it's older, it's a re-catalogued item.
Runs as part of the Netflix GitHub Actions job (combined to save API quota).
"""

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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


def api_request(path: str, params: dict) -> dict:
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url   = f"https://{API_HOST}{path}?{query}"
    req   = urllib.request.Request(url, headers={
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key":  API_KEY,
    })
    with urllib.request.urlopen(req, timeout=1000) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_changes(from_ts: int, to_ts: int) -> dict:
    """
    Fetch all change_type=new entries for Disney+ within the time window.
    Returns dict of showId -> {show, added_ts, link}.
    added_ts = availableSince from the streaming option (when it went live).
    If a showId appears multiple times, keeps the earliest timestamp.
    """
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set.")
        return {}

    results = {}
    cursor  = None

    while True:
        params = {
            "country":         "us",
            "catalogs":        "disney",
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
            print(f"  API error: {e} — retrying in 10s...")
            import time
            time.sleep(10)
            try:
                data = api_request("/changes", params)
            except Exception as e2:
                print(f"  Retry failed: {e2} — stopping.")
                break

        changes  = data.get("changes", [])
        shows    = data.get("shows", {})
        has_more = data.get("hasMore", False)
        cursor   = data.get("nextCursor", None)

        print(f"  [disney/new] got {len(changes)} changes (hasMore={has_more})")

        for change in changes:
            show_id = change.get("showId")
            if not show_id:
                continue

            show = shows.get(str(show_id), {})
            if not show:
                continue

            change_ts = change.get("timestamp", 0)

            # Get availableSince from the Disney streaming option
            streaming_options = show.get("streamingOptions", {}).get("us", [])
            disney_option = next(
                (o for o in streaming_options
                 if isinstance(o, dict) and o.get("service", {}).get("id") == "disney"),
                None
            )
            available_since = disney_option.get("availableSince") if disney_option else None
            link = change.get("link", "") or ""
            if not link and disney_option:
                link = disney_option.get("link", "")

            if show_id not in results:
                results[show_id] = {
                    "show":       show,
                    "added_ts":   available_since or change_ts,
                    "change_ts":  change_ts,
                    "link":       link,
                }
            else:
                # Keep earliest timestamps
                if change_ts and change_ts < results[show_id]["change_ts"]:
                    results[show_id]["change_ts"] = change_ts
                if available_since and (
                    not results[show_id]["added_ts"] or
                    available_since < results[show_id]["added_ts"]
                ):
                    results[show_id]["added_ts"] = available_since
                if link and not results[show_id]["link"]:
                    results[show_id]["link"] = link

        if not has_more or not cursor:
            break

    return results


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


def main():
    today = datetime.now(TIMEZONE)
    thirty_days_ago = today - timedelta(days=30)
    label = f"{thirty_days_ago.strftime('%B %-d')} \u2013 {today.strftime('%B %-d, %Y')}"
    print(f"Fetching Disney+ releases for: {label}")

    from_ts = int(thirty_days_ago.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    to_ts   = int(today.replace(hour=23, minute=59, second=59, microsecond=0).timestamp())

    print("Fetching new releases...")
    new_shows = fetch_changes(from_ts, to_ts)
    print(f"  Total new: {len(new_shows)}")

    # Filter out bulk catalogue dumps by counting how many shows share the
    # same availableSince date. Disney batch-uploads dozens of catalogue titles
    # on a single day — genuine new releases arrive 1-5 per day at most.
    from collections import Counter

    # Step 1: drop anything where availableSince predates the 30-day window
    in_window = {
        sid: entry for sid, entry in new_shows.items()
        if entry["added_ts"] and entry["added_ts"] >= from_ts
    }
    print(f"  Total after window filter: {len(in_window)}")

    # Step 2: drop bulk catalogue dump days — Disney uploads dozens of old
    # titles on a single day. Count shows per availableSince date and discard
    # any date with more than BULK_THRESHOLD shows.
    date_counts = Counter()
    for sid, entry in in_window.items():
        date_counts[entry["added_ts"] // 86400] += 1

    BULK_THRESHOLD = 6  # days with more than this many releases are catalogue dumps
    matched = {
        sid: entry for sid, entry in in_window.items()
        if date_counts[entry["added_ts"] // 86400] <= BULK_THRESHOLD
    }
    print(f"  Total after bulk-day filter (threshold={BULK_THRESHOLD}): {len(matched)}")

    shows = [build_show(sid, entry) for sid, entry in matched.items()]

    # Deduplicate by normalised title
    seen_titles: set = set()
    deduped = []
    for show in shows:
        key = show["title"].strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(show)
    shows = deduped
    print(f"  Total after title dedup: {len(shows)}")

    grouped = {}
    for show in shows:
        t = show["type"]
        grouped.setdefault(t, []).append(show)

    for t in grouped:
        grouped[t].sort(key=lambda s: s["added_ts"], reverse=True)

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
        "updated":    today.strftime("%Y-%m-%d %H:%M %Z"),
        "week_label": label,
        "groups":     ordered_groups,
    }

    with open("disney.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in ordered_groups.values())
    print(f"Done! {total} releases written to disney.json")


if __name__ == "__main__":
    main()
