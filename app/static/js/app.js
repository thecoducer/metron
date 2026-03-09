/* Metron - Main Application Controller */

import DataManager from './data-manager.js';
import TableRenderer from './table-renderer.js';
import SummaryManager from './summary-manager.js';
import SortManager from './sort-manager.js';
import ThemeManager from './theme-manager.js';
import PrivacyManager from './visibility-manager.js';
import { Formatter } from './utils.js';
import IndexTicker from './index-ticker.js';
import CrudManager from './crud-manager.js';
import { Log } from './logger.js';

class PortfolioApp {
  constructor() {
    this.dataManager = new DataManager();
    this.tableRenderer = new TableRenderer();
    this.summaryManager = new SummaryManager();
    this.sortManager = new SortManager();
    this.themeManager = new ThemeManager();
    this.privacyManager = new PrivacyManager();
    this.indexTicker = new IndexTicker();
    this.crudManager = new CrudManager((partialData) => this._handleCrudChange(partialData));
    this.needsLogin = false;
    this.lastStatus = null;
    this.lastPortfolioUpdatedAt = null;
    this.relativeStatusTimer = null;
    this.searchTimeout = null;
  }

  async init() {
    Formatter.initCompactFormat();
    this._updateCompactFormatIcon();
    this.themeManager.init();
    this.privacyManager.init();
    this._setupEventListeners();
    
    this._hideLoadingIndicators();

    // If the server embedded cached data in the page, render it immediately
    // (zero network round-trips). Otherwise fall back to empty states + fetch.
    const inlined = window.__INITIAL_DATA__;
    if (inlined) {
      delete window.__INITIAL_DATA__;
      this._applyData(inlined);
      this._hasInitialData = true;
      Log.info('App', 'Rendered inlined data (warm cache)');
    } else {
      this._renderEmptyStates();
      this._hasInitialData = false;
      Log.info('App', 'Cold start — waiting for data fetch');
    }

    // Check if a security PIN is required before fetching data.
    // The overlay blocks until the user enters their PIN.
    if (typeof window.checkAndPromptPin === 'function') {
      await window.checkAndPromptPin();
    }

    // After PIN verification, fetch all data once (non-blocking).
    // If the server didn't inline cached data, trigger a backend refresh
    // first so fresh data is generated.
    this._initialLoad();
    
    // Start live market index ticker (NIFTY 50 / SENSEX) — single fetch, no auto-refresh
    this.indexTicker.init();

    this._startRelativeStatusUpdater();
  }

  _formatStatusUpdatedText() {
    if (!this.lastPortfolioUpdatedAt) return 'updated';
    const relative = Formatter.formatRelativeTime(this.lastPortfolioUpdatedAt);
    return relative ? `updated ${relative}` : 'updated';
  }

  _refreshRelativeStatusText() {
    const statusText = document.getElementById('status_text');
    if (!statusText) return;
    if (!this.lastStatus) return;
    const isUpdating = this._isStatusUpdating(this.lastStatus);
    if (isUpdating) return;
    statusText.innerText = this._formatStatusUpdatedText();
  }

  _startRelativeStatusUpdater() {
    if (this.relativeStatusTimer) clearInterval(this.relativeStatusTimer);
    this.relativeStatusTimer = setInterval(() => this._refreshRelativeStatusText(), 60_000);
  }

  _hideLoadingIndicators() {
    const loadingIds = [
      'combined_summary_loading',
      'stocks_summary_loading',
      'mf_summary_loading'
    ];
    
    loadingIds.forEach(id => {
      const element = document.getElementById(id);
      if (element) element.style.display = 'none';
    });
  }

  _renderEmptyStates() {
    this.tableRenderer.renderStocksTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderETFTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderGoldETFTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderSilverETFTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderMFTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderSIPsTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderPhysicalGoldTable([]);
    this.tableRenderer.renderFixedDepositsTable([]);
    this.tableRenderer.renderProvidentFundTable([]);
    this.tableRenderer.renderFDSummaryTable([]);
  }

  _isStatusUpdating(status) {
    // True when any primary data source is still fetching.
    return status.portfolio_state === 'updating' || status.sheets_state === 'updating';
  }

  /**
   * Calculate combined totals by summing invested/current across multiple total objects.
   * @param  {...Object} totalObjects - Objects with invested, current, pl properties
   * @returns {Object} Combined totals with invested, current, pl, plPct
   */
  _combineTotals(...totalObjects) {
    const invested = totalObjects.reduce((s, t) => s + (t.invested || 0), 0);
    const current = totalObjects.reduce((s, t) => s + (t.current || 0), 0);
    const pl = current - invested;
    const plPct = invested ? (pl / invested * 100) : 0;
    return { invested, current, pl, plPct };
  }

  _updateCompactFormatIcon() {
    const icon = document.getElementById('compact_toggle_icon');
    const btn = document.getElementById('compact_toggle_btn');
    const label = document.getElementById('compact_toggle_label');
    if (btn) {
      btn.classList.toggle('active', Formatter.isCompactFormat);
    }
    if (label) {
      label.classList.toggle('toggle-on', Formatter.isCompactFormat);
    }
    if (icon) {
      // Switch between 'Tt' (compact) and 'T' (full) icon paths
      if (Formatter.isCompactFormat) {
        icon.innerHTML = '<line x1="4" y1="4" x2="4" y2="20"/><line x1="4" y1="4" x2="13" y2="4"/><line x1="4" y1="12" x2="11" y2="12"/><line x1="15" y1="10" x2="15" y2="20"/><line x1="12" y1="10" x2="18" y2="10"/>';
      } else {
        icon.innerHTML = '<polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/>';
      }
    }
  }

  _setupEventListeners() {
    const searchInput = document.getElementById('search');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.handleSearch(), 150);
      });
    }

    window.toggleTheme = () => this.themeManager.toggle();
    window.togglePrivacy = () => this.privacyManager.toggle();
    window.toggleCompactFormat = () => {
      Formatter.toggleCompactFormat();
      this._updateCompactFormatIcon();
      this.handleSearch();
    };
    window.triggerRefresh = () => this.handleRefresh();

    // CRUD handlers (used by Add buttons in section headers and action icons in rows)
    window.crudAdd = (schemaKey) => this.crudManager.openAdd(schemaKey);
    window.crudEdit = (schemaKey, rowNumber, valuesJSON) => {
      try {
        const values = JSON.parse(decodeURIComponent(valuesJSON));
        this.crudManager.openEdit(schemaKey, rowNumber, values);
      } catch { /* ignore bad JSON */ }
    };
    window.crudDelete = (schemaKey, rowNumber) => this.crudManager.confirmDelete(schemaKey, rowNumber);
    // Sort handlers
    window.sortStocksTable = (sortBy) => this._handleSort('Stocks', sortBy);
    window.sortETFTable = (sortBy) => this._handleSort('ETF', sortBy);
    window.sortGoldETFTable = (sortBy) => this._handleSort('GoldETF', sortBy);
    window.sortSilverETFTable = (sortBy) => this._handleSort('SilverETF', sortBy);
    window.sortMFTable = (sortBy) => this._handleSort('MF', sortBy);
    window.sortPhysicalGoldTable = (sortBy) => this._handleSort('PhysicalGold', sortBy);
    window.sortFixedDepositsTable = (sortBy) => this.handleFixedDepositsSort(sortBy);
    window.sortProvidentFundTable = (sortBy) => this.handleProvidentFundSort(sortBy);
    window.sortFDSummaryTable = (sortBy) => this.handleFDSummarySort(sortBy);

    this._setupHeaderSortListeners();

    this._setupSummaryCardNavigation();

    this._setupInfoToasters();

    // Detect when the user returns to this tab (e.g. after broker login
    // in another tab) and re-check session status automatically.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') this._onTabVisible();
    });

    this._currentTooltip = null;
    this._tooltipIcon = null;
    this._tooltipPinned = false;
    this._tooltipHideTimer = null;

    document.addEventListener('mouseover', (event) => {
      const icon = event.target.closest('.fd-alert-icon');
      if (icon) {
        this._cancelHideTimer();
        if (this._tooltipIcon !== icon) this._showFDTooltip(icon, false);
        return;
      }
      if (this._currentTooltip?.contains(event.target)) this._cancelHideTimer();
    });

    document.addEventListener('mouseout', (event) => {
      if (this._tooltipPinned) return;
      const icon = event.target.closest('.fd-alert-icon');
      if (!icon && !(this._currentTooltip?.contains(event.target))) return;
      const related = event.relatedTarget;
      if (related?.closest?.('.fd-alert-icon') === this._tooltipIcon) return;
      if (this._currentTooltip?.contains(related)) return;
      this._tooltipHideTimer = setTimeout(() => this._destroyTooltip(), 250);
    });

    document.addEventListener('click', (event) => {
      const icon = event.target.closest('.fd-alert-icon');
      if (icon) {
        event.stopPropagation();
        this._cancelHideTimer();
        if (this._tooltipPinned && this._tooltipIcon === icon) {
          this._destroyTooltip();
        } else {
          this._showFDTooltip(icon, true);
        }
        return;
      }
      if (this._currentTooltip?.contains(event.target)) return;
      if (this._currentTooltip) this._destroyTooltip();
    });
  }

  _showFDTooltip(icon, pinned) {
    this._destroyTooltip();
    if (!icon.dataset.fdWarning) return;

    this._tooltipIcon = icon;
    this._tooltipPinned = pinned;

    const tooltip = document.createElement('div');
    tooltip.className = 'fd-tooltip-fixed';
    tooltip.innerHTML = (pinned ? '<button class="fd-tooltip-close" aria-label="Close">&times;</button>' : '')
      + 'DICGC insures deposits up to ₹5 Lakhs per bank. Spread your savings across multiple banks to maximize your coverage. '
      + '<a href="https://www.dicgc.org.in/guide-to-deposit-insurance" target="_blank" rel="noopener noreferrer">Learn more at DICGC</a>';
    document.body.appendChild(tooltip);

    if (pinned) {
      tooltip.querySelector('.fd-tooltip-close').addEventListener('click', (e) => {
        e.stopPropagation();
        this._destroyTooltip();
      });
    }

    const rect = icon.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    let top = rect.top - tooltipRect.height - 8;
    let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
    if (top < 10) top = rect.bottom + 8;
    left = Math.max(10, Math.min(left, window.innerWidth - tooltipRect.width - 10));
    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;

    this._currentTooltip = tooltip;
  }

  _cancelHideTimer() {
    if (this._tooltipHideTimer) {
      clearTimeout(this._tooltipHideTimer);
      this._tooltipHideTimer = null;
    }
  }

  _destroyTooltip() {
    this._cancelHideTimer();
    this._currentTooltip?.remove();
    this._currentTooltip = null;
    this._tooltipIcon = null;
    this._tooltipPinned = false;
  }

  // ─── Section Info Toasters ────────────────────────────────────

  _setupInfoToasters() {
    const INFO_CONTENT = {
      stocks: {
        title: 'Stocks',
        items: [
          'Shows all your equity holdings across broker accounts.',
          'Same stock from multiple accounts is grouped \u2014 click to expand and see the split.',
          '<strong>To add:</strong> Click <strong>+ Add</strong> and enter the symbol (e.g. RELIANCE), quantity, average price, and exchange (NSE/BSE).',
          'Broker-synced holdings update automatically. Manually added entries show a person icon.',
          '<strong>P/L</strong> = (Current Price \u2212 Avg Price) \u00d7 Qty. <strong>Day\u2019s Change</strong> shows today\u2019s move.',
        ]
      },
      etfs: {
        title: 'ETFs',
        items: [
          'Exchange-Traded Funds that are not gold or silver \u2014 index ETFs, liquid ETFs, etc.',
          'Gold ETFs (GOLDBEES, etc.) and Silver ETFs (SILVERBEES, etc.) have their own dedicated tables under Gold and Silver sections.',
          '<strong>To add:</strong> Click <strong>+ Add</strong>, enter the ETF symbol (e.g. NIFTYBEES, LIQUIDETF), quantity, average price, and exchange.',
          'Same structure as the stocks table \u2014 sortable columns, grouped by symbol.',
        ]
      },
      mutual_funds: {
        title: 'Mutual Funds',
        items: [
          'All your mutual fund holdings with current NAV and returns.',
          '<strong>To add:</strong> Click <strong>+ Add</strong>, enter the exact fund name (e.g. AXIS BLUECHIP FUND), units held, and average NAV.',
          'NAV (Net Asset Value) is the per-unit price. The date below NAV shows when it was last updated.',
          'Funds from multiple accounts are grouped by name \u2014 click to expand.',
        ]
      },
      silver: {
        title: 'Silver',
        items: [
          'Tracks your silver exposure through Silver ETFs like SILVERBEES, SILVRETF, etc.',
          'Silver ETFs are automatically detected from the ETFs sheet and shown in this dedicated table.',
          'The summary above shows your combined silver investment, current value, and P/L.',
          '<strong>To add:</strong> Add a silver ETF via the ETFs section\u2019s <strong>+ Add</strong> button. It will automatically appear here.',
        ]
      },
      gold: {
        title: 'Gold',
        items: [
          'Combines all your gold holdings \u2014 <strong>Gold ETFs</strong>, <strong>Physical Gold</strong>, and <strong>SGBs</strong> (Sovereign Gold Bonds) \u2014 into one unified view.',
          '<strong>Gold ETFs</strong> (GOLDBEES, GOLDPETL, etc.) are automatically detected and shown in a separate table within this section.',
          '<strong>SGBs</strong> (SGB24JUN, SGBNOV28, etc.) are stocks that start with "SGB" \u2014 they appear in the Stocks table but their value counts here.',
          '<strong>Physical Gold:</strong> Track jewellery, coins, bars. Valued using daily IBJA (India Bullion and Jewellers Association) rates.',
          '<strong>To add physical gold:</strong> Click <strong>+ Add</strong>, enter date, type, purity (24K/22K/18K), weight in grams, and the IBJA rate/gm on the purchase date.',
          'The breakdown strip shows how your gold is split across ETFs, Physical, and SGBs.',
        ]
      },
      fixed_deposits: {
        title: 'Fixed Deposits',
        items: [
          'Track your FDs across banks with maturity dates and interest rates.',
          '<strong>To add:</strong> Click <strong>+ Add</strong>, enter deposit date, bank, tenure (years/months/days), amount, interest rate, and account label.',
          '<strong>Original Amt:</strong> The money you first deposited when you opened the FD.',
          '<strong>Reinvested Amt:</strong> When an FD auto-renews (rolls over), the maturity amount (principal + interest) becomes the reinvested amount for the new tenure.',
          '<strong>Reinvested On:</strong> The date the FD was auto-renewed. Leave blank for first-time deposits.',
          'For an <strong>auto-renewed FD</strong>: Original Amt is what you deposited before the last tenure. Reinvested Amt is the rolled-over amount (original + accrued interest).',
          '<strong>Current Value:</strong> Estimated value today based on tenure elapsed and interest rate.',
          'The <span style="color:#f59e0b;font-weight:700">!</span> icon appears when deposits at a bank exceed \u20b95 Lakhs \u2014 the DICGC insurance coverage limit.',
          'Switch to <strong>By Bank</strong> tab to see aggregated totals per bank.',
        ]
      },
      provident_fund: {
        title: 'Provident Fund',
        items: [
          'Track your EPF/PF across employers with compounding interest.',
          '<strong>Active Employment:</strong> Enter company, start date, end date (blank if current), monthly contribution, and interest rate.',
          '<strong>Past Employer:</strong> Enter accumulated balance and your contribution (employer + employee contribution from EPFO passbook) to track carry-forward interest accurately.',
          '<strong>Interest Rate:</strong> Enter 0 or leave blank to auto-apply the official EPFO rate for each financial year. Or enter a custom rate.',
          'Multiple stints at the same company are grouped \u2014 click to expand.',
          '<strong>P&L:</strong> For past employers, the split between your contribution and interest earned is based on the contribution you enter. This ensures accurate portfolio-level profit tracking.',
        ]
      },
      sips: {
        title: 'SIPs',
        items: [
          'Track your Systematic Investment Plans with frequency, status, and next due date.',
          '<strong>To add:</strong> Click <strong>+ Add</strong>, enter fund name, amount, frequency (Monthly/Weekly/Quarterly), status, and next due date.',
          '<strong>Installments:</strong> Enter \u22121 for perpetual SIPs (no end date). Otherwise enter total installments planned.',
          'The rhythm summary at the top shows your total monthly and annual SIP outflow across all active SIPs.',
          'The frequency bar shows how your SIP amount is distributed across weekly, monthly, and quarterly SIPs.',
        ]
      },
    };

    this._activeInfoPopup = null;

    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.section-info-btn');
      if (btn) {
        e.stopPropagation();
        const key = btn.dataset.info;
        if (!key || !INFO_CONTENT[key]) return;

        // Toggle off if same popup
        if (this._activeInfoPopup && this._activeInfoPopup.dataset.infoKey === key) {
          this._closeInfoPopup();
          return;
        }
        this._closeInfoPopup();
        this._showInfoPopup(btn, key, INFO_CONTENT[key]);
        return;
      }
      // Close if clicking the overlay backdrop
      if (this._activeInfoPopup && e.target.classList.contains('section-info-overlay')) {
        this._closeInfoPopup();
      }
    });
  }

  _showInfoPopup(btn, key, content) {
    const overlay = document.createElement('div');
    overlay.className = 'section-info-overlay';
    overlay.dataset.infoKey = key;

    let html = `<div class="section-info-popup">
      <div class="section-info-popup-header">
        <span class="section-info-popup-title">${content.title}</span>
        <button class="section-info-popup-close" aria-label="Close">&times;</button>
      </div>
      <div class="section-info-popup-body">
        <ul class="section-info-popup-list">`;
    content.items.forEach(item => {
      html += `<li>${item}</li>`;
    });
    html += '</ul></div></div>';
    overlay.innerHTML = html;

    document.body.appendChild(overlay);

    // Animate in
    requestAnimationFrame(() => overlay.classList.add('open'));

    // Close button
    overlay.querySelector('.section-info-popup-close').addEventListener('click', (e) => {
      e.stopPropagation();
      this._closeInfoPopup();
    });

    // Escape key
    this._infoPopupEscHandler = (e) => {
      if (e.key === 'Escape') this._closeInfoPopup();
    };
    document.addEventListener('keydown', this._infoPopupEscHandler);

    this._activeInfoPopup = overlay;
    btn.classList.add('active');
  }

  _closeInfoPopup() {
    if (!this._activeInfoPopup) return;
    const overlay = this._activeInfoPopup;
    overlay.classList.remove('open');

    // Remove active state from the button
    const key = overlay.dataset.infoKey;
    const btn = document.querySelector(`.section-info-btn[data-info="${key}"]`);
    if (btn) btn.classList.remove('active');

    // Remove after transition
    overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
    // Fallback removal
    setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 300);

    if (this._infoPopupEscHandler) {
      document.removeEventListener('keydown', this._infoPopupEscHandler);
      this._infoPopupEscHandler = null;
    }
    this._activeInfoPopup = null;
  }

  _setupHeaderSortListeners() {
    const tableConfigs = [
      {
        selector: '#stocksTable',
        getSortOrder: () => this.sortManager.getStocksSortOrder(),
        applySort: (sortBy) => this._handleSort('Stocks', sortBy)
      },
      {
        selector: '#etfTable',
        getSortOrder: () => this.sortManager.getETFSortOrder(),
        applySort: (sortBy) => this._handleSort('ETF', sortBy)
      },
      {
        selector: '#goldETFTable',
        getSortOrder: () => this.sortManager.getGoldETFSortOrder(),
        applySort: (sortBy) => this._handleSort('GoldETF', sortBy)
      },
      {
        selector: '#silverETFTable',
        getSortOrder: () => this.sortManager.getSilverETFSortOrder(),
        applySort: (sortBy) => this._handleSort('SilverETF', sortBy)
      },
      {
        selector: '#mfTable',
        getSortOrder: () => this.sortManager.getMFSortOrder(),
        applySort: (sortBy) => this._handleSort('MF', sortBy)
      },
      {
        selector: '#physicalGoldTable',
        getSortOrder: () => this.sortManager.getPhysicalGoldSortOrder(),
        applySort: (sortBy) => this._handleSort('PhysicalGold', sortBy)
      },
      {
        selector: '#fixedDepositsTable',
        getSortOrder: () => this.sortManager.getFixedDepositsSortOrder(),
        applySort: (sortBy) => this.handleFixedDepositsSort(sortBy)
      },
      {
        selector: '#providentFundTable',
        getSortOrder: () => this.sortManager.getProvidentFundSortOrder(),
        applySort: (sortBy) => this.handleProvidentFundSort(sortBy)
      },
      {
        selector: '#fdSummaryTable',
        getSortOrder: () => this.sortManager.getFDSummarySortOrder(),
        applySort: (sortBy) => this.handleFDSummarySort(sortBy)
      }
    ];

    tableConfigs.forEach(({ selector, getSortOrder, applySort }) => {
      const table = document.querySelector(selector);
      if (!table) return;

      const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
      sortableHeaders.forEach((header) => {
        header.classList.add('sortable-header');
        header.setAttribute('role', 'button');
        header.setAttribute('tabindex', '0');

        const runSort = () => {
          const nextSort = this._getNextHeaderSortOrder(header, getSortOrder());
          applySort(nextSort);
          this._syncHeaderSortIndicators(table, getSortOrder());
        };

        header.addEventListener('click', runSort);
        header.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            runSort();
          }
        });
      });

      this._syncHeaderSortIndicators(table, getSortOrder());
    });
  }

  _getNextHeaderSortOrder(header, currentSortOrder) {
    const ascSort = header.dataset.sortAsc;
    const descSort = header.dataset.sortDesc;
    const asc2Sort = header.dataset.sortAsc2;
    const desc2Sort = header.dataset.sortDesc2;
    const defaultDirection = header.dataset.sortDefault || 'desc';

    // Cycle: desc → asc → (desc2 → asc2 →) desc
    if (currentSortOrder === descSort) return ascSort;
    if (currentSortOrder === ascSort) {
      return desc2Sort ? desc2Sort : descSort;
    }
    if (desc2Sort && currentSortOrder === desc2Sort) return asc2Sort;
    if (asc2Sort && currentSortOrder === asc2Sort) return descSort;
    return defaultDirection === 'asc' ? ascSort : descSort;
  }

  _syncHeaderSortIndicators(table, currentSortOrder) {
    const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
    sortableHeaders.forEach((header) => {
      const ascSort = header.dataset.sortAsc;
      const descSort = header.dataset.sortDesc;
      const asc2Sort = header.dataset.sortAsc2;
      const desc2Sort = header.dataset.sortDesc2;

      header.classList.remove('sorted-asc', 'sorted-desc', 'sorted-pct-asc', 'sorted-pct-desc');
      header.setAttribute('aria-sort', 'none');

      if (currentSortOrder === ascSort) {
        header.classList.add('sorted-asc');
        header.setAttribute('aria-sort', 'ascending');
      } else if (currentSortOrder === descSort) {
        header.classList.add('sorted-desc');
        header.setAttribute('aria-sort', 'descending');
      } else if (asc2Sort && currentSortOrder === asc2Sort) {
        header.classList.add('sorted-pct-asc');
        header.setAttribute('aria-sort', 'ascending');
      } else if (desc2Sort && currentSortOrder === desc2Sort) {
        header.classList.add('sorted-pct-desc');
        header.setAttribute('aria-sort', 'descending');
      }
    });
  }

  _setupSummaryCardNavigation() {
    const bar = document.getElementById('allocation_bar');
    const labels = document.getElementById('alloc_labels');
    const focus = document.getElementById('alloc_focus');
    if (!bar || !labels || !focus) return;

    const activate = (asset) => {
      const isAlready = bar.querySelector(`.alloc-seg.active[data-asset="${asset}"]`);
      // Clear all
      bar.querySelectorAll('.alloc-seg').forEach(s => s.classList.remove('active'));
      labels.querySelectorAll('.alloc-tag').forEach(t => t.classList.remove('active'));
      focus.querySelectorAll('.alloc-focus-row').forEach(r => r.classList.remove('active'));

      if (isAlready) {
        // Deactivate
        bar.classList.remove('has-focus');
        labels.classList.remove('has-focus');
        focus.classList.remove('open');
      } else {
        // Activate
        bar.classList.add('has-focus');
        labels.classList.add('has-focus');
        bar.querySelector(`.alloc-seg[data-asset="${asset}"]`)?.classList.add('active');
        labels.querySelector(`.alloc-tag[data-asset="${asset}"]`)?.classList.add('active');
        const row = focus.querySelector(`.alloc-focus-row[data-asset="${asset}"]`);
        if (row) row.classList.add('active');
        focus.classList.add('open');
      }
    };

    // Bar segment click
    bar.querySelectorAll('.alloc-seg[data-asset]').forEach(seg => {
      seg.addEventListener('click', () => activate(seg.dataset.asset));
    });

    // Label tag click — highlight + scroll to section
    labels.querySelectorAll('.alloc-tag[data-asset]').forEach(tag => {
      tag.addEventListener('click', () => {
        activate(tag.dataset.asset);
      });
      tag.addEventListener('dblclick', () => {
        const section = document.getElementById(tag.dataset.section);
        if (!section) return;
        const hdr = document.querySelector('header');
        const hdrH = hdr ? hdr.getBoundingClientRect().height : 0;
        const top = section.getBoundingClientRect().top + window.scrollY - hdrH - 12;
        window.scrollTo({ top: Math.max(top, 0), behavior: 'smooth' });
      });
    });

    // Click outside allocation area to collapse focus shelf
    const allocation = document.getElementById('data-container-summary');
    document.addEventListener('click', (e) => {
      if (!focus.classList.contains('open')) return;
      if (allocation && allocation.contains(e.target)) return;
      bar.querySelectorAll('.alloc-seg').forEach(s => s.classList.remove('active'));
      labels.querySelectorAll('.alloc-tag').forEach(t => t.classList.remove('active'));
      focus.querySelectorAll('.alloc-focus-row').forEach(r => r.classList.remove('active'));
      bar.classList.remove('has-focus');
      labels.classList.remove('has-focus');
      focus.classList.remove('open');
    });
  }

  /**
   * Initial load after PIN verification.
   * If we have inlined data, just fetch status. Otherwise trigger a
   * backend refresh and poll incrementally — rendering each data source
   * as it becomes available rather than waiting for everything.
   */
  async _initialLoad() {
    try {
      if (this._hasInitialData) {
        // Warm cache — data already rendered from server-inlined payload.
        // Just fetch & apply status UI.
        const status = await this._fetchStatus();
        this._applyStatus(status);
        Log.info('App', 'Initial status applied (warm cache)');
        // Even with warm cache, LTPs may still be updating
        this._pollForManualLTPs(status);
        return;
      }

      // Cold start — check backend state first
      this._setUpdatingUI();
      const status = await this._fetchStatus();

      if (this._isStatusUpdating(status)) {
        // Backend is already fetching — poll incrementally
        Log.info('App', 'Backend already updating — polling incrementally');
        const finalStatus = await this._pollIncremental(status);
        this._updateRefreshButton(false);
        this._pollForManualLTPs(finalStatus);
        this.indexTicker.fetchAndRender();
      } else if (this._hasDataReady(status)) {
        // Data already fetched (pill navigation) — just grab it
        Log.info('App', 'Data already available — loading');
        await this.updateData();
        this._applyStatus(status);
        this._updateRefreshButton(false);
        this._pollForManualLTPs(status);
      } else {
        // No data yet — trigger a refresh
        Log.info('App', 'No data — triggering refresh');
        try {
          await this.dataManager.triggerRefresh();
        } catch (e) {
          if (!e.message?.includes('409')) {
            Log.warn('App', 'Initial refresh failed:', e.message);
          }
        }
        const afterTrigger = await this._fetchStatus();
        const finalStatus = await this._pollIncremental(afterTrigger);
        this._updateRefreshButton(false);
        this._pollForManualLTPs(finalStatus);
        this.indexTicker.fetchAndRender();
      }
    } catch (error) {
      Log.error('App', 'Initial load error:', error);
      this._updateRefreshButton(false);
    }
  }

  _hasDataReady(status) {
    // Data is ready if any tracked state has been updated at least once
    return status.portfolio_last_updated != null ||
           status.sheets_last_updated != null ||
           status.physical_gold_last_updated != null ||
           status.fixed_deposits_last_updated != null;
  }

  /**
   * Fetch /api/status and return the parsed JSON.
   */
  async _fetchStatus() {
    const resp = await fetch('/api/status', { credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`Status fetch failed: ${resp.status}`);
    return resp.json();
  }

  /**
   * Poll /api/status and render incrementally as each data source
   * completes.  Detects transitions from 'updating' → terminal and
   * re-fetches data so the UI shows results as they arrive.
   *
   * @param {Object} initialStatus - Status snapshot captured before polling starts,
   *   used to detect the first transition.
   * @returns {Promise<Object>} Final status when all sources are done.
   */
  async _pollIncremental(initialStatus) {
    const POLL_INTERVAL = 2000;
    const MAX_POLLS = 90; // 3 minutes max
    let prev = initialStatus || {};
    // Track which sources have been fetched across the entire poll loop
    // so we can catch sources that completed before polling started.
    let portfolioFetched = false;
    let sheetsFetched = false;

    // Eagerly fetch any sources already completed before polling begins.
    // This avoids waiting an extra poll cycle (or deferring to catch-up)
    // when a fast source finishes before the first poll fires.
    const portfolioAlreadyDone = prev.portfolio_state && prev.portfolio_state !== 'updating';
    const sheetsAlreadyDone = prev.sheets_state && prev.sheets_state !== 'updating';

    if (portfolioAlreadyDone && sheetsAlreadyDone) {
      Log.info('App', 'Both sources already done — loading all');
      await this.updateData();
      portfolioFetched = true;
      sheetsFetched = true;
    } else if (portfolioAlreadyDone) {
      Log.info('App', 'Portfolio already done — loading broker data');
      await this.updatePortfolioData();
      portfolioFetched = true;
    } else if (sheetsAlreadyDone) {
      Log.info('App', 'Sheets already done — loading sheets data');
      await this.updateSheetsData();
      sheetsFetched = true;
    }

    // If everything is done, no need to poll at all.
    if (portfolioFetched && sheetsFetched && !this._isStatusUpdating(prev)) {
      this._applyStatus(prev);
      if (prev.manual_ltp_last_updated) {
        this._lastManualLtpUpdate = prev.manual_ltp_last_updated;
      }
      return prev;
    }

    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, POLL_INTERVAL));
      const status = await this._fetchStatus();

      // Detect per-source transitions from 'updating' → terminal.
      const portfolioCompleted = prev.portfolio_state === 'updating' && status.portfolio_state !== 'updating';
      const sheetsCompleted = prev.sheets_state === 'updating' && status.sheets_state !== 'updating';

      if (portfolioCompleted && sheetsCompleted) {
        Log.info('App', 'Both sources completed — refreshing all');
        await this.updateData();
        portfolioFetched = true;
        sheetsFetched = true;
      } else if (portfolioCompleted) {
        Log.info('App', 'Portfolio completed — refreshing broker data');
        await this.updatePortfolioData();
        portfolioFetched = true;
      } else if (sheetsCompleted) {
        Log.info('App', 'Sheets completed — refreshing sheets data');
        await this.updateSheetsData();
        sheetsFetched = true;
        // Manual stocks/SIPs live in the sheets cache, so if portfolio
        // was already fetched before sheets were ready, re-fetch it now
        // to pick up manual entries (e.g. manually added stocks & SIPs).
        if (portfolioFetched) {
          Log.info('App', 'Re-fetching portfolio data (manual entries now available from sheets)');
          await this.updatePortfolioData();
        }
      }

      this._applyStatus(status);
      prev = { ...status };

      if (!this._isStatusUpdating(status)) {
        // Fetch any sources whose transition was missed (completed
        // before polling started, or state was never 'updating').
        if (!portfolioFetched && !sheetsFetched) {
          await this.updateData();
        } else if (!portfolioFetched) {
          Log.info('App', 'Catching up portfolio data (transition missed)');
          await this.updatePortfolioData();
        } else if (!sheetsFetched) {
          Log.info('App', 'Catching up sheets data (transition missed)');
          await this.updateSheetsData();
          // Manual stocks/SIPs depend on sheets cache — refresh portfolio
          // so manually added entries appear in the stocks/SIPs tables.
          if (portfolioFetched) {
            Log.info('App', 'Re-fetching portfolio data (manual entries now available from sheets)');
            await this.updatePortfolioData();
          }
        }
        // Record LTP timestamp so _pollForManualLTPs doesn't re-fetch
        if (status.manual_ltp_last_updated) {
          this._lastManualLtpUpdate = status.manual_ltp_last_updated;
        }
        return status;
      }
    }
    Log.warn('App', 'Poll timeout — proceeding with available data');
    const finalStatus = await this._fetchStatus();
    await this.updateData();
    return finalStatus;
  }

  /**
   * Non-blocking: If manual LTP fetch is still in progress, poll in the
   * background and re-fetch data once LTPs are ready.  Also handles the
   * race where LTPs finished while /api/all_data was being served.
   */
  async _pollForManualLTPs(status) {
    const POLL_INTERVAL = 2000;
    const MAX_POLLS = 30; // 1 minute max

    if (status?.manual_ltp_state === 'updating') {
      Log.info('App', 'Manual LTP fetch in progress — polling for completion');
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise(r => setTimeout(r, POLL_INTERVAL));
        const s = await this._fetchStatus();
        if (s.manual_ltp_state !== 'updating') {
          Log.info('App', 'Manual LTPs ready — refreshing portfolio data');
          this._lastManualLtpUpdate = s.manual_ltp_last_updated;
          await this.updatePortfolioData();
          this._applyStatus(s);
          return;
        }
      }
      Log.warn('App', 'Manual LTP poll timeout');
      return;
    }

    // LTPs already finished (fast fetch) — re-fetch data once if we
    // haven't incorporated this update yet.
    if (status?.manual_ltp_state === 'updated' &&
        status?.manual_ltp_last_updated &&
        status.manual_ltp_last_updated !== this._lastManualLtpUpdate) {
      Log.info('App', 'Manual LTPs completed (fast) — refreshing portfolio data');
      this._lastManualLtpUpdate = status.manual_ltp_last_updated;
      await this.updatePortfolioData();
    }
  }

  /**
   * Apply a status object to the UI (status tag, login banner, etc.)
   * without triggering data fetches.
   */
  _applyStatus(status) {
    this.lastStatus = status;
    const statusTag = document.getElementById('status_tag');
    const statusText = document.getElementById('status_text');
    const isUpdating = this._isStatusUpdating(status);

    statusTag.classList.toggle('updating', isUpdating);
    statusTag.classList.toggle('updated', !isUpdating);
    statusTag.classList.toggle('market_closed', status.market_open === false);

    if (isUpdating) {
      statusText.innerText = 'updating';
    } else {
      this.lastPortfolioUpdatedAt = status.portfolio_last_updated || null;
      statusText.innerText = this._formatStatusUpdatedText();
    }

    const unauthenticated = status.unauthenticated_accounts || [];
    this._updateLoginBanner(unauthenticated, isUpdating);
    this._updateConnectNudge(status);

    // Refresh settings drawer pills if drawer is open
    if (typeof window.loadDrawerAccounts === 'function') {
      const drawer = document.getElementById('settingsDrawer');
      if (drawer && drawer.classList.contains('open')) {
        window.loadDrawerAccounts();
      }
    }
  }

  /**
   * Set UI to "updating" state (status tag + refresh button).
   */
  _setUpdatingUI() {
    const statusTag = document.getElementById('status_tag');
    const statusText = document.getElementById('status_text');
    statusTag.className = 'updating';
    statusText.innerText = 'updating';
    this._updateRefreshButton(true);
  }

  _renderTablesAndSummary(hasData, status, isUpdating) {
    const sortedPhysicalGold = this.sortManager.sortPhysicalGold(
      this.dataManager.getPhysicalGold(),
      this.sortManager.getPhysicalGoldSortOrder()
    );
    const physicalGoldTotals = this.tableRenderer.renderPhysicalGoldTable(sortedPhysicalGold);

    const sortedFixedDeposits = this.sortManager.sortFixedDeposits(
      this.dataManager.getFixedDeposits(),
      this.sortManager.getFixedDepositsSortOrder()
    );
    const fdTotals = this.tableRenderer.renderFixedDepositsTable(sortedFixedDeposits);

    const sortedProvidentFund = this.sortManager.sortProvidentFund(
      this.dataManager.getProvidentFund(),
      this.sortManager.getProvidentFundSortOrder()
    );
    const pfTotals = this.tableRenderer.renderProvidentFundTable(sortedProvidentFund);

    const Z = { invested: 0, current: 0, pl: 0, plPct: 0 };

    let stockTotals = Z, etfTotals = Z, mfTotals = Z;
    let goldTotals = Z, goldETFTotals = Z, sgbTotals = Z;
    let silverTotals = Z, silverETFTotals = Z;

    if (hasData) {
      const allStocks = this.dataManager.getStocks();
      const sortedHoldings = this.sortManager.sortStocks(allStocks, this.sortManager.getStocksSortOrder());
      const sortedETF = this.sortManager.sortETFs(allStocks, this.sortManager.getETFSortOrder());
      const sortedGoldETF = this.sortManager.sortGoldETFs(allStocks, this.sortManager.getGoldETFSortOrder());
      const sortedSilverETF = this.sortManager.sortSilverETFs(allStocks, this.sortManager.getSilverETFSortOrder());
      const sortedMF = this.sortManager.sortMF(this.dataManager.getMFHoldings(), this.sortManager.getMFSortOrder());

      ({ stockTotals, goldTotals, sgbTotals, silverTotals } = this.tableRenderer.renderStocksTable(sortedHoldings, status));
      ({ etfTotals } = this.tableRenderer.renderETFTable(sortedETF, status));
      goldETFTotals = this.tableRenderer.renderGoldETFTable(sortedGoldETF, status);
      silverETFTotals = this.tableRenderer.renderSilverETFTable(sortedSilverETF, status);
      mfTotals = this.tableRenderer.renderMFTable(sortedMF, status);
      this.tableRenderer.renderSIPsTable(this.dataManager.getSIPs(), status);
    }

    this.summaryManager.updateAllSummaries(
      stockTotals,
      etfTotals,
      this._combineTotals(goldTotals, goldETFTotals, sgbTotals, physicalGoldTotals),
      this._combineTotals(silverTotals, silverETFTotals),
      mfTotals,
      fdTotals,
      isUpdating,
      goldETFTotals,
      sgbTotals,
      physicalGoldTotals,
      pfTotals
    );
  }

  /**
   * Sort all data, render all tables, and update summary cards.
   * Centralizes the repeated sort→render→summarize pattern.
   * @param {Object} status - Current status object
   * @param {Object} [opts] - Options
   * @param {boolean} [opts.renderSIPs=false] - Whether to also render the SIPs table
   * @param {boolean} [opts.isUpdating=false] - Whether data is currently updating
   * @param {Array|null} [opts.fdSummaryData=null] - If provided, render FD summary table with this data
   */
  _renderAllAndUpdateSummaries(status, { renderSIPs = false, isUpdating = false, fdSummaryData = null } = {}) {
    const allStocks = this.dataManager.getStocks();
    const sortedHoldings = this.sortManager.sortStocks(
      allStocks,
      this.sortManager.getStocksSortOrder()
    );
    const sortedETFHoldings = this.sortManager.sortETFs(
      allStocks,
      this.sortManager.getETFSortOrder()
    );
    const sortedGoldETFHoldings = this.sortManager.sortGoldETFs(
      allStocks,
      this.sortManager.getGoldETFSortOrder()
    );
    const sortedSilverETFHoldings = this.sortManager.sortSilverETFs(
      allStocks,
      this.sortManager.getSilverETFSortOrder()
    );
    const sortedMFHoldings = this.sortManager.sortMF(
      this.dataManager.getMFHoldings(),
      this.sortManager.getMFSortOrder()
    );
    const sortedPhysicalGold = this.sortManager.sortPhysicalGold(
      this.dataManager.getPhysicalGold(),
      this.sortManager.getPhysicalGoldSortOrder()
    );
    const sortedFixedDeposits = this.sortManager.sortFixedDeposits(
      this.dataManager.getFixedDeposits(),
      this.sortManager.getFixedDepositsSortOrder()
    );

    const { stockTotals, goldTotals, sgbTotals, silverTotals } = this.tableRenderer.renderStocksTable(sortedHoldings, status);
    const { etfTotals } = this.tableRenderer.renderETFTable(sortedETFHoldings, status);
    const goldETFTotals = this.tableRenderer.renderGoldETFTable(sortedGoldETFHoldings, status);
    const silverETFTotals = this.tableRenderer.renderSilverETFTable(sortedSilverETFHoldings, status);
    const mfTotals = this.tableRenderer.renderMFTable(sortedMFHoldings, status);
    if (renderSIPs) {
      this.tableRenderer.renderSIPsTable(this.dataManager.getSIPs(), status);
    }
    const physicalGoldTotals = this.tableRenderer.renderPhysicalGoldTable(sortedPhysicalGold);
    const fdTotals = this.tableRenderer.renderFixedDepositsTable(sortedFixedDeposits);

    const sortedProvidentFund = this.sortManager.sortProvidentFund(
      this.dataManager.getProvidentFund(),
      this.sortManager.getProvidentFundSortOrder()
    );
    const pfTotals = this.tableRenderer.renderProvidentFundTable(sortedProvidentFund);

    if (fdSummaryData && fdSummaryData.length > 0) {
      this.tableRenderer.renderFDSummaryTable(fdSummaryData);
    }

    const combinedGoldTotals = this._combineTotals(goldTotals, goldETFTotals, sgbTotals, physicalGoldTotals);
    const combinedSilverTotals = this._combineTotals(silverTotals, silverETFTotals);

    this.summaryManager.updateAllSummaries(
      stockTotals,
      etfTotals,
      combinedGoldTotals,
      combinedSilverTotals,
      mfTotals,
      fdTotals,
      isUpdating,
      goldETFTotals,
      sgbTotals,
      physicalGoldTotals,
      pfTotals
    );
  }

  handleSearch() {
    const searchEl = document.getElementById('search');
    const searchQuery = searchEl ? searchEl.value : '';
    this.tableRenderer.setSearchQuery(searchQuery);
    this._renderAllAndUpdateSummaries(this.lastStatus || {}, { renderSIPs: true });
  }

  /**
   * Apply a data payload (inlined or fetched) to the data manager and render.
   */
  _applyData({ stocks, mfHoldings, sips, physicalGold, fixedDeposits, providentFund, fdSummary, status }) {
    const searchEl = document.getElementById('search');
    const searchQuery = searchEl ? searchEl.value : '';
    const forceUpdate = searchQuery !== '';

    this.dataManager.updateStocks(stocks || [], forceUpdate);
    this.dataManager.updateMFHoldings(mfHoldings || [], forceUpdate);
    this.dataManager.updateSIPs(sips || [], forceUpdate);
    this.dataManager.updatePhysicalGold(physicalGold || [], forceUpdate);
    this.dataManager.updateFixedDeposits(fixedDeposits || [], forceUpdate);
    this.dataManager.updateProvidentFund(providentFund || [], forceUpdate);
    const computedSummary = (fdSummary && fdSummary.length)
      ? fdSummary
      : this.dataManager._computeFDSummary(fixedDeposits || []);
    this.dataManager.updateFDSummary(computedSummary, forceUpdate);

    this.tableRenderer.setSearchQuery(searchQuery);

    this._renderAllAndUpdateSummaries(status || {}, {
      renderSIPs: true,
      isUpdating: this._isStatusUpdating(status || {}),
      fdSummaryData: this.dataManager.getFDSummary()
    });
  }

  /**
   * Apply portfolio (broker) data only — stocks, MFs, SIPs.
   */
  _applyPortfolioData({ stocks, mfHoldings, sips, status }) {
    const searchEl = document.getElementById('search');
    const searchQuery = searchEl ? searchEl.value : '';
    const forceUpdate = searchQuery !== '';

    this.dataManager.updateStocks(stocks || [], forceUpdate);
    this.dataManager.updateMFHoldings(mfHoldings || [], forceUpdate);
    this.dataManager.updateSIPs(sips || [], forceUpdate);

    this.tableRenderer.setSearchQuery(searchQuery);

    if (status) {
      this.lastPortfolioUpdatedAt = status.portfolio_last_updated || null;
    }

    this._renderAllAndUpdateSummaries(status || this.lastStatus || {}, {
      renderSIPs: true,
      isUpdating: this._isStatusUpdating(status || this.lastStatus || {}),
      fdSummaryData: this.dataManager.getFDSummary()
    });
  }

  /**
   * Apply sheets data only — physical gold, FDs, provident fund.
   */
  _applySheetsData({ physicalGold, fixedDeposits, providentFund, fdSummary, status }) {
    const searchEl = document.getElementById('search');
    const searchQuery = searchEl ? searchEl.value : '';
    const forceUpdate = searchQuery !== '';

    this.dataManager.updatePhysicalGold(physicalGold || [], forceUpdate);
    this.dataManager.updateFixedDeposits(fixedDeposits || [], forceUpdate);
    this.dataManager.updateProvidentFund(providentFund || [], forceUpdate);
    const computedSummary = (fdSummary && fdSummary.length)
      ? fdSummary
      : this.dataManager._computeFDSummary(fixedDeposits || []);
    this.dataManager.updateFDSummary(computedSummary, forceUpdate);

    this.tableRenderer.setSearchQuery(searchQuery);

    this._renderAllAndUpdateSummaries(status || this.lastStatus || {}, {
      renderSIPs: false,
      isUpdating: this._isStatusUpdating(status || this.lastStatus || {}),
      fdSummaryData: this.dataManager.getFDSummary()
    });
  }

  async updateData() {
    try {
      Log.time('Data', 'fetchAllData');
      const data = await this.dataManager.fetchAllData();
      Log.timeEnd('Data', 'fetchAllData');
      this._hideLoadingIndicators();
      this._applyData(data);

      // Update status tracking from the response
      const respTimestamp = data.status?.portfolio_last_updated || null;
      if (respTimestamp) {
        this.lastPortfolioUpdatedAt = respTimestamp;
        const statusText = document.getElementById('status_text');
        if (statusText && !this._isStatusUpdating(this.lastStatus || {})) {
          statusText.innerText = this._formatStatusUpdatedText();
        }
      }
    } catch (error) {
      Log.error('Data', 'Error updating data:', error);
    }
  }

  async updatePortfolioData() {
    try {
      Log.time('Data', 'fetchPortfolioData');
      const data = await this.dataManager.fetchPortfolioData();
      Log.timeEnd('Data', 'fetchPortfolioData');
      this._hideLoadingIndicators();
      this._applyPortfolioData(data);
    } catch (error) {
      Log.error('Data', 'Error updating portfolio data:', error);
    }
  }

  async updateSheetsData() {
    try {
      Log.time('Data', 'fetchSheetsData');
      const data = await this.dataManager.fetchSheetsData();
      Log.timeEnd('Data', 'fetchSheetsData');
      this._hideLoadingIndicators();
      this._applySheetsData(data);
    } catch (error) {
      Log.error('Data', 'Error updating sheets data:', error);
    }
  }

  /**
   * Handle a CRUD mutation.  If the response carried refreshed data for
   * the affected table type, merge it with the current state and re-render
   * without hitting the server again.  Falls back to a full updateData()
   * when no data was provided (e.g. if the backend refresh failed).
   */
  _handleCrudChange(partialData) {
    if (partialData && typeof partialData === 'object' && Object.keys(partialData).length > 0) {
      const merged = {
        stocks: partialData.stocks ?? this.dataManager.getStocks(),
        mfHoldings: partialData.mfHoldings ?? this.dataManager.getMFHoldings(),
        sips: partialData.sips ?? this.dataManager.getSIPs(),
        physicalGold: partialData.physicalGold ?? this.dataManager.getPhysicalGold(),
        fixedDeposits: partialData.fixedDeposits ?? this.dataManager.getFixedDeposits(),
        providentFund: partialData.providentFund ?? this.dataManager.getProvidentFund(),
        fdSummary: null,  // let _applyData recompute from fixedDeposits
        status: this.lastStatus || {},
      };
      this._applyData(merged);
    } else {
      // Fallback: no data in response — do a full refresh.
      this.updateData();
    }
  }

  /**
   * Generic sort handler for tables that just need sort + full re-render.
   * @param {string} tableType - PascalCase table name (e.g. 'Stocks', 'ETF', 'MF', 'PhysicalGold')
   * @param {string} sortBy - Column key to sort by
   */
  _handleSort(tableType, sortBy) {
    this.sortManager[`set${tableType}SortOrder`](sortBy);
    this._renderAllAndUpdateSummaries(this.lastStatus || {});
  }

  handleFixedDepositsSort(sortBy) {
    this.sortManager.setFixedDepositsSortOrder(sortBy);
    const sortedFixedDeposits = this.sortManager.sortFixedDeposits(
      this.dataManager.getFixedDeposits(),
      this.sortManager.getFixedDepositsSortOrder()
    );
    this.tableRenderer.renderFixedDepositsTable(sortedFixedDeposits);
    this.tableRenderer.renderFDSummaryTable(sortedFixedDeposits);
  }

  handleProvidentFundSort(sortBy) {
    this.sortManager.setProvidentFundSortOrder(sortBy);
    const sortedPF = this.sortManager.sortProvidentFund(
      this.dataManager.getProvidentFund(),
      this.sortManager.getProvidentFundSortOrder()
    );
    this.tableRenderer.renderProvidentFundTable(sortedPF);
  }

  handleFDSummarySort(sortBy) {
    this.sortManager.setFDSummarySortOrder(sortBy);
    const fixedDeposits = this.dataManager.getFixedDeposits();
    const tbody = document.getElementById('fd_summary_table_body');
    if (!tbody) return;

    // Get current summary data from table
    const groupedData = this.tableRenderer._groupFDByBankAndAccount(fixedDeposits);
    const summaryArray = Object.values(groupedData);

    // Sort and re-render with row limit
    const sortedSummary = this.sortManager.sortFDSummary(summaryArray, sortBy);
    const rowLimit = this.tableRenderer.rowLimit;
    const pageData = sortedSummary.slice(0, rowLimit);

    let rowsHTML = '';
    pageData.forEach((summary) => {
      rowsHTML += this.tableRenderer._buildFDSummaryRow(summary);
    });

    if (sortedSummary.length > rowLimit) {
      rowsHTML += this.tableRenderer._buildViewMoreRow(sortedSummary.length, 5, 'fixed-deposits', 'summaries');
    }
    this.tableRenderer._updateTbodyContent(tbody, rowsHTML);
  }

  async handleRefresh() {
    this._setUpdatingUI();

    try {
      await this.dataManager.triggerRefresh();
    } catch (error) {
      // 409 = already in progress — still poll for completion
      if (!error.message?.includes('409')) {
        Log.warn('Refresh', 'Request failed:', error.message);
        this._updateRefreshButton(false);
        return;
      }
    }

    try {
      const afterTrigger = await this._fetchStatus();
      const finalStatus = await this._pollIncremental(afterTrigger);
      this._updateRefreshButton(false);
      this._pollForManualLTPs(finalStatus);
      this.indexTicker.fetchAndRender();
    } catch (error) {
      Log.error('Refresh', 'Error during polling/fetch:', error);
      this._updateRefreshButton(false);
    }
  }

  _updateRefreshButton(isUpdating) {
    const btn = document.getElementById('refresh_btn');
    if (isUpdating) {
      btn.classList.add('loading');
      btn.disabled = true;
    } else {
      btn.classList.remove('loading');
      btn.disabled = false;
    }
  }

  _escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  _updateLoginBanner(unauthenticatedAccounts, isUpdating) {
    const banner = document.getElementById('loginBanner');
    if (!banner) return;

    const hasUnauthenticated = unauthenticatedAccounts.length > 0;
    const isVisible = banner.style.display !== 'none';

    // While refreshing, leave banner as-is so it doesn't detach/reattach
    if (isUpdating) return;

    if (hasUnauthenticated && !isVisible) {
      // First appearance — show with entrance animation
      banner.style.display = '';
      banner.classList.remove('login-banner-enter');
      void banner.offsetWidth; // reflow
      banner.classList.add('login-banner-enter');
    } else if (!hasUnauthenticated && isVisible) {
      // Accounts are now synced — hide
      banner.style.display = 'none';
      banner.classList.remove('login-banner-enter');
    }
  }

  _updateConnectNudge(status) {
    const nudge = document.getElementById('connectNudge');
    if (!nudge) return;
    const DISMISS_KEY = 'metron_connect_nudge_dismissed';

    // Once user connects accounts, auto-hide and clear dismiss state
    if (status.has_zerodha_accounts) {
      if (nudge.style.display !== 'none') {
        nudge.style.display = 'none';
      }
      return;
    }

    // Don't show if user explicitly dismissed
    if (localStorage.getItem(DISMISS_KEY)) return;

    // Show the nudge
    if (nudge.style.display === 'none') {
      nudge.style.display = '';
    }
  }

  /**
   * Called when the browser tab becomes visible again.
   * If broker accounts were previously unauthenticated, re-check status
   * and auto-start data fetching if sessions are now valid.
   */
  async _onTabVisible() {
    const prevUnauthenticated = this.lastStatus?.unauthenticated_accounts || [];
    if (prevUnauthenticated.length === 0) return;

    try {
      const status = await this._fetchStatus();
      const nowUnauthenticated = status.unauthenticated_accounts || [];

      // Some accounts were re-authenticated while the tab was hidden
      if (nowUnauthenticated.length < prevUnauthenticated.length) {
        Log.info('App', 'Broker session restored — refreshing');
        this._applyStatus(status);

        // Also refresh the drawer accounts (even if drawer is closed)
        if (typeof window.loadDrawerAccounts === 'function') {
          window.loadDrawerAccounts();
        }

        // If backend already started fetching (callback triggers this),
        // poll for results. Otherwise trigger a fresh refresh.
        if (this._isStatusUpdating(status)) {
          this._setUpdatingUI();
          const finalStatus = await this._pollIncremental(status);
          this._updateRefreshButton(false);
          this._pollForManualLTPs(finalStatus);
          this.indexTicker.fetchAndRender();
        } else {
          await this.handleRefresh();
        }
      } else {
        // Still unauthenticated — just update status UI
        this._applyStatus(status);
      }
    } catch (error) {
      Log.warn('App', 'Tab-visible status check failed:', error.message);
    }
  }

  disconnect() {
    if (this.relativeStatusTimer) {
      clearInterval(this.relativeStatusTimer);
      this.relativeStatusTimer = null;
    }
  }
}

// Global function to toggle group expansion
window.toggleGroupExpand = function(event, groupId) {
  event.stopPropagation();
  const toggleBtn = document.querySelector(`.expand-toggle[data-group-id="${groupId}"]`);
  if (!toggleBtn) return;
  const breakdownRows = document.querySelectorAll(`.breakdown-row.${groupId}`);
  const isExpanded = toggleBtn.classList.contains('expanded');
  
  // Access the global app instance to track expanded state
  if (window.portfolioApp && window.portfolioApp.tableRenderer) {
    if (isExpanded) {
      breakdownRows.forEach(row => {
        row.style.display = 'none';
      });
      toggleBtn.classList.remove('expanded');
      window.portfolioApp.tableRenderer.markGroupCollapsed(groupId);
    } else {
      breakdownRows.forEach(row => {
        row.style.display = 'table-row';
      });
      toggleBtn.classList.add('expanded');
      window.portfolioApp.tableRenderer.markGroupExpanded(groupId);
    }
  }
};

// Delegate row-click on group rows to toggle expansion
document.addEventListener('click', function(event) {
  // Don't trigger on buttons, links, or CRUD actions inside the row
  const target = event.target;
  if (target.closest('button, a, .crud-row-actions, .source-indicator')) return;
  const groupRow = target.closest('tr.group-row');
  if (!groupRow) return;
  const toggle = groupRow.querySelector('.expand-toggle[data-group-id]');
  if (!toggle) return;
  const groupId = toggle.dataset.groupId;
  window.toggleGroupExpand(event, groupId);
});

// Global function to switch Fixed Deposits tabs
window.switchFDTab = function(tabName) {
  // Update tab buttons
  const tabs = document.querySelectorAll('.fd-tab');
  tabs.forEach(tab => {
    if (tab.dataset.tab === tabName) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  // Update tab content
  const contents = document.querySelectorAll('.fd-tab-content');
  contents.forEach(content => {
    if (content.id === `fd-tab-${tabName}`) {
      content.classList.add('active');
    } else {
      content.classList.remove('active');
    }
  });

  const maturityControl = document.getElementById('fixed_deposits_header_control');
  const summaryControl = document.getElementById('fd_summary_header_control');

  if (!maturityControl || !summaryControl) {
    return;
  }

  if (tabName === 'maturity') {
    maturityControl.classList.add('active');
    summaryControl.classList.remove('active');
  } else {
    summaryControl.classList.add('active');
    maturityControl.classList.remove('active');
  }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const app = new PortfolioApp();
  window.portfolioApp = app; // Expose app globally for toggle function
  app.init();
});

export default PortfolioApp;
