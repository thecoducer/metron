/* Metron - Data Management Module */
import { metronFetch } from './utils.js';

class DataManager {
  constructor() {
    this.latestStocks = [];
    this.latestMFHoldings = [];
    this.latestSIPs = [];
    this.latestPhysicalGold = [];
    this.latestFixedDeposits = [];
    this.latestFDSummary = [];
    this.latestProvidentFund = [];
    this.lastRenderedJSON = "";
    this.lastRenderedMFJSON = "";
    this.lastRenderedSIPsJSON = "";
    this.lastRenderedPhysicalGoldJSON = "";
    this.lastRenderedFixedDepositsJSON = "";
    this.lastRenderedFDSummaryJSON = "";
    this.lastRenderedProvidentFundJSON = "";
  }

  async _fetchEndpoint(endpoint) {
    const response = await metronFetch(endpoint);
    return await response.json();
  }

  async fetchStocks() {
    return this._fetchEndpoint('/api/stocks_data');
  }

  async fetchMFHoldings() {
    return this._fetchEndpoint('/api/mf_holdings_data');
  }

  async fetchSIPs() {
    return this._fetchEndpoint('/api/sips_data');
  }

  async fetchPhysicalGold() {
    return this._fetchEndpoint('/api/physical_gold_data');
  }

  async fetchFixedDeposits() {
    return this._fetchEndpoint('/api/fixed_deposits_data');
  }

  async fetchProvidentFund() {
    return this._fetchEndpoint('/api/provident_fund_data');
  }

  async fetchStatus() {
    return this._fetchEndpoint('/api/status');
  }

  async fetchPortfolioData() {
    const resp = await this._fetchEndpoint('/api/data/portfolio');
    return {
      stocks: resp.stocks || [],
      mfHoldings: resp.mfHoldings || [],
      sips: resp.sips || [],
      status: resp.status || {},
    };
  }

  async fetchSheetsData() {
    const resp = await this._fetchEndpoint('/api/data/sheets');
    const fixedDeposits = resp.fixedDeposits || [];
    return {
      physicalGold: resp.physicalGold || [],
      fixedDeposits,
      providentFund: resp.providentFund || [],
      fdSummary: this._computeFDSummary(fixedDeposits),
      status: resp.status || {},
    };
  }

  async fetchAllData() {
    const resp = await this._fetchEndpoint('/api/all_data');
    const stocks = resp.stocks || [];
    const mfHoldings = resp.mfHoldings || [];
    const sips = resp.sips || [];
    const physicalGold = resp.physicalGold || [];
    const fixedDeposits = resp.fixedDeposits || [];
    const providentFund = resp.providentFund || [];
    const status = resp.status || {};
    const fdSummary = this._computeFDSummary(fixedDeposits);
    return { stocks, mfHoldings, sips, physicalGold, fixedDeposits, providentFund, fdSummary, status };
  }

  _computeFDSummary(deposits) {
    if (!deposits || !deposits.length) return [];
    const groups = {};
    for (const d of deposits) {
      const key = `${d.bank_name || 'Unknown'}|${d.account || 'Unknown'}`;
      if (!groups[key]) {
        groups[key] = { bank: d.bank_name || 'Unknown', account: d.account || 'Unknown', totalDeposited: 0, totalCurrentValue: 0, totalReturns: 0 };
      }
      groups[key].totalDeposited += d.original_amount || 0;
      groups[key].totalCurrentValue += d.current_value || 0;
    }
    for (const g of Object.values(groups)) {
      g.totalReturns = g.totalCurrentValue - g.totalDeposited;
    }
    return Object.values(groups);
  }

  _updateData(data, currentData, lastJSON, forceUpdate) {
    const dataJSON = JSON.stringify(data);
    if (dataJSON !== lastJSON || forceUpdate) {
      return { updated: true, newData: data, newJSON: dataJSON };
    }
    return { updated: false, newData: currentData, newJSON: lastJSON };
  }

  updateStocks(stocks, forceUpdate = false) {
    const result = this._updateData(stocks, this.latestStocks, this.lastRenderedJSON, forceUpdate);
    if (result.updated) {
      this.latestStocks = result.newData;
      this.lastRenderedJSON = result.newJSON;
    }
    return result.updated;
  }

  updateMFHoldings(mfHoldings, forceUpdate = false) {
    const result = this._updateData(mfHoldings, this.latestMFHoldings, this.lastRenderedMFJSON, forceUpdate);
    if (result.updated) {
      this.latestMFHoldings = result.newData;
      this.lastRenderedMFJSON = result.newJSON;
    }
    return result.updated;
  }

  updateSIPs(sips, forceUpdate = false) {
    const result = this._updateData(sips, this.latestSIPs, this.lastRenderedSIPsJSON, forceUpdate);
    if (result.updated) {
      this.latestSIPs = result.newData;
      this.lastRenderedSIPsJSON = result.newJSON;
    }
    return result.updated;
  }

  getStocks() {
    return this.latestStocks;
  }

  getMFHoldings() {
    return this.latestMFHoldings;
  }

  getSIPs() {
    return this.latestSIPs;
  }

  updatePhysicalGold(physicalGold, forceUpdate = false) {
    const result = this._updateData(physicalGold, this.latestPhysicalGold, this.lastRenderedPhysicalGoldJSON, forceUpdate);
    if (result.updated) {
      this.latestPhysicalGold = result.newData;
      this.lastRenderedPhysicalGoldJSON = result.newJSON;
    }
    return result.updated;
  }

  getPhysicalGold() {
    return this.latestPhysicalGold;
  }

  updateFixedDeposits(fixedDeposits, forceUpdate = false) {
    const result = this._updateData(fixedDeposits, this.latestFixedDeposits, this.lastRenderedFixedDepositsJSON, forceUpdate);
    if (result.updated) {
      this.latestFixedDeposits = result.newData;
      this.lastRenderedFixedDepositsJSON = result.newJSON;
    }
    return result.updated;
  }

  getFixedDeposits() {
    return this.latestFixedDeposits;
  }

  updateProvidentFund(providentFund, forceUpdate = false) {
    const result = this._updateData(providentFund, this.latestProvidentFund, this.lastRenderedProvidentFundJSON, forceUpdate);
    if (result.updated) {
      this.latestProvidentFund = result.newData;
      this.lastRenderedProvidentFundJSON = result.newJSON;
    }
    return result.updated;
  }

  getProvidentFund() {
    return this.latestProvidentFund;
  }

  updateFDSummary(fdSummary, forceUpdate = false) {
    const result = this._updateData(fdSummary, this.latestFDSummary, this.lastRenderedFDSummaryJSON, forceUpdate);
    if (result.updated) {
      this.latestFDSummary = result.newData;
      this.lastRenderedFDSummaryJSON = result.newJSON;
    }
    return result.updated;
  }

  getFDSummary() {
    return this.latestFDSummary;
  }

  async triggerRefresh() {
    const response = await metronFetch('/api/refresh', { method: 'POST' });
    if (response.status !== 202) {
      const data = await response.json();
      throw new Error(data.error || 'Unknown error');
    }
    return await response.json();
  }
}

export default DataManager;
