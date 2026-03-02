/* Metron - Sort Manager Module */

import { Calculator } from './utils.js';

class SortManager {
  constructor() {
    this.stocksSortOrder = 'default';
    this.etfSortOrder = 'default';
    this.mfSortOrder = 'default';
    this.physicalGoldSortOrder = 'default';
    this.fixedDepositsSortOrder = 'default';
    this.fdSummarySortOrder = 'default';
  }

  /**
   * Generic comparator for numeric sorting
   * @param {function} getValue - Function to extract value from item
   * @param {boolean} descending - Sort direction
   * @returns {function} Comparator function
   */
  _numericComparator(getValue, descending = true) {
    return (a, b) => {
      const aVal = getValue(a);
      const bVal = getValue(b);
      return descending ? bVal - aVal : aVal - bVal;
    };
  }

  /**
   * Generic comparator for date string sorting
   * @param {function} getValue - Function to extract date string from item
   * @param {boolean} descending - Sort direction (true = newest first)
   * @returns {function} Comparator function
   */
  _dateComparator(getValue, descending = true) {
    return (a, b) => {
      const aVal = getValue(a);
      const bVal = getValue(b);
      
      // Parse dates (format: "Month Day, Year")
      const aDate = aVal ? new Date(aVal) : new Date(0);
      const bDate = bVal ? new Date(bVal) : new Date(0);
      
      return descending ? bDate - aDate : aDate - bDate;
    };
  }

  /**
   * Generic comparator for string sorting
   * @param {function} getValue - Function to extract value from item
   * @param {boolean} descending - Sort direction
   * @returns {function} Comparator function
   */
  _stringComparator(getValue, descending = false) {
    return (a, b) => {
      const aVal = getValue(a) || '';
      const bVal = getValue(b) || '';
      return descending ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
    };
  }

  /**
   * Sort stocks array based on selected criteria
   * @param {Array} holdings - Stock holdings array
   * @param {string} sortBy - Sort criteria
   * @returns {Array} Sorted array
   */
  sortStocks(holdings, sortBy = 'default') {
    if (sortBy === 'default' || !holdings || holdings.length === 0) {
      return holdings;
    }

    const sorted = [...holdings];

    // Cache metrics to avoid recalculating per comparison
    const metricsCache = new WeakMap();
    const getMetrics = (h) => {
      if (!metricsCache.has(h)) metricsCache.set(h, Calculator.calculateStockMetrics(h));
      return metricsCache.get(h);
    };
    
    // Map sort criteria to comparator functions
    const comparators = {
      'pl_pct_desc': this._numericComparator(h => getMetrics(h).plPct, true),
      'pl_pct_asc': this._numericComparator(h => getMetrics(h).plPct, false),
      'pl_desc': this._numericComparator(h => getMetrics(h).pl, true),
      'pl_asc': this._numericComparator(h => getMetrics(h).pl, false),
      'invested_desc': this._numericComparator(h => getMetrics(h).invested, true),
      'invested_asc': this._numericComparator(h => getMetrics(h).invested, false),
      'current_desc': this._numericComparator(h => getMetrics(h).current, true),
      'current_asc': this._numericComparator(h => getMetrics(h).current, false),
      'day_change_desc': this._numericComparator(h => getMetrics(h).dayChange, true),
      'day_change_asc': this._numericComparator(h => getMetrics(h).dayChange, false),
      'qty_desc': this._numericComparator(h => getMetrics(h).qty, true),
      'qty_asc': this._numericComparator(h => getMetrics(h).qty, false),
      'avg_desc': this._numericComparator(h => getMetrics(h).avg, true),
      'avg_asc': this._numericComparator(h => getMetrics(h).avg, false),
      'ltp_desc': this._numericComparator(h => getMetrics(h).ltp, true),
      'ltp_asc': this._numericComparator(h => getMetrics(h).ltp, false),
      'exchange_asc': this._stringComparator(h => h.exchange, false),
      'exchange_desc': this._stringComparator(h => h.exchange, true),
      'account_asc': this._stringComparator(h => h.account, false),
      'account_desc': this._stringComparator(h => h.account, true),
      'symbol_asc': this._stringComparator(h => h.tradingsymbol, false),
      'symbol_desc': this._stringComparator(h => h.tradingsymbol, true)
    };

    const comparator = comparators[sortBy];
    return comparator ? sorted.sort(comparator) : holdings;
  }

  /**
   * Sort ETFs array based on selected criteria (same logic as stocks)
   * @param {Array} holdings - ETF holdings array
   * @param {string} sortBy - Sort criteria
   * @returns {Array} Sorted array
   */
  sortETFs(holdings, sortBy = 'default') {
    return this.sortStocks(holdings, sortBy);
  }

  /**
   * Sort mutual funds array based on selected criteria
   * @param {Array} mfHoldings - MF holdings array
   * @param {string} sortBy - Sort criteria
   * @returns {Array} Sorted array
   */
  sortMF(mfHoldings, sortBy = 'default') {
    if (sortBy === 'default' || !mfHoldings || mfHoldings.length === 0) {
      return mfHoldings;
    }

    const sorted = [...mfHoldings];

    // Cache metrics to avoid recalculating per comparison
    const metricsCache = new WeakMap();
    const getMetrics = (h) => {
      if (!metricsCache.has(h)) metricsCache.set(h, Calculator.calculateMFMetrics(h));
      return metricsCache.get(h);
    };

    // Map sort criteria to comparator functions
    const comparators = {
      'pl_pct_desc': this._numericComparator(h => getMetrics(h).plPct, true),
      'pl_pct_asc': this._numericComparator(h => getMetrics(h).plPct, false),
      'pl_desc': this._numericComparator(h => getMetrics(h).pl, true),
      'pl_asc': this._numericComparator(h => getMetrics(h).pl, false),
      'invested_desc': this._numericComparator(h => getMetrics(h).invested, true),
      'invested_asc': this._numericComparator(h => getMetrics(h).invested, false),
      'current_desc': this._numericComparator(h => getMetrics(h).current, true),
      'current_asc': this._numericComparator(h => getMetrics(h).current, false),
      'qty_desc': this._numericComparator(h => getMetrics(h).qty, true),
      'qty_asc': this._numericComparator(h => getMetrics(h).qty, false),
      'avg_desc': this._numericComparator(h => getMetrics(h).avg, true),
      'avg_asc': this._numericComparator(h => getMetrics(h).avg, false),
      'nav_desc': this._numericComparator(h => getMetrics(h).nav, true),
      'nav_asc': this._numericComparator(h => getMetrics(h).nav, false),
      'account_asc': this._stringComparator(h => h.account, false),
      'account_desc': this._stringComparator(h => h.account, true),
      'name_asc': this._stringComparator(h => h.fund || h.tradingsymbol, false),
      'name_desc': this._stringComparator(h => h.fund || h.tradingsymbol, true)
    };

    const comparator = comparators[sortBy];
    return comparator ? sorted.sort(comparator) : mfHoldings;
  }

  setStocksSortOrder(sortBy) {
    this.stocksSortOrder = sortBy;
  }

  setETFSortOrder(sortBy) {
    this.etfSortOrder = sortBy;
  }

  setMFSortOrder(sortBy) {
    this.mfSortOrder = sortBy;
  }

  getStocksSortOrder() {
    return this.stocksSortOrder;
  }

  getETFSortOrder() {
    return this.etfSortOrder;
  }

  getMFSortOrder() {
    return this.mfSortOrder;
  }

  /**
   * Sort physical gold array based on selected criteria
   * @param {Array} holdings - Physical gold holdings array
   * @param {string} sortBy - Sort criteria
   * @returns {Array} Sorted array
   */
  sortPhysicalGold(holdings, sortBy = 'default') {
    if (sortBy === 'default' || !holdings || holdings.length === 0) {
      return holdings;
    }

    const sorted = [...holdings];

    // Map sort criteria to comparator functions
    const comparators = {
      'date_desc': this._numericComparator(h => new Date(h.date || 0).getTime(), true),
      'date_asc': this._numericComparator(h => new Date(h.date || 0).getTime(), false),
      'weight_desc': this._numericComparator(h => h.weight_gms || 0, true),
      'weight_asc': this._numericComparator(h => h.weight_gms || 0, false),
      'bought_rate_desc': this._numericComparator(h => h.bought_ibja_rate_per_gm || 0, true),
      'bought_rate_asc': this._numericComparator(h => h.bought_ibja_rate_per_gm || 0, false),
      'latest_rate_desc': this._numericComparator(h => h.latest_ibja_price_per_gm || 0, true),
      'latest_rate_asc': this._numericComparator(h => h.latest_ibja_price_per_gm || 0, false),
      'pl_desc': this._numericComparator(h => h.pl || 0, true),
      'pl_asc': this._numericComparator(h => h.pl || 0, false),
      'outlet_asc': this._stringComparator(h => h.retail_outlet, false),
      'outlet_desc': this._stringComparator(h => h.retail_outlet, true),
      'purity_asc': this._stringComparator(h => h.purity, false),
      'purity_desc': this._stringComparator(h => h.purity, true),
      'type_asc': this._stringComparator(h => h.type, false),
      'type_desc': this._stringComparator(h => h.type, true)
    };

    const comparator = comparators[sortBy];
    return comparator ? sorted.sort(comparator) : holdings;
  }

  setPhysicalGoldSortOrder(sortBy) {
    this.physicalGoldSortOrder = sortBy;
  }

  getPhysicalGoldSortOrder() {
    return this.physicalGoldSortOrder;
  }

  /**
   * Sort fixed deposits array based on selected criteria
   * @param {Array} deposits - Fixed deposits array
   * @param {string} sortBy - Sort criteria
   * @returns {Array} Sorted array
   */
  sortFixedDeposits(deposits, sortBy = 'default') {
    if (sortBy === 'default' || !deposits || deposits.length === 0) {
      return deposits;
    }

    const sorted = [...deposits];

    // Map sort criteria to comparator functions
    const comparators = {
      'date_desc': this._dateComparator(d => d.original_investment_date || d.deposited_on, true),
      'date_asc': this._dateComparator(d => d.original_investment_date || d.deposited_on, false),
      'reinvested_date_desc': this._dateComparator(d => d.reinvested_date || d.reinvested_on, true),
      'reinvested_date_asc': this._dateComparator(d => d.reinvested_date || d.reinvested_on, false),
      'amount_desc': this._numericComparator(d => d.original_amount || d.amount || 0, true),
      'amount_asc': this._numericComparator(d => d.original_amount || d.amount || 0, false),
      'reinvested_amount_desc': this._numericComparator(d => d.reinvested_amount || 0, true),
      'reinvested_amount_asc': this._numericComparator(d => d.reinvested_amount || 0, false),
      'roi_desc': this._numericComparator(d => d.interest_rate || 0, true),
      'roi_asc': this._numericComparator(d => d.interest_rate || 0, false),
      'bank_asc': this._stringComparator(d => d.bank_name, false),
      'bank_desc': this._stringComparator(d => d.bank_name, true),
      'maturity_desc': this._dateComparator(d => d.maturity_date, true),
      'maturity_asc': this._dateComparator(d => d.maturity_date, false),
      'current_desc': this._numericComparator(d => d.current_value || 0, true),
      'current_asc': this._numericComparator(d => d.current_value || 0, false),
      'account_asc': this._stringComparator(d => d.account, false),
      'account_desc': this._stringComparator(d => d.account, true)
    };

    const comparator = comparators[sortBy];
    return comparator ? sorted.sort(comparator) : deposits;
  }

  setFixedDepositsSortOrder(sortBy) {
    this.fixedDepositsSortOrder = sortBy;
  }

  getFixedDepositsSortOrder() {
    return this.fixedDepositsSortOrder;
  }

  /**
   * Sort FD summary data
   */
  sortFDSummary(summaries, sortBy = 'default') {
    const sorted = [...summaries];

    if (sortBy === 'default') {
      return sorted;
    }

    const comparators = {
      'bank_asc': this._stringComparator(s => s.bank, false),
      'bank_desc': this._stringComparator(s => s.bank, true),
      'account_asc': this._stringComparator(s => s.account, false),
      'account_desc': this._stringComparator(s => s.account, true),
      'deposited_desc': this._numericComparator(s => s.totalDeposited, true),
      'deposited_asc': this._numericComparator(s => s.totalDeposited, false),
      'current_desc': this._numericComparator(s => s.totalCurrentValue, true),
      'current_asc': this._numericComparator(s => s.totalCurrentValue, false),
      'returns_desc': this._numericComparator(s => s.totalReturns, true),
      'returns_asc': this._numericComparator(s => s.totalReturns, false)
    };

    const comparator = comparators[sortBy];
    return comparator ? sorted.sort(comparator) : summaries;
  }

  setFDSummarySortOrder(sortBy) {
    this.fdSummarySortOrder = sortBy;
  }

  getFDSummarySortOrder() {
    return this.fdSummarySortOrder;
  }
}

export default SortManager;
