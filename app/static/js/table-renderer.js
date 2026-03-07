/* Metron - Table Rendering Module */

import { Formatter, Calculator, isGoldInstrument, isSGBInstrument, isSilverInstrument, isETFInstrument } from './utils.js';

/**
 * Build inline edit + delete action buttons for a manual-entry row.
 * @param {string} schemaKey - CRUD schema key (e.g. 'stocks', 'physical_gold')
 * @param {number} rowNumber - Sheet row number
 * @param {Object} values - Current field values for pre-populating the edit form
 * @returns {string} HTML string with action icons
 */
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

class TableRenderer {
  constructor() {
    this.searchQuery = '';
    this.rowLimit = window.__TABLE_ROW_LIMIT__ || 10;
    this.expandedGroups = new Set(); // Track which groups are expanded
  }

  /**
   * Replace the data rows of a <tbody> while preserving any active CRUD
   * inline form row that lives inside it.  When no form is present this
   * is equivalent to `tbody.innerHTML = html`.
   *
   * How it works:
   * 1. Identify the inline form <tr> (.crud-inline-row) if present.
   * 2. Remove every *other* child row from the tbody.
   * 3. Inject the new HTML into a temporary container.
   * 4. Move the new rows into the tbody, positioning them around the
   *    form row (form stays in place, original data row hidden).
   *
   * Because the form <tr> never leaves the DOM, its focus, input values,
   * and CSS animation state are fully preserved.
   */
  _updateTbodyContent(tbody, html) {
    const formRow = tbody.querySelector('tr.crud-inline-row');
    if (!formRow) {
      tbody.innerHTML = html;
      return;
    }

    // --- Form is open: surgical update ---

    // Remember the original data row the form is editing (if any)
    const editedRowNum = formRow.previousElementSibling?.dataset?.manualRow
      || formRow.nextElementSibling?.dataset?.manualRow;
    const editedSchema = formRow.previousElementSibling?.dataset?.schema
      || formRow.nextElementSibling?.dataset?.schema;

    // 1. Remove all rows except the form row
    Array.from(tbody.children).forEach(row => {
      if (row !== formRow) row.remove();
    });

    // 2. Parse the new HTML into a document fragment
    const temp = document.createElement('tbody');
    temp.innerHTML = html;
    const newRows = Array.from(temp.children);

    // 3. Re-insert new rows, hiding the one being edited and placing
    //    new rows before/after the form row as appropriate.
    let foundEditedRow = false;
    let insertedFormRowDataBefore = false;

    newRows.forEach(row => {
      const isEditedRow = row.dataset.manualRow === editedRowNum
                       && row.dataset.schema === editedSchema
                       && editedRowNum !== undefined;

      if (isEditedRow) {
        // This is the re-rendered version of the row being edited —
        // insert it right before the form row and keep it hidden.
        row.style.display = 'none';
        tbody.insertBefore(row, formRow);
        foundEditedRow = true;
        insertedFormRowDataBefore = true;
      } else if (!insertedFormRowDataBefore && !foundEditedRow) {
        // Rows before the edited row → insert before the form row
        tbody.insertBefore(row, formRow);
      } else {
        // Rows after the edited row → append at end
        tbody.appendChild(row);
      }
    });

    // 4. If no matching data row was found (e.g. add mode, or row is
    //    on a different page), make sure the form row stays at top.
    if (!foundEditedRow && formRow !== tbody.firstChild) {
      tbody.insertBefore(formRow, tbody.firstChild);
    }
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
   * @param {boolean} hasData - Whether the section has data to display
   */
  _toggleSectionVisibility({ table, emptyState, controls, tabs }, hasData) {
    // Table is always visible (headers stay accessible)
    if (table) table.style.display = 'table';
    if (emptyState) emptyState.style.display = 'none'; // replaced by in-table CTA

    if (hasData) {
      if (controls) controls.style.display = 'flex';
      if (tabs) tabs.style.display = 'flex';
    } else {
      // Hide controls (Add button) when empty — the in-table CTA already provides Add
      if (controls) controls.style.display = 'none';
      if (tabs) tabs.style.display = 'none';
    }
  }

  /**
   * Build a subtle "View all" footer row that links to the standalone table page.
   * Only shown when the total count exceeds the row limit.
   * @param {number} totalCount - Total number of items
   * @param {number} colCount - Number of columns for colspan
   * @param {string} tableKey - Route key (e.g. 'stocks', 'etfs', 'mutual-funds')
   * @param {string} label - Human-readable plural label (e.g. 'stocks', 'ETFs')
   * @returns {string} HTML string for the footer row, or empty string
   */
  _buildViewMoreRow(totalCount, colCount, tableKey, label) {
    if (totalCount <= this.rowLimit) return '';
    const remaining = totalCount - this.rowLimit;
    return `<tr class="view-more-row">
      <td colspan="${colCount}">
        <a href="/details/${tableKey}" class="view-more-link">
          View all ${totalCount} ${label}
          <span class="view-more-extra">+${remaining} more</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><polyline points="12 5 19 12 12 19"/></svg>
        </a>
      </td>
    </tr>`;
  }

  /**
   * Render an in-table empty-state CTA row.
   * @param {HTMLElement} tbody - Target tbody
   * @param {string} schemaKey - CRUD schema key for the Add button
   * @param {string} label - Human-readable type label
   * @param {number} colCount - Number of columns for colspan
   */
  _renderEmptyCta(tbody, schemaKey, label, colCount) {
    // If an inline add/edit form is already open, don't show the empty CTA —
    // the user is actively adding a row.  The CTA will reappear naturally if
    // they cancel the form and the table is still empty.
    if (tbody.querySelector('tr.crud-inline-row')) return;

    const ctaHtml = `<tr class="crud-empty-cta-row">
      <td colspan="${colCount}">
        <div class="crud-empty-cta" onclick="window.crudAdd('${schemaKey}')" role="button" tabindex="0">
          <button class="crud-empty-add-btn">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
            Add ${label}
          </button>
        </div>
      </td>
    </tr>`;
    this._updateTbodyContent(tbody, ctaHtml);
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
   * Build a P/L cell showing both value and percentage.
   * @param {number} value - P/L value
   * @param {number} percentage - P/L percentage
   * @param {string} cssClass - Optional CSS class
   * @returns {string} HTML string for P/L cell with percentage
   */
  _buildPLWithPctCell(value, percentage, cssClass = '') {
    const formatted = Formatter.formatCurrency(value);
    const color = Formatter.colorPL(value);
    const pctText = Formatter.formatPercentage(percentage);
    return `<td><span class="${cssClass}" style="color:${color};font-weight:600">${formatted}</span> <span class="pl_pct_small" style="color:${color}">${pctText}</span></td>`;
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
      const isETF = isETFInstrument(symbol, isin, holding.manual_type);
      
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

    // Slice to row limit for portfolio dashboard
    const totalGroups = groupedArray.length;
    const pageData = groupedArray.slice(0, this.rowLimit);

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
    // Append "view more" footer if data exceeds row limit
    rowsHTML += this._buildViewMoreRow(totalGroups, 10, 'stocks', 'stocks');

    if (filteredHoldings.length === 0 && holdings.length === 0) {
      this._renderEmptyCta(tbody, 'stocks', 'stocks', 10);
    } else {
      this._updateTbodyContent(tbody, rowsHTML);
    }

    // Show/hide table and empty state
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: null,
      controls: section.querySelector('.controls-container'),
    }, filteredHoldings.length > 0);

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

    // Slice to row limit for portfolio dashboard
    const totalGroups = groupedArray.length;
    const pageData = groupedArray.slice(0, this.rowLimit);

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
    // Append "view more" footer if data exceeds row limit
    rowsHTML += this._buildViewMoreRow(totalGroups, 8, 'mutual-funds', 'funds');

    if (filteredHoldings.length === 0 && mfHoldings.length === 0) {
      this._renderEmptyCta(tbody, 'mutual_funds', 'mutual funds', 8);
    } else {
      this._updateTbodyContent(tbody, rowsHTML);
    }

    // Show/hide table and empty state
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: null,
      controls: section.querySelector('.controls-container'),
    }, filteredHoldings.length > 0);

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

    let allRows = [];
    let totalMonthlyAmount = 0;
    const frequencyCounts = { monthly: 0, weekly: 0, quarterly: 0 };
    const frequencyAmounts = { monthly: 0, weekly: 0, quarterly: 0 };

    sips.forEach(sip => {
      const fundName = (sip.fund || sip.tradingsymbol).toUpperCase();
      const text = (fundName + sip.account).toLowerCase();
      if (!text.includes(this.searchQuery)) return;

      allRows.push(this._buildSIPRow(fundName, sip, dataClass));

      // Calculate total monthly amount for SIPs
      if (sip.status === 'ACTIVE' && sip.instalment_amount) {
        const frequency = (sip.frequency || 'monthly').toLowerCase();
        const amount = sip.instalment_amount;

        if (frequency === 'monthly') {
          totalMonthlyAmount += amount;
          frequencyCounts.monthly++;
          frequencyAmounts.monthly += amount;
        } else if (frequency === 'weekly') {
          totalMonthlyAmount += amount * 4.33;
          frequencyCounts.weekly++;
          frequencyAmounts.weekly += amount;
        } else if (frequency === 'quarterly') {
          totalMonthlyAmount += amount / 3;
          frequencyCounts.quarterly++;
          frequencyAmounts.quarterly += amount;
        }
      }
    });

    if (allRows.length === 0 && sips.length === 0) {
      this._renderEmptyCta(tbody, 'sips', 'SIPs', 7);
    } else {
      const totalVisible = allRows.length;
      let rowsHTML = allRows.slice(0, this.rowLimit).join('');

      if (totalVisible > this.rowLimit) {
        rowsHTML += this._buildViewMoreRow(totalVisible, 7, 'sips', 'SIPs');
      }

      this._updateTbodyContent(tbody, rowsHTML);
    }

    // Render SIP Rhythm Summary
    this._renderSIPRhythm(totalMonthlyAmount, frequencyCounts, frequencyAmounts);

    // Show/hide table and controls (Add button)
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: null,
      controls: section.querySelector('.controls-container'),
    }, sips.length > 0);
  }


  /**
   * Render the SIP Rhythm summary strip — total monthly/annual amounts,
   * frequency contribution segments, and a proportional stacked bar.
   */
  _renderSIPRhythm(totalMonthly, counts, amounts) {
    const rhythm = document.getElementById('sip_rhythm');
    if (!rhythm) return;

    const hasActive = counts.monthly + counts.weekly + counts.quarterly > 0;
    rhythm.style.display = hasActive ? '' : 'none';
    if (!hasActive) return;

    // Monthly & annual totals
    const monthlyEl = document.getElementById('sip_monthly_total');
    const annualEl = document.getElementById('sip_annual_total');
    monthlyEl.textContent = '₹' + Formatter.formatCompactIndian(totalMonthly, 1);
    annualEl.textContent = '₹' + Formatter.formatCompactIndian(totalMonthly * 12, 1);

    // Convert raw amounts to monthly equivalents for proportions
    const monthlyEquiv = {
      weekly: amounts.weekly * 4.33,
      monthly: amounts.monthly,
      quarterly: amounts.quarterly / 3
    };

    // Frequency segments
    const segmentsEl = document.getElementById('sip_freq_segments');
    const order = ['weekly', 'monthly', 'quarterly'];
    const labels = { weekly: 'Weekly', monthly: 'Monthly', quarterly: 'Quarterly' };
    const perLabels = { weekly: '/wk', monthly: '/mo', quarterly: '/qtr' };

    let segsHTML = '';
    order.forEach(freq => {
      if (counts[freq] === 0) return;
      const perAmount = amounts[freq] / counts[freq]; // amount per SIP
      const moEquiv = monthlyEquiv[freq];
      const sipWord = counts[freq] === 1 ? 'SIP' : 'SIPs';
      const showEquiv = freq !== 'monthly'; // only show "≈ ₹X/mo" for non-monthly

      segsHTML += `<div class="sip-freq-seg">
  <div class="sip-freq-seg-header">
    <span class="sip-freq-dot sip-freq-dot--${freq}"></span>
    <span class="sip-freq-name">${labels[freq]}</span>
    <span class="sip-freq-count">${counts[freq]} ${sipWord}</span>
  </div>
  <div class="sip-freq-amount">₹${Formatter.formatCompactIndian(amounts[freq], 1)}${perLabels[freq]}</div>
  ${showEquiv ? `<div class="sip-freq-monthly-eq">≈ ₹${Formatter.formatCompactIndian(moEquiv, 1)}/mo</div>` : ''}
</div>`;
    });
    segmentsEl.innerHTML = segsHTML;

    // Proportional stacked bar
    const barEl = document.getElementById('sip_proportion_bar');
    let barHTML = '';
    order.forEach(freq => {
      if (counts[freq] === 0) return;
      const pct = totalMonthly > 0 ? (monthlyEquiv[freq] / totalMonthly * 100) : 0;
      barHTML += `<span class="sip-bar-seg sip-bar-seg--${freq}" style="width:${pct.toFixed(1)}%"></span>`;
    });
    barEl.innerHTML = barHTML;
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
      `<span class="expand-toggle" data-group-id="${classes.groupId}"></span>` : 
      `<span class="expand-toggle-spacer"></span>`;
    
    const symbol = holding.tradingsymbol;
    const accountDisplay = classes.hasMultipleAccounts ? '> 1' : (holding.account || '-');
    const isManual = !classes.hasMultipleAccounts && holding.source === 'manual';
    const manualBadge = isManual ? '<span class="source-indicator source-manual" data-tip="Manually added"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5c0 .3-.2.5-.5.5h-9a.5.5 0 0 1-.5-.5Z"/></svg></span>' : '';
    const crudType = (isManual && holding.manual_type === 'etfs') ? 'etfs' : 'stocks';
    const actions = isManual ? buildCrudActions(crudType, holding.row_number, {
      symbol: holding.tradingsymbol, qty: holding.quantity,
      avg_price: holding.average_price, exchange: holding.exchange, account: holding.account
    }) : '';
    const manualAttrs = isManual ? ` data-manual-row="${holding.row_number}" data-schema="${crudType}"` : '';
    
    return `<tr${manualAttrs} class="${classes.groupId ? `group-row ${classes.groupId}` : ''}" style="background-color:${Formatter.rowColor(pl)}">
  ${this._buildCell(expandBtn + symbol + manualBadge, classes.symbolClass)}
  ${this._buildCell(qty.toLocaleString(), classes.qtyClass)}
  ${this._buildCell(Formatter.formatCurrency(avg), classes.avgClass)}
  ${this._buildCell(Formatter.formatCurrency(invested), classes.investedClass)}
  ${this._buildCell(Formatter.formatCurrency(current), classes.currentClass)}
  ${this._buildCell(Formatter.formatLTP(ltp), classes.ltpClass)}
  ${this._buildPLWithPctCell(pl, plPct, classes.plClass)}
  ${this._buildChangeCell(dayChange, dayChangePct, classes.dayChangeClass)}
  ${this._buildCell(holding.exchange, classes.exchangeClass)}
  ${this._buildCell(accountDisplay + actions, classes.accountClass)}
  </tr>`;
  }

  _buildStockBreakdownRow(holding, metrics, groupId) {
    const { qty, avg, invested, ltp, dayChange, pl, current, plPct, dayChangePct } = metrics;
    const isManual = holding.source === 'manual';
    const manualBadge = isManual ? ' <span class="source-indicator source-manual" data-tip="Manually added"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5c0 .3-.2.5-.5.5h-9a.5.5 0 0 1-.5-.5Z"/></svg></span>' : '';
    const crudType = (isManual && holding.manual_type === 'etfs') ? 'etfs' : 'stocks';
    const actions = isManual ? buildCrudActions(crudType, holding.row_number, {
      symbol: holding.tradingsymbol, qty: holding.quantity,
      avg_price: holding.average_price, exchange: holding.exchange, account: holding.account
    }) : '';
    const manualAttrs = isManual ? ` data-manual-row="${holding.row_number}" data-schema="${crudType}"` : '';
    
    return `<tr${manualAttrs} class="breakdown-row ${groupId}" style="display:none;background-color:${Formatter.rowColor(pl)};opacity:0.85;">
  ${this._buildCell(`<span class="breakdown-branch"></span>${holding.account}${manualBadge}`, '')}
  ${this._buildCell(qty.toLocaleString(), '')}
  ${this._buildCell(Formatter.formatCurrency(avg), '')}
  ${this._buildCell(Formatter.formatCurrency(invested), '')}
  ${this._buildCell(Formatter.formatCurrency(current), '')}
  ${this._buildCell(Formatter.formatLTP(ltp), '')}
  ${this._buildPLWithPctCell(pl, plPct, '')}
  ${this._buildChangeCell(dayChange, dayChangePct, '')}
  ${this._buildCell(holding.exchange, '')}
  ${this._buildCell(actions, '')}
  </tr>`;
  }

  _buildMFRow(fundName, mf, metrics, classes) {
    const { qty, avg, invested, nav, current, pl, plPct } = metrics;
    
    const expandBtn = classes.hasMultipleAccounts ? 
      `<span class="expand-toggle mf-expand-icon" data-group-id="${classes.groupId}"></span>` : 
      `<span class="mf-expand-placeholder"></span>`;
    
    const accountDisplay = classes.hasMultipleAccounts ? '> 1' : (mf.account || '-');
    
    let navDateText = '';
    if (mf.last_price_date) {
      const formattedDate = Formatter.formatRelativeDate(mf.last_price_date, true);
      if (formattedDate) {
        navDateText = `<span class="nav-date-sub">${formattedDate.toLowerCase()}</span>`;
      }
    }

    const mfNameCell = `<span class="mf-fund-cell"><span class="mf-fund-label">${fundName}</span></span>`;
    const isManual = !classes.hasMultipleAccounts && mf.source === 'manual';
    const manualBadge = isManual ? '<span class="source-indicator source-manual" data-tip="Manually added"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5c0 .3-.2.5-.5.5h-9a.5.5 0 0 1-.5-.5Z"/></svg></span>' : '';
    const crudActions = isManual ? buildCrudActions('mutual_funds', mf.row_number, {
      fund: mf.fund || mf.tradingsymbol, qty: mf.quantity,
      avg_nav: mf.average_price, account: mf.account
    }) : '';
    
    const manualAttrs = isManual ? ` data-manual-row="${mf.row_number}" data-schema="mutual_funds"` : '';
    return `<tr${manualAttrs} class="${classes.groupId ? `group-row ${classes.groupId}` : ''}" style="background-color:${Formatter.rowColor(pl)}">
  ${this._buildCell(expandBtn + mfNameCell + manualBadge, classes.fundClass)}
  ${this._buildCell(qty.toLocaleString(), classes.qtyClass)}
  ${this._buildCell(Formatter.formatCurrency(avg), classes.avgClass)}
  ${this._buildCell(Formatter.formatCurrency(invested), classes.investedClass)}
  ${this._buildCell(Formatter.formatCurrency(current), classes.currentClass)}
  <td class="${classes.navClass}">${Formatter.formatLTP(nav)}${navDateText}</td>
  ${this._buildPLWithPctCell(pl, plPct, classes.plClass)}
  ${this._buildCell(accountDisplay + crudActions, classes.accountClass)}
  </tr>`;
  }

  _buildMFBreakdownRow(fundName, mf, metrics, groupId) {
    const { qty, avg, invested, nav, current, pl, plPct } = metrics;
    const isManual = mf.source === 'manual';
    const manualBadge = isManual ? ' <span class="source-indicator source-manual" data-tip="Manually added"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5c0 .3-.2.5-.5.5h-9a.5.5 0 0 1-.5-.5Z"/></svg></span>' : '';
    const crudActions = isManual ? buildCrudActions('mutual_funds', mf.row_number, {
      fund: mf.fund || mf.tradingsymbol, qty: mf.quantity,
      avg_nav: mf.average_price, account: mf.account
    }) : '';
    const manualAttrs = isManual ? ` data-manual-row="${mf.row_number}" data-schema="mutual_funds"` : '';
    
    let navDateText = '';
    if (mf.last_price_date) {
      const formattedDate = Formatter.formatRelativeDate(mf.last_price_date, true);
      if (formattedDate) {
        navDateText = `<span class="nav-date-sub">${formattedDate.toLowerCase()}</span>`;
      }
    }
    
    return `<tr${manualAttrs} class="breakdown-row ${groupId}" style="display:none;background-color:${Formatter.rowColor(pl)};opacity:0.85;">
  ${this._buildCell(`<span class="breakdown-branch"></span>${mf.account}${manualBadge}`, '')}
  ${this._buildCell(qty.toLocaleString(), '')}
  ${this._buildCell(Formatter.formatCurrency(avg), '')}
  ${this._buildCell(Formatter.formatCurrency(invested), '')}
  ${this._buildCell(Formatter.formatCurrency(current), '')}
  <td>${Formatter.formatLTP(nav)}${navDateText}</td>
  ${this._buildPLWithPctCell(pl, plPct, '')}
  ${this._buildCell(crudActions, '')}
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
    
    const isManual = sip.source === 'manual';
    const manualBadge = isManual ? ' <span class="source-indicator source-manual" data-tip="Manually added"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5c0 .3-.2.5-.5.5h-9a.5.5 0 0 1-.5-.5Z"/></svg></span>' : '';
    const crudActions = isManual ? buildCrudActions('sips', sip.row_number, {
      fund: sip.fund || sip.tradingsymbol, amount: sip.instalment_amount,
      frequency: sip.frequency || 'MONTHLY',
      installments: sip.instalments || -1, completed: sip.completed_instalments || 0,
      status: sip.status || 'ACTIVE', next_due: sip.next_instalment || '',
      account: sip.account
    }) : '';

    const manualAttrs = isManual ? ` data-manual-row="${sip.row_number}" data-schema="sips"` : '';
    return `<tr${manualAttrs}>
<td class="${dataClass}">${fundName}${manualBadge}</td>
<td class="${dataClass}">${Formatter.formatCurrency(sip.instalment_amount || 0)}</td>
<td class="${dataClass}">${frequency}</td>
<td class="${dataClass}">${installments}</td>
<td class="${dataClass}"><span style="color:${statusColor};font-weight:600">${status}</span></td>
<td class="${dataClass}">${nextDueText}</td>
<td class="${dataClass}">${sip.account}${crudActions}</td>
</tr>`;
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
      const isETF = isETFInstrument(symbol, isin, holding.manual_type);

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

    // Slice to row limit for portfolio dashboard
    const totalGroups = groupedArray.length;
    const pageData = groupedArray.slice(0, this.rowLimit);

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
    // Append "view more" footer if data exceeds row limit
    rowsHTML += this._buildViewMoreRow(totalGroups, 10, 'etfs', 'ETFs');

    if (filteredHoldings.length === 0 && holdings.filter(h => isETFInstrument(h.tradingsymbol || '', h.isin || '', h.manual_type)).length === 0) {
      this._renderEmptyCta(tbody, 'etfs', 'ETFs', 10);
    } else {
      this._updateTbodyContent(tbody, rowsHTML);
    }

    // Show/hide table and empty state
    this._toggleSectionVisibility({
      table: section.querySelector('table'),
      emptyState: null,
      controls: section.querySelector('.controls-container'),
    }, filteredHoldings.length > 0);

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

  /**
   * Render physical gold holdings table
   */
  renderPhysicalGoldTable(holdings) {
    const tbody = document.getElementById('physical_gold_table_body');
    const section = document.getElementById('physical-gold-section');
    
    if (!tbody) return { invested: 0, current: 0, pl: 0, plPct: 0 };

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      emptyState: null,
      controls: section ? section.querySelector('.controls-container') : null,
    };

    if (!holdings || holdings.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      this._renderEmptyCta(tbody, 'physical_gold', 'physical gold', 8);
      return { invested: 0, current: 0, pl: 0, plPct: 0 };
    }

    let totalPhysicalGoldInvested = 0;
    let totalPhysicalGoldCurrent = 0;
    let totalPhysicalGoldPL = 0;
    
    this._toggleSectionVisibility(sectionElements, true);
    
    holdings.forEach((holding) => {
      const weight = holding.weight_gms || 0;
      const ibjaRate = holding.bought_ibja_rate_per_gm || 0;
      const latestPrice = holding.latest_ibja_price_per_gm || ibjaRate;
      totalPhysicalGoldInvested += weight * ibjaRate;
      totalPhysicalGoldCurrent += weight * latestPrice;
      totalPhysicalGoldPL += holding.pl || 0;
    });

    // Slice to row limit for portfolio dashboard
    const totalCount = holdings.length;
    const pageData = holdings.slice(0, this.rowLimit);

    let rowsHTML = '';
    pageData.forEach((holding) => {
      rowsHTML += this._buildPhysicalGoldRow(holding);
    });
    // Append "view more" footer if data exceeds row limit
    rowsHTML += this._buildViewMoreRow(totalCount, 8, 'physical-gold', 'holdings');
    this._updateTbodyContent(tbody, rowsHTML);
    
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

  /**
   * Render fixed deposits table
   */
  renderFixedDepositsTable(deposits) {
    const tbody = document.getElementById('fixed_deposits_table_body');
    const section = document.getElementById('fixed-deposits-section');
    
    if (!tbody) return { invested: 0, maturity: 0, returns: 0, returnsPct: 0 };

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      emptyState: null,
      controls: section ? section.querySelector('.controls-container') : null,
      tabs: section ? section.querySelector('.fd-tabs') : null
    };

    if (!deposits || deposits.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      this._renderEmptyCta(tbody, 'fixed_deposits', 'fixed deposits', 9);
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

    // Slice to row limit for portfolio dashboard
    const totalGroups = groupedArray.length;
    const pageData = groupedArray.slice(0, this.rowLimit);

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
    // Append "view more" footer if data exceeds row limit
    rowsHTML += this._buildViewMoreRow(totalGroups, 9, 'fixed-deposits', 'deposits');
    this._updateTbodyContent(tbody, rowsHTML);
    
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
      `<span class="expand-toggle" data-group-id="${classes.groupId}"></span>` : 
      `<span class="expand-toggle-spacer"></span>`;
    
    const reinvestedDisplay = (reinvestedAmount && Number(reinvestedAmount) > 0)
      ? Formatter.formatCurrency(reinvestedAmount)
      : '-';
    const interestRateDisplay = interestRate ? `${interestRate.toFixed(2)}%` : '-';

    const crudActions = (!classes.hasMultipleAccounts && deposit.row_number) ? buildCrudActions('fixed_deposits', deposit.row_number, {
      original_investment_date: deposit.original_investment_date || '',
      reinvested_date: deposit.reinvested_date || '',
      bank_name: deposit.bank_name || '',
      deposit_year: deposit.deposit_year || 0,
      deposit_month: deposit.deposit_month || 0,
      deposit_day: deposit.deposit_day || 0,
      original_amount: deposit.original_amount || 0,
      reinvested_amount: deposit.reinvested_amount || 0,
      interest_rate: deposit.interest_rate || 0,
      account: deposit.account || ''
    }) : '';

    const manualAttrs = (!classes.hasMultipleAccounts && deposit.row_number) ? ` data-manual-row="${deposit.row_number}" data-schema="fixed_deposits"` : '';
    return `<tr${manualAttrs} class="${classes.groupId ? `group-row ${classes.groupId}` : ''}">
      <td>${expandBtn}${Formatter.formatShortDate(deposit.original_investment_date)}</td>
      <td>${Formatter.formatShortDate(deposit.reinvested_date)}</td>
      <td>${deposit.bank_name || '-'}</td>
      <td>${Formatter.formatCurrency(originalAmount)}</td>
      <td>${reinvestedDisplay}</td>
      <td style="color:#3498db;font-weight:600">${interestRateDisplay}</td>
      <td>${Formatter.formatShortDate(deposit.maturity_date)}</td>
      <td>${Formatter.formatCurrency(currentValue)}</td>
      <td>${accountDisplay}${crudActions}</td>
    </tr>`;
  }

  _buildFixedDepositBreakdownRow(deposit, metrics, groupId) {
    const { originalAmount, reinvestedAmount, interestRate, currentValue } = metrics;
    
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
      account: deposit.account || ''
    }) : '';
    const manualAttrs = deposit.row_number ? ` data-manual-row="${deposit.row_number}" data-schema="fixed_deposits"` : '';

    return `<tr${manualAttrs} class="breakdown-row ${groupId}" style="display:none;">
      <td><span class="breakdown-branch"></span>${Formatter.formatShortDate(deposit.original_investment_date)}</td>
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



  /**
   * Group provident fund entries by company name
   */
  _groupProvidentFundByCompany(entries) {
    const groups = {};
    entries.forEach(entry => {
      const company = entry.company_name || '';
      if (!groups[company]) {
        groups[company] = { holdings: [] };
      }
      groups[company].holdings.push(entry);
    });
    return groups;
  }

  /**
   * Calculate aggregated metrics for a group of PF entries (same company)
   */
  _calculateAggregatedPFMetrics(holdings) {
    let totalMonths = 0;
    let totalContributed = 0;
    let totalInterest = 0;
    let closingBalance = 0;
    let weightedRateSum = 0;
    let totalMonthsForRate = 0;

    holdings.forEach(entry => {
      const months = entry.months_worked || 0;
      totalMonths += months;
      totalContributed += entry.total_contribution || 0;
      totalInterest += entry.interest_earned || 0;
      closingBalance += entry.closing_balance || 0;
      const rate = entry.effective_rate || entry.interest_rate || 0;
      weightedRateSum += rate * months;
      totalMonthsForRate += months;
    });

    return {
      months: totalMonths,
      totalContributed,
      totalInterest,
      closingBalance,
      weightedRate: totalMonthsForRate > 0 ? weightedRateSum / totalMonthsForRate : 0,
    };
  }

  /**
   * Render provident fund table grouped by company
   */
  renderProvidentFundTable(entries) {
    const tbody = document.getElementById('provident_fund_table_body');
    const section = document.getElementById('provident-fund-section');

    if (!tbody) return { contributed: 0, corpus: 0, interest: 0, interestPct: 0 };

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      emptyState: null,
      controls: section ? section.querySelector('.controls-container') : null,
    };

    if (!entries || entries.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      this._renderEmptyCta(tbody, 'provident_fund', 'provident fund entries', 9);
      return { contributed: 0, corpus: 0, interest: 0, interestPct: 0 };
    }

    this._toggleSectionVisibility(sectionElements, true);

    // Use the last entry's corpus_value as the total (since it includes all stints)
    const lastEntry = entries[entries.length - 1];
    const totalCorpus = lastEntry.corpus_value || 0;
    const totalContributed = lastEntry.total_corpus_contributions || 0;
    const totalInterest = lastEntry.total_corpus_interest || 0;
    const interestPct = totalContributed > 0 ? (totalInterest / totalContributed * 100) : 0;

    // Group by company
    const groupedEntries = this._groupProvidentFundByCompany(entries);
    const groupedArray = Object.values(groupedEntries);

    const totalGroups = groupedArray.length;
    const pageData = groupedArray.slice(0, this.rowLimit);

    let rowsHTML = '';
    pageData.forEach((group, index) => {
      const groupId = `pf-group-${index}`;
      const hasMultiple = group.holdings.length > 1;

      if (hasMultiple) {
        const metrics = this._calculateAggregatedPFMetrics(group.holdings);
        rowsHTML += this._buildProvidentFundGroupRow(group.holdings[0], metrics, {
          groupId, hasMultiple: true,
        });
        group.holdings.forEach(entry => {
          rowsHTML += this._buildProvidentFundBreakdownRow(entry, groupId);
        });
      } else {
        rowsHTML += this._buildProvidentFundRow(group.holdings[0], {
          groupId, hasMultiple: false,
        });
      }
    });
    rowsHTML += this._buildViewMoreRow(totalGroups, 9, 'provident-fund', 'entries');
    this._updateTbodyContent(tbody, rowsHTML);
    this._restoreExpandedState();

    return { contributed: totalContributed, corpus: totalCorpus, interest: totalInterest, interestPct };
  }

  /**
   * Build a single PF row (when the company has only one entry)
   */
  _buildProvidentFundRow(entry, classes) {
    const monthlyContrib = entry.monthly_contribution || 0;
    const rate = entry.effective_rate || entry.interest_rate || 0;
    const months = entry.months_worked || 0;
    const totalContrib = entry.total_contribution || 0;
    const interestEarned = entry.interest_earned || 0;
    const corpusValue = entry.closing_balance || 0;
    const endDateDisplay = entry.end_date ? Formatter.formatShortDate(entry.end_date) : 'Present';
    const rateDisplay = `${rate.toFixed(2)}%`;

    const crudActions = buildCrudActions('provident_fund', entry.row_number, {
      company_name: entry.company_name || '',
      start_date: entry.start_date || '',
      end_date: entry.end_date || '',
      monthly_contribution: entry.monthly_contribution || 0,
      interest_rate: entry.interest_rate || 0,
    });

    return `<tr data-manual-row="${entry.row_number}" data-schema="provident_fund" class="${classes.groupId ? `group-row ${classes.groupId}` : ''}">
      <td style="font-weight:600"><span class="expand-toggle-spacer"></span>${entry.company_name || '-'}</td>
      <td>${Formatter.formatShortDate(entry.start_date)}</td>
      <td>${endDateDisplay}</td>
      <td>${Formatter.formatCurrency(monthlyContrib)}</td>
      <td style="color:#3498db;font-weight:600">${rateDisplay}</td>
      <td>${months}</td>
      <td>${Formatter.formatCurrency(totalContrib)}</td>
      <td style="color:${Formatter.colorPL(interestEarned)};font-weight:600">${Formatter.formatCurrency(interestEarned)}</td>
      <td style="font-weight:600">${Formatter.formatCurrency(corpusValue)}${crudActions}</td>
    </tr>`;
  }

  /**
   * Build a summary/group row for a company with multiple PF entries
   */
  _buildProvidentFundGroupRow(firstEntry, metrics, classes) {
    const rateDisplay = `${metrics.weightedRate.toFixed(2)}%`;

    return `<tr data-schema="provident_fund" class="group-row ${classes.groupId}">
      <td style="font-weight:600"><span class="expand-toggle" data-group-id="${classes.groupId}"></span>${firstEntry.company_name || '-'}</td>
      <td></td>
      <td></td>
      <td></td>
      <td style="color:#3498db;font-weight:600">${rateDisplay}</td>
      <td>${metrics.months}</td>
      <td>${Formatter.formatCurrency(metrics.totalContributed)}</td>
      <td style="color:${Formatter.colorPL(metrics.totalInterest)};font-weight:600">${Formatter.formatCurrency(metrics.totalInterest)}</td>
      <td style="font-weight:600">${Formatter.formatCurrency(metrics.closingBalance)}</td>
    </tr>`;
  }

  /**
   * Build a breakdown row for an individual PF entry within a group
   */
  _buildProvidentFundBreakdownRow(entry, groupId) {
    const monthlyContrib = entry.monthly_contribution || 0;
    const rate = entry.effective_rate || entry.interest_rate || 0;
    const months = entry.months_worked || 0;
    const totalContrib = entry.total_contribution || 0;
    const interestEarned = entry.interest_earned || 0;
    const corpusValue = entry.closing_balance || 0;
    const endDateDisplay = entry.end_date ? Formatter.formatShortDate(entry.end_date) : 'Present';
    const rateDisplay = `${rate.toFixed(2)}%`;

    const crudActions = buildCrudActions('provident_fund', entry.row_number, {
      company_name: entry.company_name || '',
      start_date: entry.start_date || '',
      end_date: entry.end_date || '',
      monthly_contribution: entry.monthly_contribution || 0,
      interest_rate: entry.interest_rate || 0,
    });

    return `<tr data-manual-row="${entry.row_number}" data-schema="provident_fund" class="breakdown-row ${groupId}" style="display:none;">
      <td></td>
      <td><span class="breakdown-branch"></span>${Formatter.formatShortDate(entry.start_date)}</td>
      <td>${endDateDisplay}</td>
      <td>${Formatter.formatCurrency(monthlyContrib)}</td>
      <td style="color:#3498db;font-weight:600">${rateDisplay}</td>
      <td>${months}</td>
      <td>${Formatter.formatCurrency(totalContrib)}</td>
      <td style="color:${Formatter.colorPL(interestEarned)};font-weight:600">${Formatter.formatCurrency(interestEarned)}</td>
      <td style="font-weight:600">${Formatter.formatCurrency(corpusValue)}${crudActions}</td>
    </tr>`;
  }

  /**
   * Render fixed deposits summary table grouped by bank and account
   * @param {Array} summaryArray - Pre-computed summary data from renderFixedDepositsTable
   */
  renderFDSummaryTable(summaryArray) {
    const tbody = document.getElementById('fd_summary_table_body');
    const section = document.getElementById('fd-summary-section');
    
    if (!tbody) return;

    const sectionElements = {
      table: section ? section.querySelector('table') : null,
      controls: section ? section.querySelector('.controls-container') : null
    };

    if (!summaryArray || summaryArray.length === 0) {
      this._toggleSectionVisibility(sectionElements, false);
      this._updateTbodyContent(tbody, '');
      return;
    }

    const totalSummaries = summaryArray.length;
    const pageData = summaryArray.slice(0, this.rowLimit);

    let rowsHTML = '';
    pageData.forEach((summary) => {
      rowsHTML += this._buildFDSummaryRow(summary);
    });

    if (totalSummaries > this.rowLimit) {
      rowsHTML += this._buildViewMoreRow(totalSummaries, 5, 'fixed-deposits', 'summaries');
    }
    this._updateTbodyContent(tbody, rowsHTML);

    this._toggleSectionVisibility(sectionElements, true);
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

}

export default TableRenderer;
