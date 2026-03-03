/* Metron - Table Rendering Module */

import { Formatter, Calculator, isGoldInstrument, isSGBInstrument, isSilverInstrument, isETFInstrument } from './utils.js';
import PaginationManager from './pagination.js';

class TableRenderer {
  constructor() {
    this.searchQuery = '';
    this.stocksPagination = new PaginationManager(10, 1);
    this.etfPagination = new PaginationManager(10, 1);
    this.mfPagination = new PaginationManager(10, 1);
    this.physicalGoldPagination = new PaginationManager(10, 1);
    this.fixedDepositsPagination = new PaginationManager(10, 1);
    this.fdSummaryPagination = new PaginationManager(10, 1);
    this.expandedGroups = new Set(); // Track which groups are expanded
  }

  setSearchQuery(query) {
    this.searchQuery = query.toLowerCase();
  }

  _getUpdateClass(isUpdating) {
    return isUpdating ? 'updating-field' : '';
  }

  /**
   * Toggle visibility of a table section based on whether it has data.
   * @param {Object} opts - Elements to toggle
   * @param {HTMLElement} opts.table - Table element
   * @param {HTMLElement} opts.emptyState - Empty state message element
   * @param {HTMLElement} [opts.controls] - Controls container element
   * @param {HTMLElement} [opts.paginationInfo] - Pagination info element
   * @param {HTMLElement} [opts.paginationButtons] - Pagination buttons element
   * @param {boolean} hasData - Whether the section has data to display
   */
  _toggleSectionVisibility({ table, emptyState, controls, paginationInfo, paginationButtons, tabs }, hasData) {
    if (hasData) {
      if (table) table.style.display = 'table';
      if (emptyState) emptyState.style.display = 'none';
      if (controls) controls.style.display = 'flex';
      if (paginationInfo) paginationInfo.style.display = 'block';
      if (paginationButtons) paginationButtons.style.display = 'flex';
      if (tabs) tabs.style.display = 'flex';
    } else {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      if (controls) controls.style.display = 'none';
      if (paginationInfo) paginationInfo.style.display = 'none';
      if (paginationButtons) paginationButtons.style.display = 'none';
      if (tabs) tabs.style.display = 'none';
    }
  }

  /**
   * Build a styled table cell with optional class.
   * @param {string} content - Cell content
   * @param {string} cssClass - Optional CSS class
   * @returns {string} HTML string for table cell
   */
  _buildCell(content, cssClass = '') {
    const classAttr = cssClass ? ` class="${cssClass}"` : '';
    return `<td${classAttr}>${content}</td>`;
  }

  /**
   * Build a styled P/L cell with color.
   * @param {number} value - P/L value
   * @param {string} cssClass - Optional CSS class
   * @returns {string} HTML string for P/L cell
   */
  _buildPLCell(value, cssClass = '') {
    const formatted = Formatter.formatCurrency(value);
    const color = Formatter.colorPL(value);
    return `<td><span class="${cssClass}" style="color:${color};font-weight:600">${formatted}</span></td>`;
  }

  /**
   * Build a cell with value and percentage with color coding.
   * @param {number|string} value - Main value (numeric or formatted string)
   * @param {number} percentage - Percentage to display
   * @param {string} cssClass - Optional CSS class
   * @returns {string} HTML string
   */
  _buildValueWithPctCell(value, percentage, cssClass = '') {
    const formatted = (typeof value === 'number') ? Formatter.formatNumberWithLocale(value, 1) : value;
    const color = Formatter.colorPL(percentage);
    const pctText = Formatter.formatPercentage(percentage);
    return `<td class="${cssClass}">${formatted} <span class="pl_pct_small" style="color:${color}">${pctText}</span></td>`;
  }

  /**
   * Build a cell with change percentage only.
   * @param {number} changeValue - Change value (used for color determination)
   * @param {number} changePercent - Change percentage
   * @param {string} cssClass - Optional CSS class
   * @returns {string} HTML string
   */
  _buildChangeCell(changeValue, changePercent, cssClass = '') {
    const color = Formatter.colorPL(changeValue);
    const formattedPct = Formatter.formatPercentage(changePercent);
    return `<td class="${cssClass}"><span style="color:${color};font-weight:600">${formattedPct}</span></td>`;
  }

  renderStocksTable(holdings, status) {
    const tbody = document.getElementById('tbody');
    const section = document.getElementById('stocks-section');
    const isUpdating = status.portfolio_state === 'updating';

    let totalInvested = 0;
    let totalCurrent = 0;
    let goldInvested = 0;
    let goldCurrent = 0;
    let sgbInvested = 0;
    let sgbCurrent = 0;
    let silverInvested = 0;
    let silverCurrent = 0;
    let filteredHoldings = [];

    // Filter and calculate totals (Gold and Silver shown in table but not in Stocks summary)
    // ETFs are excluded entirely from this table
    holdings.forEach(holding => {
      const symbol = holding.tradingsymbol || '';
      const isin = holding.isin || '';
      const text = (symbol + holding.account).toLowerCase();
      const isGold = isGoldInstrument(symbol);
      const isSGB = isSGBInstrument(symbol);
      const isSilver = isSilverInstrument(symbol);
      const isETF = isETFInstrument(symbol, isin);
      
      // Skip ETFs - they go to the ETF table
      if (isETF) return;
      
      if (text.includes(this.searchQuery)) {
        filteredHoldings.push(holding);  // Add non-ETF holdings to display
        const metrics = Calculator.calculateStockMetrics(holding);
        
        if (isSGB) {
          // SGBs tracked separately within gold
          sgbInvested += metrics.invested;
          sgbCurrent += metrics.current;
        } else if (isGold) {
          // Non-SGB gold stocks (e.g. gold futures)
          goldInvested += metrics.invested;
          goldCurrent += metrics.current;
        } else if (isSilver) {
          // Accumulate Silver totals separately (not in Stocks summary)
          silverInvested += metrics.invested;
          silverCurrent += metrics.current;
        } else {
          // Only non-Gold/Silver holdings count toward Stocks summary
          totalInvested += metrics.invested;
          totalCurrent += metrics.current;
        }
      }
    });

    // Group holdings by symbol
    const groupedHoldings = this._groupStocksBySymbol(filteredHoldings);
    const groupedArray = Object.values(groupedHoldings);

    // Use pagination manager on grouped holdings
    const paginationData = this.stocksPagination.paginate(groupedArray);
    const { pageData } = paginationData;

    let rowsHTML = '';
    pageData.forEach((group, index) => {
      const groupId = `stock-group-${index}`;
      const metrics = this._calculateAggregatedStockMetrics(group.holdings);
      rowsHTML += this._buildStockRow(group.holdings[0], metrics, {
        symbolClass: this._getUpdateClass(isUpdating),
        qtyClass: this._getUpdateClass(isUpdating),
        avgClass: this._getUpdateClass(isUpdating),
        investedClass: this._getUpdateClass(isUpdating),
        ltpClass: this._getUpdateClass(isUpdating),
        plClass: this._getUpdateClass(isUpdating),
        dayChangeClass: this._getUpdateClass(isUpdating),
        currentClass: this._getUpdateClass(isUpdating),
        exchangeClass: this._getUpdateClass(isUpdating),
        accountClass: this._getUpdateClass(isUpdating),
        groupId: groupId,
        hasMultipleAccounts: group.holdings.length > 1,
        isGroupRow: true
      });

      // Add breakdown rows if multiple accounts
      if (group.holdings.length > 1) {
        group.holdings.forEach(holding => {
          const holdingMetrics = Calculator.calculateStockMetrics(holding);
          rowsHTML += this._buildStockBreakdownRow(holding, holdingMetrics, groupId);
        });
      }
    });
    tbody.innerHTML = rowsHTML;

    // Show/hide table and empty state
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: document.getElementById('stocks_empty_state'),
      controls: section.querySelector('.controls-container'),
      paginationInfo: document.getElementById('stocks_pagination_info'),
      paginationButtons: document.getElementById('stocks_pagination_buttons')
    }, filteredHoldings.length > 0);
    
    // Update pagination UI
    PaginationManager.updatePaginationUI(
      paginationData,
      'stocks_pagination_info',
      'stocks_pagination_buttons',
      'goToStocksPage',
      'stocks'
    );

    // Restore expanded state for groups that were previously expanded
    this._restoreExpandedState();

    // Return separate totals for stocks, gold, and silver
    const stockTotals = {
      invested: totalInvested,
      current: totalCurrent,
      pl: totalCurrent - totalInvested,
      plPct: totalInvested ? ((totalCurrent - totalInvested) / totalInvested * 100) : 0
    };
    
    const goldTotals = {
      invested: goldInvested,
      current: goldCurrent,
      pl: goldCurrent - goldInvested,
      plPct: goldInvested ? ((goldCurrent - goldInvested) / goldInvested * 100) : 0
    };

    const sgbTotals = {
      invested: sgbInvested,
      current: sgbCurrent,
      pl: sgbCurrent - sgbInvested,
      plPct: sgbInvested ? ((sgbCurrent - sgbInvested) / sgbInvested * 100) : 0
    };
    
    const silverTotals = {
      invested: silverInvested,
      current: silverCurrent,
      pl: silverCurrent - silverInvested,
      plPct: silverInvested ? ((silverCurrent - silverInvested) / silverInvested * 100) : 0
    };

    return { stockTotals, goldTotals, sgbTotals, silverTotals };
  }

  renderMFTable(mfHoldings, status) {
    const tbody = document.getElementById('mf_tbody');
    const section = document.getElementById('mf-section');
    const isUpdating = status.portfolio_state === 'updating';

    tbody.innerHTML = '';
    let mfTotalInvested = 0;
    let mfTotalCurrent = 0;
    let filteredHoldings = [];

    mfHoldings.forEach(mf => {
      const fundName = mf.fund || mf.tradingsymbol;
      const text = (fundName + mf.account).toLowerCase();
      if (!text.includes(this.searchQuery)) return;

      filteredHoldings.push(mf);
      const metrics = Calculator.calculateMFMetrics(mf);
      mfTotalInvested += metrics.invested;
      mfTotalCurrent += metrics.current;
    });

    // Group mutual funds by fund name
    const groupedMF = this._groupMFByFundName(filteredHoldings);
    const groupedArray = Object.values(groupedMF);

    // Use pagination manager on grouped holdings
    const paginationData = this.mfPagination.paginate(groupedArray);
    const { pageData } = paginationData;

    let rowsHTML = '';
    pageData.forEach((group, index) => {
      const groupId = `mf-group-${index}`;
      const fundName = group.holdings[0].fund || group.holdings[0].tradingsymbol;
      const metrics = this._calculateAggregatedMFMetrics(group.holdings);
      rowsHTML += this._buildMFRow(fundName, group.holdings[0], metrics, {
        fundClass: this._getUpdateClass(isUpdating),
        qtyClass: this._getUpdateClass(isUpdating),
        avgClass: this._getUpdateClass(isUpdating),
        investedClass: this._getUpdateClass(isUpdating),
        navClass: this._getUpdateClass(isUpdating),
        currentClass: this._getUpdateClass(isUpdating),
        plClass: this._getUpdateClass(isUpdating),
        accountClass: this._getUpdateClass(isUpdating),
        groupId: groupId,
        hasMultipleAccounts: group.holdings.length > 1,
        isGroupRow: true
      });

      // Add breakdown rows if multiple accounts
      if (group.holdings.length > 1) {
        group.holdings.forEach(mf => {
          const fundName = mf.fund || mf.tradingsymbol;
          const holdingMetrics = Calculator.calculateMFMetrics(mf);
          rowsHTML += this._buildMFBreakdownRow(fundName, mf, holdingMetrics, groupId);
        });
      }
    });
    tbody.innerHTML = rowsHTML;

    // Show/hide table and empty state
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: document.getElementById('mf_empty_state'),
      controls: section.querySelector('.controls-container'),
      paginationInfo: document.getElementById('mf_pagination_info'),
      paginationButtons: document.getElementById('mf_pagination_buttons')
    }, filteredHoldings.length > 0);

    // Update pagination UI
    PaginationManager.updatePaginationUI(
      paginationData,
      'mf_pagination_info',
      'mf_pagination_buttons',
      'goToMFPage',
      'funds'
    );

    // Restore expanded state for groups that were previously expanded
    this._restoreExpandedState();

    return {
      invested: mfTotalInvested,
      current: mfTotalCurrent,
      pl: mfTotalCurrent - mfTotalInvested,
      plPct: mfTotalInvested ? ((mfTotalCurrent - mfTotalInvested) / mfTotalInvested * 100) : 0
    };
  }

  renderSIPsTable(sips, status) {
    const tbody = document.getElementById('sips_tbody');
    const section = document.getElementById('sips-section');
    const isUpdating = status.portfolio_state === 'updating';
    const dataClass = this._getUpdateClass(isUpdating);

    let rowsHTML = '';
    let totalMonthlyAmount = 0;
    let visibleCount = 0;

    sips.forEach(sip => {
      const fundName = (sip.fund || sip.tradingsymbol).toUpperCase();
      const text = (fundName + sip.account).toLowerCase();
      if (!text.includes(this.searchQuery)) return;

      visibleCount++;
      rowsHTML += this._buildSIPRow(fundName, sip, dataClass);
      
      // Calculate total monthly amount for SIPs
      if (sip.status === 'ACTIVE' && sip.instalment_amount) {
        const frequency = sip.frequency || 'monthly';
        const amount = sip.instalment_amount;
        
        // Convert to monthly equivalent
        if (frequency.toLowerCase() === 'monthly') {
          totalMonthlyAmount += amount;
        } else if (frequency.toLowerCase() === 'weekly') {
          totalMonthlyAmount += amount * 4.33; // Average weeks per month
        } else if (frequency.toLowerCase() === 'quarterly') {
          totalMonthlyAmount += amount / 3;
        }
      }
    });

    rowsHTML += this._buildSIPTotalRow(totalMonthlyAmount, dataClass);
    tbody.innerHTML = rowsHTML;
    
    // Show/hide table and empty state
    const table = section.querySelector('table');
    const emptyState = document.getElementById('sips_empty_state');
    
    if (visibleCount === 0) {
      table.style.display = 'none';
      emptyState.style.display = 'block';
    } else {
      table.style.display = 'table';
      emptyState.style.display = 'none';
    }
  }

  _buildSIPTotalRow(totalAmount, dataClass) {
    const formattedAmount = Formatter.formatCurrency(totalAmount);

    return `<tr style="border-top: 2px solid #e9e9e7; font-weight: 600;">
<td class="${dataClass}">Total Monthly SIP Amount:</td>
<td class="${dataClass}">${formattedAmount}</td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>`;
  }

  /**
   * Group stocks by symbol
   */
  _groupStocksBySymbol(holdings) {
    const groups = {};
    holdings.forEach(holding => {
      const symbol = holding.tradingsymbol || '';
      if (!groups[symbol]) {
        groups[symbol] = { holdings: [] };
      }
      groups[symbol].holdings.push(holding);
    });
    return groups;
  }

  /**
   * Group mutual funds by fund name
   */
  _groupMFByFundName(holdings) {
    const groups = {};
    holdings.forEach(mf => {
      const fundName = mf.fund || mf.tradingsymbol;
      if (!groups[fundName]) {
        groups[fundName] = { holdings: [] };
      }
      groups[fundName].holdings.push(mf);
    });
    return groups;
  }

  /**
   * Track that a group is expanded
   */
  markGroupExpanded(groupId) {
    this.expandedGroups.add(groupId);
  }

  /**
   * Track that a group is collapsed
   */
  markGroupCollapsed(groupId) {
    this.expandedGroups.delete(groupId);
  }

  /**
   * Restore previously expanded groups
   */
  _restoreExpandedState() {
    this.expandedGroups.forEach(groupId => {
      const breakdownRows = document.querySelectorAll(`.breakdown-row.${groupId}`);
      const toggleBtn = document.querySelector(`.expand-toggle[data-group-id="${groupId}"]`);
      
      if (breakdownRows.length > 0) {
        breakdownRows.forEach(row => {
          row.style.display = 'table-row';
        });
        if (toggleBtn) {
          toggleBtn.classList.add('expanded');
          toggleBtn.textContent = '▼';
        }
      }
    });
  }

  /**
   * Calculate aggregated metrics for a group of stocks
   */
  _calculateAggregatedStockMetrics(holdings) {
    let totalQty = 0;
    let totalInvested = 0;
    let totalCurrent = 0;
    let weightedAvg = 0;
    let totalDayChange = 0;
    let ltpValue = 0;
    let dayChangePct = 0;

    holdings.forEach((holding, index) => {
      const metrics = Calculator.calculateStockMetrics(holding);
      totalQty += metrics.qty;
      totalInvested += metrics.invested;
      totalCurrent += metrics.current;
      weightedAvg += metrics.avg * metrics.qty;
      totalDayChange += metrics.dayChange;
      
      // Use LTP and day change percentage from first holding (should be same for all accounts)
      if (index === 0) {
        ltpValue = metrics.ltp;
        dayChangePct = metrics.dayChangePct;
      }
    });

    const avgPrice = totalQty > 0 ? weightedAvg / totalQty : 0;
    const pl = totalCurrent - totalInvested;
    const plPct = totalInvested > 0 ? ((pl / totalInvested) * 100) : 0;

    return {
      qty: totalQty,
      avg: avgPrice,
      invested: totalInvested,
      ltp: ltpValue,
      dayChange: totalDayChange,
      pl: pl,
      current: totalCurrent,
      plPct: plPct,
      dayChangePct: dayChangePct
    };
  }

  /**
   * Calculate aggregated metrics for a group of mutual funds
   */
  _calculateAggregatedMFMetrics(holdings) {
    let totalQty = 0;
    let totalInvested = 0;
    let totalCurrent = 0;
    let weightedAvg = 0;
    let navValue = 0;

    holdings.forEach((mf, index) => {
      const metrics = Calculator.calculateMFMetrics(mf);
      totalQty += metrics.qty;
      totalInvested += metrics.invested;
      totalCurrent += metrics.current;
      weightedAvg += metrics.avg * metrics.qty;
      
      // Use NAV from first holding (should be same for all accounts)
      if (index === 0) {
        navValue = metrics.nav;
      }
    });

    const avgPrice = totalQty > 0 ? weightedAvg / totalQty : 0;
    const pl = totalCurrent - totalInvested;
    const plPct = totalInvested > 0 ? ((pl / totalInvested) * 100) : 0;

    return {
      qty: totalQty,
      avg: avgPrice,
      invested: totalInvested,
      nav: navValue,
      current: totalCurrent,
      pl: pl,
      plPct: plPct
    };
  }

  _buildStockRow(holding, metrics, classes) {
    const { qty, avg, invested, ltp, dayChange, pl, current, plPct, dayChangePct } = metrics;
    const expandBtn = classes.hasMultipleAccounts ? 
      `<span class="expand-toggle" data-group-id="${classes.groupId}" onclick="toggleGroupExpand(event, '${classes.groupId}')" style="cursor:pointer;margin-right:8px;">▶</span>` : 
      `<span style="display:inline-block;width:20px;margin-right:8px;"></span>`;
    
    const symbol = holding.tradingsymbol;
    const accountDisplay = classes.hasMultipleAccounts ? '> 1' : (holding.account || '-');
    
    return `<tr class="${classes.groupId ? `group-row ${classes.groupId}` : ''}" style="background-color:${Formatter.rowColor(pl)}">
  ${this._buildCell(expandBtn + symbol, classes.symbolClass)}
  ${this._buildCell(qty.toLocaleString(), classes.qtyClass)}
  ${this._buildCell(Formatter.formatCurrency(avg), classes.avgClass)}
  ${this._buildCell(Formatter.formatCurrency(invested), classes.investedClass)}
  ${this._buildValueWithPctCell(Formatter.formatCurrency(current), plPct, classes.currentClass)}
  ${this._buildCell(Formatter.formatLTP(ltp), classes.ltpClass)}
  ${this._buildPLCell(pl, classes.plClass)}
  ${this._buildChangeCell(dayChange, dayChangePct, classes.dayChangeClass)}
  ${this._buildCell(holding.exchange, classes.exchangeClass)}
  ${this._buildCell(accountDisplay, classes.accountClass)}
  </tr>`;
  }

  _buildStockBreakdownRow(holding, metrics, groupId) {
    const { qty, avg, invested, ltp, dayChange, pl, current, plPct, dayChangePct } = metrics;
    
    return `<tr class="breakdown-row ${groupId}" style="display:none;background-color:${Formatter.rowColor(pl)};opacity:0.85;">
  ${this._buildCell(`&nbsp;&nbsp;&nbsp;&nbsp;└ ${holding.account}`, '')}
  ${this._buildCell(qty.toLocaleString(), '')}
  ${this._buildCell(Formatter.formatCurrency(avg), '')}
  ${this._buildCell(Formatter.formatCurrency(invested), '')}
  ${this._buildValueWithPctCell(Formatter.formatCurrency(current), plPct, '')}
  ${this._buildCell(Formatter.formatLTP(ltp), '')}
  ${this._buildPLCell(pl, '')}
  ${this._buildChangeCell(dayChange, dayChangePct, '')}
  ${this._buildCell(holding.exchange, '')}
  ${this._buildCell('', '')}
  </tr>`;
  }

  _buildMFRow(fundName, mf, metrics, classes) {
    const { qty, avg, invested, nav, current, pl, plPct } = metrics;
    
    const expandBtn = classes.hasMultipleAccounts ? 
      `<span class="expand-toggle mf-expand-icon" data-group-id="${classes.groupId}" onclick="toggleGroupExpand(event, '${classes.groupId}')">▶</span>` : 
      `<span class="mf-expand-placeholder"></span>`;
    
    const accountDisplay = classes.hasMultipleAccounts ? '> 1' : (mf.account || '-');
    
    let navDateText = '';
    if (mf.last_price_date) {
      const formattedDate = Formatter.formatRelativeDate(mf.last_price_date, true);
      if (formattedDate) {
        navDateText = ` <span class="pl_pct_small">${formattedDate.toLowerCase()}</span>`;
      }
    }

    const mfNameCell = `<span class="mf-fund-cell"><span class="mf-fund-label">${fundName}</span></span>`;
    
    return `<tr class="${classes.groupId ? `group-row ${classes.groupId}` : ''}" style="background-color:${Formatter.rowColor(pl)}">
  ${this._buildCell(expandBtn + mfNameCell, classes.fundClass)}
  ${this._buildCell(qty.toLocaleString(), classes.qtyClass)}
  ${this._buildCell(Formatter.formatCurrency(avg), classes.avgClass)}
  ${this._buildCell(Formatter.formatCurrency(invested), classes.investedClass)}
  ${this._buildValueWithPctCell(Formatter.formatCurrency(current), plPct, classes.currentClass)}
  ${this._buildCell(Formatter.formatLTP(nav) + navDateText, classes.navClass)}
  ${this._buildPLCell(pl, classes.plClass)}
  ${this._buildCell(accountDisplay, classes.accountClass)}
  </tr>`;
  }

  _buildMFBreakdownRow(fundName, mf, metrics, groupId) {
    const { qty, avg, invested, nav, current, pl, plPct } = metrics;
    
    let navDateText = '';
    if (mf.last_price_date) {
      const formattedDate = Formatter.formatRelativeDate(mf.last_price_date, true);
      if (formattedDate) {
        navDateText = ` <span class="pl_pct_small">${formattedDate.toLowerCase()}</span>`;
      }
    }
    
    return `<tr class="breakdown-row ${groupId}" style="display:none;background-color:${Formatter.rowColor(pl)};opacity:0.85;">
  ${this._buildCell(`&nbsp;&nbsp;&nbsp;&nbsp;└ ${mf.account}`, '')}
  ${this._buildCell(qty.toLocaleString(), '')}
  ${this._buildCell(Formatter.formatCurrency(avg), '')}
  ${this._buildCell(Formatter.formatCurrency(invested), '')}
  ${this._buildValueWithPctCell(Formatter.formatCurrency(current), plPct, '')}
  ${this._buildCell(Formatter.formatLTP(nav) + navDateText, '')}
  ${this._buildPLCell(pl, '')}
  ${this._buildCell('', '')}
  </tr>`;
  }

  _buildSIPRow(fundName, sip, dataClass) {
    const frequency = sip.frequency || '-';
    
    let installments = '-';
    if (sip.instalments && sip.instalments !== -1) {
      const completed = sip.completed_instalments || 0;
      installments = `${completed}/${sip.instalments}`;
    } else if (sip.completed_instalments && sip.completed_instalments > 0) {
      // For perpetual SIPs, just show completed count
      installments = `${sip.completed_instalments}`;
    }
    
    // Format status with color
    const status = sip.status || 'UNKNOWN';
    let statusColor = '#666';
    if (status === 'ACTIVE') statusColor = '#28a745';
    else if (status === 'PAUSED') statusColor = '#ffc107';
    else if (status === 'CANCELLED') statusColor = '#dc3545';
    
    // Format next due date
    let nextDueText = '-';
    if (sip.next_instalment && status === 'ACTIVE') {
      const formattedDate = Formatter.formatRelativeDate(sip.next_instalment, false);
      nextDueText = formattedDate || sip.next_instalment;
    }
    
    return `<tr>
<td class="${dataClass}">${fundName}</td>
<td class="${dataClass}">${Formatter.formatCurrency(sip.instalment_amount || 0)}</td>
<td class="${dataClass}">${frequency}</td>
<td class="${dataClass}">${installments}</td>
<td class="${dataClass}"><span style="color:${statusColor};font-weight:600">${status}</span></td>
<td class="${dataClass}">${nextDueText}</td>
<td class="${dataClass}">${sip.account}</td>
</tr>`;
  }

  changeStocksPageSize(size) {
    this.stocksPagination.changePageSize(size);
  }

  goToStocksPage(page) {
    this.stocksPagination.goToPage(page);
  }

  /**
   * Render ETF holdings table (separate from stocks).
   * Gold/Silver ETFs are shown in the table but their totals go to Gold/Silver cards, not ETF card.
   * @param {Array} holdings - All holdings (stocks + ETFs combined from Zerodha)
   * @param {Object} status - Current status object
   * @returns {Object} { etfTotals, goldETFTotals, silverETFTotals }
   */
  renderETFTable(holdings, status) {
    const tbody = document.getElementById('etf_tbody');
    const section = document.getElementById('etf-section');
    const isUpdating = status.portfolio_state === 'updating';

    let etfInvested = 0;
    let etfCurrent = 0;
    let goldETFInvested = 0;
    let goldETFCurrent = 0;
    let silverETFInvested = 0;
    let silverETFCurrent = 0;
    let filteredHoldings = [];

    // Filter only ETF holdings
    holdings.forEach(holding => {
      const symbol = holding.tradingsymbol || '';
      const isin = holding.isin || '';
      const isETF = isETFInstrument(symbol, isin);

      if (!isETF) return;

      const text = (symbol + holding.account).toLowerCase();
      if (!text.includes(this.searchQuery)) return;

      const isGold = isGoldInstrument(symbol);
      const isSilver = isSilverInstrument(symbol);

      filteredHoldings.push(holding);
      const metrics = Calculator.calculateStockMetrics(holding);

      if (isGold) {
        goldETFInvested += metrics.invested;
        goldETFCurrent += metrics.current;
      } else if (isSilver) {
        silverETFInvested += metrics.invested;
        silverETFCurrent += metrics.current;
      } else {
        etfInvested += metrics.invested;
        etfCurrent += metrics.current;
      }
    });

    // Group ETFs by symbol
    const groupedHoldings = this._groupStocksBySymbol(filteredHoldings);
    const groupedArray = Object.values(groupedHoldings);

    // Use pagination manager on grouped holdings
    const paginationData = this.etfPagination.paginate(groupedArray);
    const { pageData } = paginationData;

    let rowsHTML = '';
    pageData.forEach((group, index) => {
      const groupId = `etf-group-${index}`;
      const metrics = this._calculateAggregatedStockMetrics(group.holdings);
      rowsHTML += this._buildStockRow(group.holdings[0], metrics, {
        symbolClass: this._getUpdateClass(isUpdating),
        qtyClass: this._getUpdateClass(isUpdating),
        avgClass: this._getUpdateClass(isUpdating),
        investedClass: this._getUpdateClass(isUpdating),
        ltpClass: this._getUpdateClass(isUpdating),
        plClass: this._getUpdateClass(isUpdating),
        dayChangeClass: this._getUpdateClass(isUpdating),
        currentClass: this._getUpdateClass(isUpdating),
        exchangeClass: this._getUpdateClass(isUpdating),
        accountClass: this._getUpdateClass(isUpdating),
        groupId: groupId,
        hasMultipleAccounts: group.holdings.length > 1,
        isGroupRow: true
      });

      if (group.holdings.length > 1) {
        group.holdings.forEach(holding => {
          const holdingMetrics = Calculator.calculateStockMetrics(holding);
          rowsHTML += this._buildStockBreakdownRow(holding, holdingMetrics, groupId);
        });
      }
    });
    tbody.innerHTML = rowsHTML;

    // Show/hide table and empty state
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: document.getElementById('etf_empty_state'),
      controls: section.querySelector('.controls-container'),
      paginationInfo: document.getElementById('etf_pagination_info'),
      paginationButtons: document.getElementById('etf_pagination_buttons')
    }, filteredHoldings.length > 0);

    // Update pagination UI
    PaginationManager.updatePaginationUI(
      paginationData,
      'etf_pagination_info',
      'etf_pagination_buttons',
      'goToETFPage',
      'etfs'
    );

    // Restore expanded state
    this._restoreExpandedState();

    const etfTotals = {
      invested: etfInvested,
      current: etfCurrent,
      pl: etfCurrent - etfInvested,
      plPct: etfInvested ? ((etfCurrent - etfInvested) / etfInvested * 100) : 0
    };

    const goldETFTotals = {
      invested: goldETFInvested,
      current: goldETFCurrent,
      pl: goldETFCurrent - goldETFInvested,
      plPct: goldETFInvested ? ((goldETFCurrent - goldETFInvested) / goldETFInvested * 100) : 0
    };

    const silverETFTotals = {
      invested: silverETFInvested,
      current: silverETFCurrent,
      pl: silverETFCurrent - silverETFInvested,
      plPct: silverETFInvested ? ((silverETFCurrent - silverETFInvested) / silverETFInvested * 100) : 0
    };

    return { etfTotals, goldETFTotals, silverETFTotals };
  }

  changeETFPageSize(size) {
    this.etfPagination.changePageSize(size);
  }

  goToETFPage(page) {
    this.etfPagination.goToPage(page);
  }

  changeMFPageSize(size) {
    this.mfPagination.changePageSize(size);
  }

  goToMFPage(page) {
    this.mfPagination.goToPage(page);
  }

  /**
   * Render physical gold holdings table with pagination
   */
  renderPhysicalGoldTable(holdings) {
    const tbody = document.getElementById('physical_gold_table_body');
    const section = document.getElementById('physical-gold-section');
    
    if (!tbody) return { invested: 0, current: 0, pl: 0, plPct: 0 };

    tbody.innerHTML = '';

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      emptyState: document.getElementById('physical_gold_empty_state'),
      controls: section ? section.querySelector('.controls-container') : null,
      paginationInfo: document.getElementById('physical_gold_pagination_info'),
      paginationButtons: document.getElementById('physical_gold_pagination_buttons')
    };

    if (!holdings || holdings.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      return { invested: 0, current: 0, pl: 0, plPct: 0 };
    }

    this._toggleSectionVisibility(sectionElements, true);

    let totalPhysicalGoldInvested = 0;
    let totalPhysicalGoldCurrent = 0;
    let totalPhysicalGoldPL = 0;
    
    holdings.forEach((holding) => {
      const weight = holding.weight_gms || 0;
      const ibjaRate = holding.bought_ibja_rate_per_gm || 0;
      const latestPrice = holding.latest_ibja_price_per_gm || ibjaRate;
      totalPhysicalGoldInvested += weight * ibjaRate;
      totalPhysicalGoldCurrent += weight * latestPrice;
      totalPhysicalGoldPL += holding.pl || 0;
    });

    const paginationData = this.physicalGoldPagination.paginate(holdings);
    const { pageData } = paginationData;

    let rowsHTML = '';
    pageData.forEach((holding) => {
      rowsHTML += this._buildPhysicalGoldRow(holding);
    });
    tbody.innerHTML = rowsHTML;

    this._renderPhysicalGoldPagination(paginationData);
    
    const plPct = totalPhysicalGoldInvested ? (totalPhysicalGoldPL / totalPhysicalGoldInvested * 100) : 0;
    
    return { 
      invested: totalPhysicalGoldInvested,
      current: totalPhysicalGoldCurrent,
      pl: totalPhysicalGoldPL,
      plPct: plPct
    };
  }

  _buildPhysicalGoldRow(holding) {
    const weight = holding.weight_gms ? holding.weight_gms.toFixed(3) : '0.000';
    const ibjaRate = Formatter.formatCurrency(holding.bought_ibja_rate_per_gm || 0);
    
    let latestPrice = '-';
    if (holding.latest_ibja_price_per_gm) {
      latestPrice = Formatter.formatCurrency(holding.latest_ibja_price_per_gm);
    }
    
    const pl = holding.pl || 0;
    const plPct = holding.pl_pct || 0;
    
    let plDisplay = '-';
    let plColor = '#999';
    
    if (holding.pl !== undefined) {
      plDisplay = Formatter.formatCurrency(Math.abs(pl));
      if (pl < 0) {
        plDisplay = '-' + plDisplay;
      }
      plColor = Formatter.colorPL(pl);
      const pctText = Formatter.formatPercentage(plPct);
      plDisplay = `${plDisplay} <span class="pl_pct_small" style="color:${plColor}">${pctText}</span>`;
    }

    return `<tr style="background-color:${Formatter.rowColor(pl)}">
      <td>${Formatter.formatShortDate(holding.date)}</td>
      <td>${holding.type || '-'}</td>
      <td>${holding.retail_outlet || '-'}</td>
      <td style="font-weight:600;color:#d4af37">${holding.purity || '-'}</td>
      <td>${weight}</td>
      <td>${ibjaRate}</td>
      <td>${latestPrice}</td>
      <td style="color:${plColor};font-weight:600">${plDisplay}</td>
    </tr>`;
  }

  _renderPhysicalGoldPagination(paginationData) {
    const paginationInfo = document.getElementById('physical_gold_pagination_info');
    const paginationButtons = document.getElementById('physical_gold_pagination_buttons');

    if (!paginationInfo || !paginationButtons) return;

    PaginationManager.updatePaginationUI(
      paginationData,
      'physical_gold_pagination_info',
      'physical_gold_pagination_buttons',
      'goToPhysicalGoldPage',
      'holdings'
    );
  }

  changePhysicalGoldPageSize(size) {
    this.physicalGoldPagination.changePageSize(size);
  }

  goToPhysicalGoldPage(page) {
    this.physicalGoldPagination.goToPage(page);
  }

  /**
   * Render fixed deposits table with pagination
   */
  renderFixedDepositsTable(deposits) {
    const tbody = document.getElementById('fixed_deposits_table_body');
    const section = document.getElementById('fixed-deposits-section');
    
    if (!tbody) return { invested: 0, maturity: 0, returns: 0, returnsPct: 0 };

    tbody.innerHTML = '';

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      emptyState: document.getElementById('fixed_deposits_empty_state'),
      controls: section ? section.querySelector('.controls-container') : null,
      paginationInfo: document.getElementById('fixed_deposits_pagination_info'),
      paginationButtons: document.getElementById('fixed_deposits_pagination_buttons'),
      tabs: section ? section.querySelector('.fd-tabs') : null
    };

    if (!deposits || deposits.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      return { invested: 0, maturity: 0, returns: 0, returnsPct: 0 };
    }

    this._toggleSectionVisibility(sectionElements, true);

    // Calculate totals
    let totalInvested = 0;
    let totalCurrentValue = 0;
    
    deposits.forEach((deposit) => {
      totalInvested += deposit.original_amount || 0;
      totalCurrentValue += deposit.current_value || 0;
    });
    
    const totalReturns = totalCurrentValue - totalInvested;
    const returnsPct = totalInvested > 0 ? (totalReturns / totalInvested * 100) : 0;

    // Group fixed deposits by Maturity Date, ROI, and Bank (in that order)
    const groupedDeposits = this._groupFixedDepositsByMaturityROIBank(deposits);
    const groupedArray = Object.values(groupedDeposits);

    // Use pagination manager on grouped deposits
    const paginationData = this.fixedDepositsPagination.paginate(groupedArray);
    const { pageData } = paginationData;

    let rowsHTML = '';
    pageData.forEach((group, index) => {
      const groupId = `fd-group-${index}`;
      const metrics = this._calculateAggregatedFixedDepositMetrics(group.holdings);
      rowsHTML += this._buildFixedDepositRow(group.holdings[0], metrics, {
        groupId: groupId,
        hasMultipleAccounts: group.holdings.length > 1,
        isGroupRow: true
      });

      // Add breakdown rows if multiple accounts
      if (group.holdings.length > 1) {
        group.holdings.forEach(deposit => {
          const depositMetrics = this._calculateFixedDepositMetrics(deposit);
          rowsHTML += this._buildFixedDepositBreakdownRow(deposit, depositMetrics, groupId);
        });
      }
    });
    tbody.innerHTML = rowsHTML;

    this._renderFixedDepositsPagination(paginationData);
    
    // Restore expanded state for groups that were previously expanded
    this._restoreExpandedState();
    
    return {
      invested: totalInvested,
      maturity: totalCurrentValue,
      returns: totalReturns,
      returnsPct: returnsPct
    };
  }

  /**
   * Group fixed deposits by Maturity Date, ROI (Interest Rate), and Bank
   */
  _groupFixedDepositsByMaturityROIBank(deposits) {
    const groups = {};
    deposits.forEach(deposit => {
      const maturityDate = deposit.maturity_date || '';
      const roi = deposit.interest_rate ? deposit.interest_rate.toFixed(2) : '0.00';
      const bank = deposit.bank_name || '';
      const groupKey = `${maturityDate}|${roi}|${bank}`;
      
      if (!groups[groupKey]) {
        groups[groupKey] = { holdings: [] };
      }
      groups[groupKey].holdings.push(deposit);
    });
    return groups;
  }

  /**
   * Calculate metrics for a single fixed deposit
   */
  _calculateFixedDepositMetrics(deposit) {
    const originalAmount = deposit.original_amount || 0;
    const currentValue = deposit.current_value || 0;
    const pl = currentValue - originalAmount;
    const plPct = originalAmount > 0 ? (pl / originalAmount * 100) : 0;
    
    return {
      originalAmount: originalAmount,
      reinvestedAmount: deposit.reinvested_amount || 0,
      interestRate: deposit.interest_rate || 0,
      currentValue: currentValue,
      pl: pl,
      plPct: plPct
    };
  }

  /**
   * Calculate aggregated metrics for a group of fixed deposits
   */
  _calculateAggregatedFixedDepositMetrics(holdings) {
    let totalOriginalAmount = 0;
    let totalReinvestedAmount = 0;
    let totalCurrentValue = 0;
    let interestRate = 0;

    holdings.forEach((deposit, index) => {
      totalOriginalAmount += deposit.original_amount || 0;
      totalReinvestedAmount += deposit.reinvested_amount || 0;
      totalCurrentValue += deposit.current_value || 0;
      
      // Use interest rate from first deposit (should be same for all in group)
      if (index === 0) {
        interestRate = deposit.interest_rate || 0;
      }
    });

    const pl = totalCurrentValue - totalOriginalAmount;
    const plPct = totalOriginalAmount > 0 ? (pl / totalOriginalAmount * 100) : 0;

    return {
      originalAmount: totalOriginalAmount,
      reinvestedAmount: totalReinvestedAmount,
      interestRate: interestRate,
      currentValue: totalCurrentValue,
      pl: pl,
      plPct: plPct
    };
  }

  _buildFixedDepositRow(deposit, metrics, classes) {
    const { originalAmount, reinvestedAmount, interestRate, currentValue } = metrics;
    const accountDisplay = classes.hasMultipleAccounts ? '> 1' : (deposit.account || '-');
    
    const expandBtn = classes.hasMultipleAccounts ? 
      `<span class="expand-toggle" data-group-id="${classes.groupId}" onclick="toggleGroupExpand(event, '${classes.groupId}')" style="cursor:pointer;margin-right:8px;">▶</span>` : 
      `<span style="display:inline-block;width:20px;margin-right:8px;"></span>`;
    
    const reinvestedDisplay = (reinvestedAmount && Number(reinvestedAmount) > 0)
      ? Formatter.formatCurrency(reinvestedAmount)
      : '-';
    const interestRateDisplay = interestRate ? `${interestRate.toFixed(2)}%` : '-';

    return `<tr class="${classes.groupId ? `group-row ${classes.groupId}` : ''}">
      <td>${expandBtn}${Formatter.formatShortDate(deposit.original_investment_date)}</td>
      <td>${Formatter.formatShortDate(deposit.reinvested_date)}</td>
      <td>${deposit.bank_name || '-'}</td>
      <td>${Formatter.formatCurrency(originalAmount)}</td>
      <td>${reinvestedDisplay}</td>
      <td style="color:#3498db;font-weight:600">${interestRateDisplay}</td>
      <td>${Formatter.formatShortDate(deposit.maturity_date)}</td>
      <td>${Formatter.formatCurrency(currentValue)}</td>
      <td>${accountDisplay}</td>
    </tr>`;
  }

  _buildFixedDepositBreakdownRow(deposit, metrics, groupId) {
    const { originalAmount, reinvestedAmount, interestRate, currentValue } = metrics;
    
    const reinvestedDisplay = (reinvestedAmount && Number(reinvestedAmount) > 0)
      ? Formatter.formatCurrency(reinvestedAmount)
      : '-';
    const interestRateDisplay = interestRate ? `${interestRate.toFixed(2)}%` : '-';

    return `<tr class="breakdown-row ${groupId}" style="display:none;">
      <td>&nbsp;&nbsp;&nbsp;&nbsp;└ ${Formatter.formatShortDate(deposit.original_investment_date)}</td>
      <td>${Formatter.formatShortDate(deposit.reinvested_date)}</td>
      <td>${deposit.bank_name || '-'}</td>
      <td>${Formatter.formatCurrency(originalAmount)}</td>
      <td>${reinvestedDisplay}</td>
      <td style="color:#3498db;font-weight:600">${interestRateDisplay}</td>
      <td>${Formatter.formatShortDate(deposit.maturity_date)}</td>
      <td>${Formatter.formatCurrency(currentValue)}</td>
      <td>${deposit.account || '-'}</td>
    </tr>`;
  }

  _renderFixedDepositsPagination(paginationData) {
    const paginationInfo = document.getElementById('fixed_deposits_pagination_info');
    const paginationButtons = document.getElementById('fixed_deposits_pagination_buttons');

    if (!paginationInfo || !paginationButtons) return;

    PaginationManager.updatePaginationUI(
      paginationData,
      'fixed_deposits_pagination_info',
      'fixed_deposits_pagination_buttons',
      'goToFixedDepositsPage',
      'deposits'
    );
  }

  changeFixedDepositsPageSize(size) {
    this.fixedDepositsPagination.changePageSize(size);
  }

  goToFixedDepositsPage(page) {
    this.fixedDepositsPagination.goToPage(page);
  }

  /**
   * Render fixed deposits summary table grouped by bank and account
   * @param {Array} summaryArray - Pre-computed summary data from renderFixedDepositsTable
   */
  renderFDSummaryTable(summaryArray) {
    const tbody = document.getElementById('fd_summary_table_body');
    const section = document.getElementById('fd-summary-section');
    
    if (!tbody) return;

    tbody.innerHTML = '';

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      controls: section ? section.querySelector('.controls-container') : null,
      paginationInfo: document.getElementById('fd_summary_pagination_info'),
      paginationButtons: document.getElementById('fd_summary_pagination_buttons')
    };

    if (!summaryArray || summaryArray.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      return;
    }

    // Use pagination manager on pre-computed summary data
    const paginationData = this.fdSummaryPagination.paginate(summaryArray);
    const { pageData } = paginationData;

    let rowsHTML = '';
    pageData.forEach((summary) => {
      rowsHTML += this._buildFDSummaryRow(summary);
    });
    tbody.innerHTML = rowsHTML;

    this._toggleSectionVisibility(sectionElements, true);

    PaginationManager.updatePaginationUI(
      paginationData,
      'fd_summary_pagination_info',
      'fd_summary_pagination_buttons',
      'goToFDSummaryPage',
      'summaries'
    );
  }

  /**
   * Group fixed deposits by bank and account name
   */
  _groupFDByBankAndAccount(deposits) {
    const groups = {};
    deposits.forEach(deposit => {
      const bank = deposit.bank_name || 'Unknown';
      const account = deposit.account || 'Unknown';
      const groupKey = `${bank}|${account}`;
      
      if (!groups[groupKey]) {
        groups[groupKey] = {
          bank: bank,
          account: account,
          totalDeposited: 0,
          totalCurrentValue: 0,
          totalReturns: 0
        };
      }
      
      groups[groupKey].totalDeposited += deposit.original_amount || 0;
      groups[groupKey].totalCurrentValue += deposit.current_value || 0;
    });

    // Calculate returns for each group
    Object.values(groups).forEach(group => {
      group.totalReturns = group.totalCurrentValue - group.totalDeposited;
    });

    return groups;
  }

  /**
   * Check if bank+account total is >= 5 Lakhs
   */
  _isFDSummaryHighValue(totalCurrentValue) {
    return totalCurrentValue >= 500000; // 5 Lakhs
  }

  _buildFDSummaryRow(summary) {
    const { bank, account, totalDeposited, totalCurrentValue, totalReturns } = summary;
    const isHighValue = this._isFDSummaryHighValue(totalCurrentValue);
    const returnColor = Formatter.colorPL(totalReturns);
    const returnsPct = totalDeposited > 0 ? (totalReturns / totalDeposited * 100) : 0;
    const returnsPctText = Formatter.formatPercentage(returnsPct);

    const alertIcon = isHighValue ? ' <span class="fd-alert-icon" role="img" aria-label="High FD value" data-fd-warning="true"></span>' : '';

    return `<tr>
      <td style="text-transform:uppercase">${bank}</td>
      <td>${account}</td>
      <td>${Formatter.formatCurrency(totalDeposited)}</td>
      <td>${Formatter.formatCurrency(totalCurrentValue)}${alertIcon}</td>
      <td><span style="color:${returnColor};font-weight:600">${Formatter.formatCurrency(totalReturns)} <span class="pl_pct_small" style="color:${returnColor}">${returnsPctText}</span></span></td>
    </tr>`;
  }

  changeFDSummaryPageSize(size) {
    this.fdSummaryPagination.changePageSize(size);
  }

  goToFDSummaryPage(page) {
    this.fdSummaryPagination.goToPage(page);
  }

}

export default TableRenderer;
