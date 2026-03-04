/* Metron - Standalone Table Detail Page Controller
 *
 * Renders a single table type (stocks, etfs, mutual-funds, etc.) with full
 * pagination controls.  The table key is injected by the server template via
 * window.__TABLE_KEY__.
 */

import { Formatter, Calculator, isGoldInstrument, isSGBInstrument, isSilverInstrument, isETFInstrument, metronFetch } from './utils.js';
import PaginationManager from './pagination.js';
import SortManager from './sort-manager.js';
import ThemeManager from './theme-manager.js';
import PrivacyManager from './visibility-manager.js';
import CrudManager from './crud-manager.js';

// ─── CRUD action buttons helper ──────────────────────────────────────────────

function buildCrudActions(schemaKey, rowNumber, values) {
  const encoded = encodeURIComponent(JSON.stringify(values));
  return `<span class="crud-row-actions">` +
    `<button class="crud-action-btn crud-edit-btn" onclick="event.stopPropagation();crudEdit('${schemaKey}',${rowNumber},'${encoded}')" title="Edit">` +
    `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>` +
    `</button>` +
    `<span class="crud-action-divider"></span>` +
    `<button class="crud-action-btn crud-delete-btn" onclick="event.stopPropagation();crudDelete('${schemaKey}',${rowNumber})" title="Delete">` +
    `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>` +
    `</button>` +
    `</span>`;
}

// ─── Table header definitions (match portfolio page columns) ─────────────────

const TABLE_HEADERS = {
  stocks: [
    { label: 'Symbol', sortAsc: 'symbol_asc', sortDesc: 'symbol_desc', sortDefault: 'asc' },
    { label: 'Qty', sortAsc: 'qty_asc', sortDesc: 'qty_desc' },
    { label: 'Avg Price', sortAsc: 'avg_asc', sortDesc: 'avg_desc' },
    { label: 'Invested', sortAsc: 'invested_asc', sortDesc: 'invested_desc' },
    { label: 'Current', sortAsc: 'current_asc', sortDesc: 'current_desc' },
    { label: 'LTP', sortAsc: 'ltp_asc', sortDesc: 'ltp_desc' },
    { label: 'P/L', sortAsc: 'pl_asc', sortDesc: 'pl_desc' },
    { label: "Day's Change", sortAsc: 'day_change_asc', sortDesc: 'day_change_desc' },
    { label: 'EX', sortAsc: 'exchange_asc', sortDesc: 'exchange_desc', sortDefault: 'asc' },
    { label: 'Account', sortAsc: 'account_asc', sortDesc: 'account_desc', sortDefault: 'asc' },
  ],
  etfs: [
    { label: 'Symbol', sortAsc: 'symbol_asc', sortDesc: 'symbol_desc', sortDefault: 'asc' },
    { label: 'Qty', sortAsc: 'qty_asc', sortDesc: 'qty_desc' },
    { label: 'Avg Price', sortAsc: 'avg_asc', sortDesc: 'avg_desc' },
    { label: 'Invested', sortAsc: 'invested_asc', sortDesc: 'invested_desc' },
    { label: 'Current', sortAsc: 'current_asc', sortDesc: 'current_desc' },
    { label: 'LTP', sortAsc: 'ltp_asc', sortDesc: 'ltp_desc' },
    { label: 'P/L', sortAsc: 'pl_asc', sortDesc: 'pl_desc' },
    { label: "Day's Change", sortAsc: 'day_change_asc', sortDesc: 'day_change_desc' },
    { label: 'EX', sortAsc: 'exchange_asc', sortDesc: 'exchange_desc', sortDefault: 'asc' },
    { label: 'Account', sortAsc: 'account_asc', sortDesc: 'account_desc', sortDefault: 'asc' },
  ],
  'mutual-funds': [
    { label: 'Fund', sortAsc: 'name_asc', sortDesc: 'name_desc', sortDefault: 'asc' },
    { label: 'Qty', sortAsc: 'qty_asc', sortDesc: 'qty_desc' },
    { label: 'Avg Price', sortAsc: 'avg_asc', sortDesc: 'avg_desc' },
    { label: 'Invested', sortAsc: 'invested_asc', sortDesc: 'invested_desc' },
    { label: 'Current', sortAsc: 'current_asc', sortDesc: 'current_desc' },
    { label: 'NAV', sortAsc: 'nav_asc', sortDesc: 'nav_desc' },
    { label: 'P/L', sortAsc: 'pl_asc', sortDesc: 'pl_desc' },
    { label: 'Account', sortAsc: 'account_asc', sortDesc: 'account_desc', sortDefault: 'asc' },
  ],
  'physical-gold': [
    { label: 'Bought On', sortAsc: 'date_asc', sortDesc: 'date_desc' },
    { label: 'Type', sortAsc: 'type_asc', sortDesc: 'type_desc', sortDefault: 'asc' },
    { label: 'Retail Outlet', sortAsc: 'outlet_asc', sortDesc: 'outlet_desc', sortDefault: 'asc' },
    { label: 'Purity', sortAsc: 'purity_asc', sortDesc: 'purity_desc', sortDefault: 'asc' },
    { label: 'Weight (gms)', sortAsc: 'weight_asc', sortDesc: 'weight_desc' },
    { label: 'Bought IBJA Rate/gm', sortAsc: 'bought_rate_asc', sortDesc: 'bought_rate_desc' },
    { label: 'Latest IBJA Rate/gm', sortAsc: 'latest_rate_asc', sortDesc: 'latest_rate_desc' },
    { label: 'P/L', sortAsc: 'pl_asc', sortDesc: 'pl_desc' },
  ],
  'fixed-deposits': [
    { label: 'Deposited On', sortAsc: 'date_asc', sortDesc: 'date_desc' },
    { label: 'Reinvested On', sortAsc: 'reinvested_date_asc', sortDesc: 'reinvested_date_desc' },
    { label: 'Bank', sortAsc: 'bank_asc', sortDesc: 'bank_desc', sortDefault: 'asc' },
    { label: 'Original Amt', sortAsc: 'amount_asc', sortDesc: 'amount_desc' },
    { label: 'Reinvested Amt', sortAsc: 'reinvested_amount_asc', sortDesc: 'reinvested_amount_desc' },
    { label: 'ROI', sortAsc: 'roi_asc', sortDesc: 'roi_desc' },
    { label: 'Maturity Date', sortAsc: 'maturity_asc', sortDesc: 'maturity_desc' },
    { label: 'Current Value', sortAsc: 'current_asc', sortDesc: 'current_desc' },
    { label: 'Account', sortAsc: 'account_asc', sortDesc: 'account_desc', sortDefault: 'asc' },
  ],
  sips: [
    { label: 'Fund' },
    { label: 'Amount' },
    { label: 'Frequency' },
    { label: 'Installments' },
    { label: 'Status' },
    { label: 'Next Due' },
    { label: 'Account' },
  ],
};

// ─── API endpoints per table key ─────────────────────────────────────────────

const DATA_ENDPOINTS = {
  stocks: '/api/stocks_data',
  etfs: '/api/stocks_data',        // ETFs come from the same stocks endpoint
  'mutual-funds': '/api/mf_holdings_data',
  'physical-gold': '/api/physical_gold_data',
  'fixed-deposits': '/api/fixed_deposits_data',
  sips: '/api/sips_data',
};

// ─── Sort key map (table key → SortManager method prefix) ────────────────────

const SORT_PREFIX = {
  stocks: 'Stocks',
  etfs: 'ETF',
  'mutual-funds': 'MF',
  'physical-gold': 'PhysicalGold',
  'fixed-deposits': 'FixedDeposits',
  sips: null,  // SIPs don't have sorting
};

// ─── Helper: build cell utilities ────────────────────────────────────────────

function buildCell(content, cssClass = '') {
  const classAttr = cssClass ? ` class="${cssClass}"` : '';
  return `<td${classAttr}>${content}</td>`;
}

function buildPLCell(value) {
  const formatted = Formatter.formatCurrency(value);
  const color = Formatter.colorPL(value);
  return `<td><span style="color:${color};font-weight:600">${formatted}</span></td>`;
}

function buildValueWithPctCell(value, percentage) {
  const formatted = (typeof value === 'number') ? Formatter.formatNumberWithLocale(value, 1) : value;
  const color = Formatter.colorPL(percentage);
  const pctText = Formatter.formatPercentage(percentage);
  return `<td>${formatted} <span class="pl_pct_small" style="color:${color}">${pctText}</span></td>`;
}

function buildChangeCell(changeValue, changePercent) {
  const color = Formatter.colorPL(changeValue);
  const formattedPct = Formatter.formatPercentage(changePercent);
  return `<td><span style="color:${color};font-weight:600">${formattedPct}</span></td>`;
}

// ─── Row builders per table type ─────────────────────────────────────────────

function buildStockRow(holding, metrics) {
  const { qty, avg, invested, ltp, dayChange, pl, current, plPct, dayChangePct } = metrics;
  const isManual = holding.source === 'manual';
  const manualBadge = isManual ? '<span class="crud-manual-badge">Manual</span>' : '';
  const crudType = (isManual && holding.manual_type === 'etfs') ? 'etfs' : 'stocks';
  const actions = isManual ? buildCrudActions(crudType, holding.row_number, {
    symbol: holding.tradingsymbol, qty: holding.quantity,
    avg_price: holding.average_price, exchange: holding.exchange, account: holding.account
  }) : '';
  const manualAttrs = isManual ? ` data-manual-row="${holding.row_number}" data-schema="${crudType}"` : '';
  return `<tr${manualAttrs} style="background-color:${Formatter.rowColor(pl)}">
  ${buildCell(holding.tradingsymbol + manualBadge)}
  ${buildCell(qty.toLocaleString())}
  ${buildCell(Formatter.formatCurrency(avg))}
  ${buildCell(Formatter.formatCurrency(invested))}
  ${buildValueWithPctCell(Formatter.formatCurrency(current), plPct)}
  ${buildCell(Formatter.formatLTP(ltp))}
  ${buildPLCell(pl)}
  ${buildChangeCell(dayChange, dayChangePct)}
  ${buildCell(holding.exchange)}
  ${buildCell((holding.account || '-') + actions)}
  </tr>`;
}

function buildMFRow(mf, metrics) {
  const { qty, avg, invested, nav, current, pl, plPct } = metrics;
  let navDateText = '';
  if (mf.last_price_date) {
    const formattedDate = Formatter.formatRelativeDate(mf.last_price_date, true);
    if (formattedDate) navDateText = ` <span class="pl_pct_small">${formattedDate.toLowerCase()}</span>`;
  }
  const fundName = mf.fund || mf.tradingsymbol;
  const isManual = mf.source === 'manual';
  const manualBadge = isManual ? '<span class="crud-manual-badge">Manual</span>' : '';
  const crudActions = isManual ? buildCrudActions('mutual_funds', mf.row_number, {
    fund: mf.fund || mf.tradingsymbol, qty: mf.quantity,
    avg_nav: mf.average_price, account: mf.account
  }) : '';
  const manualAttrs = isManual ? ` data-manual-row="${mf.row_number}" data-schema="mutual_funds"` : '';
  return `<tr${manualAttrs} style="background-color:${Formatter.rowColor(pl)}">
  ${buildCell(`<span class="mf-fund-cell"><span class="mf-fund-label">${fundName}</span></span>` + manualBadge)}
  ${buildCell(qty.toLocaleString())}
  ${buildCell(Formatter.formatCurrency(avg))}
  ${buildCell(Formatter.formatCurrency(invested))}
  ${buildValueWithPctCell(Formatter.formatCurrency(current), plPct)}
  ${buildCell(Formatter.formatLTP(nav) + navDateText)}
  ${buildPLCell(pl)}
  ${buildCell((mf.account || '-') + crudActions)}
  </tr>`;
}

function buildPhysicalGoldRow(holding) {
  const weight = holding.weight_gms ? holding.weight_gms.toFixed(3) : '0.000';
  const ibjaRate = Formatter.formatCurrency(holding.bought_ibja_rate_per_gm || 0);
  let latestPrice = '-';
  if (holding.latest_ibja_price_per_gm) latestPrice = Formatter.formatCurrency(holding.latest_ibja_price_per_gm);
  const pl = holding.pl || 0;
  const plPct = holding.pl_pct || 0;
  let plDisplay = '-';
  let plColor = '#999';
  if (holding.pl !== undefined) {
    plDisplay = Formatter.formatCurrency(Math.abs(pl));
    if (pl < 0) plDisplay = '-' + plDisplay;
    plColor = Formatter.colorPL(pl);
    const pctText = Formatter.formatPercentage(plPct);
    plDisplay = `${plDisplay} <span class="pl_pct_small" style="color:${plColor}">${pctText}</span>`;
  }
  const crudActions = buildCrudActions('physical_gold', holding.row_number, {
    date: holding.date || '', type: holding.type || '',
    retail_outlet: holding.retail_outlet || '', purity: holding.purity || '',
    weight_gms: holding.weight_gms || 0,
    bought_ibja_rate_per_gm: holding.bought_ibja_rate_per_gm || 0
  });
  return `<tr data-manual-row="${holding.row_number}" data-schema="physical_gold" style="background-color:${Formatter.rowColor(pl)}">
    <td>${Formatter.formatShortDate(holding.date)}</td>
    <td>${holding.type || '-'}</td>
    <td>${holding.retail_outlet || '-'}</td>
    <td style="font-weight:600;color:#d4af37">${holding.purity || '-'}</td>
    <td>${weight}</td>
    <td>${ibjaRate}</td>
    <td>${latestPrice}</td>
    <td style="color:${plColor};font-weight:600">${plDisplay}${crudActions}</td>
  </tr>`;
}

function buildFixedDepositRow(deposit) {
  const originalAmount = deposit.original_amount || 0;
  const reinvestedAmount = deposit.reinvested_amount || 0;
  const currentValue = deposit.current_value || 0;
  const interestRate = deposit.interest_rate || 0;
  const reinvestedDisplay = (reinvestedAmount && Number(reinvestedAmount) > 0)
    ? Formatter.formatCurrency(reinvestedAmount)
    : '-';
  const interestRateDisplay = interestRate ? `${interestRate.toFixed(2)}%` : '-';
  const crudActions = (deposit.row_number) ? buildCrudActions('fixed_deposits', deposit.row_number, {
    original_investment_date: deposit.original_investment_date || '',
    reinvested_date: deposit.reinvested_date || '',
    bank_name: deposit.bank_name || '',
    deposit_year: deposit.deposit_year || 0,
    deposit_month: deposit.deposit_month || 0,
    deposit_day: deposit.deposit_day || 0,
    original_amount: deposit.original_amount || 0,
    reinvested_amount: deposit.reinvested_amount || 0,
    interest_rate: deposit.interest_rate || 0,
    redeemed: deposit.redeemed ? 'Yes' : 'No',
    account: deposit.account || ''
  }) : '';
  const manualAttrs = deposit.row_number ? ` data-manual-row="${deposit.row_number}" data-schema="fixed_deposits"` : '';
  return `<tr${manualAttrs}>
    <td>${Formatter.formatShortDate(deposit.original_investment_date)}</td>
    <td>${Formatter.formatShortDate(deposit.reinvested_date)}</td>
    <td>${deposit.bank_name || '-'}</td>
    <td>${Formatter.formatCurrency(originalAmount)}</td>
    <td>${reinvestedDisplay}</td>
    <td style="color:#3498db;font-weight:600">${interestRateDisplay}</td>
    <td>${Formatter.formatShortDate(deposit.maturity_date)}</td>
    <td>${Formatter.formatCurrency(currentValue)}</td>
    <td>${(deposit.account || '-') + crudActions}</td>
  </tr>`;
}

function buildSIPRow(sip) {
  const fundName = (sip.fund || sip.tradingsymbol || '').toUpperCase();
  const frequency = sip.frequency || '-';
  let installments = '-';
  if (sip.instalments && sip.instalments !== -1) {
    const completed = sip.completed_instalments || 0;
    installments = `${completed}/${sip.instalments}`;
  } else if (sip.completed_instalments && sip.completed_instalments > 0) {
    installments = `${sip.completed_instalments}`;
  }
  const status = sip.status || 'UNKNOWN';
  let statusColor = '#666';
  if (status === 'ACTIVE') statusColor = '#28a745';
  else if (status === 'PAUSED') statusColor = '#ffc107';
  else if (status === 'CANCELLED') statusColor = '#dc3545';
  let nextDueText = '-';
  if (sip.next_instalment && status === 'ACTIVE') {
    const formattedDate = Formatter.formatRelativeDate(sip.next_instalment, false);
    nextDueText = formattedDate || sip.next_instalment;
  }
  const isManual = sip.source === 'manual';
  const manualBadge = isManual ? ' <span class="crud-manual-badge">Manual</span>' : '';
  const crudActions = isManual ? buildCrudActions('sips', sip.row_number, {
    fund: sip.fund || sip.tradingsymbol, amount: sip.instalment_amount,
    frequency: sip.frequency || 'MONTHLY',
    installments: sip.instalments || -1, completed: sip.completed_instalments || 0,
    status: sip.status || 'ACTIVE', next_due: sip.next_instalment || '',
    account: sip.account
  }) : '';
  const manualAttrs = isManual ? ` data-manual-row="${sip.row_number}" data-schema="sips"` : '';
  return `<tr${manualAttrs}>
    <td>${fundName}${manualBadge}</td>
    <td>${Formatter.formatCurrency(sip.instalment_amount || 0)}</td>
    <td>${frequency}</td>
    <td>${installments}</td>
    <td><span style="color:${statusColor};font-weight:600">${status}</span></td>
    <td>${nextDueText}</td>
    <td>${(sip.account || '-') + crudActions}</td>
  </tr>`;
}

// ─── Main controller ─────────────────────────────────────────────────────────

class TableDetailApp {
  constructor() {
    this.tableKey = window.__TABLE_KEY__;
    this.pagination = new PaginationManager(25, 1);
    this.sortManager = new SortManager();
    this.themeManager = new ThemeManager();
    this.privacyManager = new PrivacyManager();
    this.crudManager = new CrudManager(() => this._fetchData());
    this.rawData = [];
  }

  async init() {
    Formatter.initCompactFormat();
    this.themeManager.init();
    this.privacyManager.init();
    this._setupCrudHandlers();
    this._renderHeaders();
    this._setupEventListeners();
    await this._fetchData();
  }

  _setupCrudHandlers() {
    window.crudAdd = (schemaKey) => this.crudManager.openAdd(schemaKey);
    window.crudEdit = (schemaKey, rowNumber, valuesJSON) => {
      try {
        const values = JSON.parse(decodeURIComponent(valuesJSON));
        this.crudManager.openEdit(schemaKey, rowNumber, values);
      } catch { /* ignore bad JSON */ }
    };
    window.crudDelete = (schemaKey, rowNumber) => this.crudManager.confirmDelete(schemaKey, rowNumber);
  }

  _renderHeaders() {
    const thead = document.getElementById('detailThead');
    const headers = TABLE_HEADERS[this.tableKey] || [];
    let html = '<tr>';
    headers.forEach(h => {
      const sortAttrs = h.sortAsc
        ? ` data-sort-asc="${h.sortAsc}" data-sort-desc="${h.sortDesc}"${h.sortDefault ? ` data-sort-default="${h.sortDefault}"` : ''}`
        : '';
      html += `<th${sortAttrs}>${h.label}</th>`;
    });
    html += '</tr>';
    thead.innerHTML = html;

    // Set up header sort listeners
    this._setupHeaderSortListeners();
  }

  _setupEventListeners() {
    window.changeDetailPageSize = (size) => {
      this.pagination.changePageSize(parseInt(size));
      this._render();
    };
    window.goToDetailPage = (page) => {
      this.pagination.goToPage(page);
      this._render();
    };
  }

  _setupHeaderSortListeners() {
    const table = document.getElementById('detailTable');
    if (!table) return;
    const prefix = SORT_PREFIX[this.tableKey];
    if (!prefix) return;

    const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
    sortableHeaders.forEach(header => {
      header.classList.add('sortable-header');
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');

      const runSort = () => {
        const currentOrder = this.sortManager[`get${prefix}SortOrder`]();
        const nextSort = this._getNextSortOrder(header, currentOrder);
        this.sortManager[`set${prefix}SortOrder`](nextSort);
        this._render();
        this._syncSortIndicators();
      };

      header.addEventListener('click', runSort);
      header.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          runSort();
        }
      });
    });
  }

  _getNextSortOrder(header, currentSortOrder) {
    const ascSort = header.dataset.sortAsc;
    const descSort = header.dataset.sortDesc;
    const defaultDirection = header.dataset.sortDefault || 'desc';
    if (currentSortOrder === descSort) return ascSort;
    if (currentSortOrder === ascSort) return descSort;
    return defaultDirection === 'asc' ? ascSort : descSort;
  }

  _syncSortIndicators() {
    const table = document.getElementById('detailTable');
    const prefix = SORT_PREFIX[this.tableKey];
    if (!table || !prefix) return;
    const currentOrder = this.sortManager[`get${prefix}SortOrder`]();
    const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
    sortableHeaders.forEach(header => {
      header.classList.remove('sorted-asc', 'sorted-desc');
      header.setAttribute('aria-sort', 'none');
      if (currentOrder === header.dataset.sortAsc) {
        header.classList.add('sorted-asc');
        header.setAttribute('aria-sort', 'ascending');
      } else if (currentOrder === header.dataset.sortDesc) {
        header.classList.add('sorted-desc');
        header.setAttribute('aria-sort', 'descending');
      }
    });
  }

  async _fetchData() {
    const endpoint = DATA_ENDPOINTS[this.tableKey];
    if (!endpoint) return;
    try {
      const resp = await metronFetch(endpoint);
      const data = await resp.json();
      this.rawData = Array.isArray(data) ? data : [];
      this._render();
    } catch (err) {
      console.error('[TableDetail] Fetch error:', err);
    }
  }

  _getSortedData() {
    const prefix = SORT_PREFIX[this.tableKey];
    if (!prefix) return this.rawData;
    const methodName = `sort${prefix === 'ETF' ? 'ETFs' : prefix === 'Stocks' ? 'Stocks' : prefix === 'MF' ? 'MF' : prefix}`;
    const sortOrder = this.sortManager[`get${prefix}SortOrder`]();
    if (typeof this.sortManager[methodName] === 'function') {
      return this.sortManager[methodName](this.rawData, sortOrder);
    }
    return this.rawData;
  }

  _filterData(data) {
    // Filter data based on table type (ETFs come from stocks endpoint)
    if (this.tableKey === 'stocks') {
      return data.filter(h => !isETFInstrument(h.tradingsymbol || '', h.isin || '', h.manual_type));
    }
    if (this.tableKey === 'etfs') {
      return data.filter(h => isETFInstrument(h.tradingsymbol || '', h.isin || '', h.manual_type));
    }
    return data;
  }

  _render() {
    const tbody = document.getElementById('detailTbody');
    if (!tbody) return;

    const sorted = this._getSortedData();
    const filtered = this._filterData(sorted);
    const paginationData = this.pagination.paginate(filtered);
    const { pageData } = paginationData;

    let rowsHTML = '';
    if (pageData.length === 0) {
      const colCount = (TABLE_HEADERS[this.tableKey] || []).length;
      rowsHTML = `<tr><td colspan="${colCount}" style="text-align:center;padding:40px 0;color:#999;">No data available</td></tr>`;
    } else {
      pageData.forEach(item => {
        rowsHTML += this._buildRow(item);
      });
    }
    tbody.innerHTML = rowsHTML;

    PaginationManager.updatePaginationUI(
      paginationData,
      'detail_pagination_info',
      'detail_pagination_buttons',
      'goToDetailPage',
      this._itemLabel()
    );

    this._syncSortIndicators();
  }

  _buildRow(item) {
    switch (this.tableKey) {
      case 'stocks':
      case 'etfs': {
        const metrics = Calculator.calculateStockMetrics(item);
        return buildStockRow(item, metrics);
      }
      case 'mutual-funds': {
        const metrics = Calculator.calculateMFMetrics(item);
        return buildMFRow(item, metrics);
      }
      case 'physical-gold':
        return buildPhysicalGoldRow(item);
      case 'fixed-deposits':
        return buildFixedDepositRow(item);
      case 'sips':
        return buildSIPRow(item);
      default:
        return '';
    }
  }

  _itemLabel() {
    const labels = {
      stocks: 'stocks',
      etfs: 'ETFs',
      'mutual-funds': 'funds',
      'physical-gold': 'holdings',
      'fixed-deposits': 'deposits',
      sips: 'SIPs',
    };
    return labels[this.tableKey] || 'items';
  }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  const app = new TableDetailApp();
  app.init();
});

export default TableDetailApp;
