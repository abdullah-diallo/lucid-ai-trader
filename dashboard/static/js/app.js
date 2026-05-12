/**
 * Lucid AI Trader — Dashboard JS
 * Covers: view routing, live polling, TradingView widget control,
 *         account management, strategy detail modal, P&L display.
 */
'use strict';

/* ============================================================
   CONSTANTS
   ============================================================ */
const POLL_INTERVAL_MS = 5000;
const TOAST_DURATION_MS = 5000;
const TV_SYMBOLS = [
  'CME_MINI:MES1!', 'CME_MINI:MNQ1!', 'CME:ES1!', 'CME:NQ1!',
  'NASDAQ:AAPL', 'NASDAQ:TSLA', 'NYSE:SPY', 'BINANCE:BTCUSDT',
];

/* ============================================================
   § 07  NAV SCROLL
   ============================================================ */
function initNavScroll() {
  const navBar = document.getElementById('nav-bar');
  if (!navBar) return;
  const onScroll = () => {
    const scrolled = window.scrollY > 12;
    navBar.classList.toggle('nav-scrolled', scrolled);
    navBar.classList.toggle('nav-transparent', !scrolled);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

/* ============================================================
   § 05  CARD PARALLAX
   ============================================================ */
function initParallax() {
  document.querySelectorAll('.parallax-enabled').forEach(card => {
    const TILT = 6;
    card.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const dx = (e.clientX - rect.left - rect.width  / 2) / (rect.width  / 2);
      const dy = (e.clientY - rect.top  - rect.height / 2) / (rect.height / 2);
      card.style.setProperty('--rx', `${(-dy * TILT).toFixed(2)}deg`);
      card.style.setProperty('--ry', `${ (dx * TILT).toFixed(2)}deg`);
    });
    card.addEventListener('mouseleave', () => {
      card.style.setProperty('--rx', '0deg');
      card.style.setProperty('--ry', '0deg');
    });
  });
}

/* ============================================================
   § 08  PAGE STAGGER
   ============================================================ */
function initStagger() {
  document.querySelectorAll('[data-stagger]').forEach((el, i) => {
    el.style.setProperty('--i', String(i));
    el.classList.add('stagger-child');
  });
}

/* ============================================================
   ANIMATED COUNTER
   ============================================================ */
function animateNumber(el, start, end, duration = 800, decimals = 0) {
  const startTime = performance.now();
  const update = now => {
    const progress = Math.min((now - startTime) / duration, 1);
    const ease = 1 - Math.pow(1 - progress, 3);
    const value = start + (end - start) * ease;
    el.textContent = decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
    if (progress < 1) requestAnimationFrame(update);
  };
  requestAnimationFrame(update);
}

/* ============================================================
   § 06  TOGGLES
   ============================================================ */
function initToggles() {
  document.querySelectorAll('[data-toggle]').forEach(track => {
    track.addEventListener('click', () => {
      const key = track.dataset.toggle;
      const isOn = track.classList.toggle('is-on');
      if (key === 'pause') {
        fetch(isOn ? '/api/pause' : '/api/resume', { method: 'POST' })
          .then(() => refreshStatus()).catch(console.error);
        track.classList.toggle('is-pause', isOn);
        if (!isOn) track.classList.remove('is-pause');
      }
      if (key === 'theme') {
        document.documentElement.setAttribute('data-theme', isOn ? 'light' : 'dark');
        localStorage.setItem('lucid-theme', isOn ? 'light' : 'dark');
      }
    });
  });
  const savedTheme = localStorage.getItem('lucid-theme');
  if (savedTheme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    document.querySelector('[data-toggle="theme"]')?.classList.add('is-on');
  }
}

/* ============================================================
   § 09  TOAST MANAGER
   ============================================================ */
const ToastManager = (() => {
  const stack = document.getElementById('toast-stack');
  const icons = { buy: '↑', sell: '↓', close: '✕', info: 'i', warn: '⚠' };

  function show({ title, body = '', type = 'info', duration = TOAST_DURATION_MS }) {
    if (!stack) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
      <div class="toast-icon ${type}">${icons[type] || icons.info}</div>
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        ${body ? `<div class="toast-body">${body}</div>` : ''}
      </div>
      <button class="toast-dismiss" aria-label="Dismiss">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </button>
      <div class="toast-progress" style="--duration:${duration}ms"></div>`;
    toast.querySelector('.toast-dismiss').addEventListener('click', () => dismiss(toast));
    stack.appendChild(toast);
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('is-visible')));
    const timer = setTimeout(() => dismiss(toast), duration);
    toast._timer = timer;
    return toast;
  }

  function dismiss(toast) {
    clearTimeout(toast._timer);
    toast.classList.remove('is-visible');
    toast.classList.add('is-exiting');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }
  return { show };
})();

/* ============================================================
   § 09  BOTTOM SHEET
   ============================================================ */
const SheetManager = (() => {
  let activeSheet = null;
  let startY = 0, currentY = 0, isDragging = false;

  function open(sheetId) {
    const overlay = document.getElementById('modal-overlay');
    const sheet   = document.getElementById(sheetId);
    if (!sheet || !overlay) return;
    activeSheet = sheet;
    overlay.classList.add('is-open');
    sheet.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    initGesture(sheet);
  }

  function close() {
    if (!activeSheet) return;
    const overlay = document.getElementById('modal-overlay');
    activeSheet.classList.remove('is-open');
    overlay?.classList.remove('is-open');
    document.body.style.overflow = '';
    activeSheet = null;
  }

  function initGesture(sheet) {
    const handle = sheet.querySelector('.sheet-handle');
    if (!handle) return;
    handle.addEventListener('touchstart', e => { startY = e.touches[0].clientY; isDragging = true; sheet.style.transition = 'none'; }, { passive: true });
    document.addEventListener('touchmove', e => {
      if (!isDragging) return;
      currentY = e.touches[0].clientY;
      const delta = Math.max(0, currentY - startY);
      sheet.style.transform = `translateY(${delta}px)`;
    }, { passive: true });
    document.addEventListener('touchend', () => {
      isDragging = false;
      sheet.style.transition = '';
      if (currentY - startY > 100) close(); else sheet.style.transform = '';
    }, { passive: true });
  }

  document.getElementById('modal-overlay')?.addEventListener('click', close);
  return { open, close };
})();

/* ============================================================
   CENTER MODAL
   ============================================================ */
const ModalManager = (() => {
  function open(modalId) {
    const overlay = document.getElementById('modal-overlay');
    const modal   = document.getElementById(modalId);
    if (!modal || !overlay) return;
    overlay.classList.add('is-open');
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }
  function close() {
    document.querySelectorAll('.center-modal.is-open').forEach(m => m.classList.remove('is-open'));
    document.getElementById('modal-overlay')?.classList.remove('is-open');
    document.body.style.overflow = '';
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { close(); SheetManager.close(); } });
  return { open, close };
})();

/* ============================================================
   SIDEBAR TOGGLE
   ============================================================ */
function initSidebar() {
  const btn  = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  const main    = document.getElementById('main-content');
  if (!btn || !sidebar) return;
  btn.addEventListener('click', () => {
    const collapsed = sidebar.classList.toggle('collapsed');
    main?.classList.toggle('sidebar-collapsed', collapsed);
  });
}

/* ============================================================
   VIEW NAVIGATION
   ============================================================ */
const SCROLL_VIEWS = new Set(['signals']); // these scroll within dashboard

function switchView(viewName) {
  if (SCROLL_VIEWS.has(viewName)) {
    switchView('dashboard');
    const anchor = document.getElementById('signals');
    if (anchor) setTimeout(() => anchor.scrollIntoView({ behavior: 'smooth' }), 60);
    return;
  }

  document.querySelectorAll('.view-panel').forEach(p => {
    p.style.display = 'none';
    p.classList.remove('active');
  });

  const target = document.getElementById(`view-${viewName}`);
  if (target) {
    target.style.display = 'block';
    target.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  document.querySelectorAll('[data-view-link]').forEach(link => {
    const active = link.dataset.viewLink === viewName ||
      (SCROLL_VIEWS.has(viewName) && link.dataset.viewLink === 'dashboard');
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });

  if (viewName === 'strategies') loadStrategies();
  if (viewName === 'tradingview') initTVWidget();
}

function initViewNavigation() {
  document.querySelectorAll('[data-view-link]').forEach(link => {
    link.addEventListener('click', e => { e.preventDefault(); switchView(link.dataset.viewLink); });
  });
  const hash = location.hash.replace('#', '');
  if (hash) switchView(hash);
}

/* ============================================================
   LIVE DATA POLLING
   ============================================================ */
let prevSignalCount = 0;

async function refreshStatus() {
  try {
    const data = await fetch('/api/status').then(r => r.json());

    const sessionEl = document.getElementById('session-label');
    if (sessionEl) {
      sessionEl.textContent = data.session;
      sessionEl.className = `session-label-large session-${data.session.toLowerCase().replace(/[-\s]/g, '')}`;
    }

    const navBadge = document.getElementById('nav-session-badge');
    if (navBadge) {
      const cls = data.session === 'RTH' ? 'badge-rth'
        : data.session === 'Pre-market' ? 'badge-pre'
        : data.session === 'AH'  ? 'badge-ah'
        : data.session === 'Globex' ? 'badge-globex'
        : 'badge-closed';
      navBadge.className = `session-badge ${cls}`;
      navBadge.querySelector('.session-name').textContent = data.session;
    }

    const timeEl = document.getElementById('clock');
    if (timeEl) timeEl.textContent = data.time_et;

    const countEl      = document.getElementById('countdown');
    const countLabelEl = document.getElementById('countdown-label');
    if (countEl) countEl.textContent = data.countdown;
    if (countLabelEl) countLabelEl.textContent = data.until_next_label;

    const gateEl = document.getElementById('trading-gate');
    if (gateEl) {
      if (data.paused) {
        gateEl.className = 'trading-gate-pill gate-paused';
        gateEl.querySelector('.gate-label').textContent = 'Paused';
      } else if (data.should_trade) {
        gateEl.className = 'trading-gate-pill gate-active';
        gateEl.querySelector('.gate-label').textContent = 'Trading Active';
      } else {
        gateEl.className = 'trading-gate-pill gate-inactive';
        gateEl.querySelector('.gate-label').textContent = 'Trading Inactive';
      }
    }

    document.getElementById('news-indicator')?.style?.setProperty('display', data.news_window ? 'flex' : 'none');
    document.getElementById('hv-indicator')?.style?.setProperty('display', data.high_volume ? 'flex' : 'none');

    const pauseTrack = document.querySelector('[data-toggle="pause"]');
    if (pauseTrack) {
      pauseTrack.classList.toggle('is-on',    data.paused);
      pauseTrack.classList.toggle('is-pause', data.paused);
    }

    const paperEl = document.getElementById('paper-pill');
    if (paperEl) paperEl.style.display = data.paper_mode ? 'inline-flex' : 'none';

  } catch (err) { console.error('Status poll failed:', err); }
}

async function refreshSignals() {
  try {
    const data = await fetch('/api/signals?limit=12').then(r => r.json());
    const feed = document.getElementById('signal-feed');
    if (!feed) return;

    if (data.count > prevSignalCount && prevSignalCount > 0 && data.signals.length) {
      const newest = data.signals[0];
      const action = (newest.action || '').toLowerCase();
      ToastManager.show({
        title: `${newest.action} — ${newest.symbol}`,
        body: newest.reason || '',
        type: action === 'buy' ? 'buy' : action === 'sell' ? 'sell' : 'close',
        duration: TOAST_DURATION_MS,
      });
    }
    prevSignalCount = data.count;

    if (data.signals.length === 0) {
      feed.innerHTML = `<div class="signal-row" style="justify-content:center;opacity:1;"><span class="text-tertiary text-footnote">No signals yet today</span></div>`;
      return;
    }

    feed.innerHTML = data.signals.map((s, i) => {
      const action = (s.action || '').toLowerCase();
      const time   = s.received_at ? new Date(s.received_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';
      const price  = s.price ? Number(s.price).toFixed(2) : '';
      return `
        <div class="signal-row" style="--i:${i}" onclick="openSignalDetail(${JSON.stringify(JSON.stringify(s))})">
          <span class="action-badge ${action}">${(s.action || '').toUpperCase()}</span>
          <div class="signal-meta">
            <div class="signal-symbol">${s.symbol || '—'}</div>
            <div class="signal-reason">${s.reason || ''}</div>
          </div>
          <span class="signal-price">${price}</span>
          <span class="signal-time">${time}</span>
        </div>`;
    }).join('');
  } catch (err) { console.error('Signals poll failed:', err); }
}

async function refreshPerformance() {
  try {
    const data = await fetch('/api/performance').then(r => r.json());
    const animate = (id, val) => {
      const el = document.getElementById(id);
      if (!el) return;
      animateNumber(el, parseInt(el.textContent) || 0, val);
    };
    animate('perf-total',    data.total_signals   || 0);
    animate('perf-buy',      data.buy_signals      || 0);
    animate('perf-sell',     data.sell_signals     || 0);
    animate('perf-close',    data.close_signals    || 0);
    animate('perf-filtered', data.filtered_signals || 0);
  } catch (err) { console.error('Performance poll failed:', err); }
}

async function refreshPnL() {
  try {
    const data = await fetch('/api/pnl').then(r => r.json());

    const fmt = v => v === 0 ? '$0' : (v > 0 ? '+$' : '-$') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fmtPlain = v => '$' + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    const cls = (id, className) => { const el = document.getElementById(id); if (el) el.className = `pnl-card-value ${className}`; };

    set('pnl-trades', data.total_trades || '0');
    set('pnl-net',    data.total_trades ? fmt(data.net_pnl) : '—');
    set('pnl-in',     data.total_trades ? fmtPlain(data.money_in)  : '—');
    set('pnl-out',    data.total_trades ? fmtPlain(data.money_out) : '—');
    set('pnl-winrate', `win rate ${data.win_rate || 0}%`);
    set('pnl-winners', `${data.winners || 0} winners`);
    set('pnl-losers',  `${data.losers  || 0} losers`);

    cls('pnl-net', data.net_pnl > 0 ? 'text-profit' : data.net_pnl < 0 ? 'text-loss' : 'text-neutral');

    // Trade Summary card
    set('ts-net',    data.total_trades ? fmt(data.net_pnl)            : '—');
    set('ts-profit', data.total_trades ? fmtPlain(data.gross_profit)  : '—');
    set('ts-loss',   data.total_trades ? fmtPlain(data.gross_loss)    : '—');
    set('ts-wr',     data.total_trades ? `${data.win_rate}%`          : '—');
    set('ts-trades', data.total_trades || '0');

    const netEl = document.getElementById('ts-net');
    if (netEl) netEl.className = `orb-level-value text-mono ${data.net_pnl > 0 ? 'text-buy' : data.net_pnl < 0 ? 'text-sell' : ''}`;

  } catch (err) { console.error('P&L poll failed:', err); }
}

/* ============================================================
   SIGNAL DETAIL MODAL
   ============================================================ */
window.openSignalDetail = function(jsonStr) {
  try {
    const s = JSON.parse(jsonStr);
    const el = document.getElementById('signal-detail-content');
    if (!el) return;
    const action = (s.action || '').toLowerCase();
    el.innerHTML = `
      <div class="flex items-center gap-4" style="margin-bottom:var(--space-6)">
        <div class="jewel jewel-lg jewel-${action === 'buy' ? 'green' : action === 'sell' ? 'red' : 'orange'}">
          <svg width="24" height="24" viewBox="0 0 24 24" class="icon-glass-stroke">
            ${action === 'buy' ? '<path d="M12 19V5M5 12l7-7 7 7"/>'
              : action === 'sell' ? '<path d="M12 5v14M5 12l7 7 7-7"/>'
              : '<path d="M18 6L6 18M6 6l12 12"/>'}
          </svg>
        </div>
        <div>
          <div class="text-title-2">${s.symbol || '—'}</div>
          <span class="action-badge ${action}">${(s.action || '').toUpperCase()}</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-3);margin-bottom:var(--space-5)">
        ${[['Price', s.price ? Number(s.price).toFixed(2) : '—'], ['Timeframe', s.timeframe || '—'], ['Source', s.source || 'tradingview'], ['Received', s.received_at ? new Date(s.received_at).toLocaleString() : '—']]
          .map(([label, value]) => `<div class="stat-chip"><span class="stat-chip-label">${label}</span><span class="stat-chip-value text-mono">${value}</span></div>`).join('')}
      </div>
      ${s.reason ? `<div style="background:var(--glass-1);border:var(--border-hair);border-radius:var(--radius-md);padding:var(--space-4)"><p class="text-caption-1 text-secondary">${s.reason}</p></div>` : ''}`;
    ModalManager.open('signal-modal');
  } catch (e) { console.error(e); }
};

/* ============================================================
   SHIMMER → REAL CONTENT
   ============================================================ */
function revealContent() {
  document.querySelectorAll('.skeleton').forEach(el => el.classList.remove('skeleton'));
  document.querySelectorAll('[data-stagger]').forEach((el, i) => {
    el.style.setProperty('--i', String(i));
    el.classList.add('stagger-child');
  });
}

/* ============================================================
   MAIN POLL LOOP
   ============================================================ */
async function pollAll() {
  await Promise.allSettled([refreshStatus(), refreshSignals(), refreshPerformance(), refreshPnL()]);
}

/* ============================================================
   STRATEGIES
   ============================================================ */
let _strategiesLoaded = false;
const JEWEL_COLORS = ['blue','purple','orange','green','red','blue','purple','orange','green','red','blue','purple','orange','green','red','blue'];

async function loadStrategies() {
  if (_strategiesLoaded) return;
  try {
    const data = await fetch('/api/strategies').then(r => r.json());
    const grid  = document.getElementById('strategy-grid');
    const badge = document.getElementById('strategy-count-badge');
    if (!grid) return;

    if (badge) badge.textContent = `${data.count} loaded`;

    grid.innerHTML = data.strategies.map((s, i) => {
      const color = JEWEL_COLORS[i % JEWEL_COLORS.length];
      return `
        <article class="strategy-card" role="listitem" data-stagger
                 onclick="openStrategyDetail('${s.id}', ${JSON.stringify(JSON.stringify(s))})">
          <div class="strategy-card-header">
            <div class="flex items-center gap-3">
              <div class="jewel jewel-sm jewel-${color}" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 14 14" class="icon-glass-stroke">
                  <path d="M2 10l3-4 2.5 2.5 2.5-5L13 7"/>
                </svg>
              </div>
              <div>
                <div class="strategy-card-name">${s.display_name}</div>
                ${s.class_name ? `<div class="strategy-card-class">${s.class_name}</div>` : ''}
              </div>
            </div>
            <span class="strategy-pill-active">Active</span>
          </div>
          <p class="strategy-card-desc">${s.description || 'No description available.'}</p>
          <div class="strategy-card-footer">
            <span class="strategy-card-file">${s.file}</span>
            <span class="strategy-method-count">${s.methods_count || 0} methods</span>
          </div>
        </article>`;
    }).join('');

    grid.querySelectorAll('[data-stagger]').forEach((el, i) => {
      el.style.setProperty('--i', String(i));
      el.classList.add('stagger-child');
    });
    _strategiesLoaded = true;
  } catch (err) { console.error('Strategies load failed:', err); }
}

window.openStrategyDetail = async function(strategyId, metaStr) {
  const meta = JSON.parse(metaStr);
  document.getElementById('sd-title').textContent = meta.display_name || strategyId;
  document.getElementById('sd-file').textContent  = meta.file || '';
  document.getElementById('sd-content').innerHTML = '<p class="text-tertiary text-footnote" style="margin:var(--space-4) 0">Loading…</p>';
  ModalManager.open('strategy-detail-modal');

  try {
    const detail = await fetch(`/api/strategies/${strategyId}`).then(r => r.json());
    const el = document.getElementById('sd-content');
    if (!el) return;

    let html = '';

    if (detail.module_doc) {
      html += `<div style="background:var(--glass-1,rgba(255,255,255,.03));border:var(--border-hair,1px solid rgba(255,255,255,.08));border-radius:var(--radius-md,12px);padding:var(--space-4);margin-bottom:var(--space-4)">
        <p class="text-body" style="line-height:1.6">${detail.module_doc}</p>
      </div>`;
    }

    for (const cls of (detail.classes || [])) {
      html += `<p class="detail-section-label">Class</p>
        <div style="background:var(--glass-2,rgba(255,255,255,.06));border:var(--border-hair);border-radius:var(--radius-md);padding:var(--space-4);margin-bottom:var(--space-4)">
          <div class="method-name" style="font-size:15px">${cls.name}</div>
          ${cls.doc ? `<p class="method-doc" style="margin-top:6px">${cls.doc}</p>` : ''}
          ${cls.init_params && cls.init_params.length ? `
            <p class="detail-section-label" style="margin-top:var(--space-4);margin-bottom:var(--space-2)">Parameters</p>
            <div>${cls.init_params.map(p => `<span class="param-chip">${p}</span>`).join('')}</div>` : ''}
        </div>`;

      if (cls.methods && cls.methods.length) {
        html += `<p class="detail-section-label">Methods (${cls.methods.length})</p><div class="method-list">`;
        for (const m of cls.methods) {
          html += `<div class="method-item">
            <div class="method-name">${m.name}(${m.params.map(p => `<span style="color:rgba(255,255,255,.7)">${p}</span>`).join(', ')})</div>
            ${m.params.length ? `<div class="method-params">params: ${m.params.join(', ')}</div>` : ''}
            ${m.doc ? `<div class="method-doc">${m.doc}</div>` : ''}
          </div>`;
        }
        html += '</div>';
      }
    }

    el.innerHTML = html || '<p class="text-tertiary text-footnote">No details available.</p>';
  } catch (err) {
    document.getElementById('sd-content').innerHTML = `<p class="text-loss">Failed to load: ${err.message}</p>`;
  }
};

/* ============================================================
   TRADINGVIEW WIDGET (programmatic control via tv.js)
   ============================================================ */
let _tvWidget = null;
let _tvConfig = { symbol: 'CME_MINI:MES1!', interval: '5', theme: 'dark', style: '1' };
let _tvInitialized = false;

async function fetchTVConfig() {
  try {
    _tvConfig = await fetch('/api/tradingview/config').then(r => r.json());
  } catch (_) {}
}

function buildTVWidget(cfg) {
  const container = document.getElementById('tv-chart');
  if (!container) return;
  container.innerHTML = '';

  if (typeof TradingView === 'undefined') {
    container.innerHTML = '<p style="padding:40px;text-align:center;opacity:.5">TradingView library not loaded — check network connection.</p>';
    return;
  }

  _tvWidget = new TradingView.widget({
    container_id:        'tv-chart',
    width:               '100%',
    height:              '100%',
    autosize:            true,
    symbol:              cfg.symbol   || 'CME_MINI:MES1!',
    interval:            cfg.interval || '5',
    timezone:            'America/New_York',
    theme:               cfg.theme    || 'dark',
    style:               cfg.style    || '1',
    locale:              'en',
    toolbar_bg:          cfg.theme === 'light' ? '#f8f8f8' : '#131722',
    enable_publishing:   false,
    allow_symbol_change: true,
    save_image:          false,
    studies:             cfg.studies  || ['RSI@tv-basicstudies', 'VWAP@tv-basicstudies'],
    show_popup_button:   true,
    popup_width:         '1000',
    popup_height:        '650',
  });

  // Sync symbol input + interval select
  const symbolInput    = document.getElementById('tv-symbol-input');
  const intervalSelect = document.getElementById('tv-interval-select');
  const styleSelect    = document.getElementById('tv-style-select');
  if (symbolInput)    symbolInput.value   = cfg.symbol   || 'CME_MINI:MES1!';
  if (intervalSelect) intervalSelect.value = cfg.interval || '5';
  if (styleSelect)    styleSelect.value   = cfg.style    || '1';
}

async function initTVWidget() {
  if (_tvInitialized) return;
  _tvInitialized = true;
  await fetchTVConfig();
  buildTVWidget(_tvConfig);
  loadTVAccounts();
}

function applyTVSettings() {
  const symbol   = document.getElementById('tv-symbol-input')?.value.trim()   || _tvConfig.symbol;
  const interval = document.getElementById('tv-interval-select')?.value        || _tvConfig.interval;
  const style    = document.getElementById('tv-style-select')?.value           || _tvConfig.style;

  _tvConfig = { ..._tvConfig, symbol, interval, style };

  // Try live chart update first (no flicker)
  if (_tvWidget) {
    try {
      _tvWidget.onChartReady(() => {
        _tvWidget.activeChart().setSymbol(symbol, () => {});
        _tvWidget.activeChart().setResolution(interval, () => {});
      });
      // Save to backend
      fetch('/api/tradingview/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, interval, style }),
      }).catch(console.error);
      ToastManager.show({ title: 'Chart updated', body: `${symbol} · ${interval}m`, type: 'info', duration: 2500 });
      return;
    } catch (_) {}
  }

  // Fallback: rebuild widget
  fetch('/api/tradingview/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, interval, style }),
  }).then(() => {
    _tvWidget = null;
    buildTVWidget(_tvConfig);
    ToastManager.show({ title: 'Chart reloaded', body: `${symbol}`, type: 'info', duration: 2500 });
  }).catch(console.error);
}

/* ============================================================
   TV ACCOUNT MANAGEMENT
   ============================================================ */
async function loadTVAccounts() {
  try {
    const data = await fetch('/api/tradingview/accounts').then(r => r.json());
    renderTVAccounts(data.accounts, data.active_account_id);
  } catch (_) {}
}

function renderTVAccounts(accounts, activeId) {
  const list = document.getElementById('tv-account-list');
  if (!list) return;
  if (!accounts.length) {
    list.innerHTML = '<span style="font-size:12px;opacity:.5">No accounts saved — click Add Account</span>';
    return;
  }
  list.innerHTML = accounts.map(acc => `
    <div class="tv-account-pill ${acc.id === activeId ? 'is-active' : ''}"
         onclick="activateTVAccount('${acc.id}')">
      <span class="dot ${acc.id === activeId ? '' : 'tv-account-dot-off'}"></span>
      <span>${acc.display_name || acc.username}</span>
      <button onclick="event.stopPropagation();deleteTVAccount('${acc.id}')"
              style="background:none;border:none;cursor:pointer;padding:0 0 0 4px;opacity:.5;color:inherit;font-size:13px"
              title="Remove account">×</button>
    </div>`).join('');
}

window.activateTVAccount = async function(accountId) {
  try {
    const config = await fetch(`/api/tradingview/accounts/${accountId}/activate`, { method: 'POST' }).then(r => r.json());
    _tvConfig = { ..._tvConfig, ...config };
    _tvWidget = null;
    _tvInitialized = false;
    buildTVWidget(_tvConfig);
    loadTVAccounts();
    ToastManager.show({ title: 'Account activated', type: 'info', duration: 2000 });
  } catch (err) { console.error(err); }
};

window.deleteTVAccount = async function(accountId) {
  try {
    await fetch(`/api/tradingview/accounts/${accountId}`, { method: 'DELETE' });
    loadTVAccounts();
  } catch (err) { console.error(err); }
};

async function saveNewTVAccount() {
  const username    = document.getElementById('acc-username')?.value.trim();
  const displayName = document.getElementById('acc-display')?.value.trim();
  const symbol      = document.getElementById('acc-symbol')?.value.trim()    || 'CME_MINI:MES1!';
  const interval    = document.getElementById('acc-interval')?.value          || '5';
  if (!username) { ToastManager.show({ title: 'Username required', type: 'warn' }); return; }
  try {
    await fetch('/api/tradingview/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, display_name: displayName || username, symbol, interval }),
    });
    ModalManager.close();
    loadTVAccounts();
    ToastManager.show({ title: 'Account saved', body: displayName || username, type: 'info', duration: 2500 });
    // Clear form
    ['acc-username','acc-display','acc-symbol'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  } catch (err) { console.error(err); }
}

/* ============================================================
   BOOT
   ============================================================ */
document.addEventListener('DOMContentLoaded', async () => {
  initNavScroll();
  initParallax();
  initStagger();
  initToggles();
  initSidebar();
  initViewNavigation();

  setTimeout(revealContent, 400);
  await pollAll();
  setInterval(pollAll, POLL_INTERVAL_MS);

  // Wire close buttons
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => { ModalManager.close(); SheetManager.close(); });
  });
  document.querySelectorAll('[data-open-sheet]').forEach(btn => {
    btn.addEventListener('click', () => SheetManager.open(btn.dataset.openSheet));
  });
  document.querySelectorAll('[data-open-modal]').forEach(btn => {
    btn.addEventListener('click', () => ModalManager.open(btn.dataset.openModal));
  });

  // TradingView controls
  document.getElementById('btn-tv-apply')?.addEventListener('click', applyTVSettings);
  document.getElementById('tv-symbol-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') applyTVSettings(); });

  document.getElementById('btn-tv-fullscreen')?.addEventListener('click', () => {
    const wrap = document.getElementById('tv-chart-wrap');
    if (wrap) wrap.requestFullscreen?.() || wrap.webkitRequestFullscreen?.();
  });

  document.getElementById('btn-tv-login')?.addEventListener('click', () => {
    window.open('https://www.tradingview.com/signin/', '_blank', 'noopener');
    ToastManager.show({ title: 'Sign in on TradingView', body: 'After logging in, return here — the chart will use your session.', type: 'info', duration: 6000 });
  });

  document.getElementById('btn-add-account')?.addEventListener('click', () => ModalManager.open('add-account-modal'));
  document.getElementById('btn-save-account')?.addEventListener('click', saveNewTVAccount);

  // Boot toast
  setTimeout(() => {
    ToastManager.show({ title: 'Dashboard connected', body: 'Live data polling every 5 seconds.', type: 'info', duration: 4000 });
  }, 800);
});
