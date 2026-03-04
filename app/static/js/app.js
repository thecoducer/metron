/* Metron - Main Application Controller */

import DataManager from './data-manager.js';
import TableRenderer from './table-renderer.js';
import SummaryManager from './summary-manager.js';
import SortManager from './sort-manager.js';
import ThemeManager from './theme-manager.js';
import PrivacyManager from './visibility-manager.js';
import SSEConnectionManager from './sse-manager.js';
import PaginationManager from './pagination.js';
import { Formatter } from './utils.js';
import IndexTicker from './index-ticker.js';
import CrudManager from './crud-manager.js';

class PortfolioApp {
  constructor() {
    this.dataManager = new DataManager();
    this.tableRenderer = new TableRenderer();
    this.summaryManager = new SummaryManager();
    this.sortManager = new SortManager();
    this.themeManager = new ThemeManager();
    this.privacyManager = new PrivacyManager();
    this.sseManager = new SSEConnectionManager();
    this.indexTicker = new IndexTicker();
    this.crudManager = new CrudManager((partialData) => this._handleCrudChange(partialData));
    this.needsLogin = false;
    this.lastStatus = null;
    this.lastPortfolioUpdatedAt = null;
    this._lastFetchedPortfolioTimestamp = null; // tracks last-fetched portfolio_last_updated for change detection
    this.relativeStatusTimer = null;
    this.searchTimeout = null;
    // _wasUpdating intentionally left undefined to detect first SSE on page load
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
    } else {
      this._renderEmptyStates();
      this._hasInitialData = false;
    }
    
    // Connect SSE for live status updates
    this.connectEventSource();
    
    // Start live market index ticker (NIFTY 50 / SENSEX)
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
    this.tableRenderer.renderMFTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderSIPsTable([], { portfolio_state: 'idle' });
    this.tableRenderer.renderPhysicalGoldTable([]);
    this.tableRenderer.renderFixedDepositsTable([]);
    this.tableRenderer.renderFDSummaryTable([]);
  }

  _isStatusUpdating(status) {
    // Portfolio page: check portfolio, physical gold, and fixed deposits (not Nifty50 background fetch)
    return status.portfolio_state === 'updating' || 
           status.physical_gold_state === 'updating' ||
           status.fixed_deposits_state === 'updating';
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
    // gold card click → toggle breakdown drawer
    const goldCard = document.getElementById('gold_summary');
    if (goldCard) {
      goldCard.addEventListener('click', () => {
        this.summaryManager.toggleGoldDrawer();
      });
      goldCard.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.summaryManager.toggleGoldDrawer();
        }
      });
    }
    // Sort handlers
    window.sortStocksTable = (sortBy) => this._handleSort('Stocks', sortBy);
    window.sortETFTable = (sortBy) => this._handleSort('ETF', sortBy);
    window.sortMFTable = (sortBy) => this._handleSort('MF', sortBy);
    window.sortPhysicalGoldTable = (sortBy) => this._handleSort('PhysicalGold', sortBy);
    window.sortFixedDepositsTable = (sortBy) => this.handleFixedDepositsSort(sortBy);
    window.sortFDSummaryTable = (sortBy) => this.handleFDSummarySort(sortBy);

    this._setupHeaderSortListeners();

    // Pagination handlers — data-driven registration
    const paginatedTables = ['Stocks', 'ETF', 'MF', 'PhysicalGold', 'FixedDeposits', 'FDSummary'];
    paginatedTables.forEach((name) => {
      window[`change${name}PageSize`] = (size) => {
        this.tableRenderer[`change${name}PageSize`](parseInt(size));
        this.updateData();
      };
      window[`goTo${name}Page`] = (page) => {
        this.tableRenderer[`goTo${name}Page`](page);
        this.updateData();
      };
    });

    this._setupSummaryCardNavigation();

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
    const defaultDirection = header.dataset.sortDefault || 'desc';

    if (currentSortOrder === descSort) return ascSort;
    if (currentSortOrder === ascSort) return descSort;
    return defaultDirection === 'asc' ? ascSort : descSort;
  }

  _syncHeaderSortIndicators(table, currentSortOrder) {
    const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
    sortableHeaders.forEach((header) => {
      const ascSort = header.dataset.sortAsc;
      const descSort = header.dataset.sortDesc;

      header.classList.remove('sorted-asc', 'sorted-desc');
      header.setAttribute('aria-sort', 'none');

      if (currentSortOrder === ascSort) {
        header.classList.add('sorted-asc');
        header.setAttribute('aria-sort', 'ascending');
      } else if (currentSortOrder === descSort) {
        header.classList.add('sorted-desc');
        header.setAttribute('aria-sort', 'descending');
      }
    });
  }

  _setupSummaryCardNavigation() {
    const cardToSectionMap = {
      stocks_summary: 'stocks-section',
      etf_summary: 'etf-section',
      mf_summary: 'mf-section',
      fd_summary: 'fixed-deposits-section'
    };

    Object.entries(cardToSectionMap).forEach(([cardId, sectionId]) => {
      const card = document.getElementById(cardId);
      const section = document.getElementById(sectionId);

      if (!card || !section) return;

      card.classList.add('card--clickable');
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');

      const scrollToSection = () => {
        const header = document.querySelector('header');
        const headerHeight = header ? header.getBoundingClientRect().height : 0;
        const extraSpacing = 12;
        const targetTop = section.getBoundingClientRect().top + window.scrollY - headerHeight - extraSpacing;
        window.scrollTo({ top: Math.max(targetTop, 0), behavior: 'smooth' });
      };

      card.addEventListener('click', scrollToSection);
      card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          scrollToSection();
        }
      });
    });
  }

  connectEventSource() {
    this.sseManager.onMessage((status) => this.handleStatusUpdate(status));
    this.sseManager.connect();
  }

  handleStatusUpdate(status) {
    const statusTag = document.getElementById('status_tag');
    const statusText = document.getElementById('status_text');
    const isUpdating = this._isStatusUpdating(status);
    const isFirstSSE = this._wasUpdating === undefined;

    // Detect if the backend has newer data than what we last fetched.
    // This catches cases where the updating→updated SSE transition was
    // missed (connection hiccup, exception during rendering, SSE
    // reconnect after background auto-refresh, etc.).
    const newPortfolioTimestamp = status.portfolio_last_updated || null;
    const hasNewerData = !isUpdating && !isFirstSSE &&
                         newPortfolioTimestamp !== null &&
                         newPortfolioTimestamp !== this._lastFetchedPortfolioTimestamp;

    this.lastStatus = status;

    // ── Derive login state from new response fields ──
    const unauthenticated = status.unauthenticated_accounts || [];
    const hasAuthenticatedAccounts = (status.authenticated_accounts || []).length > 0;
    const hasUnauthenticated = unauthenticated.length > 0;

    // ── Status tag: always visible, reflects data-fetch state ──
    statusTag.classList.toggle('updating', isUpdating);
    statusTag.classList.toggle('updated', !isUpdating);
    statusTag.classList.toggle('market_closed', status.market_open === false);

    if (isUpdating) {
      statusText.innerText = 'updating';
    } else {
      this.lastPortfolioUpdatedAt = status.portfolio_last_updated || null;
      statusText.innerText = this._formatStatusUpdatedText();
    }

    // ── Login banner (floating toast for unauthenticated accounts) ──
    this._updateLoginBanner(unauthenticated, isUpdating);

    // ── Refresh settings drawer pills if drawer is open ──
    if (typeof window.loadDrawerAccounts === 'function') {
      const drawer = document.getElementById('settingsDrawer');
      if (drawer && drawer.classList.contains('open')) {
        window.loadDrawerAccounts();
      }
    }

    // ── Auto-refresh on first load ──
    // Trigger when: first SSE, server hasn't fetched yet, and at least
    // one Zerodha account is authenticated (or user has no accounts at all
    // and just needs a gold/nifty refresh with no cached data).
    if (isFirstSSE && !isUpdating && status.portfolio_state === null) {
      if (hasAuthenticatedAccounts || (!status.has_zerodha_accounts && !this._hasInitialData)) {
        this.handleRefresh();
        // Don't overwrite _wasUpdating here — handleRefresh() already
        // sets it to true synchronously before await.  Overwriting with
        // false causes a race where a fast updating→idle transition is
        // missed and data never loads.
        // Still fetch sheet-only data (gold, FD) that isn't part of the
        // broker refresh so they render on first load.
        this.updateData();
        this._wasUpdating = true;
        return;
      }
    }

    // ── Fetch data on real state transitions ──
    // 1. First SSE after page load (always – gold/FD are not inlined)
    // 2. Transition from updating → done (refresh complete)
    // 3. Backend has newer data than what we last fetched (safety net
    //    for missed transitions, SSE reconnects, etc.)
    const shouldFetchData = isFirstSSE ||
                           (!isUpdating && this._wasUpdating) ||
                           hasNewerData;

    if (shouldFetchData) {
      const isRealRefresh = !isFirstSSE && !isUpdating && this._wasUpdating;
      if (isRealRefresh || hasNewerData) {
        // Keep refresh button and status tag in "updating" state until data is loaded
        statusTag.classList.add('updating');
        statusTag.classList.remove('updated');
        statusText.innerText = 'updating';
      }
      // Track what we're fetching so duplicate SSE messages with the
      // same timestamp don't trigger redundant fetches.
      this._lastFetchedPortfolioTimestamp = newPortfolioTimestamp;
      this.updateData().then(() => {
        this._updateRefreshButton(false);
        // Restore final status tag state after data is rendered
        statusTag.classList.remove('updating');
        statusTag.classList.add('updated');
        this.lastPortfolioUpdatedAt = status.portfolio_last_updated || null;
        statusText.innerText = this._formatStatusUpdatedText();
      });
    } else {
      // No data fetch needed — update refresh button immediately
      this._updateRefreshButton(isUpdating);
      const hasData = this.dataManager.getStocks().length > 0 ||
                      this.dataManager.getMFHoldings().length > 0 ||
                      this.dataManager.getSIPs().length > 0;
      this._renderTablesAndSummary(hasData, status, isUpdating);
    }

    this._wasUpdating = isUpdating;
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

    const Z = { invested: 0, current: 0, pl: 0, plPct: 0 };

    let stockTotals = Z, etfTotals = Z, mfTotals = Z;
    let goldTotals = Z, goldETFTotals = Z, sgbTotals = Z;
    let silverTotals = Z, silverETFTotals = Z;

    if (hasData) {
      const sortedHoldings = this.sortManager.sortStocks(this.dataManager.getStocks(), this.sortManager.getStocksSortOrder());
      const sortedETF = this.sortManager.sortETFs(this.dataManager.getStocks(), this.sortManager.getETFSortOrder());
      const sortedMF = this.sortManager.sortMF(this.dataManager.getMFHoldings(), this.sortManager.getMFSortOrder());

      ({ stockTotals, goldTotals, sgbTotals, silverTotals } = this.tableRenderer.renderStocksTable(sortedHoldings, status));
      ({ etfTotals, goldETFTotals, silverETFTotals } = this.tableRenderer.renderETFTable(sortedETF, status));
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
      physicalGoldTotals
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
    const sortedHoldings = this.sortManager.sortStocks(
      this.dataManager.getStocks(),
      this.sortManager.getStocksSortOrder()
    );
    const sortedETFHoldings = this.sortManager.sortETFs(
      this.dataManager.getStocks(),
      this.sortManager.getETFSortOrder()
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
    const { etfTotals, goldETFTotals, silverETFTotals } = this.tableRenderer.renderETFTable(sortedETFHoldings, status);
    const mfTotals = this.tableRenderer.renderMFTable(sortedMFHoldings, status);
    if (renderSIPs) {
      this.tableRenderer.renderSIPsTable(this.dataManager.getSIPs(), status);
    }
    const physicalGoldTotals = this.tableRenderer.renderPhysicalGoldTable(sortedPhysicalGold);
    const fdTotals = this.tableRenderer.renderFixedDepositsTable(sortedFixedDeposits);

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
      physicalGoldTotals
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
  _applyData({ stocks, mfHoldings, sips, physicalGold, fixedDeposits, fdSummary, status }) {
    const searchEl = document.getElementById('search');
    const searchQuery = searchEl ? searchEl.value : '';
    const forceUpdate = searchQuery !== '';

    this.dataManager.updateStocks(stocks || [], forceUpdate);
    this.dataManager.updateMFHoldings(mfHoldings || [], forceUpdate);
    this.dataManager.updateSIPs(sips || [], forceUpdate);
    this.dataManager.updatePhysicalGold(physicalGold || [], forceUpdate);
    this.dataManager.updateFixedDeposits(fixedDeposits || [], forceUpdate);
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

  async updateData() {
    try {
      const data = await this.dataManager.fetchAllData();
      this._hideLoadingIndicators();
      this._applyData(data);

      // Sync timestamp tracking from the response so every /api/all_data
      // call properly updates portfolio_last_updated — not just SSE events.
      // This is critical for the first load where the early-return path
      // calls updateData() fire-and-forget without timestamp tracking.
      const respTimestamp = data.status?.portfolio_last_updated || null;
      if (respTimestamp) {
        this._lastFetchedPortfolioTimestamp = respTimestamp;
        this.lastPortfolioUpdatedAt = respTimestamp;
        const statusText = document.getElementById('status_text');
        if (statusText && !this._isStatusUpdating(this.lastStatus || {})) {
          statusText.innerText = this._formatStatusUpdatedText();
        }
      }
    } catch (error) {
      console.error('Error updating data:', error);
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

  handleFDSummarySort(sortBy) {
    this.sortManager.setFDSummarySortOrder(sortBy);
    const fixedDeposits = this.dataManager.getFixedDeposits();
    const tbody = document.getElementById('fd_summary_table_body');
    if (!tbody) return;

    // Get current summary data from table
    const groupedData = this.tableRenderer._groupFDByBankAndAccount(fixedDeposits);
    const summaryArray = Object.values(groupedData);
    
    // Sort and re-render
    const sortedSummary = this.sortManager.sortFDSummary(summaryArray, sortBy);
    
    // Update pagination and re-render
    this.tableRenderer.fdSummaryPagination.goToPage(1);
    const paginationData = this.tableRenderer.fdSummaryPagination.paginate(sortedSummary);
    
    let rowsHTML = '';
    paginationData.pageData.forEach((summary) => {
      rowsHTML += this.tableRenderer._buildFDSummaryRow(summary);
    });
    this.tableRenderer._updateTbodyContent(tbody, rowsHTML);

    PaginationManager.updatePaginationUI(
      paginationData,
      'fd_summary_pagination_info',
      'fd_summary_pagination_buttons',
      'goToFDSummaryPage',
      'summaries'
    );
  }

  async handleRefresh() {
    const statusTag = document.getElementById('status_tag');
    const statusText = document.getElementById('status_text');
    
    statusTag.className = 'updating';
    statusText.innerText = 'updating';
    this._updateRefreshButton(true);
    // Ensure the next SSE transition triggers a data fetch
    this._wasUpdating = true;

    try {
      await this.dataManager.triggerRefresh();
    } catch (error) {
      // A 409 "Fetch already in progress" is expected when
      // ensure_user_loaded already started a background fetch.
      // Don't use alert() — it blocks the JS thread and freezes
      // SSE event processing, preventing state transitions.
      console.warn('[Refresh] Request failed:', error.message);
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

  disconnect() {
    if (this.relativeStatusTimer) {
      clearInterval(this.relativeStatusTimer);
      this.relativeStatusTimer = null;
    }
    this.sseManager.disconnect();
  }
}

// Global function to toggle group expansion
window.toggleGroupExpand = function(event, groupId) {
  event.stopPropagation();
  const toggleBtn = event.target;
  const breakdownRows = document.querySelectorAll(`.breakdown-row.${groupId}`);
  const isExpanded = toggleBtn.classList.contains('expanded');
  
  // Access the global app instance to track expanded state
  if (window.portfolioApp && window.portfolioApp.tableRenderer) {
    if (isExpanded) {
      breakdownRows.forEach(row => {
        row.style.display = 'none';
      });
      toggleBtn.classList.remove('expanded');
      toggleBtn.textContent = '▶';
      window.portfolioApp.tableRenderer.markGroupCollapsed(groupId);
    } else {
      breakdownRows.forEach(row => {
        row.style.display = 'table-row';
      });
      toggleBtn.classList.add('expanded');
      toggleBtn.textContent = '▼';
      window.portfolioApp.tableRenderer.markGroupExpanded(groupId);
    }
  }
};

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
