"""
fetch_goals.py
Fetches today's goal posts from r/soccer using the Arctic Shift API.
Arctic Shift is a Reddit data mirror that works from any IP with no auth.
Runs every 15 minutes via GitHub Actions.
"""

import json
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

SUBREDDIT   = "soccer"
VIDEO_HOSTS = {"streamff.link", "streamff.com", "streamable.com",
               "youtu.be", "youtube.com", "v.redd.it"}

HEADERS = {
    "User-Agent": "sotlive-goalfeed/1.0",
    "Accept": "application/json",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def today_utc_midnight_ts():
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())


def fetch_posts(after_ts):
    url = (
        f"https://arctic-shift.photon-reddit.com/api/posts/search"
        f"?subreddit={SUBREDDIT}"
        f"&after={after_ts}"
        f"&limit=100"
        f"&sort=new"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except Exception as e:
        print(f"  Arctic Shift fetch error: {e}")
        return []


def parse_title(title):
    if re.search(r"red card|yellow card", title, re.IGNORECASE):
        return None
    minute_match = re.search(r"\s(\d{1,3})(?:\+\d+)?\s*'", title)
    if not minute_match:
        return None
    minute = int(minute_match.group(1))
    if not (1 <= minute <= 120):
        return None
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
        scorer = re.sub(r"\s*\d+.*$", "", dash_parts[1]).strip()
    return {"home": home, "homeScore": home_score, "awayScore": away_score,
            "away": away, "scorer": scorer, "minute": minute}


def extract_video_url(url):
    try:
        host = urllib.parse.urlparse(url).netloc.replace("www.", "")
        if host in VIDEO_HOSTS:
            return url
    except Exception:
        pass
    return None


def build_embed(url, post_id, subreddit):
    try:
        u = urllib.parse.urlparse(url)
        host = u.netloc.replace("www.", "")
        parts = [p for p in u.path.split("/") if p]
        vid_id = parts[-1] if parts else ""
        if host == "streamff.link":  return f"https://streamff.link/v/{vid_id}"
        if host == "streamff.com":   return f"https://streamff.com/v/{vid_id}"
        if host == "streamable.com": return f"https://streamable.com/e/{vid_id}"
        if host == "youtu.be":       return f"https://www.youtube.com/embed/{vid_id}"
        if host == "youtube.com":
            v = urllib.parse.parse_qs(u.query).get("v", [vid_id])[0]
            return f"https://www.youtube.com/embed/{v}"
    except Exception:
        pass
    return None


def match_key(home, away):
    return " vs ".join(sorted([home.lower(), away.lower()]))


def main():
    today_ts = today_utc_midnight_ts()
    print(f"Fetching goals since UTC midnight ({today_ts})...")

    posts = fetch_posts(today_ts)
    print(f"Total posts fetched: {len(posts)}")

    matches = {}

    for post in posts:
        title     = post.get("title", "")
        url       = post.get("url", "")
        post_id   = post.get("id", "")
        subreddit = post.get("subreddit", SUBREDDIT)
        created   = int(post.get("created_utc", 0))

        if created < today_ts:
            continue

        parsed = parse_title(title)
        if not parsed:
            continue

        video_url = extract_video_url(url)
        if not video_url:
            continue

        key = match_key(parsed["home"], parsed["away"])
        if key not in matches:
            matches[key] = {"home": parsed["home"], "away": parsed["away"], "goals": []}

        if any(g["postId"] == post_id for g in matches[key]["goals"]):
            continue

        direct_mp4 = None
        secure_media = post.get("secure_media") or {}
        reddit_video = secure_media.get("reddit_video") or {}
        if reddit_video.get("fallback_url"):
            direct_mp4 = reddit_video["fallback_url"]

        matches[key]["goals"].append({
            "postId":    post_id,
            "subreddit": subreddit,
            "permalink": f"https://redd.it/{post_id}",
            "scorer":    parsed["scorer"],
            "minute":    parsed["minute"],
            "homeScore": parsed["homeScore"],
            "awayScore": parsed["awayScore"],
            "videoUrl":  video_url,
            "videoEmbed": build_embed(url, post_id, subreddit),
            "directMp4": direct_mp4,
            "postedAt":  created * 1000,
        })

    for key in matches:
        matches[key]["goals"].sort(key=lambda g: (g["homeScore"] + g["awayScore"], g["minute"]))

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
