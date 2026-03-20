// Nifty 50 Page Application
import { Formatter, metronFetch } from './utils.js';
import PaginationManager from './pagination.js';
import IndexTicker from './index-ticker.js';

class Nifty50App {
  constructor() {
    this.nifty50Data = [];
    this.nifty50SortOrder = 'default';
    this.nifty50Pagination = new PaginationManager(50, 1);
    this.lastNifty50UpdatedAt = null;
  }

  async init() {
    this.setupTheme();
    this.setupHeaderSortListeners();
    this.renderNifty50Table();
    this._startRelativeStatusUpdater();
    new IndexTicker().init();

    try {
      // Check backend state before deciding what to do
      this._updateRefreshButton(true);
      this._setUpdatingUI();
      const status = await this._fetchStatus();

      if (this._isStatusUpdating(status)) {
        // Backend is already fetching — just wait for it
        await this._pollUntilDone();
      } else if (status.nifty50_last_updated) {
        // Data already fetched (pill navigation) — just grab it
      } else {
        // No data yet — trigger a refresh
        try {
          await metronFetch('/api/refresh', { method: 'POST' });
        } catch (e) { /* 409 = already in progress, fine */ }
        await this._pollUntilDone();
      }

      await this.updateNifty50();
      const finalStatus = await this._fetchStatus();
      this._applyStatus(finalStatus);
    } catch (e) {
      // Fallback: still try to show whatever data is available
      await this.updateNifty50();
      this._updateRefreshButton(false);
    }
  }

  setupHeaderSortListeners() {
    const table = document.getElementById('nifty50Table');
    if (!table) return;

    const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
    sortableHeaders.forEach((header) => {
      header.classList.add('sortable-header');
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');

      const runSort = () => {
        const nextSort = this.getNextHeaderSortOrder(header);
        this.sortNifty50Table(nextSort);
        this.syncHeaderSortIndicators();
      };

      header.addEventListener('click', runSort);
      header.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          runSort();
        }
      });
    });

    this.syncHeaderSortIndicators();
  }

  getNextHeaderSortOrder(header) {
    const ascSort = header.dataset.sortAsc;
    const descSort = header.dataset.sortDesc;
    const defaultDirection = header.dataset.sortDefault || 'desc';

    if (this.nifty50SortOrder === descSort) return ascSort;
    if (this.nifty50SortOrder === ascSort) return descSort;
    return defaultDirection === 'asc' ? ascSort : descSort;
  }

  syncHeaderSortIndicators() {
    const table = document.getElementById('nifty50Table');
    if (!table) return;

    const sortableHeaders = table.querySelectorAll('th[data-sort-asc][data-sort-desc]');
    sortableHeaders.forEach((header) => {
      const ascSort = header.dataset.sortAsc;
      const descSort = header.dataset.sortDesc;

      header.classList.remove('sorted-asc', 'sorted-desc');
      header.setAttribute('aria-sort', 'none');

      if (this.nifty50SortOrder === ascSort) {
        header.classList.add('sorted-asc');
        header.setAttribute('aria-sort', 'ascending');
      } else if (this.nifty50SortOrder === descSort) {
        header.classList.add('sorted-desc');
        header.setAttribute('aria-sort', 'descending');
      }
    });
  }

  setupTheme() {
    const theme = localStorage.getItem('theme') || 'light';
    document.body.classList.toggle('dark-theme', theme === 'dark');
    
    const themeLabel = document.getElementById('theme_toggle_label');
    if (themeLabel) {
      themeLabel.classList.toggle('toggle-on', theme === 'dark');
    }
  }

  async _fetchStatus() {
    const resp = await metronFetch('/api/status');
    if (!resp.ok) throw new Error(`Status fetch failed: ${resp.status}`);
    return resp.json();
  }

  _applyStatus(status) {
    const statusTag = document.getElementById('status_tag');
    const statusText = document.getElementById('status_text');
    const isUpdating = this._isStatusUpdating(status);

    statusTag.classList.toggle('updating', isUpdating);
    statusTag.classList.toggle('updated', !isUpdating);
    statusTag.classList.toggle('market_closed', status.market_open === false);

    if (isUpdating) {
      statusText.innerText = 'updating';
    } else {
      this.lastNifty50UpdatedAt = status.nifty50_last_updated || null;
      statusText.innerText = this._formatStatusUpdatedText();
    }

    this._updateRefreshButton(isUpdating);
  }

  async _pollUntilDone() {
    const POLL_INTERVAL = 2000;
    const MAX_POLLS = 90;
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, POLL_INTERVAL));
      const status = await this._fetchStatus();
      if (!this._isStatusUpdating(status)) return status;
    }
    return this._fetchStatus();
  }

  _isStatusUpdating(status) {
    return status.nifty50_state === 'updating';
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

  _setUpdatingUI() {
    const statusTag = document.getElementById('status_tag');
    const statusText = document.getElementById('status_text');
    statusTag.className = 'updating';
    statusText.innerText = 'updating';
    this._updateRefreshButton(true);
  }

  _formatStatusUpdatedText() {
    if (!this.lastNifty50UpdatedAt) return 'updated';
    const relative = Formatter.formatRelativeTime(this.lastNifty50UpdatedAt);
    return relative ? `updated ${relative}` : 'updated';
  }

  _refreshRelativeStatusText() {
    const statusText = document.getElementById('status_text');
    if (!statusText) return;
    const statusTag = document.getElementById('status_tag');
    if (statusTag?.classList.contains('updating')) return;
    statusText.innerText = this._formatStatusUpdatedText();
  }

  _startRelativeStatusUpdater() {
    if (this.relativeStatusTimer) clearInterval(this.relativeStatusTimer);
    this.relativeStatusTimer = setInterval(() => this._refreshRelativeStatusText(), 60_000);
  }

  async updateNifty50() {
    try {
      const response = await metronFetch('/api/nifty50_data');
      if (!response.ok) throw new Error('Failed to fetch Nifty 50 data');
      
      const nifty50Data = await response.json();
      this.nifty50Data = nifty50Data;
      this.renderNifty50Table();
    } catch (error) {
      console.error('Error fetching Nifty 50 data:', error);
    }
  }

  sortNifty50Data(data, sortOrder) {
    const sorted = [...data];
    
    switch (sortOrder) {
      case 'change_desc':
        return sorted.sort((a, b) => b.pChange - a.pChange);
      case 'change_asc':
        return sorted.sort((a, b) => a.pChange - b.pChange);
      case 'ltp_desc':
        return sorted.sort((a, b) => b.ltp - a.ltp);
      case 'ltp_asc':
        return sorted.sort((a, b) => a.ltp - b.ltp);
      case 'symbol_asc':
        return sorted.sort((a, b) => a.symbol.localeCompare(b.symbol));
      case 'symbol_desc':
        return sorted.sort((a, b) => b.symbol.localeCompare(a.symbol));
      case 'name_asc':
        return sorted.sort((a, b) => a.name.localeCompare(b.name));
      case 'name_desc':
        return sorted.sort((a, b) => b.name.localeCompare(a.name));
      case 'open_desc':
        return sorted.sort((a, b) => (b.open || 0) - (a.open || 0));
      case 'open_asc':
        return sorted.sort((a, b) => (a.open || 0) - (b.open || 0));
      case 'high_desc':
        return sorted.sort((a, b) => (b.high || 0) - (a.high || 0));
      case 'high_asc':
        return sorted.sort((a, b) => (a.high || 0) - (b.high || 0));
      case 'low_desc':
        return sorted.sort((a, b) => (b.low || 0) - (a.low || 0));
      case 'low_asc':
        return sorted.sort((a, b) => (a.low || 0) - (b.low || 0));
      case 'close_desc':
        return sorted.sort((a, b) => (b.close || 0) - (a.close || 0));
      case 'close_asc':
        return sorted.sort((a, b) => (a.close || 0) - (b.close || 0));
      default:
        return sorted;
    }
  }

  renderNifty50Table(status = null) {
    const tbody = document.getElementById('nifty50_tbody');
    if (!tbody) return;
    
    const loadingRow = document.getElementById('nifty50_table_loading');
    const isUpdating = status ? this._isStatusUpdating(status) : false;
    const hasData = this.nifty50Data && this.nifty50Data.length > 0;
    
    // Show loading row if: (updating AND no data) OR (no data at all)
    if (loadingRow) {
      const shouldShowLoading = !hasData || (isUpdating && !hasData);
      loadingRow.style.display = shouldShowLoading ? 'table-row' : 'none';
    }
    
    // If no data, don't try to render table rows
    if (!hasData) return;

    const updateClass = isUpdating ? 'updating-field' : '';
    const sortedData = this.sortNifty50Data(this.nifty50Data, this.nifty50SortOrder);
    
    // Use pagination manager
    const paginationInfo = this.nifty50Pagination.paginate(sortedData);
    const { pageData } = paginationInfo;

    tbody.innerHTML = pageData.map(stock => {
      const changeClass = stock.change >= 0 ? 'positive' : 'negative';
      const changeSign = Formatter.formatSign(stock.change);
      const changePctFormatted = Formatter.formatPercentage(stock.pChange);
      
      return `
        <tr>
          <td class="${updateClass}"><strong>${stock.symbol}</strong></td>
          <td class="${updateClass}">${stock.name}</td>
          <td class="${updateClass}">${this._formatNiftyNumber(stock.ltp)}</td>
          <td class="${changeClass} ${updateClass}">
            ${changeSign}${this._formatNiftyNumber(Math.abs(stock.change))}
            <span class="pl_pct_small">${changePctFormatted}</span>
          </td>
          <td class="${updateClass}">${this._formatNiftyNumber(stock.open)}</td>
          <td class="${updateClass}">${this._formatNiftyNumber(stock.high)}</td>
          <td class="${updateClass}">${this._formatNiftyNumber(stock.low)}</td>
          <td class="${updateClass}">${this._formatNiftyNumber(stock.close)}</td>
        </tr>
      `.trim();
    }).join('');
    
    // Update pagination UI
    PaginationManager.updatePaginationUI(
      paginationInfo,
      'nifty50_pagination_info',
      'nifty50_pagination_buttons',
      'goToNifty50Page',
      'stocks'
    );
  }

  _formatNiftyNumber(n) {
    // Use shared formatting utility with Indian locale
    return Formatter.formatNumberWithLocale(n, 2);
  }

  sortNifty50Table(sortOrder) {
    this.nifty50SortOrder = sortOrder;
    this.nifty50Pagination.goToPage(1);  // Reset to first page
    this.renderNifty50Table();
    this.syncHeaderSortIndicators();
  }

  changeNifty50PageSize(size) {
    this.nifty50Pagination.changePageSize(size);
    this.renderNifty50Table();
  }

  goToNifty50Page(page) {
    this.nifty50Pagination.goToPage(page);
    this.renderNifty50Table();
  }

  cleanup() {
    if (this.relativeStatusTimer) clearInterval(this.relativeStatusTimer);
  }
}

window.handleLogout = function() {
  metronFetch('/api/auth/logout', { method: 'POST' })
    .then(() => { window.location.href = '/'; })
    .catch(() => { window.location.href = '/'; });
};

// Global functions
window.toggleTheme = function() {
  const isDark = document.body.classList.toggle('dark-theme');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  
  const themeLabel = document.getElementById('theme_toggle_label');
  if (themeLabel) {
    themeLabel.classList.toggle('toggle-on', isDark);
  }
};

window.triggerRefresh = async function() {
  const app = window.nifty50App;
  if (!app) return;
  const refreshBtn = document.getElementById('refresh_btn');
  if (refreshBtn?.disabled) return;

  app._updateRefreshButton(true);
  app._setUpdatingUI();

  try {
    const response = await metronFetch('/api/refresh', { method: 'POST' });
    if (!response.ok && response.status !== 409) {
      console.error('Refresh failed:', response.status);
    }
    // Poll until done, then re-fetch data
    await app._pollUntilDone();
    await app.updateNifty50();
  } catch (error) {
    console.error('Error triggering refresh:', error);
  }

  // Apply final state, then stop spinner
  try {
    const status = await app._fetchStatus();
    app._applyStatus(status);
  } catch (e) { /* ignore */ }
  app._updateRefreshButton(false);
};

window.sortNifty50Table = function(sortOrder) {
  if (window.nifty50App) {
    window.nifty50App.sortNifty50Table(sortOrder);
  }
};

window.changeNifty50PageSize = function(size) {
  if (window.nifty50App) {
    window.nifty50App.changeNifty50PageSize(size);
  }
};

window.goToNifty50Page = function(page) {
  if (window.nifty50App) {
    window.nifty50App.goToNifty50Page(page);
  }
};

// Initialize app
window.nifty50App = new Nifty50App();
window.nifty50App.init();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  if (window.nifty50App) {
    window.nifty50App.cleanup();
  }
});
