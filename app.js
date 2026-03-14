// ── Timezone config ──────────────────────────────────────────────
const TIMEZONES = [
  { label: 'Eastern (ET)',  iana: 'America/New_York' },
  { label: 'Central (CT)',  iana: 'America/Chicago' },
  { label: 'Mountain (MT)', iana: 'America/Denver' },
  { label: 'Pacific (PT)',  iana: 'America/Los_Angeles' },
];

let currentTZ = localStorage.getItem('sotlive_tz') || 'America/New_York';

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

// ── League order ──────────────────────────────────────────────────
const LEAGUE_ORDER = [
  'UEFA Champions League',
  'UEFA Europa League',
  'UEFA Europa Conference League',
  'Premier League',
  'MLS',
  'CONCACAF Champions Cup',
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

  // Remove all options except the first "Show All"
  while (select.options.length > 1) select.remove(1);

  // If 1 or fewer leagues, nothing useful to filter — disable and show only "Show All"
  if (leagues.length <= 1) {
    select.disabled = true;
    select.value = '';
    return;
  }

  select.disabled = false;

  // Add options for leagues present on this day, in LEAGUE_ORDER order
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

  // Reset to Show All
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

// ── Render a day panel ────────────────────────────────────────────
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

  // Store the leagues present on this day on the panel element
  panel.dataset.leagues = JSON.stringify(Object.keys(sortedGrouped));

  let html = '';
  for (const [league, info] of Object.entries(sortedGrouped)) {
    const isUefa = ['UEFA Champions League', 'UEFA Europa League', 'UEFA Europa Conference League'].includes(league);
    html += `<div class="league-group"><div class="league-label${isUefa ? ' uefa' : ''}">${league}</div>`;
    for (const g of info.items) {
      const displayTime = (g.kick_utc ? formatTime(g.kick_utc, currentTZ) : null) || g.time;
      const utcAttr = g.kick_utc ? `data-utc="${g.kick_utc}"` : '';
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

// ── Tab switching ─────────────────────────────────────────────────
function switchTab(key) {
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.key === key);
  });
  document.querySelectorAll('.day-panel').forEach(p => {
    p.classList.toggle('active', p.id === `panel-${key}`);
  });
  document.getElementById('about-panel').classList.remove('active');
  document.getElementById('content').style.display = '';

  const activePanel = document.getElementById(`panel-${key}`);
  const isEmpty = activePanel && activePanel.dataset.empty === 'true';

  if (isEmpty) {
    hideTzPicker();
    hideLeagueFilter();
  } else {
    showTzPicker();
    // Re-enable tz picker in case it was frozen on About
    const tzSelect = document.getElementById('tz-select');
    if (tzSelect) tzSelect.disabled = false;
    showLeagueFilter();
    // Reset filter and repopulate for this day's leagues
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

  // Freeze tz picker — keep value visible but not interactive
  const tzSelect = document.getElementById('tz-select');
  if (tzSelect) tzSelect.disabled = true;

  // Reset league filter to Show All only, disabled
  showLeagueFilter();
  populateLeagueFilter([]);
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

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  let data;
  try {
    const res = await fetch('schedule.json?v=' + Date.now());
    data = await res.json();
  } catch (e) {
    // Schedule fetch failed — show error, hide both pickers
    document.getElementById('content').innerHTML =
      '<div class="empty"><div class="empty-icon">⚠️</div>Whoopsies — we\'re working to get games shown.</div>';
    hideTzPicker();
    hideLeagueFilter();
    return;
  }

  // Build pickers now that we know schedule loaded
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
      const leagues = firstPanel.dataset.leagues ? JSON.parse(firstPanel.dataset.leagues) : [];
      populateLeagueFilter(leagues);
    }
  }
}

init();
