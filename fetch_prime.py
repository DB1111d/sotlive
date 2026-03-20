"""
fetch_prime.py
Fetches Prime Video US new releases for the current calendar month.
Writes output to prime.json grouped by type, sorted newest first.
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
    if not API_KEY:
        print("ERROR: RAPIDAPI_KEY environment variable not set.")
        return {}

    results = {}
    cursor  = None

    while True:
        params = {
            "country":         "us",
            "catalogs":        "prime.subscription",
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

        print(f"  [prime/new] got {len(changes)} changes (hasMore={has_more})")

        for change in changes:
            show_id = change.get("showId")
            if not show_id or show_id in results:
                continue

            show = shows.get(str(show_id), {})
            if not show:
                continue

            added_ts = change.get("timestamp", 0)

            link = change.get("link", "") or ""
            if not link:
                streaming_options = show.get("streamingOptions", {}).get("us", [])
                prime_option = next(
                    (s for s in streaming_options
                     if isinstance(s, dict) and s.get("service", {}).get("id") == "prime"),
                    None
                )
                if prime_option:
                    link = prime_option.get("link", "")

            results[show_id] = {
                "show":     show,
                "added_ts": added_ts,
                "link":     link,
            }

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

    # Filter out old library content — only keep titles released in 2024 or newer
    release_year = show.get("releaseYear", 0) or 0
    if release_year and release_year < 2024:
        return None

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
    label = f"{thirty_days_ago.strftime('%B %-d')} – {today.strftime('%B %-d, %Y')}"
    print(f"Fetching Prime Video releases for: {label}")

    from_ts = int(thirty_days_ago.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    to_ts   = int(today.replace(hour=23, minute=59, second=59, microsecond=0).timestamp())

    print("Fetching new releases...")
    matched = fetch_changes("new", from_ts, to_ts)
    print(f"  Total new: {len(matched)}")

    shows = [build_show(sid, entry) for sid, entry in matched.items()]
    shows = [s for s in shows if s is not None]

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

    with open("prime.json", "w") as f:
        json.dump(output, f, indent=2)

    total = sum(len(v) for v in ordered_groups.values())
    print(f"Done! {total} releases written to prime.json")


if __name__ == "__main__":
    main()
