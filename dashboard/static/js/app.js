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

let _currentPerfRange = 'all';

function switchView(viewName) {
  if (viewName === 'performance') {
    loadPerformance(_currentPerfRange);
  }
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
  if (viewName === 'brokers') Brokers.load();
  if (viewName === 'ai-chat') Chat.loadSessions();
  if (viewName === 'backtest') Backtest.init();
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

    updateTVTradeBar();
  } catch (err) { console.error('Status poll failed:', err); }
}

let _signalCache = [];

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
    _signalCache = data.signals;

    if (data.signals.length === 0) {
      feed.innerHTML = `<div class="signal-row" style="justify-content:center;opacity:1;"><span class="text-tertiary text-footnote">No signals yet today</span></div>`;
      return;
    }

    feed.innerHTML = data.signals.map((s, i) => {
      const action = (s.action || '').toLowerCase();
      const time   = s.received_at ? new Date(s.received_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';
      const price  = s.price ? Number(s.price).toFixed(2) : '';
      return `
        <div class="signal-row" style="--i:${i}" data-signal-idx="${i}">
          <span class="action-badge ${action}">${(s.action || '').toUpperCase()}</span>
          <div class="signal-meta">
            <div class="signal-symbol">${s.symbol || '—'}</div>
            <div class="signal-reason">${s.reason || ''}</div>
          </div>
          <span class="signal-price">${price}</span>
          <span class="signal-time">${time}</span>
        </div>`;
    }).join('');

    // Attach click listeners after rendering (avoids JSON-in-HTML quoting bugs)
    feed.querySelectorAll('.signal-row[data-signal-idx]').forEach(row => {
      row.addEventListener('click', () => {
        const sig = _signalCache[Number(row.dataset.signalIdx)];
        if (sig) openSignalDetail(sig);
      });
    });
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
window.openSignalDetail = function(signalOrJson) {
  try {
    const s = (typeof signalOrJson === 'string') ? JSON.parse(signalOrJson) : signalOrJson;
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
  await Promise.allSettled([
    refreshStatus(), refreshSignals(), refreshPerformance(), refreshPnL(),
    refreshMode(), refreshRiskStatus(), refreshPendingSignal(),
  ]);
}

/* ============================================================
   STRATEGIES
   ============================================================ */
let _strategiesLoaded = false;
let _strategyMap = {};
const JEWEL_COLORS = ['blue','purple','orange','green','red','blue','purple','orange','green','red','blue','purple','orange','green','red','blue'];

async function loadStrategies() {
  if (_strategiesLoaded) return;
  try {
    const data = await fetch('/api/strategies').then(r => r.json());
    const grid  = document.getElementById('strategy-grid');
    const badge = document.getElementById('strategy-count-badge');
    if (!grid) return;

    if (badge) badge.textContent = `${data.count} loaded`;

    // Store data in a map so click handlers never embed JSON in HTML
    _strategyMap = {};
    data.strategies.forEach(s => { _strategyMap[s.id] = s; });

    grid.innerHTML = data.strategies.map((s, i) => {
      const color = JEWEL_COLORS[i % JEWEL_COLORS.length];
      return `
        <article class="strategy-card" role="listitem" data-stagger data-strategy-id="${s.id}">
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

    // Attach click listeners after rendering (no inline JSON in HTML)
    grid.querySelectorAll('.strategy-card[data-strategy-id]').forEach(card => {
      card.addEventListener('click', () => openStrategyDetail(card.dataset.strategyId));
    });

    grid.querySelectorAll('[data-stagger]').forEach((el, i) => {
      el.style.setProperty('--i', String(i));
      el.classList.add('stagger-child');
    });
    _strategiesLoaded = true;
  } catch (err) { console.error('Strategies load failed:', err); }
}

window.openStrategyDetail = async function(strategyId) {
  const meta = _strategyMap[strategyId] || {};
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
let _tvConfig = { symbol: 'AMEX:SPY', interval: '5', theme: 'dark', style: '1' };
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
    symbol:              cfg.symbol   || 'AMEX:SPY',
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
  if (symbolInput)    symbolInput.value   = cfg.symbol   || 'AMEX:SPY';
  if (intervalSelect) intervalSelect.value = cfg.interval || '5';
  if (styleSelect)    styleSelect.value   = cfg.style    || '1';
}

async function initTVWidget() {
  if (_tvInitialized) return;
  _tvInitialized = true;
  await fetchTVConfig();
  // Defer one frame so the flex container has a computed height before the widget queries it
  await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 50)));
  try {
    buildTVWidget(_tvConfig);
  } catch (err) {
    _tvInitialized = false; // allow retry on next view switch
    console.error('TradingView widget init failed:', err);
  }
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
  const symbol      = document.getElementById('acc-symbol')?.value.trim()    || 'AMEX:SPY';
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
   MANUAL TRADE CONTROLS (TradingView view)
   ============================================================ */
window.manualTrade = async function(action) {
  const symbol = document.getElementById('tv-symbol-input')?.value.trim() || _tvConfig.symbol;
  const label  = action === 'BUY' ? 'BUY (Long)' : action === 'SELL' ? 'SELL (Short)' : 'CLOSE ALL positions';
  if (!confirm(`Confirm: ${label} on ${symbol}?`)) return;

  const btn = document.getElementById(`tv-trade-${action.toLowerCase()}`);
  if (btn) { btn.disabled = true; btn.textContent = '…'; }

  try {
    const res  = await fetch('/api/trade/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, symbol, reason: `Manual ${action} from dashboard` }),
    });
    const data = await res.json();
    if (data.error) {
      ToastManager.show({ title: `Trade rejected`, body: data.error, type: 'warn' });
    } else {
      ToastManager.show({
        title: `${action} submitted`,
        body: symbol,
        type: action === 'BUY' ? 'buy' : action === 'SELL' ? 'sell' : 'close',
        duration: 3000,
      });
      refreshSignals();
    }
  } catch (err) {
    ToastManager.show({ title: `Network error`, body: err.message, type: 'warn' });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = action === 'CLOSE' ? 'Close All' : action;
    }
  }
};

window.tvPauseResume = async function(pause) {
  try {
    await fetch(pause ? '/api/pause' : '/api/resume', { method: 'POST' });
    await refreshStatus();
    updateTVTradeBar();
  } catch (err) { console.error(err); }
};

function updateTVTradeBar() {
  const gatePill = document.getElementById('trading-gate');
  const isActive = gatePill?.classList.contains('gate-active');
  const isPaused = gatePill?.classList.contains('gate-paused');

  const statusEl  = document.getElementById('tv-trade-status');
  const pauseBtn  = document.getElementById('tv-btn-pause');
  const resumeBtn = document.getElementById('tv-btn-resume');

  if (statusEl) {
    statusEl.textContent = isPaused ? 'Paused' : isActive ? 'Active' : 'Inactive';
    statusEl.className   = `tv-trade-status-text ${isPaused ? 'text-loss' : isActive ? 'text-profit' : 'text-neutral'}`;
  }
  if (pauseBtn)  pauseBtn.style.display  = isPaused ? 'none' : 'inline-flex';
  if (resumeBtn) resumeBtn.style.display = isPaused ? 'inline-flex' : 'none';
}

/* ============================================================
   AI CHAT
   ============================================================ */
const Chat = (() => {
  let _sessionId = null;
  let _sending   = false;

  // ── Session list ────────────────────────────────────────────
  async function refreshSessionList() {
    try {
      const data = await fetch('/api/ai/chat/sessions').then(r => r.json());
      renderSessionList(data.sessions || []);
    } catch (_) {}
  }

  async function loadSessions() {
    try {
      const data = await fetch('/api/ai/chat/sessions').then(r => r.json());
      const sessions = data.sessions || [];
      renderSessionList(sessions);
      // Auto-load the most recent session so the user can chat immediately
      if (sessions.length && !_sessionId) {
        await loadSession(sessions[0].id);
      }
    } catch (_) {}
  }

  function renderSessionList(sessions) {
    const list = document.getElementById('chat-session-list');
    if (!list) return;
    if (!sessions.length) {
      list.innerHTML = '<p style="font-size:12px;opacity:.4;padding:4px 8px">No conversations yet</p>';
      return;
    }
    list.innerHTML = sessions.map(s => `
      <div class="chat-session-item ${s.id === _sessionId ? 'is-active' : ''}"
           data-session-id="${s.id}">
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(s.title)}">${escHtml(s.title)}</span>
        <button class="chat-session-del" data-del-session="${s.id}" title="Delete chat">×</button>
      </div>`).join('');

    list.querySelectorAll('.chat-session-item').forEach(el => {
      el.addEventListener('click', e => {
        if (e.target.dataset.delSession) return;
        loadSession(el.dataset.sessionId);
      });
    });
    list.querySelectorAll('[data-del-session]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        deleteSession(btn.dataset.delSession);
      });
    });
  }

  // ── Create / load session ────────────────────────────────────
  async function createSession() {
    try {
      const res  = await fetch('/api/ai/chat/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const sess = await res.json();
      if (!res.ok || !sess.id) {
        ToastManager.show({ title: 'Could not create chat', body: sess.error || 'Server error', type: 'warn' });
        return null;
      }
      await loadSession(sess.id);   // sets _sessionId and enables input
      refreshSessionList();          // update sidebar without triggering auto-load again
      return sess.id;
    } catch (err) {
      console.error(err);
      ToastManager.show({ title: 'Network error', body: err.message, type: 'warn' });
      return null;
    }
  }

  async function loadSession(sessionId) {
    if (!sessionId) return;
    _sessionId = sessionId;
    enableInput(false);

    const titleEl = document.getElementById('chat-current-title');
    if (titleEl) titleEl.textContent = 'Loading…';

    try {
      const res  = await fetch(`/api/ai/chat/sessions/${sessionId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load session');
      if (titleEl) titleEl.textContent = data.session?.title || 'Chat';
      renderMessages(data.messages || []);
      enableInput(true);
      await refreshSessionList();
    } catch (err) {
      console.error(err);
      if (titleEl) titleEl.textContent = 'Error — retry';
      enableInput(false); // keep disabled but reset sessionId so user can try again
      _sessionId = null;
      ToastManager.show({ title: 'Failed to load chat', body: String(err.message), type: 'warn' });
    }
  }

  async function deleteSession(sessionId) {
    try {
      await fetch(`/api/ai/chat/sessions/${sessionId}`, { method: 'DELETE' });
      if (_sessionId === sessionId) {
        _sessionId = null;
        const titleEl = document.getElementById('chat-current-title');
        if (titleEl) titleEl.textContent = 'Select or start a chat';
        renderMessages([]);
        enableInput(false);
      }
      refreshSessionList();
    } catch (err) { console.error(err); }
  }

  // ── Message rendering ────────────────────────────────────────
  function renderMessages(messages) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    if (!messages.length) {
      container.innerHTML = `
        <div class="chat-empty" id="chat-empty-state">
          <div class="chat-empty-icon">💬</div>
          <p class="chat-empty-text">Start typing below to chat with Lucid AI about markets, strategies, or trade planning.</p>
          <div class="chat-starter-grid">
            <button class="chat-starter-chip" data-starter="What are the key ICT concepts I should know for trading MES futures?">
              <strong>ICT Concepts</strong>What should I know for MES futures?
            </button>
            <button class="chat-starter-chip" data-starter="Explain SMC order blocks and how to identify them on a 5-minute chart.">
              <strong>Order Blocks</strong>How do I identify them on 5m?
            </button>
            <button class="chat-starter-chip" data-starter="What is the ideal risk-reward ratio for day trading futures and why?">
              <strong>Risk Management</strong>Best R:R for day trading?
            </button>
            <button class="chat-starter-chip" data-starter="Walk me through a complete ORB (Opening Range Breakout) strategy setup for RTH.">
              <strong>ORB Strategy</strong>Setup for RTH open
            </button>
          </div>
        </div>`;
      wireStarterChips();
      return;
    }

    container.innerHTML = messages.map(m => buildBubble(m.role, m.content, m.created_at)).join('');
    scrollToBottom();
  }

  function buildBubble(role, content, ts) {
    const time = ts ? new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';
    return `
      <div class="chat-bubble ${escHtml(role)}">
        <span class="chat-bubble-role">${role === 'user' ? 'You' : 'Lucid AI'}</span>
        <div class="chat-bubble-content">${escHtml(content)}</div>
        ${time ? `<span class="chat-bubble-time">${time}</span>` : ''}
      </div>`;
  }

  function appendBubble(role, content, ts) {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    const empty = container.querySelector('.chat-empty');
    if (empty) empty.remove();
    container.insertAdjacentHTML('beforeend', buildBubble(role, content, ts));
    scrollToBottom();
  }

  function showThinking() {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    container.insertAdjacentHTML('beforeend', `
      <div class="chat-thinking" id="chat-thinking-indicator">
        Thinking
        <div class="chat-thinking-dots">
          <span></span><span></span><span></span>
        </div>
      </div>`);
    scrollToBottom();
  }

  function hideThinking() {
    document.getElementById('chat-thinking-indicator')?.remove();
  }

  function scrollToBottom() {
    const container = document.getElementById('chat-messages');
    if (container) container.scrollTop = container.scrollHeight;
  }

  // ── Send message ─────────────────────────────────────────────
  async function sendMessage(content) {
    if (_sending || !content.trim() || !_sessionId) return;
    _sending = true;
    enableInput(false);

    appendBubble('user', content, new Date().toISOString());
    showThinking();

    try {
      const res  = await fetch(`/api/ai/chat/sessions/${_sessionId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      const data = await res.json();
      hideThinking();

      const reply = data.reply || '';
      appendBubble('assistant', reply || '(no reply)', new Date().toISOString());
      refreshSessionList();
      const titleEl = document.getElementById('chat-current-title');
      if (titleEl && titleEl.textContent === 'New Chat') {
        titleEl.textContent = content.slice(0, 60) + (content.length > 60 ? '…' : '');
      }
    } catch (err) {
      hideThinking();
      ToastManager.show({ title: 'Message failed', body: err.message, type: 'warn' });
    }

    _sending = false;
    enableInput(true);
    const input = document.getElementById('chat-input');
    if (input) { input.value = ''; input.style.height = 'auto'; input.focus(); }
  }

  // ── Helpers ──────────────────────────────────────────────────
  function enableInput(on) {
    const input = document.getElementById('chat-input');
    const btn   = document.getElementById('chat-send-btn');
    if (input) input.disabled = !on;
    if (btn)   btn.disabled   = !on;
  }

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function wireStarterChips() {
    document.querySelectorAll('.chat-starter-chip[data-starter]').forEach(chip => {
      chip.addEventListener('click', async () => {
        if (!_sessionId) {
          const newId = await createSession();
          if (!newId) return; // session creation failed — toast already shown
        }
        sendMessage(chip.dataset.starter);
      });
    });
  }

  // ── Init ─────────────────────────────────────────────────────
  function init() {
    document.getElementById('btn-new-chat')?.addEventListener('click', createSession);

    const input = document.getElementById('chat-input');
    const btn   = document.getElementById('chat-send-btn');

    if (input) {
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendMessage(input.value.trim());
        }
      });
      input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
      });
    }

    if (btn) btn.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      if (input) sendMessage(input.value.trim());
    });

    wireStarterChips();
    loadSessions();
  }

  return { init, loadSessions };
})();

/* ============================================================
   TRADING MODE
   ============================================================ */
async function refreshMode() {
  try {
    const r = await fetch('/api/mode');
    if (!r.ok) return;
    const data = await r.json();
    updateModeSwitcher(data.trading_mode || 'SEMI_AUTO');
    const accountName = data.account_name || '';
    const el = document.getElementById('risk-account-name');
    if (el && accountName) el.textContent = accountName;
  } catch (_) {}
}

function updateModeSwitcher(mode) {
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.mode === mode);
  });
}

async function setMode(modeName) {
  try {
    const r = await fetch('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: modeName }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const reason = data.error || 'Mode change failed';
      ToastManager.show({ title: reason, type: 'warn', duration: 4000 });
      return;
    }
    updateModeSwitcher(modeName);
    const labels = { FULL_AUTO: 'Full Auto', SEMI_AUTO: 'Semi Auto', SIGNALS_ONLY: 'Signals Only' };
    ToastManager.show({ title: `Mode: ${labels[modeName] || modeName}`, type: 'info', duration: 3000 });
  } catch (_) {}
}

/* ============================================================
   RISK STATUS
   ============================================================ */
async function refreshRiskStatus() {
  try {
    const r = await fetch('/api/risk/status');
    if (!r.ok) return;
    const d = await r.json();
    if (d.error) return;
    updateRiskPanel(d);
  } catch (_) {}
}

function updateRiskPanel(d) {
  const dllPct   = document.getElementById('dll-pct-text');
  const dllBar   = document.getElementById('dll-bar');
  const pnlEl    = document.getElementById('risk-daily-pnl');
  const ddEl     = document.getElementById('risk-drawdown');
  const badgeEl  = document.getElementById('risk-mode-badge');

  const usedPct = d.dll_used_pct || 0;
  const level   = d.halt_level || 0;

  if (dllPct) dllPct.textContent = d.daily_loss_limit > 0 ? `${usedPct}%` : 'No limit';
  if (dllBar) {
    dllBar.style.width = Math.min(usedPct, 100) + '%';
    dllBar.className   = `dll-bar-fill level-${level}`;
  }
  if (pnlEl) {
    const pnl = d.daily_pnl || 0;
    pnlEl.textContent  = (pnl >= 0 ? '+' : '') + '$' + Math.abs(pnl).toFixed(2);
    pnlEl.style.color  = pnl >= 0 ? '#34c759' : '#ff3b30';
  }
  if (ddEl)    ddEl.textContent  = `${(d.drawdown_pct || 0).toFixed(1)}%`;
  if (badgeEl) {
    const riskMode = d.risk_mode || 'BALANCED';
    const colors   = { PROTECTED: 'close', BALANCED: 'info', FREE: 'buy', SIMULATION: 'neutral' };
    badgeEl.textContent  = riskMode;
    badgeEl.className    = `action-badge ${colors[riskMode] || 'info'}`;
  }
}

/* ============================================================
   PENDING SIGNAL (SEMI-AUTO APPROVAL)
   ============================================================ */
async function refreshPendingSignal() {
  try {
    const r = await fetch('/api/signals/pending');
    if (!r.ok) return;
    const data = await r.json();
    renderPendingSignal(data.pending);
  } catch (_) {}
}

function renderPendingSignal(pending) {
  const container = document.getElementById('pending-signal-container');
  if (!container) return;
  if (!pending) { container.innerHTML = ''; return; }

  const secs = pending.seconds_remaining || 0;
  container.innerHTML = `
    <div class="pending-signal-card">
      <div class="flex items-center justify-between" style="margin-bottom:var(--space-2)">
        <span style="font-size:12px;font-weight:600;color:#ff9f0a">⏳ Awaiting Approval</span>
        <span class="signal-timer pending-timer">${secs}s</span>
      </div>
      <p class="text-caption-1 text-secondary" style="margin-bottom:var(--space-3)">
        Semi-Auto signal pending your approval.
      </p>
      <div class="pending-actions">
        <button class="btn btn-success btn-md" style="flex:1" onclick="approveSignal('${pending.signal_id}')">✅ Approve</button>
        <button class="btn btn-destructive btn-md" style="flex:1" onclick="rejectSignal('${pending.signal_id}')">❌ Reject</button>
      </div>
    </div>`;

  // Countdown
  let t = secs;
  const timer = container.querySelector('.pending-timer');
  const interval = setInterval(() => {
    t--;
    if (timer) timer.textContent = `${Math.max(0, t)}s`;
    if (t <= 0) clearInterval(interval);
  }, 1000);
}

async function approveSignal(signalId) {
  await fetch(`/api/signals/${signalId}/approve`, { method: 'POST' });
  document.getElementById('pending-signal-container').innerHTML = '';
  ToastManager.show({ title: 'Signal approved', type: 'buy', duration: 3000 });
}

async function rejectSignal(signalId) {
  await fetch(`/api/signals/${signalId}/reject`, { method: 'POST' });
  document.getElementById('pending-signal-container').innerHTML = '';
  ToastManager.show({ title: 'Signal rejected', type: 'sell', duration: 3000 });
}

/* ============================================================
   TRADING ACCOUNTS
   ============================================================ */
async function loadTradingAccounts() {
  try {
    const r = await fetch('/api/accounts');
    if (!r.ok) return;
    const data = await r.json();
    renderTradingAccounts(data.accounts || []);
  } catch (_) {}
}

function renderTradingAccounts(accounts) {
  const container = document.getElementById('trading-accounts-list');
  if (!container) return;
  if (!accounts.length) {
    container.innerHTML = '<p class="text-caption-1 text-tertiary">No accounts yet. Add one below.</p>';
    return;
  }
  const riskColors = { PROTECTED: '#ff9f0a', BALANCED: '#64d2ff', FREE: '#34c759', SIMULATION: 'rgba(255,255,255,.4)' };
  container.innerHTML = accounts.map(a => `
    <div class="flex items-center justify-between" style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.06)">
      <div>
        <span style="font-size:13px;font-weight:600">${a.name}</span>
        <span style="font-size:10px;margin-left:6px;color:${riskColors[a.risk_mode]||'rgba(255,255,255,.4)'}">${a.risk_mode}</span>
        ${a.is_active ? '<span class="action-badge buy" style="font-size:9px;margin-left:4px">ACTIVE</span>' : ''}
      </div>
      <div class="flex items-center gap-2">
        <span class="text-mono text-caption-1 text-secondary">$${Number(a.current_balance||0).toLocaleString()}</span>
        ${!a.is_active ? `<button class="btn btn-secondary btn-sm" style="font-size:10px;padding:3px 8px" onclick="switchTradingAccount('${a.id}')">Switch</button>` : ''}
      </div>
    </div>`).join('');
}

async function switchTradingAccount(accountId) {
  try {
    const r = await fetch('/api/accounts/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId }),
    });
    if (!r.ok) { ToastManager.show({ title: 'Switch failed', type: 'warn', duration: 3000 }); return; }
    await loadTradingAccounts();
    await refreshMode();
    await refreshRiskStatus();
    ToastManager.show({ title: 'Account switched', type: 'info', duration: 3000 });
  } catch (_) {}
}

async function createTradingAccount() {
  const name    = document.getElementById('ta-name')?.value?.trim();
  const type    = document.getElementById('ta-type')?.value;
  const risk    = document.getElementById('ta-risk')?.value;
  const balance = parseFloat(document.getElementById('ta-balance')?.value || '0');
  const dll     = parseFloat(document.getElementById('ta-dll')?.value || '0');

  if (!name) { ToastManager.show({ title: 'Account name required', type: 'warn', duration: 3000 }); return; }
  try {
    const r = await fetch('/api/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, account_type: type, risk_mode: risk, starting_balance: balance, daily_loss_limit: dll }),
    });
    if (!r.ok) { ToastManager.show({ title: 'Failed to create account', type: 'warn', duration: 3000 }); return; }
    await loadTradingAccounts();
    ToastManager.show({ title: `Account "${name}" created`, type: 'buy', duration: 4000 });
  } catch (_) {}
}

/* ============================================================
   STRATEGY PERFORMANCE
   ============================================================ */
async function loadPerformance(range) {
  _currentPerfRange = range || 'all';
  document.querySelectorAll('.range-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.range === _currentPerfRange);
  });

  try {
    const r = await fetch(`/api/performance/strategies?range=${_currentPerfRange}`);
    if (!r.ok) return;
    const data = await r.json();
    renderPerformanceTable(data.strategies || []);
  } catch (_) {}
}

function renderPerformanceTable(strategies) {
  const tbody = document.getElementById('perf-tbody');
  if (!tbody) return;

  if (!strategies.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary,rgba(255,255,255,.4));padding:32px">No closed trades found.</td></tr>';
    updatePerfSummary([], 0);
    return;
  }

  const totalPnl   = strategies.reduce((s, x) => s + (x.total_pnl || 0), 0);
  const totalWins  = strategies.reduce((s, x) => s + (x.winning_trades || 0), 0);
  const totalTrades= strategies.reduce((s, x) => s + (x.total_trades || 0), 0);
  const sysWr      = totalTrades > 0 ? (totalWins / totalTrades * 100).toFixed(0) : 0;

  updatePerfSummary(strategies, totalPnl, sysWr);

  tbody.innerHTML = strategies.map((s, i) => {
    const pnlColor  = s.total_pnl >= 0 ? '#34c759' : '#ff3b30';
    const streakDir = (s.current_streak || 0) >= 0 ? '🟢' : '🔴';
    let badgeHtml   = '';
    if (s.is_underperforming) {
      badgeHtml = '<span class="perf-badge perf-badge-under">⚠ Under</span>';
    } else if ((s.win_rate_pct || 0) >= 55) {
      badgeHtml = '<span class="perf-badge perf-badge-good">✓</span>';
    }
    return `<tr>
      <td class="text-tertiary" style="font-size:11px">${i + 1}</td>
      <td style="font-weight:600;font-size:12px">${s.strategy_name || '?'}</td>
      <td>${(s.win_rate_pct || 0).toFixed(1)}%</td>
      <td style="color:${pnlColor};font-variant-numeric:tabular-nums">${s.total_pnl >= 0 ? '+' : ''}$${(s.total_pnl || 0).toFixed(2)}</td>
      <td>${s.total_trades || 0}</td>
      <td>${streakDir} ${Math.abs(s.current_streak || 0)}</td>
      <td>${badgeHtml}</td>
    </tr>`;
  }).join('');
}

function updatePerfSummary(strategies, totalPnl, sysWr) {
  const pnlEl  = document.getElementById('perf-total-pnl');
  const wrEl   = document.getElementById('perf-sys-wr');
  const bestEl = document.getElementById('perf-best-name');

  if (pnlEl) {
    pnlEl.textContent = (totalPnl >= 0 ? '+' : '') + '$' + Math.abs(totalPnl).toFixed(2);
    pnlEl.style.color  = totalPnl >= 0 ? '#34c759' : '#ff3b30';
  }
  if (wrEl)   wrEl.textContent  = sysWr + '%';
  if (bestEl && strategies.length) bestEl.textContent = strategies[0].strategy_name || '—';
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

  Chat.init();
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
    window.open('https://www.tradingview.com/accounts/signin/', '_blank', 'noopener');
    ToastManager.show({ title: 'Sign in on TradingView', body: 'After logging in, return here — the chart will use your session.', type: 'info', duration: 6000 });
  });

  document.getElementById('btn-add-account')?.addEventListener('click', () => ModalManager.open('add-account-modal'));
  document.getElementById('btn-save-account')?.addEventListener('click', saveNewTVAccount);

  // Trading account modal — load accounts when it opens
  const taModal = document.getElementById('trading-account-modal');
  if (taModal) {
    const observer = new MutationObserver(() => {
      if (taModal.classList.contains('open')) loadTradingAccounts();
    });
    observer.observe(taModal, { attributes: true, attributeFilter: ['class'] });
  }

  // Close trading-account-modal on backdrop click
  taModal?.addEventListener('click', e => { if (e.target === taModal) taModal.classList.remove('open'); });

  // Boot toast
  setTimeout(() => {
    ToastManager.show({ title: 'Dashboard connected', body: 'Live data polling every 5 seconds.', type: 'info', duration: 4000 });
  }, 800);
});

/* ============================================================
   REAL-TIME SOCKET.IO
   ============================================================ */
(function initSocketIO() {
  if (typeof io === 'undefined') return; // socket.io-client not loaded

  const socket = io();

  socket.on('signal_new', (data) => {
    ToastManager.show({ title: 'New Signal', body: `${data.instrument || data.symbol} ${data.strategy || ''}`, type: 'info', duration: 6000 });
    refreshPendingSignal();
  });

  socket.on('signal_approved', (data) => {
    ToastManager.show({ title: 'Signal Approved', body: `${data.instrument || data.symbol}`, type: 'buy', duration: 4000 });
    refreshPendingSignal();
  });

  socket.on('trade_opened', (data) => {
    ToastManager.show({ title: 'Trade Opened', body: `${data.symbol || ''} @ ${data.entry || ''}`, type: 'buy', duration: 5000 });
  });

  socket.on('trade_closed', (data) => {
    const pnl = data.pnl != null ? ` P&L: $${Number(data.pnl).toFixed(2)}` : '';
    ToastManager.show({ title: 'Trade Closed', body: pnl, type: data.pnl >= 0 ? 'buy' : 'warn', duration: 5000 });
  });

  socket.on('risk_update', (data) => {
    if (typeof refreshRiskStatus === 'function') refreshRiskStatus();
  });

  socket.on('account_switched', (data) => {
    ToastManager.show({ title: 'Account Switched', body: data.name || '', type: 'info', duration: 3000 });
    if (typeof refreshMode === 'function') refreshMode();
    if (typeof refreshRiskStatus === 'function') refreshRiskStatus();
  });

  socket.on('halt_status', (data) => {
    const halted = data.halted;
    ToastManager.show({
      title: halted ? 'Trading HALTED' : 'Trading Resumed',
      type: halted ? 'warn' : 'buy',
      duration: 5000,
    });
  });
})();

/* ============================================================
   BROKERS MODULE
   ============================================================ */
const Brokers = (() => {
  let _currentBroker = null;
  let _pendingName   = null;

  const MARKET_ICONS = {
    supports_futures: { label: 'Futures', color: '#5e5ce6' },
    supports_forex:   { label: 'Forex',   color: '#32d74b' },
    supports_stocks:  { label: 'Stocks',  color: '#ff9f0a' },
    supports_crypto:  { label: 'Crypto',  color: '#ff6b6b' },
  };

  async function load() {
    try {
      const data = await fetch('/api/brokers').then(r => r.json());
      _currentBroker = data.active;
      renderBadge(data.active);
      renderCards(data.brokers);
    } catch (e) {
      console.error('Brokers.load error', e);
    }
  }

  function renderBadge(active) {
    const badge = document.getElementById('broker-active-badge');
    if (badge) badge.textContent = `Active: ${active}`;
  }

  function renderCards(brokers) {
    const container = document.getElementById('broker-cards');
    if (!container) return;
    container.innerHTML = brokers.map(b => {
      const isActive    = b.is_active;
      const connected   = b.connected;
      const statusColor = connected ? '#32d74b' : 'rgba(255,255,255,.35)';
      const statusLabel = connected ? 'Connected' : 'Not connected';

      const markets = Object.entries(MARKET_ICONS)
        .filter(([k]) => b[k])
        .map(([, v]) => `<span style="font-size:10px;padding:2px 8px;border-radius:20px;background:${v.color}22;color:${v.color};border:1px solid ${v.color}44">${v.label}</span>`)
        .join('');

      const actions = connected
        ? (!isActive
            ? `<button class="btn btn-primary btn-sm" onclick="Brokers.activate('${b.name}')">Set Active</button>`
            : `<span class="pill pill-success" style="font-size:11px">Active</span>`)
            + (b.name !== 'paper'
              ? ` <button class="btn btn-secondary btn-sm" onclick="Brokers.disconnect('${b.name}')">Disconnect</button>`
              : '')
        : `<button class="btn btn-primary btn-sm" onclick="Brokers.openModal('${b.name}','${b.display_name}',${JSON.stringify(b.connection_fields).replace(/"/g,'&quot;')})">Connect</button>`;

      return `
        <div class="card" style="border:1px solid ${isActive ? 'rgba(94,92,230,.5)' : 'rgba(255,255,255,.08)'}">
          <div class="flex items-center justify-between" style="margin-bottom:var(--space-3)">
            <div>
              <div class="text-headline" style="font-size:15px">${b.display_name}</div>
              <div style="font-size:12px;color:${statusColor};margin-top:3px">
                <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${statusColor};margin-right:5px"></span>${statusLabel}
              </div>
            </div>
            ${isActive ? '<div style="font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#5e5ce6;background:rgba(94,92,230,.12);border:1px solid rgba(94,92,230,.3);border-radius:20px;padding:3px 10px">ACTIVE</div>' : ''}
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:var(--space-4)">${markets}</div>
          <div style="display:flex;gap:8px;align-items:center">${actions}</div>
        </div>`;
    }).join('');
  }

  function openModal(name, displayName, fields) {
    _pendingName = name;
    document.getElementById('broker-modal-title').textContent = `Connect — ${displayName}`;
    document.getElementById('broker-modal-msg').textContent = '';

    const fieldsEl = document.getElementById('broker-modal-fields');
    fieldsEl.innerHTML = fields.map(f => `
      <div class="form-group">
        <label class="form-label">${f.label}</label>
        <input class="input-glass" style="width:100%;padding:10px 12px;border-radius:var(--radius-md)"
          type="${f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'}"
          id="broker-field-${f.name}"
          placeholder="${f.default || ''}"
          value="${f.default || ''}" />
      </div>`).join('');

    document.getElementById('broker-connect-modal').style.display = 'flex';
  }

  function closeModal() {
    document.getElementById('broker-connect-modal').style.display = 'none';
    _pendingName = null;
  }

  async function submitConnect() {
    if (!_pendingName) return;
    const modal    = document.getElementById('broker-connect-modal');
    const msgEl    = document.getElementById('broker-modal-msg');
    const submitBtn = document.getElementById('broker-modal-submit');
    const fields   = document.querySelectorAll('#broker-modal-fields input');

    const credentials = {};
    fields.forEach(inp => {
      const key = inp.id.replace('broker-field-', '');
      credentials[key] = inp.value;
    });

    submitBtn.disabled = true;
    msgEl.textContent  = 'Connecting…';
    msgEl.style.color  = 'rgba(255,255,255,.5)';

    try {
      const res  = await fetch(`/api/brokers/${_pendingName}/connect`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(credentials),
      });
      const data = await res.json();
      if (res.ok) {
        closeModal();
        ToastManager.show({ title: 'Broker connected', body: data.message, type: 'buy', duration: 5000 });
        load();
      } else {
        msgEl.textContent = data.error || 'Connection failed.';
        msgEl.style.color = '#ff6b6b';
      }
    } catch (e) {
      msgEl.textContent = 'Network error — is the server running?';
      msgEl.style.color = '#ff6b6b';
    } finally {
      submitBtn.disabled = false;
    }
  }

  async function activate(name) {
    try {
      const res  = await fetch(`/api/brokers/${name}/activate`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        ToastManager.show({ title: 'Broker switched', body: data.message, type: 'info', duration: 4000 });
        load();
      } else {
        ToastManager.show({ title: 'Error', body: data.error, type: 'warn', duration: 5000 });
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function disconnect(name) {
    try {
      await fetch(`/api/brokers/${name}/disconnect`, { method: 'POST' });
      ToastManager.show({ title: 'Broker disconnected', body: name, type: 'info', duration: 3000 });
      load();
    } catch (e) {
      console.error(e);
    }
  }

  // Wire modal buttons after DOM is ready
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('broker-modal-close')?.addEventListener('click', closeModal);
    document.getElementById('broker-modal-cancel')?.addEventListener('click', closeModal);
    document.getElementById('broker-modal-submit')?.addEventListener('click', submitConnect);
    document.getElementById('broker-connect-modal')?.addEventListener('click', e => {
      if (e.target === e.currentTarget) closeModal();
    });
  });

  return { load, openModal, activate, disconnect };
})();

/* ============================================================
   BACKTEST MODULE
   ============================================================ */
const Backtest = (() => {
  let _inited = false;

  // ── Initialise: load strategies & default dates ──────────────
  async function init() {
    // Always reset run-button wiring (safe to call multiple times)
    const btn = document.getElementById('bt-run-btn');
    if (btn && !btn._wired) {
      btn.addEventListener('click', run);
      btn._wired = true;
    }

    if (_inited) return;
    _inited = true;

    // Default date range: today - 30 days → today
    const now  = new Date();
    const past = new Date(now);
    past.setDate(past.getDate() - 30);

    const startEl = document.getElementById('bt-start');
    const endEl   = document.getElementById('bt-end');
    if (startEl && !startEl.value) startEl.value = past.toISOString().slice(0, 10);
    if (endEl   && !endEl.value)   endEl.value   = now.toISOString().slice(0, 10);

    // Load strategy list
    try {
      const data = await fetch('/api/backtest/strategies').then(r => r.json());
      const sel  = document.getElementById('bt-strategy');
      if (sel && data.strategies && data.strategies.length) {
        sel.innerHTML = data.strategies.map(s =>
          `<option value="${s.name}">${s.label} — ${s.description}</option>`
        ).join('');
      }
    } catch (e) {
      console.error('Backtest: failed to load strategies', e);
    }
  }

  // ── Run backtest ─────────────────────────────────────────────
  async function run() {
    const strategy = document.getElementById('bt-strategy')?.value;
    const symbol   = (document.getElementById('bt-symbol')?.value || '').trim();
    const start    = document.getElementById('bt-start')?.value;
    const end      = document.getElementById('bt-end')?.value;
    const interval = document.getElementById('bt-interval')?.value || '5m';
    const balance  = parseFloat(document.getElementById('bt-balance')?.value || '100000');
    const qty      = parseInt(document.getElementById('bt-qty')?.value || '1', 10);

    if (!strategy || !symbol || !start || !end) {
      ToastManager.show({ title: 'Missing fields', body: 'Select a strategy and fill in symbol + dates.', type: 'warn', duration: 4000 });
      return;
    }

    const btn = document.getElementById('bt-run-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Running…'; }

    setState('running');

    try {
      const res  = await fetch('/api/backtest/run', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy_name: strategy, symbol, start, end,
          interval, starting_balance: balance, qty,
        }),
      });
      const data = await res.json();

      if (!res.ok) {
        setState('error', data.error || 'Backtest failed.');
        return;
      }

      renderResults(data);
      setState('content');

      const badge = document.getElementById('bt-run-badge');
      if (badge) {
        badge.textContent = `${data.bars_tested} bars`;
        badge.style.display = 'inline-flex';
      }

      ToastManager.show({
        title: 'Backtest complete',
        body:  `${data.metrics.total_trades} trades · P&L: $${data.metrics.total_pnl}`,
        type:  data.metrics.total_pnl >= 0 ? 'buy' : 'sell',
        duration: 6000,
      });
    } catch (err) {
      setState('error', `Network error: ${err.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 13 13" class="icon-glass-stroke"><path d="M3 2l8 4.5L3 11V2Z"/></svg> Run Backtest';
      }
    }
  }

  // ── Show/hide panels ─────────────────────────────────────────
  function setState(state, errMsg) {
    const ids = ['empty', 'running', 'error', 'content'];
    ids.forEach(id => {
      const el = document.getElementById(`bt-state-${id}`);
      if (!el) return;
      el.style.display = (id === state) ? (id === 'empty' ? 'flex' : 'block') : 'none';
    });
    if (state === 'error') {
      const el = document.getElementById('bt-state-error');
      if (el) el.textContent = errMsg || 'An error occurred.';
    }
  }

  // ── Render metrics, chart, trades ────────────────────────────
  function renderResults(data) {
    const m   = data.metrics;
    const fin = data.final_balance;
    const ini = data.starting_balance;
    const ret = ini > 0 ? ((fin - ini) / ini * 100) : 0;
    const profitColor = m.total_pnl >= 0 ? '#34c759' : '#ff3b30';

    // Summary bar
    const summaryEl = document.getElementById('bt-summary-bar');
    if (summaryEl) {
      summaryEl.innerHTML = `
        <span><strong>${data.strategy_label}</strong></span>
        <span>Symbol: <strong>${data.symbol}</strong></span>
        <span>Period: <strong>${data.start} → ${data.end}</strong></span>
        <span>Interval: <strong>${data.interval}</strong></span>
        <span>Bars: <strong>${data.bars_tested}</strong></span>`;
    }

    // Metrics grid (6 cards)
    const grid = document.getElementById('bt-metrics-grid');
    if (grid) {
      const cards = [
        { label: 'Total Trades',  value: m.total_trades,                        color: 'rgba(255,255,255,.9)' },
        { label: 'Win Rate',      value: m.win_rate + '%',                      color: m.win_rate >= 50 ? '#34c759' : '#ff9f0a' },
        { label: 'Net P&L',       value: fmt$(m.total_pnl, true),               color: profitColor },
        { label: 'Return',        value: (ret >= 0 ? '+' : '') + ret.toFixed(1) + '%', color: ret >= 0 ? '#34c759' : '#ff3b30' },
        { label: 'Profit Factor', value: m.profit_factor,                       color: m.profit_factor >= 1.5 ? '#34c759' : '#ff9f0a' },
        { label: 'Max Drawdown',  value: m.max_drawdown_pct + '%',              color: m.max_drawdown_pct > 20 ? '#ff3b30' : '#ff9f0a' },
      ];
      grid.innerHTML = cards.map(c => `
        <div class="bt-metric-card">
          <div class="bt-metric-label">${c.label}</div>
          <div class="bt-metric-value" style="color:${c.color}">${c.value}</div>
        </div>`).join('');
    }

    // Equity curve
    drawEquityCurve(data.equity, ini);
    const legendEl = document.getElementById('bt-curve-legend');
    if (legendEl) legendEl.textContent = `Starting: $${ini.toLocaleString()} · Final: $${fin.toLocaleString()}`;

    // Trades table
    const tbody   = document.getElementById('bt-trades-tbody');
    const countEl = document.getElementById('bt-trade-count');
    if (countEl) countEl.textContent = `${data.trades.length} trade${data.trades.length !== 1 ? 's' : ''}`;
    if (tbody) {
      if (!data.trades.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:rgba(255,255,255,.3);padding:24px">No trades generated — try a wider date range.</td></tr>';
      } else {
        tbody.innerHTML = data.trades.map((t, i) => {
          const pc = t.pnl >= 0 ? '#34c759' : '#ff3b30';
          const pf = (t.pnl >= 0 ? '+' : '') + '$' + Math.abs(t.pnl).toFixed(2);
          return `<tr>
            <td style="font-size:11px;color:rgba(255,255,255,.35)">${i + 1}</td>
            <td><span class="action-badge ${t.side === 'Long' ? 'buy' : 'sell'}" style="font-size:10px">${t.side}</span></td>
            <td style="text-align:right">${t.qty}</td>
            <td class="text-mono">${Number(t.entry_price).toFixed(2)}</td>
            <td class="text-mono">${Number(t.exit_price).toFixed(2)}</td>
            <td class="text-mono" style="color:${pc};font-weight:600">${pf}</td>
            <td style="font-size:11px;color:rgba(255,255,255,.4);max-width:180px;overflow:hidden;text-overflow:ellipsis">${t.reason || '—'}</td>
          </tr>`;
        }).join('');
      }
    }
  }

  // ── Canvas equity chart ───────────────────────────────────────
  function drawEquityCurve(equity, startBalance) {
    const canvas = document.getElementById('bt-equity-canvas');
    if (!canvas || !equity || equity.length < 2) return;

    const dpr = window.devicePixelRatio || 1;
    const W   = canvas.parentElement.clientWidth || 600;
    const H   = 240;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + 'px';
    canvas.style.height = H + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const PAD = { top: 16, right: 14, bottom: 38, left: 64 };
    const cW  = W - PAD.left - PAD.right;
    const cH  = H - PAD.top  - PAD.bottom;

    const vals   = equity.map(e => e.equity);
    const minV   = Math.min(...vals, startBalance) * 0.999;
    const maxV   = Math.max(...vals, startBalance) * 1.001;
    const range  = maxV - minV || 1;
    const n      = equity.length;

    const xOf = i => PAD.left + (i / (n - 1)) * cW;
    const yOf = v => PAD.top  + (1 - (v - minV) / range) * cH;

    const isProfit  = vals[n - 1] >= startBalance;
    const lineColor = isProfit ? '#34c759' : '#ff3b30';

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,.055)';
    ctx.lineWidth   = 1;
    for (let g = 0; g <= 4; g++) {
      const y = PAD.top + (g / 4) * cH;
      ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke();
    }

    // Starting balance dashed reference
    const refY = yOf(startBalance);
    ctx.strokeStyle = 'rgba(255,255,255,.18)';
    ctx.lineWidth   = 1;
    ctx.setLineDash([4, 5]);
    ctx.beginPath(); ctx.moveTo(PAD.left, refY); ctx.lineTo(W - PAD.right, refY); ctx.stroke();
    ctx.setLineDash([]);

    // Gradient fill under curve
    const grad = ctx.createLinearGradient(0, PAD.top, 0, H - PAD.bottom);
    grad.addColorStop(0, isProfit ? 'rgba(52,199,89,.22)'  : 'rgba(255,59,48,.22)');
    grad.addColorStop(1, isProfit ? 'rgba(52,199,89,.01)' : 'rgba(255,59,48,.01)');

    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(vals[0]));
    for (let i = 1; i < n; i++) ctx.lineTo(xOf(i), yOf(vals[i]));
    ctx.lineTo(xOf(n - 1), H - PAD.bottom);
    ctx.lineTo(xOf(0),     H - PAD.bottom);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Equity line
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(vals[0]));
    for (let i = 1; i < n; i++) ctx.lineTo(xOf(i), yOf(vals[i]));
    ctx.strokeStyle = lineColor;
    ctx.lineWidth   = 2;
    ctx.lineJoin    = 'round';
    ctx.stroke();

    // Y-axis labels
    ctx.fillStyle    = 'rgba(255,255,255,.32)';
    ctx.font         = `${10 * dpr / dpr}px -apple-system, system-ui, sans-serif`;
    ctx.textAlign    = 'right';
    ctx.textBaseline = 'middle';
    for (let g = 0; g <= 4; g++) {
      const v = minV + (range * (4 - g) / 4);
      const y = PAD.top + (g / 4) * cH;
      const lbl = v >= 1000 ? '$' + (v / 1000).toFixed(1) + 'k' : '$' + Math.round(v);
      ctx.fillText(lbl, PAD.left - 6, y);
    }

    // X-axis date labels (3 points: start, mid, end)
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'top';
    [0, Math.floor((n - 1) / 2), n - 1].forEach(i => {
      const raw = (equity[i]?.time || '').slice(0, 10);
      ctx.fillText(raw, xOf(i), H - PAD.bottom + 5);
    });

    // End-point dot
    ctx.beginPath();
    ctx.arc(xOf(n - 1), yOf(vals[n - 1]), 4, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();
  }

  // ── Helpers ──────────────────────────────────────────────────
  function fmt$(v, signed) {
    const prefix = signed ? (v >= 0 ? '+$' : '-$') : '$';
    return prefix + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  return { init, run };
})();
