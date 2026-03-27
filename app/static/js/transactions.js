// ─── Transaction History Page ─────────────────────────────────
// Renders charts and table for CAS-imported mutual fund transactions.

(function () {
  const metronFetch = window.metronFetch;
  if (!metronFetch) return;

  const loading = document.getElementById('txnLoading');
  const empty = document.getElementById('txnEmpty');
  const dataSection = document.getElementById('txnData');
  const summaryCards = document.getElementById('txnSummaryCards');
  const timelineChart = document.getElementById('txnTimelineChart');
  const buySellChart = document.getElementById('txnBuySellChart');
  const tableBody = document.getElementById('txnTableBody');
  const fundFilter = document.getElementById('txnFundFilter');
  const periodEl = document.getElementById('txnPeriod');

  if (!loading || !dataSection) return;

  let allTransactions = [];
  let currentSort = 'date_desc';

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

  async function init() {
    try {
      const resp = await metronFetch('/api/cas/transactions');
      if (!resp.ok) throw new Error('Failed to load');
      const data = await resp.json();

      loading.classList.add('hidden');

      if (!data.has_data || !data.transactions.length) {
        empty.classList.remove('hidden');
        return;
      }

      allTransactions = [...data.transactions]
        .sort((a, b) => (b.date || '').localeCompare(a.date || ''));

      dataSection.classList.remove('hidden');
      renderSummary();
      renderPeriod();
      renderTimelineChart();
      renderBuySellChart();
      populateFundFilter();
      setupSorting();
      renderTable(allTransactions);

    } catch {
      loading.classList.add('hidden');
      empty.classList.remove('hidden');
    }
  }

  // ── Cost Basis (average cost method, matches CAMS) ──
  // Groups transactions by ISIN, sorts chronologically, and applies the
  // average cost method: purchases add to cost basis; redemptions remove
  // (avg_cost_per_unit × redeemed_units) from cost basis.  SWITCH_IN is
  // treated as a purchase so inter-fund switches are handled correctly.
  function computeRemainingCostBasis() {
    const byIsin = {};
    allTransactions.forEach(t => {
      if (!byIsin[t.isin]) byIsin[t.isin] = [];
      byIsin[t.isin].push(t);
    });

    let total = 0;
    for (const txns of Object.values(byIsin)) {
      txns.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
      let avgCostPerUnit = 0;
      let holdingUnits = 0;
      let costBasis = 0;

      for (const t of txns) {
        const amount = Math.abs(t.amount || 0);
        const units = Math.abs(t.units || 0);
        const type = t.type || '';

        if (isPurchase(t) || type.includes('SWITCH_IN')) {
          if (units > 0) {
            costBasis += amount;
            holdingUnits += units;
            avgCostPerUnit = holdingUnits > 0 ? costBasis / holdingUnits : 0;
          }
        } else if (isRedemption(t)) {
          if (units > 0) {
            costBasis -= avgCostPerUnit * units;
            holdingUnits -= units;
          }
        }
      }
      total += Math.max(0, costBasis);
    }
    return total;
  }

  // ── Summary Cards ──
  function renderSummary() {
    const purchases = allTransactions.filter(t => isPurchase(t));
    const redemptions = allTransactions.filter(t => isRedemption(t));
    const totalInvested = purchases.reduce((s, t) => s + Math.abs(t.amount || 0), 0);
    const totalRedeemed = redemptions.reduce((s, t) => s + Math.abs(t.amount || 0), 0);
    const netInvested = computeRemainingCostBasis();
    const uniqueFunds = new Set(allTransactions.map(t => t.isin)).size;

    const cards = [
      { label: 'Total Purchases', value: formatCurrency(totalInvested), cls: '' },
      { label: 'Total Redemptions', value: formatCurrency(totalRedeemed), cls: 'txn-card-redeem' },
      { label: 'Invested (Cost Basis)', value: formatCurrency(netInvested), cls: 'txn-card-positive' },
      { label: 'Transactions', value: allTransactions.length.toString(), cls: '' },
      { label: 'Funds', value: uniqueFunds.toString(), cls: '' },
    ];

    summaryCards.innerHTML = cards.map(c =>
      '<div class="txn-summary-card ' + c.cls + '">' +
        '<span class="txn-card-label">' + c.label + '</span>' +
        '<span class="txn-card-value">' + c.value + '</span>' +
      '</div>'
    ).join('');
  }

  // ── Period Display ──
  function renderPeriod() {
    if (!periodEl || !allTransactions.length) return;
    const dates = allTransactions.map(t => t.date).filter(Boolean).sort();
    if (!dates.length) return;
    const from = formatDateFull(dates[0]);
    const to = formatDateFull(dates[dates.length - 1]);
    periodEl.textContent = from + '\u2013' + to;
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
    const isin = fundFilter ? fundFilter.value : '';
    const filtered = isin ? allTransactions.filter(t => t.isin === isin) : allTransactions;
    renderTable(sortedTransactions(filtered));
  }

  // ── Timeline Chart (SVG) ──
  function renderTimelineChart() {
    if (!timelineChart) return;
    const purchases = allTransactions.filter(t => isPurchase(t));
    if (!purchases.length) {
      timelineChart.innerHTML = '<div class="txn-chart-empty">No purchase data</div>';
      return;
    }

    // Build cumulative investment over time
    const sorted = [...purchases].sort((a, b) => a.date.localeCompare(b.date));
    let cumulative = 0;
    const points = sorted.map(t => {
      cumulative += Math.abs(t.amount || 0);
      return { date: t.date, value: cumulative };
    });

    // Deduplicate by date (keep last value per day)
    const byDate = {};
    points.forEach(p => { byDate[p.date] = p.value; });
    const dates = Object.keys(byDate).sort();
    const values = dates.map(d => byDate[d]);

    renderAreaChart(timelineChart, dates, values, '#3b82f6', '#dbeafe');
    addAreaChartTooltip(timelineChart, dates, values);
  }

  // ── Buy vs Sell Chart (SVG bar chart) ──
  function renderBuySellChart() {
    if (!buySellChart) return;
    if (!allTransactions.length) {
      buySellChart.innerHTML = '<div class="txn-chart-empty">No data</div>';
      return;
    }

    // Group by month
    const monthly = {};
    allTransactions.forEach(t => {
      const month = (t.date || '').substring(0, 7); // YYYY-MM
      if (!month || month.length < 7) return;
      if (!monthly[month]) monthly[month] = { buy: 0, sell: 0 };
      const amt = Math.abs(t.amount || 0);
      if (isPurchase(t)) monthly[month].buy += amt;
      else if (isRedemption(t)) monthly[month].sell += amt;
    });

    const months = Object.keys(monthly).sort();
    if (!months.length) {
      buySellChart.innerHTML = '<div class="txn-chart-empty">No data</div>';
      return;
    }

    renderBarChart(buySellChart, months, monthly);
    addBarChartTooltip(buySellChart, months, monthly);
  }

  // ── SVG Area Chart ──
  function renderAreaChart(container, labels, values, lineColor, fillColor) {
    const W = container.clientWidth || 600;
    const H = 200;
    const padL = 60, padR = 20, padT = 20, padB = 40;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    const maxVal = Math.max(...values, 1);
    const minVal = 0;

    const xScale = (i) => padL + (i / Math.max(labels.length - 1, 1)) * chartW;
    const yScale = (v) => padT + chartH - ((v - minVal) / (maxVal - minVal)) * chartH;

    // Build path
    const pathPoints = values.map((v, i) => `${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`);
    const linePath = 'M' + pathPoints.join('L');
    const areaPath = linePath + `L${xScale(values.length - 1).toFixed(1)},${(padT + chartH).toFixed(1)}L${padL},${(padT + chartH).toFixed(1)}Z`;

    // Y-axis ticks
    const yTicks = 5;
    let yLabels = '';
    let gridLines = '';
    for (let i = 0; i <= yTicks; i++) {
      const val = minVal + (maxVal - minVal) * (i / yTicks);
      const y = yScale(val);
      yLabels += `<text x="${padL - 8}" y="${y + 4}" class="txn-chart-label" text-anchor="end">${formatCompact(val)}</text>`;
      gridLines += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" class="txn-chart-grid"/>`;
    }

    // X-axis labels (show ~6 dates)
    let xLabels = '';
    const step = Math.max(1, Math.floor(labels.length / 6));
    for (let i = 0; i < labels.length; i += step) {
      const x = xScale(i);
      xLabels += `<text x="${x}" y="${H - 6}" class="txn-chart-label" text-anchor="middle">${formatDateShort(labels[i])}</text>`;
    }

    container.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      ${gridLines}
      <path d="${areaPath}" fill="${fillColor}" opacity="0.4"/>
      <path d="${linePath}" fill="none" stroke="${lineColor}" stroke-width="2"/>
      ${yLabels}${xLabels}
    </svg>`;
  }

  // ── SVG Bar Chart ──
  function renderBarChart(container, months, monthly) {
    const W = container.clientWidth || 600;
    const H = 200;
    const padL = 60, padR = 20, padT = 20, padB = 40;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    const maxVal = Math.max(...months.map(m => Math.max(monthly[m].buy, monthly[m].sell)), 1);
    const barGroupW = chartW / months.length;
    const barW = Math.min(barGroupW * 0.35, 20);

    const yScale = (v) => padT + chartH - (v / maxVal) * chartH;

    let bars = '';
    let xLabels = '';
    const step = Math.max(1, Math.floor(months.length / 8));

    months.forEach((m, i) => {
      const x = padL + i * barGroupW + barGroupW / 2;
      const buyH = (monthly[m].buy / maxVal) * chartH;
      const sellH = (monthly[m].sell / maxVal) * chartH;

      bars += `<rect x="${x - barW}" y="${padT + chartH - buyH}" width="${barW}" height="${buyH}" fill="#22c55e" rx="2" opacity="0.8"/>`;
      if (monthly[m].sell > 0) {
        bars += `<rect x="${x}" y="${padT + chartH - sellH}" width="${barW}" height="${sellH}" fill="#ef4444" rx="2" opacity="0.8"/>`;
      }

      if (i % step === 0) {
        xLabels += `<text x="${x}" y="${H - 6}" class="txn-chart-label" text-anchor="middle">${m.substring(2)}</text>`;
      }
    });

    // Y-axis
    let yLabels = '';
    let gridLines = '';
    for (let i = 0; i <= 4; i++) {
      const val = (maxVal / 4) * i;
      const y = yScale(val);
      yLabels += `<text x="${padL - 8}" y="${y + 4}" class="txn-chart-label" text-anchor="end">${formatCompact(val)}</text>`;
      gridLines += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" class="txn-chart-grid"/>`;
    }

    // Legend
    const legend = `<rect x="${W - 140}" y="6" width="10" height="10" fill="#22c55e" rx="2"/>
      <text x="${W - 126}" y="15" class="txn-chart-label">Buy</text>
      <rect x="${W - 90}" y="6" width="10" height="10" fill="#ef4444" rx="2"/>
      <text x="${W - 76}" y="15" class="txn-chart-label">Sell</text>`;

    container.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      ${gridLines}${bars}${yLabels}${xLabels}${legend}
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

  function showTooltip(tt, html, pageX, pageY) {
    tt.innerHTML = html;
    tt.classList.add('txn-tt-visible');
    // Keep tooltip within viewport
    const ttW = 160;
    const left = Math.min(pageX + 14, window.innerWidth - ttW - 16);
    tt.style.left = left + 'px';
    tt.style.top = (pageY - 48) + 'px';
  }

  function hideTooltip(tt) {
    tt.classList.remove('txn-tt-visible');
  }

  function addAreaChartTooltip(container, labels, values) {
    const svg = container.querySelector('svg');
    if (!svg || !labels.length) return;

    const W = parseFloat(svg.getAttribute('width')) || 600;
    const padL = 60, padR = 20;
    const chartW = W - padL - padR;
    const tt = getOrCreateTooltip();

    svg.addEventListener('mousemove', e => {
      const rect = svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const pct = Math.max(0, Math.min(1, (mouseX - padL) / chartW));
      const idx = Math.round(pct * (labels.length - 1));
      const label = labels[idx];
      const value = values[idx];
      if (label === undefined) return;
      showTooltip(tt,
        '<span class="txn-tt-label">' + formatDateFull(label) + '</span>' +
        '<span class="txn-tt-value">' + formatCurrency(value) + '</span>',
        e.pageX, e.pageY
      );
    });

    svg.addEventListener('mouseleave', () => hideTooltip(tt));
  }

  function addBarChartTooltip(container, months, monthly) {
    const svg = container.querySelector('svg');
    if (!svg || !months.length) return;

    const W = parseFloat(svg.getAttribute('width')) || 600;
    const padL = 60, padR = 20;
    const chartW = W - padL - padR;
    const barGroupW = chartW / months.length;
    const tt = getOrCreateTooltip();

    const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    svg.addEventListener('mousemove', e => {
      const rect = svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const idx = Math.floor((mouseX - padL) / barGroupW);
      if (idx < 0 || idx >= months.length) { hideTooltip(tt); return; }
      const m = months[idx];
      const d = monthly[m];
      if (!d) { hideTooltip(tt); return; }

      const [year, mon] = m.split('-');
      const label = monthNames[parseInt(mon)] + ' ' + year;
      showTooltip(tt,
        '<span class="txn-tt-label">' + label + '</span>' +
        (d.buy ? '<span class="txn-tt-buy">Buy: ' + formatCurrency(d.buy) + '</span>' : '') +
        (d.sell ? '<span class="txn-tt-sell">Sell: ' + formatCurrency(d.sell) + '</span>' : ''),
        e.pageX, e.pageY
      );
    });

    svg.addEventListener('mouseleave', () => hideTooltip(tt));
  }

  // ── Fund Filter ──
  function populateFundFilter() {
    const funds = new Map();
    allTransactions.forEach(t => {
      if (t.fund_name && !funds.has(t.isin)) {
        funds.set(t.isin, t.fund_name);
      }
    });

    fundFilter.innerHTML = '<option value="">All Funds (' + funds.size + ')</option>';
    Array.from(funds.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .forEach(([isin, name]) => {
        const opt = document.createElement('option');
        opt.value = isin;
        opt.textContent = name;
        fundFilter.appendChild(opt);
      });

    fundFilter.addEventListener('change', rerenderTable);
  }

  // ── Transaction Table ──
  function renderTable(transactions) {
    if (!tableBody) return;
    if (!transactions.length) {
      tableBody.innerHTML = '<tr><td colspan="7" class="txn-table-empty">No transactions found</td></tr>';
      return;
    }

    tableBody.innerHTML = transactions.map(t => {
      const typeClass = isPurchase(t) ? 'txn-type-buy' : isRedemption(t) ? 'txn-type-sell' : 'txn-type-other';
      const typeLabel = isPurchase(t) ? 'Buy' : isRedemption(t) ? 'Sell' : (t.type || '-');
      const amtClass = isPurchase(t) ? '' : isRedemption(t) ? 'txn-amount-negative' : '';

      return '<tr>' +
        '<td class="txn-td-date">' + formatDateFull(t.date) + '</td>' +
        '<td class="txn-td-fund" title="' + escapeAttr(t.fund_name || '') + '">' + escapeHtml(truncate(t.fund_name || t.isin, 40)) + '</td>' +
        '<td><span class="txn-type-badge ' + typeClass + '">' + typeLabel + '</span></td>' +
        '<td class="txn-td-amount ' + amtClass + '">' + formatCurrency(Math.abs(t.amount || 0)) + '</td>' +
        '<td class="txn-td-num">' + (t.units !== null ? Number(t.units).toFixed(3) : '-') + '</td>' +
        '<td class="txn-td-num">' + (t.nav !== null ? Number(t.nav).toFixed(4) : '-') + '</td>' +
        '<td class="txn-td-num">' + (t.balance !== null ? Number(t.balance).toFixed(3) : '-') + '</td>' +
      '</tr>';
    }).join('');
  }

  // ── Helpers ──
  function isPurchase(t) {
    return t.type === 'PURCHASE' || t.type === 'PURCHASE_SIP' ||
           (t.type || '').includes('PURCHASE');
  }
  function isRedemption(t) {
    return t.type === 'REDEMPTION' || (t.type || '').includes('REDEMPTION') ||
           (t.type || '').includes('SWITCH_OUT');
  }

  function formatCurrency(val) {
    return '\u20b9' + Number(val || 0).toLocaleString('en-IN', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  }
  function formatCompact(val) {
    if (val >= 10000000) return '\u20b9' + (val / 10000000).toFixed(1) + 'Cr';
    if (val >= 100000) return '\u20b9' + (val / 100000).toFixed(1) + 'L';
    if (val >= 1000) return '\u20b9' + (val / 1000).toFixed(1) + 'K';
    return '\u20b9' + Math.round(val);
  }
  function formatDateShort(d) {
    if (!d) return '';
    const parts = d.split('-');
    if (parts.length >= 2) {
      const months = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return months[parseInt(parts[1])] + ' ' + parts[0].substring(2);
    }
    return d;
  }
  function formatDateFull(d) {
    if (!d) return '-';
    try {
      return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch { return d; }
  }
  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }
  function escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }
  function truncate(str, len) {
    return str.length > len ? str.substring(0, len) + '...' : str;
  }

  // ── Responsive chart resize ──
  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      if (allTransactions.length) {
        renderTimelineChart();
        renderBuySellChart();
      }
    }, 250);
  });

  // ── Boot ──
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
