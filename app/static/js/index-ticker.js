/* Metron - Market Index Ticker */
import { metronFetch } from './utils.js';

class IndexTicker {
  constructor() {
    this.previousValues = {};
    /** Ordered keys – determines display order in the ticker bar */
    this._displayOrder = ['nifty50', 'sensex', 'sp500', 'gold', 'silver', 'usdinr'];
    this._sparklineColors = {
      positive: { stroke: '#16a34a', fill: 'rgba(22,163,74,0.08)' },
      negative: { stroke: '#dc2626', fill: 'rgba(220,38,38,0.08)' },
      neutral:  { stroke: '#888',    fill: 'rgba(136,136,136,0.06)' },
    };
    this._sparklineColorsDark = {
      positive: { stroke: '#4ade80', fill: 'rgba(74,222,128,0.10)' },
      negative: { stroke: '#f87171', fill: 'rgba(248,113,113,0.10)' },
      neutral:  { stroke: '#666',    fill: 'rgba(102,102,102,0.08)' },
    };
  }

  async init() {
    await this.fetchAndRender();
  }

  async fetchAndRender() {
    try {
      const res = await metronFetch('/api/market_indices');
      if (!res.ok) return;
      const data = await res.json();
      this._ensureDOM(data);
      for (const key of this._displayOrder) {
        if (data[key]) this.renderIndex(key, data[key]);
      }
    } catch (e) {
      console.warn('Index ticker fetch failed:', e);
    }
  }

  /** Create ticker DOM elements on first data arrival */
  _ensureDOM(data) {
    const container = document.getElementById('indexTickers');
    if (!container) return;
    for (const key of this._displayOrder) {
      const d = data[key];
      if (!d || document.getElementById(`${key}Value`)) continue;
      // Insert divider before all but the first ticker
      if (container.querySelector('.index-ticker')) {
        const div = document.createElement('div');
        div.className = 'index-divider';
        container.appendChild(div);
      }
      const ticker = document.createElement('div');
      ticker.className = 'index-ticker';
      ticker.id = `${key}Ticker`;
      ticker.title = d.name || key;
      ticker.innerHTML =
        `<span class="index-name">${this._esc(d.name || key)}</span>` +
        `<div class="index-data-row">` +
          `<div class="index-numbers">` +
            `<span class="index-value" id="${key}Value">--</span>` +
            `<span class="index-change neutral" id="${key}Change"></span>` +
          `</div>` +
          `<canvas class="sparkline-canvas" id="${key}Sparkline" width="60" height="24"></canvas>` +
        `</div>`;
      container.appendChild(ticker);
    }
  }

  _esc(s) {
    const d = document.createElement('span');
    d.textContent = s;
    return d.innerHTML;
  }

  renderIndex(key, data) {
    if (!data || data.value === 0) return;

    const valueEl  = document.getElementById(`${key}Value`);
    const changeEl = document.getElementById(`${key}Change`);

    if (valueEl) {
      const formatted = this._formatNumber(data.value);
      const prev = this.previousValues[key];
      if (prev !== undefined && prev !== data.value) {
        valueEl.classList.remove('flash-green', 'flash-red');
        void valueEl.offsetWidth;
        valueEl.classList.add(data.value > prev ? 'flash-green' : 'flash-red');
      }
      valueEl.textContent = formatted;
      this.previousValues[key] = data.value;
    }

    if (changeEl) {
      const sign  = data.change > 0 ? '+' : '';
      const arrow = data.change > 0 ? '▲' : data.change < 0 ? '▼' : '';
      const cls   = data.change > 0 ? 'positive' : data.change < 0 ? 'negative' : 'neutral';
      changeEl.innerHTML =
        `<span class="change-arrow">${arrow}</span>${sign}${data.change.toFixed(2)} (${sign}${data.pChange.toFixed(2)}%)`;
      changeEl.className = `index-change ${cls}`;
    }

    // Draw sparkline from intraday chart data
    if (data.chart && data.chart.length > 1) {
      const canvas = document.getElementById(`${key}Sparkline`);
      if (canvas) {
        const direction = data.change > 0 ? 'positive' : data.change < 0 ? 'negative' : 'neutral';
        this._drawSparkline(canvas, data.chart, direction);
      }
    }
  }

  _formatNumber(num) {
    return new Intl.NumberFormat('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(num);
  }

  /**
   * Draw a sparkline on a canvas element.
   * @param {HTMLCanvasElement} canvas
   * @param {number[]} points - array of price values
   * @param {'positive'|'negative'|'neutral'} direction
   */
  _drawSparkline(canvas, points, direction) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;

    // Set canvas resolution for sharp rendering
    canvas.width = w * dpr;
    canvas.height = h * dpr;

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    if (points.length < 2) return;

    const isDark = document.body.classList.contains('dark-theme');
    const palette = isDark ? this._sparklineColorsDark : this._sparklineColors;
    const colors = palette[direction] || palette.neutral;

    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = max - min || 1;

    const padY = 2; // vertical padding in px
    const usableH = h - padY * 2;

    // Map points to canvas coordinates
    const stepX = w / (points.length - 1);
    const coords = points.map((val, i) => ({
      x: i * stepX,
      y: padY + usableH - ((val - min) / range) * usableH,
    }));

    // Draw filled area under the line
    ctx.beginPath();
    ctx.moveTo(coords[0].x, coords[0].y);
    for (let i = 1; i < coords.length; i++) {
      ctx.lineTo(coords[i].x, coords[i].y);
    }
    ctx.lineTo(coords[coords.length - 1].x, h);
    ctx.lineTo(coords[0].x, h);
    ctx.closePath();
    ctx.fillStyle = colors.fill;
    ctx.fill();

    // Draw the line
    ctx.beginPath();
    ctx.moveTo(coords[0].x, coords[0].y);
    for (let i = 1; i < coords.length; i++) {
      ctx.lineTo(coords[i].x, coords[i].y);
    }
    ctx.strokeStyle = colors.stroke;
    ctx.lineWidth = 1.25;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Draw a small dot at the last point
    const last = coords[coords.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 1.5, 0, Math.PI * 2);
    ctx.fillStyle = colors.stroke;
    ctx.fill();
  }
}

export default IndexTicker;
