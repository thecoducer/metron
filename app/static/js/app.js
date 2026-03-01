/* Portfolio Tracker - Main Application Controller */

import DataManager from './data-manager.js';
import TableRenderer from './table-renderer.js';
import SummaryManager from './summary-manager.js';
import SortManager from './sort-manager.js';
import ThemeManager from './theme-manager.js';
import PrivacyManager from './visibility-manager.js';
import SSEConnectionManager from './sse-manager.js';
import PaginationManager from './pagination.js';
import { Formatter, Calculator } from './utils.js';
import IndexTicker from './index-ticker.js';

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
    this.needsLogin = false;
    this.lastStatus = null;
    this.lastPortfolioUpdatedAt = null;
    this.relativeStatusTimer = null;
    this.searchTimeout = null;
    // _wasUpdating and _wasWaitingForLogin intentionally left undefined
    // to detect first status update on page load
  }

  async init() {
    Formatter.initCompactFormat();
    this._updateCompactFormatIcon();
    this.themeManager.init();
    this.privacyManager.init();
    this._setupEventListeners();
    
    this._hideLoadingIndicators();
    this._renderEmptyStates();
    
    // Connect SSE without fetching initial data
    // Data will be fetched only on manual refresh or when auto-refresh completes
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
    const waitingForLogin = this.lastStatus.waiting_for_login === true;
    if (isUpdating || waitingForLogin || this.lastStatus.portfolio_state === null) return;
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
    if (icon) {
      icon.textContent = Formatter.isCompactFormat ? '🔤' : '🔢';
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
    // gold breakdown toggle (icon button)
    const goldToggle = document.getElementById('gold_breakdown_toggle');
    if (goldToggle) {
      goldToggle.addEventListener('click', () => {
        const newMode = !this.summaryManager.showGoldBreakdown;
        this.summaryManager.setGoldBreakdownMode(newMode);
        goldToggle.classList.toggle('active', newMode);
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
    const waitingForLogin = status.waiting_for_login === true;

    this.lastStatus = status;

    const physicalGoldWasUpdating = this._physicalGoldWasUpdating || false;
    const physicalGoldIsUpdating = status.physical_gold_state === 'updating';
    const physicalGoldJustCompleted = physicalGoldWasUpdating && !physicalGoldIsUpdating && status.physical_gold_state === 'updated';
    this._physicalGoldWasUpdating = physicalGoldIsUpdating;

    const fixedDepositsWasUpdating = this._fixedDepositsWasUpdating || false;
    const fixedDepositsIsUpdating = status.fixed_deposits_state === 'updating';
    const fixedDepositsJustCompleted = fixedDepositsWasUpdating && !fixedDepositsIsUpdating && status.fixed_deposits_state === 'updated';
    this._fixedDepositsWasUpdating = fixedDepositsIsUpdating;

    const portfolioWasUpdating = this._portfolioWasUpdating || false;
    const portfolioIsUpdating = status.portfolio_state === 'updating';
    const portfolioJustCompleted = portfolioWasUpdating && !portfolioIsUpdating && (status.portfolio_state === 'updated' || status.portfolio_state === 'error');
    this._portfolioWasUpdating = portfolioIsUpdating;

    const sessionValidity = status.session_validity || {};
    const anyAccountInvalid = Object.keys(sessionValidity).length > 0 && 
                              Object.values(sessionValidity).some(valid => !valid);
    this.needsLogin = anyAccountInvalid && !isUpdating && !waitingForLogin;

    const isNotLoaded = status.portfolio_state === null;
    statusTag.classList.toggle('updating', isUpdating || waitingForLogin);
    statusTag.classList.toggle('updated', !isUpdating && !waitingForLogin && !isNotLoaded);
    statusTag.classList.toggle('not-loaded', isNotLoaded);
    statusTag.classList.toggle('market_closed', status.market_open === false);
    statusTag.classList.toggle('needs-login', this.needsLogin);

    if (waitingForLogin) {
      statusText.innerText = 'waiting for login';
    } else if (isUpdating) {
      statusText.innerText = 'updating';
    } else if (status.portfolio_state === null) {
      statusText.innerText = '';
    } else {
      this.lastPortfolioUpdatedAt = status.portfolio_last_updated || null;
      statusText.innerText = this._formatStatusUpdatedText();
    }

    this._updateRefreshButton(isUpdating || waitingForLogin, this.needsLogin);

    // Fetch data when:
    // 1. First SSE status after page load (server cache may have partial data)
    // 2. State changed from 'updating' to 'updated' (normal refresh complete)
    // 3. Login just completed (was waiting, now not waiting)
    // 4. Individual data source just completed fetching (partial update)
    const shouldFetchData = this._wasUpdating === undefined ||
                           (!isUpdating && this._wasUpdating) ||
                           (this._wasWaitingForLogin && !waitingForLogin && !isUpdating) ||
                           portfolioJustCompleted ||
                           physicalGoldJustCompleted ||
                           fixedDepositsJustCompleted;

    if (shouldFetchData) {
      // Let updateData() fetch fresh data and handle full rendering
      // (including overview cards) — avoids overwriting with stale in-memory data
      this.updateData();
    } else {
      // No new data to fetch — re-render tables and overview cards
      // with current in-memory data (e.g. to toggle updating CSS classes)
      const hasData = this.dataManager.getStocks().length > 0 ||
                      this.dataManager.getMFHoldings().length > 0 ||
                      this.dataManager.getSIPs().length > 0;

      this._renderTablesAndSummary(hasData, status, isUpdating || waitingForLogin);
    }

    this._wasUpdating = isUpdating;
    this._wasWaitingForLogin = waitingForLogin;
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

    const zeroTotals = { invested: 0, current: 0, pl: 0, plPct: 0 };

    if (hasData) {
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

      const { stockTotals, goldTotals, silverTotals } = this.tableRenderer.renderStocksTable(sortedHoldings, status);
      const { etfTotals, goldETFTotals, silverETFTotals } = this.tableRenderer.renderETFTable(sortedETFHoldings, status);
      const mfTotals = this.tableRenderer.renderMFTable(sortedMFHoldings, status);
      this.tableRenderer.renderSIPsTable(this.dataManager.getSIPs(), status);
      
      const combinedGoldTotals = this._combineTotals(goldTotals, goldETFTotals, physicalGoldTotals);
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
        physicalGoldTotals
      );
    } else {
      const combinedGoldTotals = this._combineTotals(
        zeroTotals,
        zeroTotals,
        physicalGoldTotals
      );
      this.summaryManager.updateAllSummaries(
        zeroTotals,
        zeroTotals,
        combinedGoldTotals,
        zeroTotals,
        zeroTotals,
        fdTotals,
        isUpdating,
        { invested:0, current:0, pl:0, plPct:0 },
        physicalGoldTotals
      );
    }
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

    const { stockTotals, goldTotals, silverTotals } = this.tableRenderer.renderStocksTable(sortedHoldings, status);
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

    const combinedGoldTotals = this._combineTotals(goldTotals, goldETFTotals, physicalGoldTotals);
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
      physicalGoldTotals
    );
  }

  handleSearch() {
    const searchEl = document.getElementById('search');
    const searchQuery = searchEl ? searchEl.value : '';
    this.tableRenderer.setSearchQuery(searchQuery);
    this._renderAllAndUpdateSummaries(this.lastStatus || {}, { renderSIPs: true });
  }

  async updateData() {
    try {
      const { stocks, mfHoldings, sips, physicalGold, fixedDeposits, fdSummary, status } = await this.dataManager.fetchAllData();

      this._hideLoadingIndicators();

      const searchEl = document.getElementById('search');
      const searchQuery = searchEl ? searchEl.value : '';
      const forceUpdate = searchQuery !== '';
      
      this.dataManager.updateStocks(stocks, forceUpdate);
      this.dataManager.updateMFHoldings(mfHoldings, forceUpdate);
      this.dataManager.updateSIPs(sips, forceUpdate);
      this.dataManager.updatePhysicalGold(physicalGold, forceUpdate);
      this.dataManager.updateFixedDeposits(fixedDeposits, forceUpdate);
      this.dataManager.updateFDSummary(fdSummary, forceUpdate);

      this.tableRenderer.setSearchQuery(searchQuery);

      this._renderAllAndUpdateSummaries(status, {
        renderSIPs: true,
        isUpdating: this._isStatusUpdating(status),
        fdSummaryData: this.dataManager.getFDSummary()
      });
    } catch (error) {
      console.error('Error updating data:', error);
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
    tbody.innerHTML = rowsHTML;

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

    try {
      await this.dataManager.triggerRefresh();
    } catch (error) {
      alert('Error triggering refresh: ' + error.message);
    }
  }

  _updateRefreshButton(isUpdating, needsLogin = false) {
    const btnText = document.getElementById('refresh_btn_text');
    if (isUpdating) {
      btnText.innerHTML = '<span class="spinner"></span>';
    } else {
      btnText.textContent = needsLogin ? 'Login' : 'Refresh';
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
