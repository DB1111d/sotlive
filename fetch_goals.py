"""
fetch_goals.py
Fetches today's goal posts from r/soccer and writes goals.json.
Runs every 15 minutes via GitHub Actions.
Parses titles like:
  "Freiburg 2-0 Genk - Igor Matanović 25' | agg. [3]-1"
  "Barcelona [2] - 1 Real Madrid - Lewandowski 66'"
Excludes red/yellow card posts.
Only includes posts with valid video URLs.
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

SUBREDDIT   = "soccer"
PAGES       = 3       # 3 × 100 = up to 300 posts
VIDEO_HOSTS = {"streamff.link", "streamff.com", "streamable.com",
               "youtu.be", "youtube.com", "v.redd.it"}

# Reddit requires a real-looking User-Agent + Accept headers to avoid 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def today_utc_midnight_ts():
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())


def fetch_page(after=None):
    url = f"https://www.reddit.com/r/{SUBREDDIT}/new.json?limit=100"
    if after:
        url += f"&after={after}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_title(title):
    """
    Returns dict with home, homeScore, awayScore, away, scorer, minute
    or None if the title doesn't look like a goal post.
    """
    # Exclude card events
    if re.search(r"red card|yellow card", title, re.IGNORECASE):
        return None

    # Must have a minute mark: space + digits + optional +digits + quote char
    minute_match = re.search(r"\s(\d{1,3})(?:\+\d+)?\s*'", title)
    if not minute_match:
        return None
    minute = int(minute_match.group(1))
    if not (1 <= minute <= 120):
        return None

    # Must have a score: optional bracket + digit + dash + optional bracket + digit
    score_match = re.search(r"\[?(\d+)\]?\s*-\s*\[?(\d+)\]?", title)
    if not score_match:
        return None

    home_score = int(score_match.group(1))
    away_score = int(score_match.group(2))

    score_idx = title.index(score_match.group(0))
    home = title[:score_idx].strip()
    if not home:
        return None

    after_score = title[score_idx + len(score_match.group(0)):].strip()
    dash_parts = after_score.split(" - ")
    away = dash_parts[0].strip()
    if not away:
        return None

    scorer = ""
    if len(dash_parts) > 1:
        # Strip minute and anything after from scorer
        scorer = re.sub(r"\s*\d+.*$", "", dash_parts[1]).strip()

    return {
        "home":      home,
        "homeScore": home_score,
        "awayScore": away_score,
        "away":      away,
        "scorer":    scorer,
        "minute":    minute,
    }


def extract_video_url(url):
    """Returns the url if it's a supported video host, else None."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.replace("www.", "")
        if host in VIDEO_HOSTS:
            return url
    except Exception:
        pass
    return None


def build_embed(url, post_id, subreddit):
    try:
        from urllib.parse import urlparse, parse_qs
        u = urlparse(url)
        host = u.netloc.replace("www.", "")
        parts = [p for p in u.path.split("/") if p]
        vid_id = parts[-1] if parts else ""

        if host == "streamff.link":
            return f"https://streamff.link/v/{vid_id}"
        if host == "streamff.com":
            return f"https://streamff.com/v/{vid_id}"
        if host == "streamable.com":
            return f"https://streamable.com/e/{vid_id}"
        if host == "youtu.be":
            return f"https://www.youtube.com/embed/{vid_id}"
        if host == "youtube.com":
            v = parse_qs(u.query).get("v", [vid_id])[0]
            return f"https://www.youtube.com/embed/{v}"
        if host == "v.redd.it":
            return None  # use permalink instead
    except Exception:
        pass
    return None


def match_key(home, away):
    return " vs ".join(sorted([home.lower(), away.lower()]))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today_ts = today_utc_midnight_ts()
    print(f"Fetching goals since UTC midnight ({today_ts})...")

    # Fetch up to PAGES pages of new posts
    all_posts = []
    after = None
    for page in range(PAGES):
        try:
            data = fetch_page(after)
        except Exception as e:
            print(f"  Page {page+1} fetch error: {e}")
            break
        children = data.get("data", {}).get("children", [])
        all_posts.extend(children)
        after = data.get("data", {}).get("after")
        print(f"  Page {page+1}: {len(children)} posts (after={after})")
        if not after:
            break

    print(f"Total posts fetched: {len(all_posts)}")

    # Parse and group
    matches = {}

    for child in all_posts:
        post = child.get("data", {})

        # Today only
        if post.get("created_utc", 0) < today_ts:
            continue

        parsed = parse_title(post.get("title", ""))
        if not parsed:
            continue

        video_url = extract_video_url(post.get("url", ""))
        if not video_url:
            continue

        key = match_key(parsed["home"], parsed["away"])
        if key not in matches:
            matches[key] = {
                "home": parsed["home"],
                "away": parsed["away"],
                "goals": []
            }

        post_id = post.get("id", "")
        # Deduplicate
        if any(g["postId"] == post_id for g in matches[key]["goals"]):
            continue

        direct_mp4 = None
        secure_media = post.get("secure_media") or {}
        reddit_video = secure_media.get("reddit_video") or {}
        if reddit_video.get("fallback_url"):
            direct_mp4 = reddit_video["fallback_url"]

        matches[key]["goals"].append({
            "postId":    post_id,
            "subreddit": post.get("subreddit", SUBREDDIT),
            "permalink": f"https://redd.it/{post_id}",
            "scorer":    parsed["scorer"],
            "minute":    parsed["minute"],
            "homeScore": parsed["homeScore"],
            "awayScore": parsed["awayScore"],
            "videoUrl":  video_url,
            "videoEmbed": build_embed(video_url, post_id, post.get("subreddit", SUBREDDIT)),
            "directMp4": direct_mp4,
            "postedAt":  int(post.get("created_utc", 0)) * 1000,
        })

    # Sort goals within each match
    for key in matches:
        matches[key]["goals"].sort(key=lambda g: (
            g["homeScore"] + g["awayScore"],
            g["minute"]
        ))

    # Sort matches by most recent goal
    match_list = list(matches.values())
    match_list.sort(key=lambda m: max(g["postedAt"] for g in m["goals"]), reverse=True)

    output = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date":    datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "matches": match_list,
    }

    with open("goals.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_goals = sum(len(m["goals"]) for m in match_list)
    print(f"Done! {len(match_list)} matches, {total_goals} goals written to goals.json")


if __name__ == "__main__":
    main()
