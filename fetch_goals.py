"""
fetch_goals.py
Fetches today's goal posts from r/soccer using the Arctic Shift API.
"""

import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone

SUBREDDIT   = "soccer"
VIDEO_HOSTS = {"streamff.link", "streamff.com", "streamable.com",
               "youtu.be", "youtube.com", "v.redd.it", "streamain.com",
               "streamin.link", "streamin.top", "streamin.me"}

HEADERS = {
    "User-Agent": "sotlive-goalfeed/1.0",
    "Accept": "application/json",
}

def today_utc_midnight_ts():
    now = datetime.now(timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

def fetch_posts(after_ts):
    url = (
        f"https://arctic-shift.photon-reddit.com/api/posts/search"
        f"?subreddit={SUBREDDIT}&after={after_ts}&limit=100&sort=desc"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            posts = data.get("data", [])
            print(f"  Fetched {len(posts)} posts")
            return posts
    except Exception as e:
        print(f"  Fetch error: {e}")
        return []

def clean_team(name):
    # Strip anything in brackets/parens e.g. "[2-1 on agg.]", "(2-1 on agg.)"
    name = re.sub(r'[\[\(][^\]\)]*[\]\)]', '', name)
    # Strip trailing pipe and anything after e.g. "| agg. 2-1"
    name = re.sub(r'\s*\|.*$', '', name)
    return name.strip()

def clean_scorer(scorer):
    scorer = re.sub(r'\s*\|.*$', '', scorer)  # strip pipe and after
    scorer = re.sub(r'\bgreat goal\b', '', scorer, flags=re.IGNORECASE)
    scorer = re.sub(r'\s*\([^)]*\)\s*$', '', scorer)  # strip trailing (league name) etc
    return scorer.strip()

def parse_title(title):
    if re.search(r"red card|yellow card|\bsave\b", title, re.IGNORECASE):
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
    home = clean_team(title[:score_idx])
    if not home:
        return None
    after_score = title[score_idx + len(score_match.group(0)):].strip()
    dash_parts = after_score.split(" - ")
    away = clean_team(dash_parts[0])
    if not away:
        return None
    scorer = ""
    if len(dash_parts) > 1:
        scorer = clean_scorer(re.sub(r"\s*\d+['\+].*$", "", dash_parts[1]))
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

def build_embed(url, post_id):
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
        if host == "streamain.com":  return url  # direct link, no embed
        if host == "streamin.link":  return None  # blocks iframes, use link fallback
        if host == "streamin.top":   return None  # blocks iframes, use link fallback
        if host == "streamin.me":    return None  # blocks iframes, use link fallback
    except Exception:
        pass
    return None

def clean_team(name):
    # Strip anything in brackets/parens like "[2-1 on agg.]" or "(2-1 on agg.)"
    return re.sub(r'[\[\(][^\]\)]*[\]\)]', '', name).strip()

def match_key(home, away):
    return " vs ".join(sorted([clean_team(home).lower(), clean_team(away).lower()]))

def main():
    today_ts = today_utc_midnight_ts()
    print(f"Fetching goals since UTC midnight ({today_ts})...")

    posts = fetch_posts(today_ts)
    matches = {}

    for post in posts:
        title     = post.get("title", "")
        url       = post.get("url") or post.get("url_overridden_by_dest", "")
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

        # Check for duplicate by same minute (not just postId)
        existing = next((g for g in matches[key]["goals"] if g["minute"] == parsed["minute"]), None)
        if existing:
            # Prefer non-Reddit video over v.redd.it
            existing_is_reddit = existing["videoUrl"].startswith("https://v.redd.it")
            new_is_reddit = video_url.startswith("https://v.redd.it")
            if existing_is_reddit and not new_is_reddit:
                # Replace with better source
                matches[key]["goals"].remove(existing)
            else:
                continue  # keep existing, skip this one

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
            "videoEmbed": build_embed(url, post_id),
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
