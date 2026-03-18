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
  'ESPN+':            { cls: 'source-espn',    label: 'ESPN+' },
  'CBS / Paramount+': { cls: 'source-cbs',     label: 'CBS / P+' },
  'Peacock':          { cls: 'source-peacock', label: 'Peacock' },
  'USA Network':      { cls: 'source-usa',     label: 'USA Network' },
  'Apple TV':         { cls: 'source-appletv', label: 'Apple TV' },
  'FOX':              { cls: 'source-fox',     label: 'FOX' },
  'FS1':              { cls: 'source-fox',     label: 'FS1' },
  'FS2':              { cls: 'source-fox',     label: 'FS2' },
  'TBS / TNT':        { cls: 'source-cbs',     label: 'TBS / TNT' },
  'ABC / ESPN+':      { cls: 'source-espn',    label: 'ABC / ESPN+' },
  'YouTube':          { cls: 'source-appletv', label: 'YouTube' },
};

function sourceBadge(src) {
  if (!src) return `<div class="badge-stack"><span class="source-badge source-postponed">😵</span></div>`;
  const badges = src.split(' · ').map(s => {
    const b = BADGE_MAP[s.trim()];
    if (b) return `<span class="source-badge ${b.cls}">${b.label}</span>`;
    return `<span class="source-badge source-appletv">${s.trim()}</span>`;
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
  if (games.length === 0) {
    panel.dataset.empty = 'true';
    panel.innerHTML = '<div class="empty"><div class="empty-icon">🏟️</div>No matches scheduled.</div>';
    return panel;
  }

  const grouped = {};
  for (const g of games) {
    if (!grouped[g.league]) grouped[g.league] = { items: [] };
    grouped[g.league].items.push(g);
  }

  const sortedGrouped = Object.fromEntries(
    Object.entries(grouped).sort(([a], [b]) => {
      const ai = LEAGUE_ORDER.indexOf(a);
      const bi = LEAGUE_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    })
  );

  panel.dataset.leagues = JSON.stringify(Object.keys(sortedGrouped));

  let html = '';
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
        <span class="game-match">${g.match}</span>
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
        <span class="game-match">${g.match}</span>
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
function switchTab(key) {
  const prefix = currentSport === 'ncaa' ? 'ncaa-panel' : 'panel';

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

  if (isEmpty) {
    hideTzPicker();
    hideLeagueFilter();
  } else {
    showTzPicker();
    const tzSelect = document.getElementById('tz-select');
    if (tzSelect) tzSelect.disabled = false;
    showLeagueFilter();
    const leagues = activePanel.dataset.leagues ? JSON.parse(activePanel.dataset.leagues) : [];
    populateLeagueFilter(leagues);
    resetLeagueFilter();
  }
}

function switchToAbout() {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('about-tab').classList.add('active');
  document.querySelectorAll('.day-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('content').style.display = 'none';
  document.getElementById('about-panel').classList.add('active');

  const tzSelect = document.getElementById('tz-select');
  if (tzSelect) tzSelect.disabled = true;

  if (currentSport === 'netflix') {
    hideLeagueFilter();
  } else {
    const tzPicker = document.getElementById('tz-picker');
    if (tzPicker) tzPicker.style.display = '';
    showLeagueFilter();
    populateLeagueFilter([]);
  }
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

  // Netflix is a completely different layout — no day tabs
  if (sport === 'netflix') {
    let data;
    try {
      const res = await fetch('netflix.json?v=' + Math.floor(Date.now() / 3600000));
      data = await res.json();
    } catch (e) {
      contentEl.innerHTML =
        '<div class="empty"><div class="empty-icon">⚠️</div>Whoopsies — we\'re working to get releases shown.</div>';
      return;
    }

    const groups = data.groups || {};
    const groupNames = Object.keys(groups).filter(k => groups[k].length > 0);

    if (groupNames.length === 0) {
      contentEl.innerHTML =
        '<div class="empty"><div class="empty-icon">🎬</div>No new releases this week.</div>';
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
        ? `<div class="netflix-rating">⭐ ${show.rating}<span class="netflix-rating-max">/100</span></div>`
        : '';
      const overviewEl = show.overview
        ? `<div class="netflix-overview-wrap">
             <div class="netflix-overview netflix-overview-clamped">${show.overview}</div>
             <button class="netflix-show-more" onclick="toggleOverview(event,this)" type="button">Show more</button>
           </div>`
        : '';
      const posterEl = show.thumbnail
        ? `<img class="netflix-poster" src="${show.thumbnail}" alt="${show.title}" loading="lazy" decoding="async" width="140" height="210">`
        : `<div class="netflix-poster-placeholder">🎬</div>`;
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
      return show.link
        ? `<a class="netflix-card" href="${show.link}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;">${cardInner}</a>`
        : `<div class="netflix-card">${cardInner}</div>`;
    }

    function checkShowMoreButtons(grid) {
      grid.querySelectorAll('.netflix-overview-wrap').forEach(wrap => {
        const overview = wrap.querySelector('.netflix-overview');
        const btn = wrap.querySelector('.netflix-show-more');
        if (overview && btn && overview.scrollHeight <= overview.clientHeight + 2) {
          btn.style.display = 'none';
        }
      });
    }

    // Per-panel scroll state
    const netflixState = {}; // panelId -> { shows, offset, grid, sentinel, observer }

    function appendNextPage(panelId) {
      const state = netflixState[panelId];
      if (!state || state.offset >= state.shows.length) return;
      const slice = state.shows.slice(state.offset, state.offset + PAGE_SIZE);
      state.offset += slice.length;
      const frag = document.createDocumentFragment();
      const tmp = document.createElement('div');
      tmp.innerHTML = slice.map(buildCardHTML).join('');
      while (tmp.firstChild) frag.appendChild(tmp.firstChild);
      state.grid.insertBefore(frag, state.sentinel);
      checkShowMoreButtons(state.grid);
      // If all loaded, remove sentinel and disconnect observer
      if (state.offset >= state.shows.length) {
        state.sentinel.remove();
        state.observer.disconnect();
      }
    }

    // Build panel shells — only first page of cards rendered immediately
    const netflixPanels = {};
    groupNames.forEach((groupName, idx) => {
      const panelId = `panel-netflix-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
      const shows = groups[groupName];

      const panel = document.createElement('div');
      panel.className = 'day-panel';
      panel.id = panelId;

      const grid = document.createElement('div');
      grid.className = 'netflix-grid';

      // Sentinel div at end of grid — IntersectionObserver triggers next page load
      const sentinel = document.createElement('div');
      sentinel.className = 'netflix-sentinel';
      sentinel.style.cssText = 'height:1px;margin-top:40px;';
      grid.appendChild(sentinel);

      const observer = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting && panel.classList.contains('active')) appendNextPage(panelId);
      }, { rootMargin: '400px' });
      observer.observe(sentinel);

      netflixState[panelId] = { shows, offset: 0, grid, sentinel, observer };

      let headerHTML = `<div class="netflix-week-label">${data.week_label || ''}</div>`;
      headerHTML += `<div class="netflix-section-title">${groupName}</div>`;
      panel.innerHTML = headerHTML;
      panel.appendChild(grid);
      contentEl.appendChild(panel);
      netflixPanels[panelId] = panel;

      // Render first page immediately only for first tab; others render on first activation
      if (idx === 0) {
        appendNextPage(panelId);
      }
    });

    function activateNetflixPanel(panelId, tabBtn) {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tabBtn.classList.add('active');
      document.getElementById('about-panel').classList.remove('active');
      contentEl.style.display = '';
      Object.values(netflixPanels).forEach(p => p.classList.remove('active'));
      const panel = netflixPanels[panelId];
      panel.classList.add('active');
      hideTzPicker();
      hideLeagueFilter();
      // Render first page on first activation
      const state = netflixState[panelId];
      if (state && state.offset === 0) appendNextPage(panelId);
    }

    let firstTab = true;
    groupNames.forEach(groupName => {
      const panelId = `panel-netflix-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
      const btn = document.createElement('button');
      btn.className = 'tab' + (firstTab ? ' active' : '');
      btn.dataset.netflixCategory = panelId;
      btn.textContent = groupName;
      btn.addEventListener('click', () => activateNetflixPanel(panelId, btn));
      tabsEl.appendChild(btn);
      if (firstTab) netflixPanels[panelId].classList.add('active');
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
  const file = sport === 'ncaa' ? 'ncaa_basketball.json' : 'schedule.json';
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

    const panel = sport === 'ncaa'
      ? buildNcaaPanel(key, day)
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

  // Handle initial state — always re-enable tzSelect in case switchToAbout disabled it
  const tzSelect = document.getElementById('tz-select');
  if (tzSelect) tzSelect.disabled = false;

  const firstKey = dateKeys[0];
  if (firstKey) {
    const prefix = sport === 'ncaa' ? 'ncaa-panel' : 'panel';
    const firstPanel = document.getElementById(`${prefix}-${firstKey}`);
    if (firstPanel && firstPanel.dataset.empty === 'true') {
      hideTzPicker();
      hideLeagueFilter();
    } else if (firstPanel) {
      showTzPicker();
      showLeagueFilter();
      const leagues = firstPanel.dataset.leagues ? JSON.parse(firstPanel.dataset.leagues) : [];
      populateLeagueFilter(leagues);
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
    document.getElementById('content').innerHTML =
      '<div class="empty"><div class="empty-icon">⚠️</div>Whoopsies — we\'re working to get games shown.</div>';
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

  // Handle initial state
  const firstKey = dateKeys[0];
  if (firstKey) {
    const firstPanel = document.getElementById(`panel-${firstKey}`);
    if (firstPanel && firstPanel.dataset.empty === 'true') {
      hideTzPicker();
      hideLeagueFilter();
    } else if (firstPanel) {
      showTzPicker();
      showLeagueFilter();
      const leagues = firstPanel.dataset.leagues ? JSON.parse(firstPanel.dataset.leagues) : [];
      populateLeagueFilter(leagues);
    }
  }

  // Show/hide NCAA Men button based on whether any games exist
  try {
    const ncaaRes  = await fetch('ncaa_basketball.json?v=' + Date.now());
    const ncaaData = await ncaaRes.json();
    const hasGames = Object.values(ncaaData.days || {}).some(d => d.games && d.games.length > 0);
    const ncaaBtn  = document.getElementById('sport-ncaa');
    if (ncaaBtn) ncaaBtn.style.display = hasGames ? '' : 'none';
  } catch (e) {
    // If fetch fails just hide the button to be safe
    const ncaaBtn = document.getElementById('sport-ncaa');
    if (ncaaBtn) ncaaBtn.style.display = 'none';
  }
}

init();
