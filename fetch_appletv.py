"""
fetch_appletv.py
Fetches AppleTV US new releases for the last 30 days.
Writes output to appletv.json grouped by type, sorted newest first.

The /changes endpoint does not track change_type=new for AppleTV —
only change_type=upcoming is supported. We use upcoming as the primary
source, fetching both item_type=show and item_type=season, then
deduplicate by showId keeping the earliest timestamp.
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


def fetch_changes(item_type: str, from_ts: int, to_ts: int) -> dict:
    """
    Fetch change_type=upcoming entries for the given item_type.
    Returns dict of showId -> {show, added_ts, link}.
    If a showId appears multiple times, keeps the earliest added_ts.
    """
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set.")
        return {}

    results = {}
    cursor  = None

    while True:
        params = {
            "country":         "us",
            "catalogs":        "apple",
            "change_type":     "upcoming",
            "item_type":       item_type,
            "order_direction": "asc",
            "from":            from_ts,
            "to":              to_ts,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            data = api_request("/changes", params)
        except urllib.error.HTTPError as e:
            print(f"  HTTP error [{item_type}]: {e.code} {e.reason}")
            try:
                print(f"  Body: {e.read().decode('utf-8')[:500]}")
            except Exception:
                pass
            break
        except Exception as e:
            print(f"  API error [{item_type}]: {e} — retrying in 10s...")
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

        print(f"  [apple/upcoming/{item_type}] got {len(changes)} changes (hasMore={has_more})")

        for change in changes:
            show_id = change.get("showId")
            if not show_id:
                continue

            show = shows.get(str(show_id), {})
            if not show:
                continue

            added_ts = change.get("timestamp", 0)

            link = change.get("link", "") or ""
            if not link:
                streaming_options = show.get("streamingOptions", {}).get("us", [])
                apple_option = next(
                    (s for s in streaming_options
                     if isinstance(s, dict) and s.get("service", {}).get("id") == "apple"),
                    None
                )
                if apple_option:
                    link = apple_option.get("link", "")

            if show_id not in results:
                results[show_id] = {"show": show, "added_ts": added_ts, "link": link}
            else:
                # Keep earliest timestamp — represents when the show first appeared
                if added_ts and added_ts < results[show_id]["added_ts"]:
                    results[show_id]["added_ts"] = added_ts
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
    print(f"Fetching AppleTV releases for: {label}")

    from_ts = int(thirty_days_ago.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    to_ts   = int(today.replace(hour=23, minute=59, second=59, microsecond=0).timestamp())

    # Fetch upcoming for both show and season — AppleTV does not populate change_type=new
    print("Fetching upcoming (item_type=show)...")
    matched = fetch_changes("show", from_ts, to_ts)
    print(f"  Subtotal: {len(matched)}")

    print("Fetching upcoming (item_type=season)...")
    season_results = fetch_changes("season", from_ts, to_ts)
    print(f"  Subtotal: {len(season_results)}")

    # Merge season results — add any showIds not already captured
    for show_id, entry in season_results.items():
        if show_id not in matched:
            matched[show_id] = entry
        else:
            if entry["added_ts"] and entry["added_ts"] < matched[show_id]["added_ts"]:
                matched[show_id]["added_ts"] = entry["added_ts"]
            if entry["link"] and not matched[show_id]["link"]:
                matched[show_id]["link"] = entry["link"]

    print(f"  Total unique shows after merge: {len(matched)}")

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

    with open("appletv.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in ordered_groups.values())
    print(f"Done! {total} releases written to appletv.json")


if __name__ == "__main__":
    main()
