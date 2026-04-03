"""
fetch_goals.py
Fetches today's goal posts from r/soccer using the Arctic Shift API.
Cross-references against today's schedule to filter and canonicalize team names.
"""

import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

SUBREDDIT   = "soccer"
VIDEO_HOSTS = {"streamff.link", "streamff.com", "streamable.com",
               "youtu.be", "youtube.com", "v.redd.it", "streamain.com",
               "streamin.link", "streamin.top", "streamin.me"}

# Leagues to include — everything except USL Championship, USL League One, Dutch Eredivisie, EFL Championship, MLS, US Open Cup
ALLOWED_LEAGUES = {
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Europa Conference League",
    "Premier League",
    "CONCACAF Champions Cup",
    "English FA Cup",
    "Serie A",
    "German Bundesliga",
    "La Liga",
}

HEADERS = {
    "User-Agent": "sotlive-goalfeed/1.0",
    "Accept": "application/json",
}

WOMENS_TEAMS = {
    "angel city", "bay fc", "boston legacy", "chicago stars", "denver summit",
    "gotham fc", "houston dash", "kansas city current", "north carolina courage",
    "orlando pride", "portland thorns", "racing louisville", "san diego wave",
    "seattle reign", "utah royals", "washington spirit", "west ham w", "arsenal w",
    "chelsea fc w", "manchester city w", "manchester united w", "barcelona w",

    "lyon w", "chelsea w", "liverpool w", "tottenham w", "aston villa w",
}

def load_today_teams(schedule_path="schedule.json"):
    """
    Load today scheduled team pairs from schedule.json.
    Returns list of dicts: {home, away, league, home_norm, away_norm}
    Only includes games from ALLOWED_LEAGUES.
    """
    teams = []
    try:
        with open(schedule_path, encoding="utf-8") as f:
            data = json.load(f)
        for day in data.get("days", {}).values():
            for game in day.get("games", []):
                league = game.get("league", "")
                if league not in ALLOWED_LEAGUES:
                    continue
                match = game.get("match", "")
                if " vs " not in match:
                    continue
                home, away = match.split(" vs ", 1)
                teams.append({
                    "home":      home.strip(),
                    "away":      away.strip(),
                    "league":    league,
                    "home_norm": normalize_team(home.strip()),
                    "away_norm": normalize_team(away.strip()),
                })
    except Exception as e:
        print(f"  Warning: could not load schedule — {e}")
    return teams


def normalize_team(name):
    """Lowercase and strip punctuation for substring comparison."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def find_schedule_match(parsed_home, parsed_away, today_teams):
    """
    Match parsed Reddit team names against today's scheduled games using substring matching.
    At least one team name must be a substring of a scheduled team name or vice versa.
    Returns the matching scheduled game dict or None.
    """
    ph = normalize_team(parsed_home)
    pa = normalize_team(parsed_away)

    for game in today_teams:
        sh = game["home_norm"]
        sa = game["away_norm"]

        # Both teams must match — one alone causes false positives
        # e.g. "Sporting vs Santa Clara" wrongly mapping to "Sporting CP vs Arsenal"
        home_match = len(ph) >= 3 and (ph in sh or sh in ph)
        away_match = len(pa) >= 3 and (pa in sa or sa in pa)
        home_match_swap = len(ph) >= 3 and (ph in sa or sa in ph)
        away_match_swap = len(pa) >= 3 and (pa in sh or sh in pa)

        if (home_match and away_match) or (home_match_swap and away_match_swap):
            return game

    return None


def today_utc_midnight_ts():
    now = datetime.now(EASTERN)
    eastern_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(eastern_midnight.astimezone(timezone.utc).timestamp())

def fetch_posts(after_ts):
    """Paginate through all posts since after_ts using before= cursor."""
    all_posts = []
    before_ts = None

    while True:
        url = (
            f"https://arctic-shift.photon-reddit.com/api/posts/search"
            f"?subreddit={SUBREDDIT}&after={after_ts}&limit=100&sort=desc"
        )
        if before_ts is not None:
            url += f"&before={before_ts}"

        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                posts = data.get("data", [])
        except Exception as e:
            print(f"  Fetch error: {e}")
            break

        if not posts:
            break

        all_posts.extend(posts)
        print(f"  Fetched {len(posts)} posts (total so far: {len(all_posts)})")

        # Fewer than 100 means we've reached the start of the day
        if len(posts) < 100:
            break

        # Paginate backwards using the oldest post timestamp
        oldest_ts = min(int(p.get("created_utc", 0)) for p in posts)
        if oldest_ts <= after_ts:
            break
        before_ts = oldest_ts - 1

    return all_posts

def clean_team(name):
    name = re.sub(r'[\[\(][^\]\)]*[\]\)]', '', name)
    name = re.sub(r'\s*\|.*$', '', name)
    return name.strip()

def clean_scorer(scorer):
    scorer = re.sub(r'\bgreat goal\b', '', scorer, flags=re.IGNORECASE)
    scorer = re.sub(r'\s*\([^)]*\)\s*$', '', scorer)
    return scorer.strip()

def is_own_goal(title):
    return bool(re.search(
        r'\b(o\.?g\.?|own[\s-]goal|auto[\s-]?gol|but\s+contre\s+son\s+camp|csc|contre\s+son\s+camp|gol\s+en\s+contra|gol\s+propio)\b',
        title, re.IGNORECASE
    ))

def parse_title(title):
    if re.search(r"red card|yellow card|\bsave\b", title, re.IGNORECASE):
        return None
    # Filter out women's matches — W/F flag, or women's language in title
    if re.search(r'\b[WF]\b', title):
        return None
    if re.search(r'\b(femeni|femenino|femenina|feminino|feminina|women|womens|nwsl|wsl|uwcl)\b', title, re.IGNORECASE):
        return None
    # Filter out known women's teams
    title_lower = title.lower()
    if any(team in title_lower for team in WOMENS_TEAMS):
        return None

    minute_match = re.search(r"(?<!\d)(\d{1,3})(?:\+\d+)?\s*['\u2019\u2032\u02bc]", title)
    if minute_match:
        minute = int(minute_match.group(1))
        if not (1 <= minute <= 120):
            return None
    else:
        if not re.search(r'\[\d+\]', title):
            return None
        minute = None

    score_match = re.search(r"\[?(\d+)\]?\s*-\s*\[?(\d+)\]?", title)
    if not score_match:
        return None
    home_score = int(score_match.group(1))
    away_score = int(score_match.group(2))
    score_idx = title.index(score_match.group(0))
    home = clean_team(title[:score_idx])
    if not home or len(home) > 50 or ',' in home or '~' in home:
        return None
    after_score = title[score_idx + len(score_match.group(0)):].strip()
    # Support both " - " and " | " as separators between away team and scorer
    if " - " in after_score:
        dash_parts = after_score.split(" - ")
    elif " | " in after_score:
        dash_parts = after_score.split(" | ")
    else:
        dash_parts = [after_score]
    away = clean_team(dash_parts[0])
    if not away or len(away) > 50 or ',' in away or '~' in away:
        return None
    # Reject if away looks like a scorer — contains a minute marker or is all digits
    if re.search(r"\d+\s*['\u2019\u2032\u02bc]", away) or re.match(r"^\d+$", away):
        return None
    scorer = ""
    if len(dash_parts) > 1:
        # Try to extract minute from scorer string if not already found in title
        if minute is None:
            minute_in_scorer = re.search(r"(\d{1,3})(?:\+\d+)?\s*['\u2019\u2032\u02bc]", dash_parts[1])
            if minute_in_scorer:
                m = int(minute_in_scorer.group(1))
                if 1 <= m <= 120:
                    minute = m
        # Fallback: plain number at end of scorer string with no apostrophe (e.g. "Raul Ura 85 (Great commentary)")
        if minute is None:
            plain_minute = re.search(r"(?<!\d)(\d{1,3})(?:\+\d+)?\s*(?:\([^)]*\))?\s*$", dash_parts[1])
            if plain_minute:
                m = int(plain_minute.group(1))
                if 1 <= m <= 120:
                    minute = m
        scorer = clean_scorer(re.sub(r"\s*\d+['\+\u2019\u2032\u02bc].*$", "", re.sub(r"\s+\d{1,3}(?:\+\d+)?\s*(?:\([^)]*\))?\s*$", "", dash_parts[1])))
    if is_own_goal(title):
        scorer = "Own Goal"
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
        if host == "streamain.com":  return url
        if host == "streamin.link":  return None
        if host == "streamin.top":   return None
        if host == "streamin.me":    return None
    except Exception:
        pass
    return None

def match_key(home, away):
    return " vs ".join(sorted([clean_team(home).lower(), clean_team(away).lower()]))

def main():
    today_ts = today_utc_midnight_ts()
    print(f"Fetching goals since UTC midnight ({today_ts})...")

    posts = fetch_posts(today_ts)

    # Load today's scheduled teams for cross-reference filtering
    today_teams = load_today_teams()
    print(f"  Loaded {len(today_teams)} scheduled games for allowed leagues")

    # Seed from existing goals.json so early-morning goals persist all day
    matches = {}
    try:
        with open("goals.json", encoding="utf-8") as f:
            old = json.load(f)
        for m in old.get("matches", []):
            key = match_key(m["home"], m["away"])
            # Only keep goals from today — discard yesterday's
            m["goals"] = [g for g in m["goals"] if g["postedAt"] >= today_ts * 1000]
            if m["goals"]:
                matches[key] = m
    except Exception:
        pass  # First run or missing file — start fresh

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

        # Cross-reference against today's schedule — tag league if matched, else Rest of World
        scheduled = find_schedule_match(parsed["home"], parsed["away"], today_teams) if today_teams else None
        canon_home   = scheduled["home"]   if scheduled else parsed["home"]
        canon_away   = scheduled["away"]   if scheduled else parsed["away"]
        canon_league = scheduled["league"] if scheduled else "Rest of World"

        key = match_key(canon_home, canon_away)
        if key not in matches:
            matches[key] = {"home": canon_home, "away": canon_away, "league": canon_league, "goals": []}
        elif matches[key].get("league", "Rest of World") == "Rest of World" and canon_league != "Rest of World":
            # Upgrade league tag if we now have a better match
            matches[key]["league"] = canon_league

        # Dedup by score
        existing = next((g for g in matches[key]["goals"] if g["homeScore"] == parsed["homeScore"] and g["awayScore"] == parsed["awayScore"]), None)
        if existing:
            existing_is_reddit = existing["videoUrl"].startswith("https://v.redd.it")
            new_is_reddit = video_url.startswith("https://v.redd.it")
            if existing_is_reddit and not new_is_reddit:
                matches[key]["goals"].remove(existing)
            else:
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
            "videoEmbed": build_embed(url, post_id),
            "directMp4": direct_mp4,
            "postedAt":  created * 1000,
        })

    for key in matches:
        matches[key]["goals"].sort(key=lambda g: (g["homeScore"] + g["awayScore"], g["minute"] or 0))

    # Detect disallowed goals — sort by postedAt, compare consecutive goals.
    # If home score OR away score drops between posts, the previous goal was disallowed.
    for key in matches:
        goals_by_time = sorted(matches[key]["goals"], key=lambda g: g["postedAt"])
        for i in range(1, len(goals_by_time)):
            prev = goals_by_time[i - 1]
            curr = goals_by_time[i]
            if curr["homeScore"] < prev["homeScore"] or curr["awayScore"] < prev["awayScore"]:
                prev["disallowed"] = True

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
