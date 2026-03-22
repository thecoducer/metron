/* Metron - Summary Module */

import { Formatter } from './utils.js';

// Element ID constants
const ELEMENT_IDS = {
  STOCK: {
    INVESTED: 'total_invested',
    CURRENT: 'current_value',
    PL: 'total_pl',
    PL_PCT: 'total_pl_pct'
  },
  ETF: {
    INVESTED: 'etf_total_invested',
    CURRENT: 'etf_current_value',
    PL: 'etf_total_pl',
    PL_PCT: 'etf_total_pl_pct'
  },
  GOLD: {
    INVESTED: 'gold_total_invested',
    CURRENT: 'gold_current_value',
    PL: 'gold_total_pl',
    PL_PCT: 'gold_total_pl_pct'
  },
  GOLD_ETF: {
    INVESTED: 'gold_etf_total_invested',
    CURRENT: 'gold_etf_current_value',
    PL: 'gold_etf_total_pl',
    PL_PCT: 'gold_etf_total_pl_pct'
  },
  GOLD_SGB: {
    INVESTED: 'gold_sgb_total_invested',
    CURRENT: 'gold_sgb_current_value',
    PL: 'gold_sgb_total_pl',
    PL_PCT: 'gold_sgb_total_pl_pct'
  },
  GOLD_PHYSICAL: {
    INVESTED: 'gold_physical_total_invested',
    CURRENT: 'gold_physical_current_value',
    PL: 'gold_physical_total_pl',
    PL_PCT: 'gold_physical_total_pl_pct'
  },
  SILVER: {
    INVESTED: 'silver_total_invested',
    CURRENT: 'silver_current_value',
    PL: 'silver_total_pl',
    PL_PCT: 'silver_total_pl_pct'
  },
  MF: {
    INVESTED: 'mf_total_invested',
    CURRENT: 'mf_current_value',
    PL: 'mf_total_pl',
    PL_PCT: 'mf_total_pl_pct'
  },
  FD: {
    INVESTED: 'fd_total_invested',
    MATURITY: 'fd_maturity_value',
    PL: 'fd_total_pl',
    PL_PCT: 'fd_total_pl_pct'
  },
  COMBINED: {
    INVESTED: 'combined_total_invested',
    CURRENT: 'combined_current_value',
    PL: 'combined_total_pl',
    PL_PCT: 'combined_total_pl_pct'
  }
};

class SummaryManager {
  constructor() {
    // store last totals so strip can render without new data fetch
    this._lastCombinedGold = { invested: 0, current: 0, pl: 0, plPct: 0 };
    this._lastGoldBreakdown = {
      etf: { invested: 0, current: 0, pl: 0, plPct: 0 },
      sgb: { invested: 0, current: 0, pl: 0, plPct: 0 },
      physical: { invested: 0, current: 0, pl: 0, plPct: 0 }
    };
  }

  /**
   * Update all summary cards with provided totals
   * @param {Object} stockTotals - { invested, current, pl, plPct }
   * @param {Object} etfTotals - { invested, current, pl, plPct } (excludes Gold/Silver ETFs)
   * @param {Object} goldTotals - { invested, current, pl, plPct } (combined stock/ETF/physical)
   * @param {Object} silverTotals - { invested, current, pl, plPct }
   * @param {Object} mfTotals - { invested, current, pl, plPct }
   * @param {Object} fdTotals - { invested, maturity, returns, returnsPct }
   * @param {boolean} isUpdating - Whether refresh/update is in progress
   * @param {Object|null} goldETFTotals - (optional) ETF portion of gold
   * @param {Object|null} sgbTotals - (optional) SGB portion of gold
   * @param {Object|null} physicalGoldTotals - (optional) physical gold portion
   */
  updateAllSummaries(stockTotals, etfTotals, goldTotals, silverTotals, mfTotals, fdTotals, isUpdating = false, goldETFTotals = null, sgbTotals = null, physicalGoldTotals = null) {
    // Provide default values if undefined
    const stock = stockTotals || { invested: 0, current: 0, pl: 0, plPct: 0 };
    const etf = etfTotals || { invested: 0, current: 0, pl: 0, plPct: 0 };
    const gold = goldTotals || { invested: 0, current: 0, pl: 0, plPct: 0 };
    const silver = silverTotals || { invested: 0, current: 0, pl: 0, plPct: 0 };
    const mf = mfTotals || { invested: 0, current: 0, pl: 0, plPct: 0 };
    const fd = fdTotals || { invested: 0, maturity: 0, returns: 0, returnsPct: 0 };

    // Calculate combined totals (FD maturity counts as "current")
    const combinedInvested = stock.invested + etf.invested + gold.invested + silver.invested + mf.invested + fd.invested;
    const combinedCurrent = stock.current + etf.current + gold.current + silver.current + mf.current + fd.maturity;
    const combinedPL = combinedCurrent - combinedInvested;
    const combinedPLPct = combinedInvested ? (combinedPL / combinedInvested * 100) : 0;

    // Calculate allocation percentages
    const stockAllocation = combinedInvested ? (stock.invested / combinedInvested * 100) : 0;
    const etfAllocation = combinedInvested ? (etf.invested / combinedInvested * 100) : 0;
    const goldAllocation = combinedInvested ? (gold.invested / combinedInvested * 100) : 0;
    const silverAllocation = combinedInvested ? (silver.invested / combinedInvested * 100) : 0;
    const mfAllocation = combinedInvested ? (mf.invested / combinedInvested * 100) : 0;
    const fdAllocation = combinedInvested ? (fd.invested / combinedInvested * 100) : 0;

    // Update allocation percentages
    this._updateAllocationPercentage('stocks_allocation_pct', stockAllocation);
    this._updateAllocationPercentage('etf_allocation_pct', etfAllocation);
    this._updateAllocationPercentage('gold_allocation_pct', goldAllocation);
    this._updateAllocationPercentage('silver_allocation_pct', silverAllocation);
    this._updateAllocationPercentage('mf_allocation_pct', mfAllocation);
    this._updateAllocationPercentage('fd_allocation_pct', fdAllocation);

    // Update allocation bar segments
    this._updateAllocationBar({
      stocks: stockAllocation,
      etf: etfAllocation,
      mf: mfAllocation,
      gold: goldAllocation,
      silver: silverAllocation,
      fd: fdAllocation
    });

    // remember totals so drawer can re-render later
    this._lastCombinedGold = gold;
    this._lastGoldBreakdown = {
      etf: goldETFTotals || { invested:0, current:0, pl:0, plPct:0 },
      sgb: sgbTotals || { invested:0, current:0, pl:0, plPct:0 },
      physical: physicalGoldTotals || { invested:0, current:0, pl:0, plPct:0 }
    };

    // Update all cards (non-gold cards unchanged)
    this._updateStockCard(stock);
    this._updateETFCard(etf);
    this._refreshGoldCard();
    this._updateSilverCard(silver);
    this._updateMFCard(mf);
    this._updateFDCard(fd);
    this._updateCombinedCard({
      invested: combinedInvested,
      current: combinedCurrent,
      pl: combinedPL,
      plPct: combinedPLPct
    });

    // Update portfolio snapshot grid (pass allocation % for label strip)
    this._updateSnapshotGrid(stock, mf, etf, gold, silver, fd, {
      stocks: stockAllocation, mf: mfAllocation, etf: etfAllocation,
      gold: goldAllocation, silver: silverAllocation, fd: fdAllocation
    });
  }

  _updateSnapshotCell(prefix, invested, current, pl, plPct, allocPct) {
    const currentEl = document.getElementById(`snap_${prefix}_current`);
    const investedEl = document.getElementById(`snap_${prefix}_invested`);
    const plEl = document.getElementById(`snap_${prefix}_pl`);
    const pctEl = document.getElementById(`snap_${prefix}_pct`);
    if (!currentEl) return;

    currentEl.innerText = Formatter.formatCurrencyForSummary(current);
    if (investedEl) investedEl.innerText = Formatter.formatCurrencyForSummary(invested);
    if (plEl) {
      plEl.innerText = (pl < 0 ? '-' : '') + Formatter.formatCurrencyForSummary(Math.abs(pl));
      plEl.style.color = Formatter.colorPL(pl);
    }
    if (pctEl) {
      pctEl.innerText = Formatter.formatPercentage(plPct);
      pctEl.style.color = Formatter.colorPL(pl);
    }
    // Show allocation % in label strip tag
    const tagPct = document.querySelector(`[data-snap-pct="${prefix}"]`);
    if (tagPct) {
      tagPct.innerText = allocPct !== null ? allocPct.toFixed(1) + '%' : '';
      tagPct.style.color = '';
    }
  }

  _updateSnapshotGrid(stock, mf, etf, gold, silver, fd, alloc) {
    this._updateSnapshotCell('stocks', stock.invested, stock.current, stock.pl, stock.plPct, alloc.stocks);
    this._updateSnapshotCell('mf', mf.invested, mf.current, mf.pl, mf.plPct, alloc.mf);
    this._updateSnapshotCell('etf', etf.invested, etf.current, etf.pl, etf.plPct, alloc.etf);
    this._updateSnapshotCell('gold', gold.invested, gold.current, gold.pl, gold.plPct, alloc.gold);
    this._updateSnapshotCell('silver', silver.invested, silver.current, silver.pl, silver.plPct, alloc.silver);
    this._updateSnapshotCell('fd', fd.invested, fd.maturity, fd.returns, fd.returnsPct, alloc.fd);
  }

  _updateAllocationPercentage(elementId, percentage) {
    const el = document.getElementById(elementId);
    if (el) {
      el.innerText = percentage.toFixed(1) + '%';
      
      // Set progress bar on parent section summary strip
      const strip = el.closest('.section-summary') || el.closest('.gold-rhythm');
      if (strip) {
        strip.style.setProperty('--allocation-width', `${percentage}%`);
        
        // Set color based on element type
        let color = '#64748b'; // default slate
        if (elementId === 'stocks_allocation_pct') {
          color = '#e11d48'; // rose-red
        } else if (elementId === 'etf_allocation_pct') {
          color = '#7c3aed'; // violet
        } else if (elementId === 'mf_allocation_pct') {
          color = '#0284c7'; // sky blue
        } else if (elementId === 'gold_allocation_pct') {
          color = '#b45309'; // amber
        } else if (elementId === 'silver_allocation_pct') {
          color = '#64748b'; // slate
        } else if (elementId === 'fd_allocation_pct') {
          color = '#0f766e'; // teal
        }
        strip.style.setProperty('--allocation-color', color);
      }
    }
  }

  _updateAllocationBar(allocations) {
    const segmentOrder = ['stocks', 'mf', 'etf', 'gold', 'silver', 'fd'];
    const segmentIds = {
      stocks: 'alloc_seg_stocks',
      etf: 'alloc_seg_etf',
      mf: 'alloc_seg_mf',
      gold: 'alloc_seg_gold',
      silver: 'alloc_seg_silver',
      fd: 'alloc_seg_fd'
    };

    let lastVisibleSeg = null;
    for (const key of segmentOrder) {
      const seg = document.getElementById(segmentIds[key]);
      if (!seg) continue;
      const pct = allocations[key] || 0;
      seg.style.width = `${pct}%`;
      // Reset dynamic border-radius (CSS :first-child handles left side)
      seg.style.borderRadius = '';
      if (pct > 0) lastVisibleSeg = seg;
    }
    // Apply right border-radius to the last visible segment
    if (lastVisibleSeg) {
      lastVisibleSeg.style.borderRadius = '0 5px 5px 0';
    }
  }

  _updateStockCard(totals) {
    this._updateCard(
      ELEMENT_IDS.STOCK.INVESTED,
      ELEMENT_IDS.STOCK.CURRENT,
      ELEMENT_IDS.STOCK.PL,
      ELEMENT_IDS.STOCK.PL_PCT,
      totals
    );
  }

  _updateETFCard(totals) {
    this._updateCard(
      ELEMENT_IDS.ETF.INVESTED,
      ELEMENT_IDS.ETF.CURRENT,
      ELEMENT_IDS.ETF.PL,
      ELEMENT_IDS.ETF.PL_PCT,
      totals
    );
  }

  _updateGoldCard(totals) {
    this._updateCard(
      ELEMENT_IDS.GOLD.INVESTED,
      ELEMENT_IDS.GOLD.CURRENT,
      ELEMENT_IDS.GOLD.PL,
      ELEMENT_IDS.GOLD.PL_PCT,
      totals
    );
  }

  _updateGoldBreakdown(etfTotals, sgbTotals, physicalTotals) {
    // update individual ETF, SGB, and physical rows in the drawer
    this._updateCard(
      ELEMENT_IDS.GOLD_ETF.INVESTED,
      ELEMENT_IDS.GOLD_ETF.CURRENT,
      ELEMENT_IDS.GOLD_ETF.PL,
      ELEMENT_IDS.GOLD_ETF.PL_PCT,
      etfTotals
    );
    this._updateCard(
      ELEMENT_IDS.GOLD_SGB.INVESTED,
      ELEMENT_IDS.GOLD_SGB.CURRENT,
      ELEMENT_IDS.GOLD_SGB.PL,
      ELEMENT_IDS.GOLD_SGB.PL_PCT,
      sgbTotals
    );
    this._updateCard(
      ELEMENT_IDS.GOLD_PHYSICAL.INVESTED,
      ELEMENT_IDS.GOLD_PHYSICAL.CURRENT,
      ELEMENT_IDS.GOLD_PHYSICAL.PL,
      ELEMENT_IDS.GOLD_PHYSICAL.PL_PCT,
      physicalTotals
    );
  }

  _refreshGoldCard() {
    // always show combined totals on the main rhythm values
    this._updateGoldCard(this._lastCombinedGold);
    // always update the breakdown segment values
    this._updateGoldBreakdown(
      this._lastGoldBreakdown.etf,
      this._lastGoldBreakdown.sgb,
      this._lastGoldBreakdown.physical
    );
    // update proportion bar
    this._updateGoldProportionBar();
    // show the strip when any gold value exists
    const rhythm = document.getElementById('gold_summary');
    if (rhythm) {
      rhythm.style.display = '';
    }
  }

  _updateGoldProportionBar() {
    const barEl = document.getElementById('gold_proportion_bar');
    if (!barEl) return;
    const etfVal = Math.abs(this._lastGoldBreakdown.etf.current || 0);
    const physVal = Math.abs(this._lastGoldBreakdown.physical.current || 0);
    const sgbVal = Math.abs(this._lastGoldBreakdown.sgb.current || 0);
    const total = etfVal + physVal + sgbVal;
    if (total === 0) { barEl.innerHTML = ''; return; }
    const pcts = {
      etf: (etfVal / total * 100).toFixed(1),
      physical: (physVal / total * 100).toFixed(1),
      sgb: (sgbVal / total * 100).toFixed(1)
    };
    barEl.innerHTML = ['physical', 'etf', 'sgb']
      .filter(k => parseFloat(pcts[k]) > 0)
      .map(k => `<span class="gold-bar-seg gold-bar-seg--${k}" style="width:${pcts[k]}%"></span>`)
      .join('');
  }

  _updateSilverCard(totals) {
    this._updateCard(
      ELEMENT_IDS.SILVER.INVESTED,
      ELEMENT_IDS.SILVER.CURRENT,
      ELEMENT_IDS.SILVER.PL,
      ELEMENT_IDS.SILVER.PL_PCT,
      totals
    );
  }

  _updateMFCard(totals) {
    this._updateCard(
      ELEMENT_IDS.MF.INVESTED,
      ELEMENT_IDS.MF.CURRENT,
      ELEMENT_IDS.MF.PL,
      ELEMENT_IDS.MF.PL_PCT,
      totals
    );
  }

  _updateFDCard(totals) {
    // Fixed deposits use invested, maturity (instead of current), returns, returnsPct
    const investedEl = document.getElementById(ELEMENT_IDS.FD.INVESTED);
    const maturityEl = document.getElementById(ELEMENT_IDS.FD.MATURITY);
    const plEl = document.getElementById(ELEMENT_IDS.FD.PL);
    const plPctEl = document.getElementById(ELEMENT_IDS.FD.PL_PCT);

    if (!investedEl || !maturityEl || !plEl || !plPctEl) return;

    const invested = isNaN(totals.invested) ? 0 : totals.invested;
    const maturity = isNaN(totals.maturity) ? 0 : totals.maturity;
    const returns = isNaN(totals.returns) ? 0 : totals.returns;
    const returnsPct = isNaN(totals.returnsPct) ? 0 : totals.returnsPct;

    investedEl.innerText = Formatter.formatCurrencyForSummary(invested);
    maturityEl.innerText = Formatter.formatCurrencyForSummary(maturity);
    
    if (returns < 0) {
      plEl.innerText = '-' + Formatter.formatCurrencyForSummary(Math.abs(returns));
    } else {
      plEl.innerText = Formatter.formatCurrencyForSummary(returns);
    }
    plEl.style.color = Formatter.colorPL(returns);
    
    plPctEl.innerText = Formatter.formatPercentage(returnsPct);
    plPctEl.style.color = Formatter.colorPL(returns);
  }

  _updateCombinedCard(totals) {
    this._updateCard(
      ELEMENT_IDS.COMBINED.INVESTED,
      ELEMENT_IDS.COMBINED.CURRENT,
      ELEMENT_IDS.COMBINED.PL,
      ELEMENT_IDS.COMBINED.PL_PCT,
      totals
    );
  }

  _updateCard(investedId, currentId, plId, plPctId, totals) {
    const investedEl = document.getElementById(investedId);
    const currentEl = document.getElementById(currentId);
    const plEl = document.getElementById(plId);
    const plPctEl = document.getElementById(plPctId);

    // Safeguard against NaN values
    const invested = isNaN(totals.invested) ? 0 : totals.invested;
    const current = isNaN(totals.current) ? 0 : totals.current;
    const pl = isNaN(totals.pl) ? 0 : totals.pl;
    const plPct = isNaN(totals.plPct) ? 0 : totals.plPct;

    // Format invested, current, and P/L using summary currency formatter (respects compact toggle)
    investedEl.innerText = Formatter.formatCurrencyForSummary(invested);
    currentEl.innerText = Formatter.formatCurrencyForSummary(current);
    // Show '-' before currency for negative P/L
    if (pl < 0) {
      plEl.innerText = '-' + Formatter.formatCurrencyForSummary(Math.abs(pl));
    } else {
      plEl.innerText = Formatter.formatCurrencyForSummary(pl);
    }
    plEl.style.color = Formatter.colorPL(pl);
    // Show only one sign before percent value, use absolute value
    if (pl < 0) {
      plPctEl.innerText = '-' + Math.abs(plPct).toFixed(2) + '%';
    } else if (pl > 0) {
      plPctEl.innerText = '+' + Math.abs(plPct).toFixed(2) + '%';
    } else {
      plPctEl.innerText = '0.00%';
    }
    plPctEl.style.color = Formatter.colorPL(pl);
  }
}

export default SummaryManager;
