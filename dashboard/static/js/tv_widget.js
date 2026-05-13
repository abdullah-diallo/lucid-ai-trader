/**
 * TradingView Widget — vanilla JS, no framework.
 * Mounts into any element with id="tv-widget-root".
 *
 * Modes:
 *   embedded  — loads the TradingView embedded chart widget
 *   ai-draws  — polls /api/tv/drawings every 5s and lists AI drawing events
 *
 * Keyboard: Ctrl+T toggles between modes.
 */

const SYMBOLS = { MES: 'CME_MINI:MES1!', MNQ: 'CME_MINI:MNQ1!' };
const INTERVALS = { '1m': '1', '5m': '5', '15m': '15', '1H': '60', '4H': '240' };

class TradingViewWidget {
  constructor(rootId = 'tv-widget-root') {
    this.root = document.getElementById(rootId);
    if (!this.root) return;

    this.instrument = 'MES';
    this.interval   = '15m';
    this.mode       = 'embedded';
    this.drawings   = [];
    this._pollTimer = null;

    this._render();
    this._bindKeyboard();
  }

  // ── Public ──────────────────────────────────────────────────────────────────

  setInstrument(i) { this.instrument = i; this._render(); }
  setInterval(tf)  { this.interval   = tf; this._render(); }
  setMode(m)       { this.mode = m; this._render(); }

  // ── Internal ─────────────────────────────────────────────────────────────────

  _render() {
    clearInterval(this._pollTimer);
    this.root.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.style.cssText = 'height:100%;display:flex;flex-direction:column;';

    wrap.appendChild(this._buildControls());

    if (this.mode === 'embedded') {
      wrap.appendChild(this._buildEmbeddedChart());
    } else {
      wrap.appendChild(this._buildAiDrawsPanel());
      this._startPolling();
    }

    this.root.appendChild(wrap);
  }

  _buildControls() {
    const bar = document.createElement('div');
    bar.style.cssText = 'display:flex;gap:8px;padding:8px;flex-shrink:0;flex-wrap:wrap;align-items:center;';

    // Instrument buttons
    Object.keys(SYMBOLS).forEach(sym => {
      bar.appendChild(this._btn(sym, sym === this.instrument, () => this.setInstrument(sym)));
    });

    // Divider
    const div = document.createElement('span');
    div.textContent = '|';
    div.style.opacity = '0.3';
    bar.appendChild(div);

    // Timeframe buttons
    Object.keys(INTERVALS).forEach(tf => {
      bar.appendChild(this._btn(tf, tf === this.interval, () => this.setInterval(tf)));
    });

    // Mode toggle — pushed right
    const spacer = document.createElement('span');
    spacer.style.flex = '1';
    bar.appendChild(spacer);

    bar.appendChild(this._btn('Chart', this.mode === 'embedded', () => this.setMode('embedded')));
    bar.appendChild(this._btn('AI Draws', this.mode === 'ai-draws', () => this.setMode('ai-draws')));

    return bar;
  }

  _btn(label, active, onClick) {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = `
      padding:4px 10px;border-radius:4px;border:1px solid rgba(255,255,255,0.15);
      background:transparent;color:#e2e8f0;cursor:pointer;font-size:12px;
      opacity:${active ? '1' : '0.4'};transition:opacity .15s;
    `;
    b.addEventListener('click', onClick);
    return b;
  }

  _buildEmbeddedChart() {
    const container = document.createElement('div');
    container.className = 'tradingview-widget-container';
    container.style.flex = '1';

    const inner = document.createElement('div');
    inner.className = 'tradingview-widget-container__widget';
    inner.style.height = '100%';
    container.appendChild(inner);

    const script = document.createElement('script');
    script.src   = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async  = true;
    script.type   = 'text/javascript';
    script.textContent = JSON.stringify({
      autosize:           true,
      symbol:             SYMBOLS[this.instrument],
      interval:           INTERVALS[this.interval],
      timezone:           'America/New_York',
      theme:              'dark',
      style:              '1',
      locale:             'en',
      backgroundColor:    'rgba(4,4,10,1)',
      gridColor:          'rgba(255,255,255,0.04)',
      studies:            ['STD;VWAP'],
      hide_top_toolbar:   false,
    });
    container.appendChild(script);
    return container;
  }

  _buildAiDrawsPanel() {
    const panel = document.createElement('div');
    panel.style.cssText = 'flex:1;padding:1rem;overflow-y:auto;';

    this._statusEl = document.createElement('p');
    this._statusEl.style.cssText = 'color:#94a3b8;margin-bottom:.5rem;';
    this._statusEl.textContent   = 'AI Draws Mode — polling /api/tv/drawings every 5s.';
    panel.appendChild(this._statusEl);

    const countRow = document.createElement('p');
    countRow.style.color = '#64748b';
    this._countEl = countRow;
    panel.appendChild(countRow);

    const clearBtn = document.createElement('button');
    clearBtn.textContent  = 'Clear All Drawings';
    clearBtn.style.cssText = 'margin:.5rem 0;padding:6px 14px;border-radius:4px;border:1px solid #ef4444;color:#ef4444;background:transparent;cursor:pointer;';
    clearBtn.addEventListener('click', () => this._clearDrawings());
    panel.appendChild(clearBtn);

    this._listEl = document.createElement('div');
    this._listEl.style.cssText = 'margin-top:.75rem;font-family:monospace;font-size:12px;';
    panel.appendChild(this._listEl);

    this._refreshDrawingList();
    return panel;
  }

  _startPolling() {
    this._pollTimer = setInterval(() => this._poll(), 5000);
  }

  async _poll() {
    try {
      const r    = await fetch('/api/tv/drawings');
      const data = await r.json();
      if (data.drawings && data.drawings.length > 0) {
        this.drawings = [...this.drawings, ...data.drawings];
        this._refreshDrawingList();
      }
    } catch (e) {
      if (this._statusEl) this._statusEl.textContent = 'Poll error: ' + e.message;
    }
  }

  async _clearDrawings() {
    await fetch('/api/tv/clear', { method: 'POST' });
    this.drawings = [];
    this._refreshDrawingList();
  }

  _refreshDrawingList() {
    if (!this._countEl || !this._listEl) return;
    const active = this.drawings.filter(d => d.type !== 'CLEAR_ALL').length;
    this._countEl.textContent = `Active drawings: ${active}`;

    const recent = [...this.drawings].reverse().slice(0, 20);
    this._listEl.innerHTML = recent.map(d => {
      const ts = (d.timestamp || '').slice(11, 19);
      const params = JSON.stringify(d.params || {});
      return `<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.06);">
        <span style="color:#64748b">${ts}</span>
        <span style="color:#38bdf8;margin:0 6px">${d.type}</span>
        <span style="color:#94a3b8">${params}</span>
      </div>`;
    }).join('');
  }

  _bindKeyboard() {
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 't') {
        e.preventDefault();
        this.setMode(this.mode === 'embedded' ? 'ai-draws' : 'embedded');
      }
    });
  }
}

// Auto-mount when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window._tvWidget = new TradingViewWidget('tv-widget-root');
});
