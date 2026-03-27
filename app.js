// ── Timezone config ──────────────────────────────────────────────
const TIMEZONES = [
  { label: 'Eastern (ET)',  iana: 'America/New_York' },
  { label: 'Central (CT)',  iana: 'America/Chicago' },
  { label: 'Mountain (MT)', iana: 'America/Denver' },
  { label: 'Pacific (PT)',  iana: 'America/Los_Angeles' },
];

let currentTZ   = localStorage.getItem('sotlive_tz') || 'America/New_York';
let currentSport = 'soccer'; // tracks which sport is active

function formatTime(kick_utc, iana) {
  if (!kick_utc) return null;
  try {
    return new Date(kick_utc).toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZone: iana,
    });
  } catch {
    return null;
  }
}

// ── League order (soccer) ─────────────────────────────────────────
const LEAGUE_ORDER = [
  'UEFA Champions League',
  'UEFA Europa League',
  'UEFA Europa Conference League',
  'Premier League',
  'MLS',
  'CONCACAF Champions Cup',
  'US Open Cup',
  'English FA Cup',
  'EFL Championship',
  'Serie A',
  'German Bundesliga',
  'La Liga',
  'Dutch Eredivisie',
  'USL Championship',
  'USL League One',
  'Liga MX',
  'World Cup Qualifying',
  'International Friendly',
  'Friendly',
];

// ── Helpers ───────────────────────────────────────────────────────
function tabLabel(key) {
  const year = key.slice(0, 4), mon = key.slice(4, 6), day = key.slice(6, 8);
  const d = new Date(`${year}-${mon}-${day}T12:00:00`);
  const label = d.toLocaleDateString('en-US', { weekday: 'long' });
  const short = d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  return { label, short };
}

function normalize(str) {
  return str.toLowerCase()
    .replace(/[áàä]/g, 'a').replace(/[éèë]/g, 'e')
    .replace(/[íìï]/g, 'i').replace(/[óòö]/g, 'o')
    .replace(/[úùü]/g, 'u')
    .replace(/\s+/g, ' ').trim();
}

function dedup(games) {
  const seen = [];
  const result = [];
  for (const g of games) {
    const key = normalize(g.match) + '|' + g.time;
    const existing = seen.find(s => s.key === key);
    if (existing) {
      if (!existing.game.source.includes(g.source)) {
        existing.game.source += ' · ' + g.source;
      }
    } else {
      const clone = { ...g };
      seen.push({ key, game: clone });
      result.push(clone);
    }
  }
  return result;
}

const BADGE_MAP = {
  'ESPN':             { cls: 'source-espn',    label: 'ESPN' },
  'ESPN2':            { cls: 'source-espn',    label: 'ESPN2' },
  'ESPN+':            { cls: 'source-espn',    label: 'ESPN+' },
  'ESPN Unlmtd':      { cls: 'source-espn',    label: 'UNLTD' },
  'Hulu':             { cls: 'source-espn',    label: 'Hulu' },
  'ABC':              { cls: 'source-espn',    label: 'ABC' },
  'ABC / ESPN+':      { cls: 'source-espn',    label: 'ABC / ESPN+' },
  'CBS':              { cls: 'source-cbs',     label: 'CBS' },
  'CBS / Paramount+': { cls: 'source-cbs',     label: 'CBS / P+' },
  'Paramount+':       { cls: 'source-cbs',     label: 'Paramount+' },
  'HBO Max':          { cls: 'source-cbs',     label: 'HBO Max' },
  'Max':              { cls: 'source-cbs',     label: 'Max' },
  'TNT':              { cls: 'source-cbs',     label: 'TNT' },
  'TBS':              { cls: 'source-cbs',     label: 'TBS' },
  'TBS / TNT':        { cls: 'source-cbs',     label: 'TBS / TNT' },
  'truTV':            { cls: 'source-cbs',     label: 'truTV' },
  'Peacock':          { cls: 'source-peacock', label: 'Peacock' },
  'NBC':              { cls: 'source-usa',     label: 'NBC' },
  'NBCSN':            { cls: 'source-usa',     label: 'NBCSN' },
  'USA Network':      { cls: 'source-usa',     label: 'USA Network' },
  'FOX':              { cls: 'source-fox',     label: 'FOX' },
  'FS1':              { cls: 'source-fox',     label: 'FS1' },
  'FS2':              { cls: 'source-fox',     label: 'FS2' },
  'Apple TV':         { cls: 'source-appletv', label: 'Apple TV' },
  'YouTube':          { cls: 'source-appletv', label: 'YouTube' },
  'NBA TV':           { cls: 'source-espn',    label: 'NBA TV' },
  'NHL Network':      { cls: 'source-espn',    label: 'NHL Network' },
  'MLB Network':      { cls: 'source-espn',    label: 'MLB Network' },
  'Netflix':          { cls: 'source-netflix',  label: 'Netflix' },
};

function buildMatchHtml(g) {
  const parts = g.match.split(' vs ');
  const homeName = parts[0] || g.match;
  const awayName = parts[1] || '';
  if (!awayName) return `<span class="game-match">${g.match}</span>`;
  const homeLogo = g.home_logo ? `<img src="${g.home_logo}" class="team-logo" alt="">` : '<span class="team-logo-placeholder"></span>';
  const awayLogo = g.away_logo ? `<img src="${g.away_logo}" class="team-logo" alt="">` : '<span class="team-logo-placeholder team-logo-placeholder--away"></span>';
  return `<span class="game-match">
    <span class="match-team">${homeLogo}<span class="team-name">${homeName}</span></span>
    <span class="match-vs">vs</span>
    <span class="match-team">${awayLogo}<span class="team-name">${awayName}</span></span>
  </span>`;
}

function sourceBadge(src) {
  if (!src) return `<div class="badge-stack"><span class="source-badge source-postponed">😵</span></div>`;

  const badges = src.split(' · ')
    .sort((a, b) => a.trim().length - b.trim().length)
    .map(s => {
      const label = s.trim();
      const b = BADGE_MAP[label];
      if (b) return `<span class="source-badge ${b.cls}" data-label="${b.label}">${b.label}</span>`;
      return `<span class="source-badge source-appletv" data-label="${label}">${label}</span>`;
    }).join('');
  return `<div class="badge-stack">${badges}</div>`;
}

// ── Timezone picker ───────────────────────────────────────────────
function buildTzPicker() {
  const wrapper = document.getElementById('tz-picker');
  if (!wrapper) return;

  const select = document.createElement('select');
  select.className = 'tz-select';
  select.id = 'tz-select';

  TIMEZONES.forEach(tz => {
    const opt = document.createElement('option');
    opt.value = tz.iana;
    opt.textContent = tz.label;
    if (tz.iana === currentTZ) opt.selected = true;
    select.appendChild(opt);
  });

  select.addEventListener('change', () => {
    currentTZ = select.value;
    localStorage.setItem('sotlive_tz', currentTZ);
    refreshAllTimes();
  });

  wrapper.appendChild(select);
}

function hideTzPicker() {
  const picker = document.getElementById('tz-picker');
  if (picker) picker.style.display = 'none';
}

function showTzPicker() {
  const picker = document.getElementById('tz-picker');
  if (picker) picker.style.display = '';
}

// ── League filter ─────────────────────────────────────────────────
function buildLeagueFilter() {
  const wrapper = document.getElementById('league-filter');
  if (!wrapper) return;

  const select = document.createElement('select');
  select.className = 'tz-select';
  select.id = 'league-select';

  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = 'Show All';
  select.appendChild(defaultOpt);

  select.addEventListener('change', () => {
    applyLeagueFilter(select.value);
  });

  wrapper.appendChild(select);
}

function populateLeagueFilter(leagues) {
  const select = document.getElementById('league-select');
  if (!select) return;

  while (select.options.length > 1) select.remove(1);

  if (leagues.length <= 1) {
    select.disabled = true;
    select.value = '';
    return;
  }

  select.disabled = false;

  const sorted = leagues.slice().sort((a, b) => {
    const ai = LEAGUE_ORDER.indexOf(a);
    const bi = LEAGUE_ORDER.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  sorted.forEach(league => {
    const opt = document.createElement('option');
    opt.value = league;
    opt.textContent = league;
    select.appendChild(opt);
  });

  select.value = '';
}

function applyLeagueFilter(selectedLeague) {
  const activePanel = document.querySelector('.day-panel.active');
  if (!activePanel) return;

  activePanel.querySelectorAll('.league-group').forEach(group => {
    if (!selectedLeague) {
      group.style.display = '';
    } else {
      const label = group.querySelector('.league-label');
      group.style.display = (label && label.textContent.trim() === selectedLeague) ? '' : 'none';
    }
  });
}

function hideLeagueFilter() {
  const el = document.getElementById('league-filter');
  if (el) el.style.display = 'none';
}

function showLeagueFilter() {
  const el = document.getElementById('league-filter');
  if (el) el.style.display = '';
}

function resetLeagueFilter() {
  const select = document.getElementById('league-select');
  if (select) select.value = '';
  applyLeagueFilter('');
}

// ── Refresh times ─────────────────────────────────────────────────
function refreshAllTimes() {
  document.querySelectorAll('.game-card[data-utc]').forEach(card => {
    const utc = card.dataset.utc;
    const timeEl = card.querySelector('.game-time');
    if (timeEl && utc) {
      const formatted = formatTime(utc, currentTZ);
      if (formatted) timeEl.textContent = formatted;
    }
  });
}

// ── Render a soccer day panel ─────────────────────────────────────
function buildPanel(key, day) {
  const panel = document.createElement('div');
  panel.className = 'day-panel';
  panel.id = `panel-${key}`;

  const games = day.games || [];
  const todayKey = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }).replace(/-/g, '');
  const goalfeedBanner = key === todayKey ? `
    <a href="soccer-goals.html" class="goalfeed-banner">
      <span class="goalfeed-banner-icon">🥅</span>
      <span class="goalfeed-banner-text"><span class="goalfeed-green">GOAL</span>FEED</span>
    </a>` : '';

  if (games.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = goalfeedBanner + '<div class="empty"><div class="empty-icon">🏟️</div>No matches scheduled.</div>';
    return panel;
  }

  const grouped = {};
  for (const g of games) {
    if (!grouped[g.league]) grouped[g.league] = { items: [] };
    grouped[g.league].items.push(g);
  }

  const PRIORITY_LEAGUES = ['World Cup Qualifying', 'International Friendly', 'Friendly'];

  const sortedGrouped = Object.fromEntries(
    Object.entries(grouped).sort(([a], [b]) => {
      const aPriority = PRIORITY_LEAGUES.includes(a);
      const bPriority = PRIORITY_LEAGUES.includes(b);
      if (aPriority && !bPriority) return -1;
      if (!aPriority && bPriority) return 1;
      const ai = LEAGUE_ORDER.indexOf(a);
      const bi = LEAGUE_ORDER.indexOf(b);
      const aOrder = ai === -1 ? LEAGUE_ORDER.length : ai;
      const bOrder = bi === -1 ? LEAGUE_ORDER.length : bi;
      return aOrder - bOrder;
    })
  );

  panel.dataset.leagues = JSON.stringify(Object.keys(sortedGrouped));

  let html = goalfeedBanner;
  for (const [league, info] of Object.entries(sortedGrouped)) {
    const isUefa = ['UEFA Champions League', 'UEFA Europa League', 'UEFA Europa Conference League'].includes(league);
    html += `<div class="league-group"><div class="league-label${isUefa ? ' uefa' : ''}">${league}</div>`;
    for (const g of info.items) {
      const NON_TIMES = new Set(['canceled','cancelled','postponed','suspended','delayed','tbd']);
      const isNonTime = NON_TIMES.has(g.time.trim().toLowerCase());
      const displayTime = (!isNonTime && g.kick_utc ? formatTime(g.kick_utc, currentTZ) : null) || g.time;
      const utcAttr = (!isNonTime && g.kick_utc) ? `data-utc="${g.kick_utc}"` : '';
      let roundLine = '';
      if (g.round_label) {
        const parts = g.round_label.split(' · ');
        const roundName = parts[0];
        const legPart = parts[1] ? `<div class="leg-label">${parts[1]}</div>` : '';
        roundLine = `<div class="round-label">${roundName}</div>${legPart}`;
      }
      html += `<div class="game-card" ${utcAttr}>
        <div class="game-card-left">
          ${roundLine}
          <span class="game-time">${displayTime}</span>
        </div>
        ${buildMatchHtml(g)}
        ${sourceBadge(g.source)}
      </div>`;
    }
    html += `</div>`;
  }
  panel.innerHTML = html;
  return panel;
}

// ── Render an NCAA day panel ──────────────────────────────────────
function buildNcaaPanel(key, day) {
  const panel = document.createElement('div');
  panel.className = 'day-panel ncaa-panel';
  panel.id = `ncaa-panel-${key}`;

  const games = day.games || [];
  if (games.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = '<div class="empty"><div class="empty-icon">🏀</div>No games scheduled.</div>';
    return panel;
  }

  // Group by tourney_round (if set) or conference
  const grouped = {};
  for (const g of games) {
    const groupKey = g.tourney_round || g.conference || 'Other';
    if (!grouped[groupKey]) grouped[groupKey] = [];
    grouped[groupKey].push(g);
  }

  panel.dataset.leagues = JSON.stringify(Object.keys(grouped));

  let html = '';
  for (const [groupName, items] of Object.entries(grouped)) {
    html += `<div class="league-group"><div class="league-label">${groupName}</div>`;
    for (const g of items) {
      const NON_TIMES = new Set(['canceled','cancelled','postponed','suspended','delayed','tbd']);
      const isNonTime = NON_TIMES.has(g.time.trim().toLowerCase());
      const displayTime = (!isNonTime && g.kick_utc ? formatTime(g.kick_utc, currentTZ) : null) || g.time;
      const utcAttr = (!isNonTime && g.kick_utc) ? `data-utc="${g.kick_utc}"` : '';
      html += `<div class="game-card" ${utcAttr}>
        <div class="game-card-left">
          <span class="game-time">${displayTime}</span>
        </div>
        ${buildMatchHtml(g)}
        ${sourceBadge(g.source)}
      </div>`;
    }
    html += `</div>`;
  }
  panel.innerHTML = html;
  return panel;
}

// ── Render an NBA day panel ───────────────────────────────────────
function buildNbaPanel(key, day) {
  const panel = document.createElement('div');
  panel.className = 'day-panel nba-panel';
  panel.id = `nba-panel-${key}`;

  const games = day.games || [];
  if (games.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = '<div class="empty"><div class="empty-icon">☄️</div>No games scheduled.</div>';
    return panel;
  }

  const grouped = {};
  for (const g of games) {
    const groupKey = g.group || 'Regular Season';
    if (!grouped[groupKey]) grouped[groupKey] = [];
    grouped[groupKey].push(g);
  }

  panel.dataset.leagues = JSON.stringify(Object.keys(grouped));

  let html = '';
  for (const [groupName, items] of Object.entries(grouped)) {
    html += `<div class="league-group"><div class="league-label">${groupName}</div>`;
    for (const g of items) {
      const NON_TIMES = new Set(['canceled','cancelled','postponed','suspended','delayed','tbd']);
      const isNonTime = NON_TIMES.has(g.time.trim().toLowerCase());
      const displayTime = (!isNonTime && g.kick_utc ? formatTime(g.kick_utc, currentTZ) : null) || g.time;
      const utcAttr = (!isNonTime && g.kick_utc) ? `data-utc="${g.kick_utc}"` : '';
      html += `<div class="game-card" ${utcAttr}>
        <div class="game-card-left">
          <span class="game-time">${displayTime}</span>
        </div>
        ${buildMatchHtml(g)}
        ${sourceBadge(g.source)}
      </div>`;
    }
    html += `</div>`;
  }
  panel.innerHTML = html;
  return panel;
}

// ── Render an NHL day panel ───────────────────────────────────────
function buildNhlPanel(key, day) {
  const panel = document.createElement('div');
  panel.className = 'day-panel nhl-panel';
  panel.id = `nhl-panel-${key}`;

  const games = day.games || [];
  if (games.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = '<div class="empty"><div class="empty-icon">🏒</div>No games scheduled.</div>';
    return panel;
  }

  const grouped = {};
  for (const g of games) {
    const groupKey = g.group || 'Regular Season';
    if (!grouped[groupKey]) grouped[groupKey] = [];
    grouped[groupKey].push(g);
  }

  panel.dataset.leagues = JSON.stringify(Object.keys(grouped));

  let html = '';
  for (const [groupName, items] of Object.entries(grouped)) {
    html += `<div class="league-group"><div class="league-label">${groupName}</div>`;
    for (const g of items) {
      const NON_TIMES = new Set(['canceled','cancelled','postponed','suspended','delayed','tbd']);
      const isNonTime = NON_TIMES.has(g.time.trim().toLowerCase());
      const displayTime = (!isNonTime && g.kick_utc ? formatTime(g.kick_utc, currentTZ) : null) || g.time;
      const utcAttr = (!isNonTime && g.kick_utc) ? `data-utc="${g.kick_utc}"` : '';
      html += `<div class="game-card" ${utcAttr}>
        <div class="game-card-left">
          <span class="game-time">${displayTime}</span>
        </div>
        ${buildMatchHtml(g)}
        ${sourceBadge(g.source)}
      </div>`;
    }
    html += `</div>`;
  }
  panel.innerHTML = html;
  return panel;
}

// ── Render an MLB day panel ───────────────────────────────────────
function buildMlbPanel(key, day) {
  const panel = document.createElement('div');
  panel.className = 'day-panel mlb-panel';
  panel.id = `mlb-panel-${key}`;

  const games = day.games || [];
  if (games.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = '<div class="empty"><div class="empty-icon">⚾</div>No games scheduled.</div>';
    return panel;
  }

  const grouped = {};
  for (const g of games) {
    const groupKey = g.group || 'Regular Season';
    if (!grouped[groupKey]) grouped[groupKey] = [];
    grouped[groupKey].push(g);
  }

  panel.dataset.leagues = JSON.stringify(Object.keys(grouped));

  let html = '';
  for (const [groupName, items] of Object.entries(grouped)) {
    html += `<div class="league-group"><div class="league-label">${groupName}</div>`;
    for (const g of items) {
      const NON_TIMES = new Set(['canceled','cancelled','postponed','suspended','delayed','tbd']);
      const isNonTime = NON_TIMES.has(g.time.trim().toLowerCase());
      const displayTime = (!isNonTime && g.kick_utc ? formatTime(g.kick_utc, currentTZ) : null) || g.time;
      const utcAttr = (!isNonTime && g.kick_utc) ? `data-utc="${g.kick_utc}"` : '';
      html += `<div class="game-card" ${utcAttr}>
        <div class="game-card-left">
          <span class="game-time">${displayTime}</span>
        </div>
        ${buildMatchHtml(g)}
        ${sourceBadge(g.source)}
      </div>`;
    }
    html += `</div>`;
  }
  panel.innerHTML = html;
  return panel;
}

// ── Render a Netflix panel ────────────────────────────────────────
function buildNetflixPanel(data) {
  const panel = document.createElement('div');
  panel.className = 'day-panel';
  panel.id = 'panel-netflix';

  const groups = data.groups || {};
  const keys   = Object.keys(groups);

  if (keys.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = '<div class="empty"><div class="empty-icon">🎬</div>No new releases this week.</div>';
    return panel;
  }

  let html = `<div class="netflix-week-label">${data.week_label || ''}</div>`;

  for (const [groupName, shows] of Object.entries(groups)) {
    html += `<div class="league-group"><div class="netflix-group-label">${groupName}</div>`;
    for (const show of shows) {
      const genres  = show.genres && show.genres.length ? show.genres.join(', ') : '';
      const genreEl = genres ? `<div class="netflix-genres">${genres}</div>` : '';
      const overviewEl = show.overview
        ? `<div class="netflix-overview">${show.overview}</div>`
        : '';
      html += `
        <div class="netflix-card">
          <div class="netflix-card-header">
            <span class="netflix-title">${show.title}</span>
            <span class="netflix-date">${show.added_date || ''}</span>
          </div>
          ${genreEl}
          ${overviewEl}
        </div>`;
    }
    html += `</div>`;
  }

  panel.innerHTML = html;
  return panel;
}
// Sports that never show the league filter
const NO_LEAGUE_FILTER_SPORTS = new Set(['nba', 'nhl', 'mlb']);

function switchTab(key) {
  const prefix = currentSport === 'ncaa' ? 'ncaa-panel'
               : currentSport === 'nba'  ? 'nba-panel'
               : currentSport === 'nhl'  ? 'nhl-panel'
               : currentSport === 'mlb'  ? 'mlb-panel'
               : 'panel';

  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.key === key);
  });
  document.querySelectorAll('.day-panel').forEach(p => {
    p.classList.toggle('active', p.id === `${prefix}-${key}`);
  });
  document.getElementById('about-panel').classList.remove('active');
  document.getElementById('content').style.display = '';

  const activePanel = document.getElementById(`${prefix}-${key}`);
  const isEmpty = activePanel && activePanel.dataset.empty === 'true';
  const alwaysBothDropdowns = currentSport === 'soccer' || currentSport === 'ncaa';
  const tzSelect = document.getElementById('tz-select');

  if (alwaysBothDropdowns) {
    // Soccer + NCAA: always show both dropdowns, disable when empty
    showTzPicker();
    showLeagueFilter();
    if (isEmpty) {
      if (tzSelect) tzSelect.disabled = true;
      populateLeagueFilter([]);
    } else {
      if (tzSelect) tzSelect.disabled = false;
      const leagues = activePanel.dataset.leagues ? JSON.parse(activePanel.dataset.leagues) : [];
      populateLeagueFilter(leagues);
      resetLeagueFilter();
    }
  } else if (isEmpty) {
    // NBA/NHL/MLB empty: show timezone (disabled), hide league filter
    showTzPicker();
    if (tzSelect) tzSelect.disabled = true;
    hideLeagueFilter();
  } else {
    // NBA/NHL/MLB with games: show timezone only, never show league filter
    showTzPicker();
    if (tzSelect) tzSelect.disabled = false;
    hideLeagueFilter();
  }
}

function switchToAbout() {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('about-tab').classList.add('active');
  document.querySelectorAll('.day-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('content').style.display = 'none';
  document.getElementById('about-panel').classList.add('active');

  // Change 2: always hide both dropdowns on About
  hideTzPicker();
  hideLeagueFilter();
}

// ── Sport switching ───────────────────────────────────────────────
async function switchSport(sport) {
  if (sport === currentSport) return;
  currentSport = sport;

  // Update sport nav button styles
  document.querySelectorAll('.sport-btn').forEach(b => {
    b.classList.toggle('active', b.id === `sport-${sport}`);
  });

  // Clear existing tabs and panels
  const tabsEl    = document.getElementById('tabs');
  const contentEl = document.getElementById('content');
  tabsEl.innerHTML    = '';
  contentEl.innerHTML = '';

  // Always reset about panel state when switching sports
  document.getElementById('about-panel').classList.remove('active');
  contentEl.style.display = '';

  // Hide pickers — netflix doesn't use them
  hideTzPicker();
  hideLeagueFilter();
  resetLeagueFilter();

  // Local TV — coming soon placeholder
  if (sport === 'localtv') {
    contentEl.innerHTML = '<div class="empty"><div class="empty-icon">🐰</div>Coming soon.</div>';
    return;
  }

  // Netflix and HBO Max share the same tile layout — no day tabs
  if (sport === 'netflix' || sport === 'hbo' || sport === 'prime' || sport === 'appletv') {
    const jsonFile = sport === 'hbo' ? 'hbo.json' : sport === 'prime' ? 'prime.json' : sport === 'appletv' ? 'appletv.json' : 'netflix.json';
    let data;
    try {
      const res = await fetch(jsonFile + '?v=' + Math.floor(Date.now() / 3600000));
      data = await res.json();
    } catch (e) {
      contentEl.innerHTML =
        '<div class="empty"><div class="empty-icon">⚠️</div>Whoopsies — we\'re working to get releases shown.</div>';
      return;
    }

    const groups = data.groups || {};
    const groupNames = Object.keys(groups).filter(k => groups[k].length > 0);

    if (groupNames.length === 0) {
      const emptyIcon = sport === 'hbo' ? '📼' : sport === 'prime' ? '📦' : sport === 'appletv' ? '🍎' : '🎬';
      contentEl.innerHTML =
        `${data.week_label ? `<div class="netflix-week-label">${data.week_label}</div>` : ''}<div class="empty"><div class="empty-icon">${emptyIcon}</div>No new releases this month.</div>`;
      const aboutBtn = document.createElement('button');
      aboutBtn.className = 'tab';
      aboutBtn.id = 'about-tab';
      aboutBtn.textContent = 'About';
      aboutBtn.addEventListener('click', switchToAbout);
      tabsEl.appendChild(aboutBtn);
      return;
    }

    const PAGE_SIZE = 30;

    function buildCardHTML(show) {
      const genres = show.genres && show.genres.length ? show.genres.join(', ') : '';
      const genreEl = genres ? `<div class="netflix-genres">${genres}</div>` : '';
      const ratingEl = (show.rating != null && show.rating > 0)
        ? `<div class="netflix-rating"><span class="netflix-rating-label">Rating</span> <span class="netflix-rating-score">${show.rating}</span><span class="netflix-rating-max">/100</span></div>`
        : '';
      const overviewEl = show.overview
        ? `<div class="netflix-overview-wrap">
             <div class="netflix-overview netflix-overview-clamped">${show.overview}</div>
             <button class="netflix-show-more" onclick="toggleOverview(event,this)" type="button">Show more</button>
           </div>`
        : '';
      const posterEl = show.thumbnail
        ? (show.link
            ? `<a href="${show.link}" target="_blank" rel="noopener" class="netflix-poster" style="display:block;padding:0;"><img src="${show.thumbnail}" alt="${show.title}" loading="lazy" decoding="async" width="140" height="210" style="display:block;width:100%;height:100%;object-fit:cover;"></a>`
            : `<img class="netflix-poster" src="${show.thumbnail}" alt="${show.title}" loading="lazy" decoding="async" width="140" height="210">`)
        : `<div class="netflix-poster-placeholder">${sport === 'hbo' ? '📼' : sport === 'prime' ? '📦' : sport === 'appletv' ? '🍎' : '🎬'}</div>`;
      const cardInner = `
        ${posterEl}
        <div class="netflix-card-body">
          <div class="netflix-card-header">
            <span class="netflix-title">${show.title}</span>
            <span class="netflix-date">${show.added_date || ''}</span>
          </div>
          ${genreEl}
          ${ratingEl}
          ${overviewEl}
        </div>`;
      return `<div class="netflix-card">${cardInner}</div>`;
    }

    function checkShowMoreButtons(grid) {
      requestAnimationFrame(() => {
        grid.querySelectorAll('.netflix-overview-wrap').forEach(wrap => {
          const overview = wrap.querySelector('.netflix-overview');
          const btn = wrap.querySelector('.netflix-show-more');
          if (overview && btn && overview.scrollHeight <= overview.clientHeight + 2) {
            btn.style.display = 'none';
          }
        });
      });
    }

    let activeGenre = '';

    const streamingState = {};
    const streamingPanels = {};

    function appendNextPage(panelId) {
      const state = streamingState[panelId];
      if (!state || state.offset >= state.shows.length) return;
      const slice = state.shows.slice(state.offset, state.offset + PAGE_SIZE);
      state.offset += slice.length;
      const frag = document.createDocumentFragment();
      const tmp = document.createElement('div');
      tmp.innerHTML = slice.map(buildCardHTML).join('');
      while (tmp.firstChild) frag.appendChild(tmp.firstChild);
      state.grid.insertBefore(frag, state.sentinel);
      checkShowMoreButtons(state.grid);
      if (state.offset >= state.shows.length) {
        state.sentinel.remove();
        state.observer.disconnect();
      }
    }

    groupNames.forEach((groupName, idx) => {
      const panelId = `panel-${sport}-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
      const shows = groups[groupName];

      const panel = document.createElement('div');
      panel.className = 'day-panel';
      panel.id = panelId;

      const grid = document.createElement('div');
      grid.className = 'netflix-grid';

      const sentinel = document.createElement('div');
      sentinel.className = 'netflix-sentinel';
      sentinel.style.cssText = 'height:1px;margin-top:40px;';
      grid.appendChild(sentinel);

      const observer = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting && panel.classList.contains('active')) appendNextPage(panelId);
      }, { rootMargin: '400px' });
      observer.observe(sentinel);

      streamingState[panelId] = { shows, offset: 0, grid, sentinel, observer };

      // Only show genres that exist in THIS panel's shows
      const panelGenres = [...new Set(shows.flatMap(s => s.genres || []))].sort();

      let headerHTML = `<div class="netflix-week-label">${data.week_label || ''}</div>`;
      headerHTML += `<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:20px;">`;
      headerHTML += `<div class="netflix-section-title" style="margin-bottom:0;">${groupName}</div>`;
      if (panelGenres.length) {
        headerHTML += `<select class="tz-select genre-select" style="font-size:10px;" data-panel="${panelId}"><option value="">All Genres</option>${panelGenres.map(g=>`<option value="${g}">${g}</option>`).join('')}</select>`;
      } else {
        headerHTML += `<select class="tz-select" style="font-size:10px;" disabled><option>All Genres</option></select>`;
      }
      headerHTML += `</div>`;
      panel.innerHTML = headerHTML;
      panel.querySelector('.genre-select')?.addEventListener('change', function() {
        const genre = this.value;
        activeGenre = genre;
        panel.querySelectorAll('.netflix-card, a.netflix-card').forEach(card => {
          if (!genre) { card.style.display = ''; return; }
          const genreEl = card.querySelector('.netflix-genres');
          card.style.display = (genreEl && genreEl.textContent.includes(genre)) ? '' : 'none';
        });
      });
      panel.appendChild(grid);
      contentEl.appendChild(panel);
      streamingPanels[panelId] = panel;

      if (idx === 0) appendNextPage(panelId);
    });

    function activateStreamingPanel(panelId, tabBtn) {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tabBtn.classList.add('active');
      document.getElementById('about-panel').classList.remove('active');
      contentEl.style.display = '';
      Object.values(streamingPanels).forEach(p => p.classList.remove('active'));
      streamingPanels[panelId].classList.add('active');
      hideTzPicker();
      hideLeagueFilter();
      const state = streamingState[panelId];
      if (state && state.offset === 0) appendNextPage(panelId);
      // Reset genre filter
      activeGenre = '';
      const sel = streamingPanels[panelId].querySelector('.genre-select');
      if (sel) sel.value = '';
    }

    let firstTab = true;
    groupNames.forEach(groupName => {
      const panelId = `panel-${sport}-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
      const btn = document.createElement('button');
      btn.className = 'tab' + (firstTab ? ' active' : '');
      btn.textContent = groupName;
      btn.addEventListener('click', () => activateStreamingPanel(panelId, btn));
      tabsEl.appendChild(btn);
      if (firstTab) streamingPanels[panelId].classList.add('active');
      firstTab = false;
    });

    const aboutBtn = document.createElement('button');
    aboutBtn.className = 'tab';
    aboutBtn.id = 'about-tab';
    aboutBtn.textContent = 'About';
    aboutBtn.addEventListener('click', switchToAbout);
    tabsEl.appendChild(aboutBtn);
    return;
  }

  // Load the correct JSON for sports
  const file = sport === 'ncaa' ? 'ncaa_basketball.json'
             : sport === 'nba'  ? 'nba.json'
             : sport === 'nhl'  ? 'nhl.json'
             : sport === 'mlb'  ? 'mlb.json'
             : 'schedule.json';
  let data;
  try {
    const res = await fetch(`${file}?v=` + Date.now());
    data = await res.json();
  } catch (e) {
    contentEl.innerHTML =
      '<div class="empty"><div class="empty-icon">⚠️</div>Whoopsies — we\'re working to get games shown.</div>';
    return;
  }

  // Build tabs and panels for sports
  const dateKeys  = Object.keys(data.days);
  let firstActive = true;

  dateKeys.forEach((key) => {
    const day = data.days[key];
    const { label, short } = tabLabel(key);

    const btn = document.createElement('button');
    btn.className = 'tab' + (firstActive ? ' active' : '');
    btn.dataset.key = key;
    btn.innerHTML = `${label}<span class="tab-day">${short}</span>`;
    btn.addEventListener('click', () => switchTab(key));
    tabsEl.appendChild(btn);

    const panel = sport === 'ncaa' ? buildNcaaPanel(key, day)
                : sport === 'nba'  ? buildNbaPanel(key, day)
                : sport === 'nhl'  ? buildNhlPanel(key, day)
                : sport === 'mlb'  ? buildMlbPanel(key, day)
                : buildPanel(key, day);

    if (firstActive) panel.classList.add('active');
    contentEl.appendChild(panel);
    firstActive = false;
  });

  // About tab
  const aboutBtn = document.createElement('button');
  aboutBtn.className = 'tab';
  aboutBtn.id = 'about-tab';
  aboutBtn.textContent = 'About';
  aboutBtn.addEventListener('click', switchToAbout);
  tabsEl.appendChild(aboutBtn);

  // Handle initial state
  const tzSelect = document.getElementById('tz-select');
  const alwaysBothDropdowns = sport === 'soccer' || sport === 'ncaa';

  const firstKey = dateKeys[0];
  if (firstKey) {
    const prefix = sport === 'ncaa' ? 'ncaa-panel'
                 : sport === 'nba'  ? 'nba-panel'
                 : sport === 'nhl'  ? 'nhl-panel'
                 : sport === 'mlb'  ? 'mlb-panel'
                 : 'panel';
    const firstPanel = document.getElementById(`${prefix}-${firstKey}`);
    const isEmpty = firstPanel && firstPanel.dataset.empty === 'true';

    if (alwaysBothDropdowns) {
      // Soccer + NCAA: always show both dropdowns, disable when empty
      showTzPicker();
      showLeagueFilter();
      if (isEmpty) {
        if (tzSelect) tzSelect.disabled = true;
        populateLeagueFilter([]);
      } else if (firstPanel) {
        if (tzSelect) tzSelect.disabled = false;
        const leagues = firstPanel.dataset.leagues ? JSON.parse(firstPanel.dataset.leagues) : [];
        populateLeagueFilter(leagues);
      }
    } else if (isEmpty) {
      // NBA/NHL/MLB empty: show timezone (disabled), hide league filter
      showTzPicker();
      if (tzSelect) tzSelect.disabled = true;
      hideLeagueFilter();
    } else if (firstPanel) {
      // NBA/NHL/MLB with games: show timezone only
      showTzPicker();
      if (tzSelect) tzSelect.disabled = false;
      hideLeagueFilter();
    }
  }
}

// ── Contact form ──────────────────────────────────────────────────
async function submitContact() {
  const name    = document.getElementById('cf-name').value.trim();
  const email   = document.getElementById('cf-email').value.trim();
  const subject = document.getElementById('cf-subject').value.trim();
  const message = document.getElementById('cf-message').value.trim();
  const status  = document.getElementById('cf-status');
  const btn     = document.getElementById('cf-submit');

  if (!name || !email || !subject || !message) {
    status.className = 'contact-status error';
    status.textContent = 'Please fill in all fields.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Sending…';
  status.textContent = '';

  try {
    const res = await fetch('https://xh66q28v71.execute-api.us-east-2.amazonaws.com/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'sotlive', name, email, subject, message })
    });

    if (res.ok) {
      status.className = 'contact-status success';
      status.textContent = '✓ Message sent! We\'ll get back to you soon.';
      document.getElementById('cf-name').value    = '';
      document.getElementById('cf-email').value   = '';
      document.getElementById('cf-subject').value = '';
      document.getElementById('cf-message').value = '';
    } else {
      throw new Error('Server error');
    }
  } catch (e) {
    status.className = 'contact-status error';
    status.textContent = 'Something went wrong. Please try again.';
  }

  btn.textContent = 'Send Message';
  btn.disabled = false;
}

// ── Netflix "Show more" toggle ────────────────────────────────────
function toggleOverview(e, btn) {
  e.preventDefault();
  e.stopPropagation();

  const overview = btn.previousElementSibling;
  const isClamped = overview.classList.contains('netflix-overview-clamped');

  if (isClamped) {
    overview.classList.remove('netflix-overview-clamped');
    btn.textContent = 'Show less';
  } else {
    overview.classList.add('netflix-overview-clamped');
    btn.textContent = 'Show more';
  }
}

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  let data;
  try {
    const res = await fetch('schedule.json?v=' + Date.now());
    data = await res.json();
  } catch (e) {
    const todayKey = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }).replace(/-/g, '');
    const goalfeedBanner = `<a href="soccer-goals.html" class="goalfeed-banner"><span class="goalfeed-banner-icon">🥅</span><span class="goalfeed-banner-text"><span class="goalfeed-green">GOAL</span>FEED</span></a>`;
    document.getElementById('content').innerHTML =
      goalfeedBanner + '<div class="empty"><div class="empty-icon">⚠️</div>Whoopsies — we\'re working to get games shown.</div>';
    hideTzPicker();
    hideLeagueFilter();
    return;
  }

  buildTzPicker();
  buildLeagueFilter();

  const tabsEl    = document.getElementById('tabs');
  const contentEl = document.getElementById('content');
  const dateKeys  = Object.keys(data.days);
  let firstActive = true;

  dateKeys.forEach((key) => {
    const day = data.days[key];
    const { label, short } = tabLabel(key);

    const btn = document.createElement('button');
    btn.className = 'tab' + (firstActive ? ' active' : '');
    btn.dataset.key = key;
    btn.innerHTML = `${label}<span class="tab-day">${short}</span>`;
    btn.addEventListener('click', () => switchTab(key));
    tabsEl.appendChild(btn);

    const panel = buildPanel(key, day);
    if (firstActive) panel.classList.add('active');
    contentEl.appendChild(panel);
    firstActive = false;
  });

  // About tab
  const aboutBtn = document.createElement('button');
  aboutBtn.className = 'tab';
  aboutBtn.id = 'about-tab';
  aboutBtn.textContent = 'About';
  aboutBtn.addEventListener('click', switchToAbout);
  tabsEl.appendChild(aboutBtn);

  // Handle initial state — soccer always shows both dropdowns
  const firstKey = dateKeys[0];
  if (firstKey) {
    const firstPanel = document.getElementById(`panel-${firstKey}`);
    const tzSelect = document.getElementById('tz-select');
    showTzPicker();
    showLeagueFilter();
    if (firstPanel && firstPanel.dataset.empty === 'true') {
      if (tzSelect) tzSelect.disabled = true;
      populateLeagueFilter([]);
    } else if (firstPanel) {
      if (tzSelect) tzSelect.disabled = false;
      const leagues = firstPanel.dataset.leagues ? JSON.parse(firstPanel.dataset.leagues) : [];
      populateLeagueFilter(leagues);
    }
  }

  // Show/hide NCAA Men, NBA, NHL buttons based on whether any games exist
  const sportChecks = [
    { id: 'sport-ncaa', file: 'ncaa_basketball.json' },
    { id: 'sport-nba',  file: 'nba.json' },
    { id: 'sport-nhl',  file: 'nhl.json' },
    { id: 'sport-mlb',  file: 'mlb.json' },
  ];
  for (const { id, file } of sportChecks) {
    try {
      const res  = await fetch(`${file}?v=` + Date.now());
      const data = await res.json();
      const hasGames = Object.values(data.days || {}).some(d => d.games && d.games.length > 0);
      const btn  = document.getElementById(id);
      if (btn) btn.style.display = hasGames ? '' : 'none';
    } catch (e) {
      const btn = document.getElementById(id);
      if (btn) btn.style.display = 'none';
    }
  }
}

init();
