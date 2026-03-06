# ⚽ Schedule

An independent, non-commercial website providing informational listings of football / soccer match broadcast schedules available to viewers within the United States. All times are displayed in Eastern Time (ET) — New York City.

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
| La Liga | ESPN+ / CBS |
| Dutch Eredivisie | ESPN+ |
| USL Championship | ESPN+ |

---

## Scope Limitations

This site does not include listings for Spanish-language exclusive broadcasts or women's competitions. Schedule data is sourced from publicly available third-party broadcast platforms and is subject to change without notice. Users are advised to confirm match times directly with the relevant broadcaster prior to viewing.

---

## How It Works

```
GitHub Actions (runs daily at 6AM UTC / 2AM Eastern)
        ↓
fetch_schedule.py scrapes ESPN & CBS Sports
        ↓
Filters & deduplicates across sources
        ↓
Writes schedule.json to the repo
        ↓
GitHub Pages serves index.html → reads schedule.json
```

---

## Setup

### 1. Fork / Clone This Repository

### 2. Enable GitHub Pages
- Go to **Settings → Pages**
- Set source to **Deploy from a branch**
- Select branch: `main`, folder: `/ (root)`
- Save — your site will be live at `https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/`

### 3. Enable GitHub Actions
- Go to the **Actions** tab
- If prompted, click "I understand my workflows, enable them"

### 4. Run Manually for the First Time
- Go to **Actions → Update Soccer Schedule → Run workflow**
- This generates the initial `schedule.json`

Subsequent runs execute automatically every day. No further action required.

---

## Run Locally

```bash
pip install playwright
playwright install chromium
python fetch_schedule.py
# Then open index.html in your browser
```

---

## Disclaimer & Limitation of Liability

This website is an independent, unofficial resource and is not affiliated with, endorsed by, authorized by, or sponsored by any football league, governing body, club, team, player, or broadcast provider referenced herein. All league names, club names, competition names, logos, and trademarks are the sole property of their respective owners and are referenced for informational purposes only.

The information provided on this website is furnished on an "as is" and "as available" basis, without warranty of any kind, express or implied, including but not limited to warranties of accuracy, completeness, fitness for a particular purpose, or non-infringement. The operator of this website expressly disclaims all liability for any loss, damage, inconvenience, or expense of any nature whatsoever — whether direct, indirect, incidental, consequential, or otherwise — arising out of or in connection with any reliance upon the schedule data, match times, broadcast information, or any other content displayed on this site. Use of this website constitutes acceptance of these terms.
