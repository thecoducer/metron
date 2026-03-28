// ─── Transaction History Page ─────────────────────────────────
// Renders charts and table for CAS-imported mutual fund transactions.
// Data computation is done server-side; this module handles rendering only.

import { Formatter, chartColor, escapeHtml, escapeAttr, truncate, metronFetch } from './utils.js';
import PaginationManager from './pagination.js';

function isDark() {
  return document.body.classList.contains('dark-theme');
}

const loading = document.getElementById('txnLoading');
const empty = document.getElementById('txnEmpty');
const dataSection = document.getElementById('txnData');
const summaryCards = document.getElementById('txnSummaryCards');
const timelineChart = document.getElementById('txnTimelineChart');
const buySellChart = document.getElementById('txnBuySellChart');
const allocationChart = document.getElementById('txnAllocationChart');
const navCompareChart = document.getElementById('txnNavCompareChart');
const heatmapChart = document.getElementById('txnHeatmapChart');
const navTrendChart = document.getElementById('txnNavTrendChart');
const unitsChartEl = document.getElementById('txnUnitsChart');
const navFundSelect = document.getElementById('txnNavFundSelect');
const unitsFundSelect = document.getElementById('txnUnitsFundSelect');
const tableBody = document.getElementById('txnTableBody');
const fundFilter = document.getElementById('txnFundFilter');
const accountFilter = document.getElementById('txnAccountFilter');
const periodEl = document.getElementById('txnPeriod');

// State: raw data from API
let apiData = {};
let allTransactions = [];
let allSchemes = [];
let selectedFundIsin = '';
let currentSort = 'date_desc';
let currentAccount = '';
const txnPagination = new PaginationManager(10, 1);

const sortComparators = {
  date_asc:    (a, b) => (a.date || '').localeCompare(b.date || ''),
  date_desc:   (a, b) => (b.date || '').localeCompare(a.date || ''),
  fund_asc:    (a, b) => (a.fund_name || '').localeCompare(b.fund_name || ''),
  fund_desc:   (a, b) => (b.fund_name || '').localeCompare(a.fund_name || ''),
  type_asc:    (a, b) => (a.type || '').localeCompare(b.type || ''),
  type_desc:   (a, b) => (b.type || '').localeCompare(a.type || ''),
  amount_asc:  (a, b) => Math.abs(a.amount || 0) - Math.abs(b.amount || 0),
  amount_desc: (a, b) => Math.abs(b.amount || 0) - Math.abs(a.amount || 0),
  units_asc:   (a, b) => (a.units || 0) - (b.units || 0),
  units_desc:  (a, b) => (b.units || 0) - (a.units || 0),
  nav_asc:     (a, b) => (a.nav || 0) - (b.nav || 0),
  nav_desc:    (a, b) => (b.nav || 0) - (a.nav || 0),
  balance_asc: (a, b) => (a.balance || 0) - (b.balance || 0),
  balance_desc:(a, b) => (b.balance || 0) - (a.balance || 0),
};

async function fetchData(account) {
  const params = new URLSearchParams();
  if (account) params.set('account', account);
  const url = '/api/mutual-funds/transactions' + (params.toString() ? '?' + params : '');
  const resp = await metronFetch(url);
  if (!resp.ok) throw new Error('Failed to load');
  return resp.json();
}

async function init() {
  if (!loading || !dataSection) return;
  try {
    const data = await fetchData('');
    loading.classList.add('hidden');

    if (!data.has_data || !data.transactions.length) {
      empty.classList.remove('hidden');
      return;
    }

    applyData(data);
    dataSection.classList.remove('hidden');
    populateAccountFilter(data.accounts || []);
    renderAll();
    populateFundFilter();
    setupSorting();
    renderTable(allTransactions);

  } catch {
    loading.classList.add('hidden');
    empty.classList.remove('hidden');
  }
}

function applyData(data) {
  apiData = data;
  allTransactions = [...data.transactions]
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  allSchemes = data.schemes || [];
}

// ── Render all views (cards, period, charts) ──
function renderAll() {
  renderSummary();
  renderPeriod();
  renderTimelineChart();
  renderBuySellChart();
  renderAllocationChart();
  renderNavCompareChart();
  renderHeatmapChart();
  populatePerFundSelects();
  renderNavTrendChart();
  renderUnitsChart();
}

// ── Account Filter ──
function populateAccountFilter(accounts) {
  if (!accountFilter) return;
  const filterRow = accountFilter.closest('.txn-filter-row');
  if (accounts.length <= 1) {
    if (filterRow) filterRow.classList.add('hidden');
    return;
  }
  if (filterRow) filterRow.classList.remove('hidden');
  accountFilter.innerHTML = '<option value="">All Accounts (' + accounts.length + ')</option>';
  accounts.forEach(acc => {
    const opt = document.createElement('option');
    opt.value = acc;
    opt.textContent = acc;
    accountFilter.appendChild(opt);
  });
  accountFilter.addEventListener('change', onAccountChange);
}

async function onAccountChange() {
  currentAccount = accountFilter ? accountFilter.value : '';
  const data = await fetchData(currentAccount);
  applyData(data);
  selectedFundIsin = '';
  populateFundFilter();
  renderAll();
  rerenderTable();
}

// ── Summary Cards (from API precomputed data) ──
function renderSummary() {
  const s = apiData.summary || {};
  const cards = [
    { label: 'Total Purchases', sub: 'Money poured in', value: Formatter.formatCurrency(s.total_purchases || 0, 2), cls: 'txn-card-purchases' },
    { label: 'Total Redeemed', sub: 'Money taken out', value: Formatter.formatCurrency(s.total_redeemed || 0, 2), cls: 'txn-card-redeem' },
    { label: 'Current Invested', sub: 'Still in the game', value: Formatter.formatCurrency(s.total_current_invested || 0, 2), cls: 'txn-card-positive' },
    { label: 'Transactions', sub: 'Buys & sells combined', value: (s.transaction_count || 0).toString(), cls: 'txn-card-txns' },
    { label: 'Funds', sub: 'Active & redeemed', value: (s.unique_funds || 0).toString(), cls: 'txn-card-funds' },
  ];

  summaryCards.innerHTML = cards.map(c =>
    '<div class="txn-summary-card ' + c.cls + '">' +
      '<span class="txn-card-label">' + c.label + '</span>' +
      '<span class="txn-card-value">' + c.value + '</span>' +
      '<span class="txn-card-sub">' + c.sub + '</span>' +
    '</div>'
  ).join('');
}

// ── Period Display (from API precomputed data) ──
function renderPeriod() {
  const p = apiData.period || {};
  if (!periodEl || !p.first_date) return;

  const fmt = (d) => {
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return d;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return dt.getDate() + ' ' + months[dt.getMonth()] + ' ' + dt.getFullYear();
  };

  const years = p.duration_years || 0;
  const months = p.duration_months || 0;
  let span = '';
  if (years > 0) span += years + (years === 1 ? ' year' : ' years');
  if (years > 0 && months > 0) span += ', ';
  if (months > 0 || years === 0) span += months + (months === 1 ? ' month' : ' months');

  periodEl.innerHTML =
    '<svg class="txn-period-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>' +
    '</svg>' +
    '<span class="txn-period-range">' + fmt(p.first_date) + '</span>' +
    '<span class="txn-period-sep">\u2192</span>' +
    '<span class="txn-period-range">' + fmt(p.last_date) + '</span>' +
    '<span class="txn-period-span">(' + span + ')</span>';
  periodEl.classList.remove('hidden');
}

// ── Sort ──
function sortedTransactions(txns) {
  const fn = sortComparators[currentSort];
  return fn ? [...txns].sort(fn) : [...txns];
}

function setupSorting() {
  const table = document.getElementById('txnTable');
  if (!table) return;
  const headers = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
  headers.forEach(th => {
    th.classList.add('sortable-header');
    th.setAttribute('role', 'button');
    th.setAttribute('tabindex', '0');
    const runSort = () => {
      const asc = th.dataset.sortAsc;
      const desc = th.dataset.sortDesc;
      const defaultDir = th.dataset.sortDefault || 'desc';
      if (currentSort === desc) currentSort = asc;
      else if (currentSort === asc) currentSort = desc;
      else currentSort = defaultDir === 'asc' ? asc : desc;
      syncSortIndicators(table);
      rerenderTable();
    };
    th.addEventListener('click', runSort);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); runSort(); }
    });
  });
  syncSortIndicators(table);
}

function syncSortIndicators(table) {
  table.querySelectorAll('th[data-sort-asc][data-sort-desc]').forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    th.removeAttribute('aria-sort');
    if (currentSort === th.dataset.sortAsc) {
      th.classList.add('sorted-asc');
      th.setAttribute('aria-sort', 'ascending');
    } else if (currentSort === th.dataset.sortDesc) {
      th.classList.add('sorted-desc');
      th.setAttribute('aria-sort', 'descending');
    }
  });
}

function rerenderTable() {
  const filtered = selectedFundIsin
    ? allTransactions.filter(t => t.isin === selectedFundIsin)
    : allTransactions;
  txnPagination.goToPage(1);
  renderTable(sortedTransactions(filtered));
}

// ── Timeline Chart (SVG) — uses API cumulative_timeline ──
function renderTimelineChart() {
  if (!timelineChart) return;
  const timeline = apiData.cumulative_timeline || [];
  if (!timeline.length) {
    timelineChart.innerHTML = '<div class="txn-chart-empty">No purchase data</div>';
    return;
  }

  const dates = timeline.map(p => p.date);
  const values = timeline.map(p => p.value);

  renderAreaChart(timelineChart, dates, values, '#3b82f6',
    isDark() ? '#1e3a5f' : '#dbeafe');
  addAreaChartTooltip(timelineChart, dates, values);
}

// ── Buy vs Sell Chart (SVG bar chart) — uses API monthly_buy_sell ──
function renderBuySellChart() {
  if (!buySellChart) return;
  const monthlyArr = apiData.monthly_buy_sell || [];
  if (!monthlyArr.length) {
    buySellChart.innerHTML = '<div class="txn-chart-empty">No data</div>';
    return;
  }

  const months = monthlyArr.map(d => d.month);
  const monthly = {};
  monthlyArr.forEach(d => { monthly[d.month] = { buy: d.buy, sell: d.sell }; });

  renderBarChart(buySellChart, months, monthly);
  addBarChartTooltip(buySellChart, months, monthly);
}

// ── SVG Area Chart ──
function renderAreaChart(container, labels, values, lineColor, fillColor, opts) {
  const yFmt = (opts && opts.yFormat) || Formatter.formatCurrencyForSummary.bind(Formatter);
  const xFmt = (opts && opts.xFormat) || Formatter.formatMonthShort;
  const W = container.clientWidth || 600;
  const H = 200;
  const padL = 60, padR = 20, padT = 20, padB = 40;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  const maxVal = Math.max(...values, 1);
  const minVal = 0;

  const xScale = (i) => padL + (i / Math.max(labels.length - 1, 1)) * chartW;
  const yScale = (v) => padT + chartH - ((v - minVal) / (maxVal - minVal)) * chartH;

  const pathPoints = values.map((v, i) => `${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`);
  const linePath = 'M' + pathPoints.join('L');
  const areaPath = linePath + `L${xScale(values.length - 1).toFixed(1)},${(padT + chartH).toFixed(1)}L${padL},${(padT + chartH).toFixed(1)}Z`;

  const yTicks = 5;
  let yLabels = '';
  let gridLines = '';
  for (let i = 0; i <= yTicks; i++) {
    const val = minVal + (maxVal - minVal) * (i / yTicks);
    const y = yScale(val);
    yLabels += `<text x="${padL - 8}" y="${y + 4}" class="txn-chart-label" text-anchor="end">${yFmt(val)}</text>`;
    gridLines += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" class="txn-chart-grid"/>`;
  }

  let xLabels = '';
  const maxXLabels = Math.max(2, Math.min(6, Math.floor(chartW / 70)));
  const step = Math.max(1, Math.floor(labels.length / maxXLabels));
  for (let i = 0; i < labels.length; i += step) {
    const x = xScale(i);
    xLabels += `<text x="${x}" y="${H - 6}" class="txn-chart-label" text-anchor="middle">${xFmt(labels[i])}</text>`;
  }

  container.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    ${gridLines}
    <path d="${areaPath}" fill="${fillColor}" opacity="0.4"/>
    <path d="${linePath}" fill="none" stroke="${lineColor}" stroke-width="2"/>
    <line class="txn-crosshair-v" x1="0" y1="${padT}" x2="0" y2="${padT + chartH}"/>
    <line class="txn-crosshair-h" x1="${padL}" y1="0" x2="${W - padR}" y2="0"/>
    <circle class="txn-crosshair-dot" r="4" fill="${lineColor}" stroke="${isDark() ? '#1e1e1e' : '#fff'}" stroke-width="1.5"/>
    ${yLabels}${xLabels}
  </svg>`;
}

// ── SVG Bar Chart ──
function renderBarChart(container, months, monthly) {
  const W = container.clientWidth || 600;
  const H = 220;
  const padL = 60, padR = 20, padT = 20, padB = 60;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  const maxVal = Math.max(...months.map(m => Math.max(monthly[m].buy, monthly[m].sell)), 1);
  const barGroupW = chartW / months.length;
  const barW = Math.min(barGroupW * 0.35, 20);

  const yScale = (v) => padT + chartH - (v / maxVal) * chartH;

  const shortMonth = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const fmtMonth = m => {
    const parts = m.split('-');
    return shortMonth[parseInt(parts[1], 10) - 1] + ' ' + parts[0].substring(2);
  };

  let bars = '';
  let xLabels = '';
  // Show at most ~8 labels, evenly spaced
  const maxLabels = Math.min(months.length, Math.floor(chartW / 50));
  const step = Math.max(1, Math.ceil(months.length / maxLabels));

  months.forEach((m, i) => {
    const x = padL + i * barGroupW + barGroupW / 2;
    const buyH = (monthly[m].buy / maxVal) * chartH;
    const sellH = (monthly[m].sell / maxVal) * chartH;

    bars += `<rect x="${x - barW}" y="${padT + chartH - buyH}" width="${barW}" height="${buyH}" fill="#22c55e" rx="2" opacity="0.8"/>`;
    if (monthly[m].sell > 0) {
      bars += `<rect x="${x}" y="${padT + chartH - sellH}" width="${barW}" height="${sellH}" fill="#ef4444" rx="2" opacity="0.8"/>`;
    }

    if (i % step === 0) {
      xLabels += `<text x="${x}" y="${padT + chartH + 14}" class="txn-chart-label" text-anchor="end" transform="rotate(-45 ${x} ${padT + chartH + 14})">${fmtMonth(m)}</text>`;
    }
  });

  let yLabels = '';
  let gridLines = '';
  for (let i = 0; i <= 4; i++) {
    const val = (maxVal / 4) * i;
    const y = yScale(val);
    yLabels += `<text x="${padL - 8}" y="${y + 4}" class="txn-chart-label" text-anchor="end">${Formatter.formatCurrencyForSummary(val)}</text>`;
    gridLines += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" class="txn-chart-grid"/>`;
  }

  const legend = `<rect x="${W - 140}" y="6" width="10" height="10" fill="#22c55e" rx="2"/>
    <text x="${W - 126}" y="15" class="txn-chart-label">Buy</text>
    <rect x="${W - 90}" y="6" width="10" height="10" fill="#ef4444" rx="2"/>
    <text x="${W - 76}" y="15" class="txn-chart-label">Sell</text>`;

  container.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    ${gridLines}${bars}${yLabels}${xLabels}${legend}
    <line class="txn-crosshair-v" x1="0" y1="${padT}" x2="0" y2="${padT + chartH}"/>
  </svg>`;
}

// ── Chart Tooltips ──
function getOrCreateTooltip() {
  let tt = document.getElementById('txnChartTooltip');
  if (!tt) {
    tt = document.createElement('div');
    tt.id = 'txnChartTooltip';
    tt.className = 'txn-chart-tooltip';
    document.body.appendChild(tt);
  }
  return tt;
}

function showTooltip(tt, html, clientX, clientY) {
  tt.innerHTML = html;
  tt.classList.add('txn-tt-visible');
  const ttW = 160;
  const left = Math.min(clientX + 14, window.innerWidth - ttW - 16);
  const top = Math.max(clientY - 48, 8);
  tt.style.left = left + 'px';
  tt.style.top = top + 'px';
}

function hideTooltip(tt) {
  tt.classList.remove('txn-tt-visible');
}

function addAreaChartTooltip(container, labels, values) {
  const svg = container.querySelector('svg');
  if (!svg || !labels.length) return;

  const W = parseFloat(svg.getAttribute('width')) || 600;
  const H = parseFloat(svg.getAttribute('height')) || 200;
  const padL = 60, padR = 20, padT = 20, padB = 40;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const tt = getOrCreateTooltip();

  const crossV = svg.querySelector('.txn-crosshair-v');
  const crossH = svg.querySelector('.txn-crosshair-h');
  const crossDot = svg.querySelector('.txn-crosshair-dot');
  const maxVal = Math.max(...values, 1);
  const yScale = (v) => padT + chartH - (v / maxVal) * chartH;
  const xScale = (i) => padL + (i / Math.max(labels.length - 1, 1)) * chartW;

  svg.addEventListener('mousemove', e => {
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, (mouseX - padL) / chartW));
    const idx = Math.round(pct * (labels.length - 1));
    const label = labels[idx];
    const value = values[idx];
    if (label === undefined) return;

    const cx = xScale(idx);
    const cy = yScale(value);

    if (crossV) { crossV.setAttribute('x1', cx); crossV.setAttribute('x2', cx); crossV.style.opacity = '1'; }
    if (crossH) { crossH.setAttribute('y1', cy); crossH.setAttribute('y2', cy); crossH.style.opacity = '1'; }
    if (crossDot) { crossDot.setAttribute('cx', cx); crossDot.setAttribute('cy', cy); crossDot.style.opacity = '1'; }

    showTooltip(tt,
      '<span class="txn-tt-label">' + Formatter.formatShortDate(label) + '</span>' +
      '<span class="txn-tt-value">' + Formatter.formatCurrency(value, 2) + '</span>',
      e.clientX, e.clientY
    );
  });

  svg.addEventListener('mouseleave', () => {
    hideTooltip(tt);
    if (crossV) crossV.style.opacity = '0';
    if (crossH) crossH.style.opacity = '0';
    if (crossDot) crossDot.style.opacity = '0';
  });
}

function addBarChartTooltip(container, months, monthly) {
  const svg = container.querySelector('svg');
  if (!svg || !months.length) return;

  const W = parseFloat(svg.getAttribute('width')) || 600;
  const padL = 60, padR = 20, padT = 20;
  const chartW = W - padL - padR;
  const barGroupW = chartW / months.length;
  const tt = getOrCreateTooltip();
  const crossV = svg.querySelector('.txn-crosshair-v');

  const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  svg.addEventListener('mousemove', e => {
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const idx = Math.floor((mouseX - padL) / barGroupW);
    if (idx < 0 || idx >= months.length) { hideTooltip(tt); if (crossV) crossV.style.opacity = '0'; return; }
    const m = months[idx];
    const d = monthly[m];
    if (!d) { hideTooltip(tt); if (crossV) crossV.style.opacity = '0'; return; }

    const cx = padL + idx * barGroupW + barGroupW / 2;
    if (crossV) { crossV.setAttribute('x1', cx); crossV.setAttribute('x2', cx); crossV.style.opacity = '1'; }

    const [year, mon] = m.split('-');
    const label = monthNames[parseInt(mon)] + ' ' + year;
    showTooltip(tt,
      '<span class="txn-tt-label">' + label + '</span>' +
      (d.buy ? '<span class="txn-tt-buy">Buy: ' + Formatter.formatCurrency(d.buy, 2) + '</span>' : '') +
      (d.sell ? '<span class="txn-tt-sell">Sell: ' + Formatter.formatCurrency(d.sell, 2) + '</span>' : ''),
      e.clientX, e.clientY
    );
  });

  svg.addEventListener('mouseleave', () => {
    hideTooltip(tt);
    if (crossV) crossV.style.opacity = '0';
  });
}

// ── Fund Allocation Donut Chart ──
function renderAllocationChart() {
  if (!allocationChart) return;
  if (!allSchemes.length) {
    allocationChart.innerHTML = '<div class="txn-chart-empty">No data</div>';
    return;
  }
  // Aggregate by ISIN to avoid duplicates across accounts
  const byIsin = new Map();
  allSchemes.filter(s => s.cost > 0).forEach(s => {
    const key = s.isin || s.fund_name;
    const existing = byIsin.get(key);
    if (existing) { existing.value += s.cost; }
    else { byIsin.set(key, { name: s.fund_name || s.isin, value: s.cost }); }
  });
  const data = Array.from(byIsin.values())
    .map((d, i) => ({ ...d, color: chartColor(i) }))
    .sort((a, b) => b.value - a.value);
  if (!data.length) { allocationChart.innerHTML = '<div class="txn-chart-empty">No data</div>'; return; }

  const total = data.reduce((s, d) => s + d.value, 0);
  const size = Math.min(allocationChart.clientWidth || 300, 260);
  const cx = size / 2, cy = size / 2, r = size * 0.38, inner = size * 0.22;

  let arcs = '';
  let legendHTML = '';
  let startAngle = -Math.PI / 2;

  data.forEach((d, i) => {
    const pct = d.value / total;
    const sweep = pct * 2 * Math.PI;
    const endAngle = startAngle + sweep;
    const largeArc = sweep > Math.PI ? 1 : 0;

    const x1o = cx + r * Math.cos(startAngle), y1o = cy + r * Math.sin(startAngle);
    const x2o = cx + r * Math.cos(endAngle), y2o = cy + r * Math.sin(endAngle);
    const x1i = cx + inner * Math.cos(endAngle), y1i = cy + inner * Math.sin(endAngle);
    const x2i = cx + inner * Math.cos(startAngle), y2i = cy + inner * Math.sin(startAngle);

    const midAngle = startAngle + sweep / 2;
    const tox = (cx + (r + inner) / 2 * Math.cos(midAngle)).toFixed(2);
    const toy = (cy + (r + inner) / 2 * Math.sin(midAngle)).toFixed(2);

    arcs += '<path d="M' + x1o.toFixed(2) + ',' + y1o.toFixed(2) +
      ' A' + r + ',' + r + ' 0 ' + largeArc + ' 1 ' + x2o.toFixed(2) + ',' + y2o.toFixed(2) +
      ' L' + x1i.toFixed(2) + ',' + y1i.toFixed(2) +
      ' A' + inner + ',' + inner + ' 0 ' + largeArc + ' 0 ' + x2i.toFixed(2) + ',' + y2i.toFixed(2) +
      ' Z" fill="' + d.color + '" class="txn-donut-segment" data-idx="' + i + '"' +
      ' style="transform-origin:' + tox + 'px ' + toy + 'px"/>';

    const label = truncate(d.name, 28);
    legendHTML +=
      '<div class="txn-donut-legend-item">' +
        '<span class="txn-donut-dot" style="background:' + d.color + '"></span>' +
        '<span class="txn-donut-name">' + escapeHtml(label) + '</span>' +
        '<span class="txn-donut-pct">' + (pct * 100).toFixed(1) + '%</span>' +
      '</div>';

    startAngle = endAngle;
  });

  allocationChart.innerHTML =
    '<div class="txn-donut-wrap">' +
      '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
        arcs +
        '<text x="' + cx + '" y="' + cy + '" text-anchor="middle" class="txn-donut-total-label">Total</text>' +
        '<text x="' + cx + '" y="' + (cy + 14) + '" text-anchor="middle" class="txn-donut-total-value">' + Formatter.formatCurrencyForSummary(total) + '</text>' +
      '</svg>' +
    '</div>' +
    '<div class="txn-donut-legend">' + legendHTML + '</div>';

  const svg = allocationChart.querySelector('svg');
  const tt = getOrCreateTooltip();
  svg.addEventListener('mousemove', e => {
    const seg = e.target.closest('.txn-donut-segment');
    if (!seg) return;
    const d = data[parseInt(seg.dataset.idx)];
    if (!d) return;
    showTooltip(tt,
      '<span class="txn-tt-label">' + escapeHtml(truncate(d.name, 36)) + '</span>' +
      '<span class="txn-tt-value">' + Formatter.formatCurrency(d.value, 2) + '</span>' +
      '<span class="txn-tt-label">' + (d.value / total * 100).toFixed(1) + '%</span>',
      e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => hideTooltip(tt));
}

// ── Monthly Investment Trend ──
// ── Avg NAV vs Latest NAV ──
function renderNavCompareChart() {
  if (!navCompareChart) return;
  if (!allSchemes.length) {
    navCompareChart.innerHTML = '<div class="txn-chart-empty">No data</div>';
    return;
  }

  // Aggregate by ISIN to avoid duplicates across accounts
  const navByIsin = new Map();
  allSchemes.filter(s => s.avg_nav && s.latest_nav).forEach(s => {
    const key = s.isin || s.fund_name;
    const existing = navByIsin.get(key);
    if (existing) {
      const totalUnits = existing.units + (s.units || 0);
      if (totalUnits > 0) {
        existing.avg_nav = (existing.avg_nav * existing.units + s.avg_nav * (s.units || 0)) / totalUnits;
      }
      existing.units = totalUnits;
      existing.cost = (existing.cost || 0) + (s.cost || 0);
      existing.latest_nav = s.latest_nav;
    } else {
      navByIsin.set(key, { ...s });
    }
  });
  const schemes = Array.from(navByIsin.values())
    .sort((a, b) => (b.cost || 0) - (a.cost || 0))
    .slice(0, 10);

  if (!schemes.length) { navCompareChart.innerHTML = '<div class="txn-chart-empty">No NAV data</div>'; return; }

  const W = navCompareChart.clientWidth || 600;
  const rowH = 30, gap = 12, padL = 10, padT = 28;
  const H = padT + schemes.length * (rowH + gap) + 10;
  const maxNav = Math.max(...schemes.map(s => Math.max(s.avg_nav, s.latest_nav)));

  // Measure label widths and percentage widths
  const measSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  measSvg.style.position = 'absolute'; measSvg.style.visibility = 'hidden';
  document.body.appendChild(measSvg);
  const measText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  measText.setAttribute('class', 'txn-chart-label txn-nav-label');
  measSvg.appendChild(measText);
  let labelW = 0;
  schemes.forEach(s => {
    measText.textContent = truncate(s.fund_name || s.isin, 22);
    labelW = Math.max(labelW, measText.getBBox().width);
  });
  // Measure max pct label width
  const pctText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  pctText.setAttribute('class', 'txn-chart-label');
  pctText.style.fontWeight = '600';
  pctText.style.fontSize = '12px';
  measSvg.appendChild(pctText);
  let pctW = 0;
  schemes.forEach(s => {
    const pct = ((s.latest_nav - s.avg_nav) / s.avg_nav * 100).toFixed(1);
    pctText.textContent = (s.latest_nav >= s.avg_nav ? '+' : '') + pct + '%';
    pctW = Math.max(pctW, pctText.getBBox().width);
  });
  document.body.removeChild(measSvg);
  labelW = Math.ceil(labelW) + 14;
  const padR = Math.ceil(pctW) + 22; // space for pct label + dot + gap

  const chartW = W - padL - padR - labelW;
  const toX = nav => padL + labelW + (nav / maxNav) * chartW;

  let dumbbellHTML = '';
  schemes.forEach((s, i) => {
    const cy = padT + i * (rowH + gap) + rowH / 2;
    const name = truncate(s.fund_name || s.isin, 22);
    const x1 = toX(Math.min(s.avg_nav, s.latest_nav));
    const x2 = toX(Math.max(s.avg_nav, s.latest_nav));
    const gain = s.latest_nav >= s.avg_nav;
    const lineColor = gain ? '#22c55e' : '#ef4444';
    const pctChange = ((s.latest_nav - s.avg_nav) / s.avg_nav * 100).toFixed(1);
    const pctLabel = (gain ? '+' : '') + pctChange + '%';
    const avgX = toX(s.avg_nav);
    const latX = toX(s.latest_nav);

    // Label
    dumbbellHTML += `<text x="${padL}" y="${cy + 4}" class="txn-chart-label txn-nav-label">${escapeHtml(name)}</text>`;
    // Connecting line
    dumbbellHTML += `<line x1="${x1}" y1="${cy}" x2="${x2}" y2="${cy}" stroke="${lineColor}" stroke-width="3" stroke-linecap="round" opacity="0.35"/>`;
    // Avg NAV dot (orange)
    dumbbellHTML += `<circle cx="${avgX}" cy="${cy}" r="6" fill="#f59e0b" stroke="${isDark() ? '#1e1e1e' : '#fff'}" stroke-width="1.5"/>`;
    // Latest NAV dot (blue)
    dumbbellHTML += `<circle cx="${latX}" cy="${cy}" r="6" fill="#3b82f6" stroke="${isDark() ? '#1e1e1e' : '#fff'}" stroke-width="1.5"/>`;
    // Percentage label
    dumbbellHTML += `<text x="${x2 + 10}" y="${cy + 4}" class="txn-chart-label" fill="${lineColor}" style="font-weight:600;font-size:12px">${pctLabel}</text>`;
  });

  const legend = `<circle cx="${W - 195}" cy="8" r="4" fill="#f59e0b"/>
    <text x="${W - 188}" y="12" class="txn-chart-label">Avg NAV</text>
    <circle cx="${W - 115}" cy="8" r="4" fill="#3b82f6"/>
    <text x="${W - 108}" y="12" class="txn-chart-label">Latest NAV</text>`;

  navCompareChart.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    ${dumbbellHTML}${legend}
  </svg>`;

  const svg = navCompareChart.querySelector('svg');
  const tt = getOrCreateTooltip();
  svg.addEventListener('mousemove', e => {
    const rect = svg.getBoundingClientRect();
    const mouseY = e.clientY - rect.top;
    const idx = Math.floor((mouseY - padT) / (rowH + gap));
    if (idx < 0 || idx >= schemes.length) { hideTooltip(tt); return; }
    const s = schemes[idx];
    const gain = s.latest_nav >= s.avg_nav;
    const pct = ((s.latest_nav - s.avg_nav) / s.avg_nav * 100).toFixed(1);
    showTooltip(tt,
      '<span class="txn-tt-label">' + escapeHtml(truncate(s.fund_name || s.isin, 36)) + '</span>' +
      '<span class="txn-tt-buy">Avg NAV: \u20b9' + s.avg_nav.toFixed(4) + '</span>' +
      '<span class="txn-tt-sell">Latest NAV: \u20b9' + s.latest_nav.toFixed(4) + '</span>' +
      '<span style="color:' + (gain ? '#22c55e' : '#ef4444') + '">' + (gain ? '+' : '') + pct + '%</span>',
      e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => hideTooltip(tt));
}

// ── SIP Consistency Heatmap (month-wise) — uses API heatmap ──
function renderHeatmapChart() {
  if (!heatmapChart) return;
  const heatmapData = apiData.heatmap || [];
  if (!heatmapData.length) {
    heatmapChart.innerHTML = '<div class="txn-chart-empty">No data</div>';
    return;
  }

  const byMonth = {};
  heatmapData.forEach(d => { byMonth[d.month] = d.count; });
  const months = Object.keys(byMonth).sort();
  const firstYear = parseInt(months[0].split('-')[0]);
  const lastYear = parseInt(months[months.length - 1].split('-')[0]);
  const years = [];
  for (let y = firstYear; y <= lastYear; y++) years.push(y);

  const maxCount = Math.max(...Object.values(byMonth));
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const containerW = heatmapChart.clientWidth || 600;
  const gap = 3;
  const padL = 42, padR = 6, padT = 24, padB = 6;
  const cellW = Math.max(16, Math.floor((containerW - padL - padR - gap * 11) / 12));
  const cellH = Math.max(16, Math.min(cellW, 28));
  const W = containerW;
  const H = padT + years.length * (cellH + gap) + padB;

  const dark = document.body.classList.contains('dark-theme');
  const colorScale = (count) => {
    if (!count) return dark ? '#1e293b' : '#f1f5f9';
    const intensity = Math.min(count / maxCount, 1);
    const r = dark ? Math.round(30 + intensity * 49) : Math.round(220 - intensity * 186);
    const g = dark ? Math.round(120 + intensity * 80) : Math.round(230 - intensity * 130);
    const b = dark ? Math.round(50 + intensity * 80) : Math.round(240 - intensity * 60);
    return `rgb(${r},${g},${b})`;
  };

  // Month column headers
  let headerHTML = '';
  for (let m = 0; m < 12; m++) {
    const x = padL + m * (cellW + gap) + cellW / 2;
    headerHTML += `<text x="${x}" y="${padT - 8}" class="txn-chart-label" text-anchor="middle" font-size="10">${monthNames[m]}</text>`;
  }

  // Year rows
  let cells = '';
  let yearLabels = '';
  years.forEach((year, yi) => {
    const rowY = padT + yi * (cellH + gap);
    yearLabels += `<text x="${padL - 6}" y="${rowY + cellH / 2 + 4}" class="txn-chart-label" text-anchor="end" font-size="10">${year}</text>`;
    for (let m = 0; m < 12; m++) {
      const key = year + '-' + String(m + 1).padStart(2, '0');
      const count = byMonth[key] || 0;
      const x = padL + m * (cellW + gap);
      cells += `<rect x="${x}" y="${rowY}" width="${cellW}" height="${cellH}" rx="3" fill="${colorScale(count)}" class="txn-heatmap-cell" data-month="${key}" data-count="${count}"/>`;
    }
  });

  heatmapChart.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    ${headerHTML}${yearLabels}${cells}
  </svg>`;

  const svg = heatmapChart.querySelector('svg');
  const tt = getOrCreateTooltip();
  svg.addEventListener('mousemove', e => {
    const cell = e.target.closest('.txn-heatmap-cell');
    if (!cell) { hideTooltip(tt); return; }
    const [yr, mn] = cell.dataset.month.split('-');
    const count = parseInt(cell.dataset.count);
    showTooltip(tt,
      '<span class="txn-tt-label">' + monthNames[parseInt(mn) - 1] + ' ' + yr + '</span>' +
      '<span class="txn-tt-value">' + count + ' transaction' + (count !== 1 ? 's' : '') + '</span>',
      e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => hideTooltip(tt));
}

// ── Per-fund chart selects ──
function populatePerFundSelects() {
  const funds = new Map();
  allTransactions.forEach(t => {
    if (t.fund_name && !funds.has(t.isin)) funds.set(t.isin, t.fund_name);
  });
  const sorted = Array.from(funds.entries()).sort((a, b) => a[1].localeCompare(b[1]));

  [navFundSelect, unitsFundSelect].forEach(sel => {
    if (!sel) return;
    sel.innerHTML = '';
    sorted.forEach(([isin, name]) => {
      const opt = document.createElement('option');
      opt.value = isin;
      opt.textContent = name;
      sel.appendChild(opt);
    });
    if (sorted.length) sel.value = sorted[0][0];
  });

  if (navFundSelect) navFundSelect.addEventListener('change', renderNavTrendChart);
  if (unitsFundSelect) unitsFundSelect.addEventListener('change', renderUnitsChart);
}

// ── NAV Trend Chart ──
function renderNavTrendChart() {
  if (!navTrendChart) return;
  const isin = navFundSelect ? navFundSelect.value : '';
  if (!isin) { navTrendChart.innerHTML = '<div class="txn-chart-empty">Select a fund above</div>'; return; }

  const txns = allTransactions
    .filter(t => t.isin === isin && t.nav)
    .sort((a, b) => (a.date || '').localeCompare(b.date || ''));

  if (!txns.length) { navTrendChart.innerHTML = '<div class="txn-chart-empty">No NAV data</div>'; return; }

  const labels = txns.map(t => t.date);
  const values = txns.map(t => Number(t.nav));

  renderAreaChart(navTrendChart, labels, values, '#10b981',
    isDark() ? '#064e3b' : '#d1fae5', {
    yFormat: (v) => '\u20b9' + v.toFixed(2),
    xFormat: Formatter.formatMonthShort,
  });

  const svg = navTrendChart.querySelector('svg');
  if (!svg) return;
  const tt = getOrCreateTooltip();
  const W = parseFloat(svg.getAttribute('width')) || 600;
  const H = parseFloat(svg.getAttribute('height')) || 200;
  const padL = 60, padR = 20, padT = 20, padB = 40;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const crossV = svg.querySelector('.txn-crosshair-v');
  const crossH = svg.querySelector('.txn-crosshair-h');
  const crossDot = svg.querySelector('.txn-crosshair-dot');
  const maxVal = Math.max(...values, 1);
  const yScale = (v) => padT + chartH - (v / maxVal) * chartH;
  const xScale = (i) => padL + (i / Math.max(labels.length - 1, 1)) * chartW;

  svg.addEventListener('mousemove', e => {
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, (mouseX - padL) / chartW));
    const idx = Math.round(pct * (labels.length - 1));
    const date = labels[idx];
    const value = values[idx];
    if (date === undefined) return;

    const cx = xScale(idx);
    const cy = yScale(value);
    if (crossV) { crossV.setAttribute('x1', cx); crossV.setAttribute('x2', cx); crossV.style.opacity = '1'; }
    if (crossH) { crossH.setAttribute('y1', cy); crossH.setAttribute('y2', cy); crossH.style.opacity = '1'; }
    if (crossDot) { crossDot.setAttribute('cx', cx); crossDot.setAttribute('cy', cy); crossDot.style.opacity = '1'; }
    showTooltip(tt,
      '<span class="txn-tt-label">' + Formatter.formatShortDate(date) + '</span>' +
      '<span class="txn-tt-value">NAV: \u20b9' + value.toFixed(4) + '</span>',
      e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => {
    hideTooltip(tt);
    if (crossV) crossV.style.opacity = '0';
    if (crossH) crossH.style.opacity = '0';
    if (crossDot) crossDot.style.opacity = '0';
  });
}

// ── Units Accumulated Chart ──
function renderUnitsChart() {
  if (!unitsChartEl) return;
  const isin = unitsFundSelect ? unitsFundSelect.value : '';
  if (!isin) { unitsChartEl.innerHTML = '<div class="txn-chart-empty">Select a fund above</div>'; return; }

  const txns = allTransactions
    .filter(t => t.isin === isin && t.balance !== null && t.balance !== undefined)
    .sort((a, b) => (a.date || '').localeCompare(b.date || ''));

  if (!txns.length) { unitsChartEl.innerHTML = '<div class="txn-chart-empty">No balance data</div>'; return; }

  const labels = txns.map(t => t.date);
  const values = txns.map(t => Number(t.balance));

  renderAreaChart(unitsChartEl, labels, values, '#f59e0b',
    isDark() ? '#451a03' : '#fef3c7', {
    yFormat: (v) => v.toFixed(1),
    xFormat: Formatter.formatMonthShort,
  });

  const svg = unitsChartEl.querySelector('svg');
  if (!svg) return;
  const tt = getOrCreateTooltip();
  const W = parseFloat(svg.getAttribute('width')) || 600;
  const H = parseFloat(svg.getAttribute('height')) || 200;
  const padL = 60, padR = 20, padT = 20, padB = 40;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const crossV = svg.querySelector('.txn-crosshair-v');
  const crossH = svg.querySelector('.txn-crosshair-h');
  const crossDot = svg.querySelector('.txn-crosshair-dot');
  const maxVal = Math.max(...values, 1);
  const yScale = (v) => padT + chartH - (v / maxVal) * chartH;
  const xScale = (i) => padL + (i / Math.max(labels.length - 1, 1)) * chartW;

  svg.addEventListener('mousemove', e => {
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, (mouseX - padL) / chartW));
    const idx = Math.round(pct * (labels.length - 1));
    const date = labels[idx];
    const value = values[idx];
    if (date === undefined) return;

    const cx = xScale(idx);
    const cy = yScale(value);
    if (crossV) { crossV.setAttribute('x1', cx); crossV.setAttribute('x2', cx); crossV.style.opacity = '1'; }
    if (crossH) { crossH.setAttribute('y1', cy); crossH.setAttribute('y2', cy); crossH.style.opacity = '1'; }
    if (crossDot) { crossDot.setAttribute('cx', cx); crossDot.setAttribute('cy', cy); crossDot.style.opacity = '1'; }
    showTooltip(tt,
      '<span class="txn-tt-label">' + Formatter.formatShortDate(date) + '</span>' +
      '<span class="txn-tt-value">' + value.toFixed(3) + ' units</span>',
      e.clientX, e.clientY);
  });
  svg.addEventListener('mouseleave', () => {
    hideTooltip(tt);
    if (crossV) crossV.style.opacity = '0';
    if (crossH) crossH.style.opacity = '0';
    if (crossDot) crossDot.style.opacity = '0';
  });
}

// ── Fund Filter Dropdown ──
function populateFundFilter() {
  if (!fundFilter) return;
  const funds = new Map();
  allTransactions.forEach(t => {
    if (t.fund_name && !funds.has(t.isin)) funds.set(t.isin, t.fund_name);
  });

  let html = '<option value="">All Funds (' + funds.size + ')</option>';
  Array.from(funds.entries())
    .sort((a, b) => a[1].localeCompare(b[1]))
    .forEach(([isin, name]) => {
      html += '<option value="' + escapeAttr(isin) + '">' + escapeHtml(name) + '</option>';
    });

  fundFilter.innerHTML = html;
  fundFilter.value = selectedFundIsin;
  fundFilter.addEventListener('change', () => {
    selectedFundIsin = fundFilter.value;
    rerenderTable();
  });
}

// ── Transaction Table ──
// Global handlers for PaginationManager
window.txnGoToPage = function(page) {
  txnPagination.goToPage(page);
  renderTable(_cachedTableTransactions);
  const wrapper = document.querySelector('.txn-table-wrapper');
  if (wrapper) wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

window.changeTxnPageSize = function(size) {
  txnPagination.changePageSize(size);
  renderTable(_cachedTableTransactions);
};

function renderTable(transactions) {
  if (!tableBody) return;
  if (!transactions.length) {
    tableBody.innerHTML = '<tr><td colspan="7" class="txn-table-empty">No transactions found</td></tr>';
    const infoDiv = document.getElementById('txn_pagination_info');
    const btnsDiv = document.getElementById('txn_pagination_buttons');
    if (infoDiv) infoDiv.textContent = '';
    if (btnsDiv) btnsDiv.innerHTML = '';
    return;
  }

  const paginationInfo = txnPagination.paginate(transactions);
  const pageItems = paginationInfo.pageData;

  tableBody.innerHTML = pageItems.map(t => {
    const typeClass = isPurchase(t) ? 'txn-type-buy' : isRedemption(t) ? 'txn-type-sell' : 'txn-type-other';
    const typeLabel = isPurchase(t) ? 'Buy' : isRedemption(t) ? 'Sell' : (t.type || '-');
    const amtClass = isPurchase(t) ? '' : isRedemption(t) ? 'txn-amount-negative' : '';

    let plBadge = '';
    if (isRedemption(t) && t.pl_amount !== undefined) {
      const isGain = t.pl_amount >= 0;
      plBadge = '<span class="txn-pl-badge ' + (isGain ? 'txn-pl-gain' : 'txn-pl-loss') + '" title="P&L based on FIFO cost basis">' +
        (isGain ? '+' : '') + Formatter.formatCurrency(t.pl_amount, 0) +
        ' (' + (isGain ? '+' : '') + t.pl_pct.toFixed(1) + '%)' +
      '</span>';
    }

    return '<tr>' +
      '<td class="txn-td-date">' + Formatter.formatShortDate(t.date) + '</td>' +
      '<td class="txn-td-fund">' + escapeHtml(t.fund_name || t.isin) + '</td>' +
      '<td><span class="txn-type-badge ' + typeClass + '">' + typeLabel + '</span></td>' +
      '<td class="txn-td-amount ' + amtClass + '">' + Formatter.formatCurrency(Math.abs(t.amount || 0), 2) + plBadge + '</td>' +
      '<td class="txn-td-num">' + (t.units !== null ? Number(t.units).toFixed(3) : '-') + '</td>' +
      '<td class="txn-td-num">' + (t.nav !== null ? Number(t.nav).toFixed(4) : '-') + '</td>' +
      '<td class="txn-td-num">' + (t.balance !== null ? Number(t.balance).toFixed(3) : '-') + '</td>' +
    '</tr>';
  }).join('');

  PaginationManager.updatePaginationUI(
    paginationInfo,
    'txn_pagination_info',
    'txn_pagination_buttons',
    'txnGoToPage',
    'transactions'
  );
  _cachedTableTransactions = transactions;
}

let _cachedTableTransactions = [];

// ── Helpers ──
function isPurchase(t) {
  return (t.type || '').includes('PURCHASE') ||
         (t.type || '').includes('SWITCH_IN');
}
function isRedemption(t) {
  return (t.type || '').includes('REDEMPTION') ||
         (t.type || '').includes('SWITCH_OUT');
}

// ── Responsive chart resize ──
let resizeTimeout;
function _txnResizeHandler() {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    if (allTransactions.length) {
      renderTimelineChart();
      renderBuySellChart();
      renderAllocationChart();
      renderNavCompareChart();
      renderHeatmapChart();
      renderNavTrendChart();
      renderUnitsChart();
    }
  }, 250);
}
window.addEventListener('resize', _txnResizeHandler);

// ── Public reload (called from cas-import.js after import) ──
window.reloadTransactions = async function() {
  try {
    const data = await fetchData(currentAccount);
    if (!data.has_data || !data.transactions.length) return;
    applyData(data);
    empty.classList.add('hidden');
    dataSection.classList.remove('hidden');
    populateAccountFilter(data.accounts || []);
    selectedFundIsin = '';
    populateFundFilter();
    renderAll();
    rerenderTable();
  } catch { /* silent */ }
};

// ── Re-render charts on theme toggle ──
const _txnThemeObserver = new MutationObserver(() => {
  if (allTransactions.length) {
    renderAll();
  }
});
_txnThemeObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });

// ── Cleanup (called by SPA router on navigation away) ──
window.cleanupTransactions = function() {
  window.removeEventListener('resize', _txnResizeHandler);
  clearTimeout(resizeTimeout);
  _txnThemeObserver.disconnect();
  delete window.reloadTransactions;
  delete window.txnGoToPage;
  delete window.changeTxnPageSize;
};

// ── Boot ──
init();
