// ── Local TV ──────────────────────────────────────────────────────
// Standalone handler for the Local TV tab.
// Does NOT touch app.js.
// Login / signup UI is visual only — buttons do nothing yet.
// AWS Cognito auth + Schedules Direct backend wired in later.

(function () {

  // ── Styles ──────────────────────────────────────────────────────
  const style = document.createElement('style');
  style.textContent = `
    .ltv-wrap {
      max-width: 420px;
      margin: 48px auto 0;
      padding: 0 24px;
    }
    .ltv-logo {
      text-align: center;
      font-size: 36px;
      margin-bottom: 8px;
    }
    .ltv-heading {
      font-family: 'DM Sans', sans-serif;
      font-size: 20px;
      font-weight: 600;
      color: #1a1a1a;
      text-align: center;
      margin-bottom: 4px;
    }
    .ltv-sub {
      font-family: 'DM Sans', sans-serif;
      font-size: 14px;
      color: #888880;
      text-align: center;
      margin-bottom: 32px;
    }
    .ltv-card {
      background: #ffffff;
      border: 1.5px solid #e8e6e1;
      border-radius: 10px;
      padding: 28px 24px;
    }
    .ltv-tabs {
      display: flex;
      border-bottom: 1.5px solid #e8e6e1;
      margin-bottom: 24px;
    }
    .ltv-tab {
      flex: 1;
      background: none;
      border: none;
      padding: 10px 0;
      font-family: 'DM Sans', sans-serif;
      font-size: 14px;
      font-weight: 500;
      color: #888880;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1.5px;
      transition: color 0.15s, border-color 0.15s;
    }
    .ltv-tab:hover { color: #1a1a1a; }
    .ltv-tab.active {
      color: #1a1a1a;
      font-weight: 700;
      border-bottom-color: #1a1a1a;
    }
    .ltv-panel { display: none; }
    .ltv-panel.active { display: block; }
    .ltv-field { margin-bottom: 14px; }
    .ltv-label {
      display: block;
      font-family: 'DM Sans', sans-serif;
      font-size: 13px;
      font-weight: 500;
      color: #1a1a1a;
      margin-bottom: 6px;
    }
    .ltv-input {
      width: 100%;
      height: 40px;
      border: 1.5px solid #e8e6e1;
      border-radius: 8px;
      padding: 0 12px;
      font-family: 'DM Sans', sans-serif;
      font-size: 15px;
      color: #1a1a1a;
      background: #faf9f7;
      outline: none;
      transition: border-color 0.15s;
      box-sizing: border-box;
    }
    .ltv-input:focus {
      border-color: #1a1a1a;
      background: #fff;
    }
    .ltv-btn {
      width: 100%;
      height: 42px;
      margin-top: 8px;
      background: #1a1a1a;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-family: 'DM Sans', sans-serif;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.15s;
    }
    .ltv-btn:hover { opacity: 0.85; }
    .ltv-forgot {
      display: block;
      text-align: right;
      font-family: 'DM Sans', sans-serif;
      font-size: 12px;
      color: #888880;
      margin-top: -8px;
      margin-bottom: 14px;
      cursor: pointer;
    }
    .ltv-forgot:hover { color: #1a1a1a; }
    .ltv-terms {
      font-family: 'DM Sans', sans-serif;
      font-size: 12px;
      color: #888880;
      text-align: center;
      margin-top: 16px;
      line-height: 1.5;
    }
  `;
  document.head.appendChild(style);

  // ── Hook into switchSport ────────────────────────────────────────
  // Waits for app.js to finish loading before patching switchSport
  window.addEventListener('load', function () {
    const _original = window.switchSport;

    window.switchSport = async function (sport) {
      if (sport !== 'localtv') {
        return _original.apply(this, arguments);
      }

      // Mirror what app.js does for nav state
      document.querySelectorAll('.sport-btn').forEach(b => {
        b.classList.toggle('active', b.id === 'sport-localtv');
      });

      const tabsEl    = document.getElementById('tabs');
      const contentEl = document.getElementById('content');
      tabsEl.innerHTML    = '';
      contentEl.innerHTML = '';

      document.getElementById('about-panel').classList.remove('active');
      contentEl.style.display = '';

      const tzPicker = document.getElementById('tz-picker');
      const lgFilter = document.getElementById('league-filter');
      if (tzPicker) tzPicker.style.display = 'none';
      if (lgFilter) lgFilter.style.display = 'none';

      renderLocalTV(contentEl, tabsEl);
    };
  });

  // ── Render login/signup UI ───────────────────────────────────────
  function renderLocalTV(contentEl, tabsEl) {
    const wrap = document.createElement('div');
    wrap.className = 'ltv-wrap';

    wrap.innerHTML = `
      <div class="ltv-logo">🐰</div>
      <div class="ltv-heading">Local TV</div>
      <div class="ltv-sub">Coming soon.</div>

      <div class="ltv-card">
        <div class="ltv-tabs">
          <button class="ltv-tab active" id="ltv-tab-login">Sign in</button>
          <button class="ltv-tab" id="ltv-tab-signup">Create account</button>
        </div>

        <!-- Sign in panel -->
        <div class="ltv-panel active" id="ltv-panel-login">
          <div class="ltv-field">
            <label class="ltv-label">Email</label>
            <input class="ltv-input" type="email" placeholder="you@example.com" autocomplete="email" />
          </div>
          <div class="ltv-field">
            <label class="ltv-label">Password</label>
            <input class="ltv-input" type="password" placeholder="••••••••" autocomplete="current-password" />
          </div>
          <span class="ltv-forgot">Forgot password?</span>
          <button class="ltv-btn" id="ltv-login-btn">Sign in</button>
        </div>

        <!-- Create account panel -->
        <div class="ltv-panel" id="ltv-panel-signup">
          <div class="ltv-field">
            <label class="ltv-label">Email</label>
            <input class="ltv-input" type="email" placeholder="you@example.com" autocomplete="email" />
          </div>
          <div class="ltv-field">
            <label class="ltv-label">Password</label>
            <input class="ltv-input" type="password" placeholder="••••••••" autocomplete="new-password" />
          </div>
          <div class="ltv-field">
            <label class="ltv-label">Confirm password</label>
            <input class="ltv-input" type="password" placeholder="••••••••" autocomplete="new-password" />
          </div>
          <button class="ltv-btn" id="ltv-signup-btn">Create account</button>
          <div class="ltv-terms">By creating an account you agree to our terms of service.</div>
        </div>
      </div>
    `;

    contentEl.appendChild(wrap);

    // Tab switching between sign in / create account
    document.getElementById('ltv-tab-login').addEventListener('click', () => {
      document.getElementById('ltv-tab-login').classList.add('active');
      document.getElementById('ltv-tab-signup').classList.remove('active');
      document.getElementById('ltv-panel-login').classList.add('active');
      document.getElementById('ltv-panel-signup').classList.remove('active');
    });

    document.getElementById('ltv-tab-signup').addEventListener('click', () => {
      document.getElementById('ltv-tab-signup').classList.add('active');
      document.getElementById('ltv-tab-login').classList.remove('active');
      document.getElementById('ltv-panel-signup').classList.add('active');
      document.getElementById('ltv-panel-login').classList.remove('active');
    });

    // Buttons intentionally do nothing — AWS Cognito wired in later
    document.getElementById('ltv-login-btn').addEventListener('click', () => {});
    document.getElementById('ltv-signup-btn').addEventListener('click', () => {});


  }

})();
