# ⚽ SOTLive

An independent, non-commercial website listing football / soccer match broadcast schedules available to viewers in the United States. All times are displayed in Eastern Time (ET) — New York City.

Live site: https://db1111d.github.io/sotlive/

---

## Covered Competitions

| Competition | Broadcast Source |
|---|---|
| UEFA Champions League | CBS / Paramount+ |
| UEFA Europa League | CBS / Paramount+ |
| UEFA Europa Conference League | CBS / Paramount+ |
| Premier League | CBS / Paramount+ |
| English FA Cup | ESPN+ |
| EFL Championship | CBS / Paramount+ |
| Serie A | CBS / Paramount+ |
| German Bundesliga | ESPN+ |
| La Liga | ESPN+ |
| Dutch Eredivisie | ESPN+ |
| USL Championship | ESPN+ |

---

## How It Works

Schedule data is pulled from ESPN's API every 4 hours via GitHub Actions and written to schedule.json. The site reads that file and displays the next 5 days of matches grouped by league.

Games on Today's tab are automatically removed 4 hours after kickoff. If all games for a league are gone, the league disappears too.

---

## Setup

1. Fork this repo
2. Go to **Settings → Pages** → Deploy from branch → main / root → Save
3. Go to **Actions** → enable workflows
4. Go to **Actions → Update Soccer Schedule → Run workflow** to populate data for the first time

After that it runs automatically every 4 hours. You never touch it again.

---

## Manual Trigger

Go to **Actions → Update Soccer Schedule → Run workflow** at any time to force a refresh.

---

## Disclaimer

This website is an independent, unofficial resource and is not affiliated with, endorsed by, authorized by, or sponsored by any football league, governing body, club, team, player, or broadcast provider referenced herein. All league names, club names, competition names, logos, and trademarks are the sole property of their respective owners and are referenced for informational purposes only.

The information provided is furnished on an "as is" and "as available" basis without warranty of any kind. The operator expressly disclaims all liability for any loss, damage, or inconvenience arising from reliance on this data. Use of this website constitutes acceptance of these terms.
