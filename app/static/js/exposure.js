/* global RefreshUI */
(function() {
  'use strict';

  // ─── Utilities ────────────────────────────────────────────────

  var privacyMode = localStorage.getItem('metron_privacy') === '1';
  var compactMode = localStorage.getItem('metron_compact') === '1';

  function formatAmount(v) {
    if (privacyMode) return '••••';
    if (compactMode) {
      if (v >= 1e7) return '₹' + (v / 1e7).toFixed(2) + ' Cr';
      if (v >= 1e5) return '₹' + (v / 1e5).toFixed(2) + ' L';
      if (v >= 1e3) return '₹' + (v / 1e3).toFixed(1) + 'K';
    }
    return '₹' + v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  function formatPct(v) {
    return v.toFixed(2) + '%';
  }

  // ─── Chart helpers ────────────────────────────────────────────

  // Generate visually distinct colors using golden-angle hue spacing.
  var GOLDEN_ANGLE = 137.508;
  function chartColor(index) {
    var hue = (index * GOLDEN_ANGLE) % 360;
    var dark = isDark();
    var sat = dark ? '55%' : '58%';
    var lum = dark ? '62%' : '56%';
    return 'hsl(' + hue + ',' + sat + ',' + lum + ')';
  }

  function isDark() {
    return document.body.classList.contains('dark-theme');
  }

  // ─── D3 Bar Chart Race ────────────────────────────────────────

  var _raceData = null;
  var _raceResizeTimer = null;

  function buildTopCompaniesChart(companies) {
    _raceData = companies.slice(0, 10);
    _drawRaceChart(_raceData);
  }

  function _drawRaceChart(top10) {
    var container = document.getElementById('topCompaniesChart');
    if (!container || !top10 || !top10.length) return;
    container.innerHTML = '';

    var data = top10.slice(0, 10);
    var maxVal = data[0].holding_amount;

    // Scale bars to 85% max so rank #1 always has room for its stats text
    container.innerHTML = data.map(function(d, i) {
      var barPct = (d.holding_amount / maxVal * 85).toFixed(2);
      var color = chartColor(i);
      return (
        '<div class="rc-row">' +
          '<span class="rc-name" title="' + d.company_name + '">' + d.company_name + '</span>' +
          '<div class="rc-track-area">' +
            '<div class="rc-track"></div>' +
            '<div class="rc-flex">' +
              '<div class="rc-bar" style="background:' + color + '" data-pct="' + barPct + '">' +
                '<span class="rc-rank">' + (i + 1) + '</span>' +
              '</div>' +
              '<div class="rc-stats">' +
                '<span class="rc-val">' + formatAmount(d.holding_amount) + '</span>' +
                '<span class="rc-pct-text">' + d.percentage_of_portfolio.toFixed(2) + '%</span>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    }).join('');

    // Trigger CSS transition after first paint (double rAF ensures width:0 is painted first)
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        container.querySelectorAll('.rc-bar').forEach(function(bar) {
          bar.style.width = bar.dataset.pct + '%';
        });
      });
    });
  }

  // Redraw chart on resize (debounced)
  window.addEventListener('resize', function() {
    clearTimeout(_raceResizeTimer);
    _raceResizeTimer = setTimeout(function() {
      if (_raceData) _drawRaceChart(_raceData);
    }, 200);
  });

  // Redraw chart on dark/light theme toggle (no page refresh needed)
  new MutationObserver(function() {
    if (_raceData) _drawRaceChart(_raceData);
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });

  var SECTOR_PREVIEW_LIMIT = 20;
  var allSectorEntries = [];

  function initSectorEntries(sectorTotals) {
    allSectorEntries = Object.entries(sectorTotals).sort(function(a, b) { return b[1] - a[1]; });
  }

  function buildSectorBars(sectorTotals, totalPortfolioValue) {
    var entries = Object.entries(sectorTotals).sort(function(a, b) { return b[1] - a[1]; });
    var top = entries.slice(0, SECTOR_PREVIEW_LIMIT);
    var container = document.getElementById('sectorBars');
    var maxVal = entries.length ? entries[0][1] : 1;
    container.innerHTML = top.map(function(e, i) {
      var pct = totalPortfolioValue > 0 ? (e[1] / totalPortfolioValue * 100) : 0;
      var barWidth = (e[1] / maxVal * 100).toFixed(1);
      return '<div class="sector-bar-row">' +
        '<span class="sector-bar-label" title="' + e[0] + '">' + e[0] + '</span>' +
        '<div class="sector-bar-track"><div class="sector-bar-fill" style="width:' + barWidth + '%;background:' + chartColor(i) + '"></div></div>' +
        '<span class="sector-bar-pct">' + pct.toFixed(1) + '%</span>' +
        '</div>';
    }).join('');

    if (entries.length > SECTOR_PREVIEW_LIMIT) {
      var footer = document.getElementById('barsViewAllFooter');
      document.getElementById('barsViewAllCount').textContent = entries.length;
      footer.style.display = 'flex';
    }
  }

  // ─── Sector modal ──────────────────────────────────────────────

  function openSectorModal() {
    var total = allSectorEntries.reduce(function(s, e) { return s + e[1]; }, 0);
    document.getElementById('sectorModalTitle').textContent =
      'All Sectors (' + allSectorEntries.length + ')';
    document.getElementById('sectorModalBody').innerHTML = allSectorEntries.map(function(e) {
      var pct = total > 0 ? (e[1] / total * 100).toFixed(1) : '0.0';
      return '<div class="sector-modal-row">' +
        '<span class="sector-modal-name" title="' + e[0] + '">' + e[0] + '</span>' +
        '<span class="sector-modal-value">' + formatAmount(e[1]) + '</span>' +
        '<span class="sector-modal-pct">' + pct + '%</span>' +
        '</div>';
    }).join('');
    document.getElementById('sectorModalOverlay').classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeSectorModal(evt) {
    if (evt && evt.target !== document.getElementById('sectorModalOverlay')) return;
    document.getElementById('sectorModalOverlay').classList.remove('open');
    document.body.style.overflow = '';
  }

  // Expose modal functions globally for onclick handlers
  window.openSectorModal = openSectorModal;
  window.closeSectorModal = closeSectorModal;

  // ─── Fund popup / modal ──────────────────────────────────

  var MOBILE_BREAKPOINT = 768;

  function isMobileView() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  // Create the fund modal overlay once
  var fundModalOverlay = document.createElement('div');
  fundModalOverlay.className = 'fund-modal-overlay';
  fundModalOverlay.id = 'fundModalOverlay';
  fundModalOverlay.innerHTML =
    '<div class="fund-modal">' +
      '<div class="fund-modal-head">' +
        '<h3 class="fund-modal-title" id="fundModalTitle">Held via</h3>' +
        '<button class="fund-modal-close" id="fundModalClose" aria-label="Close">\u2715</button>' +
      '</div>' +
      '<div class="fund-modal-body" id="fundModalBody"></div>' +
    '</div>';
  document.body.appendChild(fundModalOverlay);

  document.getElementById('fundModalClose').addEventListener('click', closeFundModal);
  fundModalOverlay.addEventListener('click', function(e) {
    if (e.target === fundModalOverlay) closeFundModal();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && fundModalOverlay.classList.contains('open')) {
      closeFundModal();
    }
  });

  function closeFundModal() {
    fundModalOverlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  function openFundModal(funds) {
    var body = document.getElementById('fundModalBody');
    var tags = funds.map(function(f) {
      var cls = f === 'Direct' ? 'fund-tag fund-tag--direct' : 'fund-tag';
      return '<span class="' + cls + '">' + f + '</span>';
    }).join('');
    document.getElementById('fundModalTitle').textContent =
      'Held via (' + funds.length + ')';
    body.innerHTML = '<div class="fund-tags">' + tags + '</div>';
    fundModalOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  // Desktop popup: position fixed near the button
  window.toggleFundPopup = function(btn) {
    var popupId = btn.getAttribute('data-popup');
    var fundsAttr = btn.getAttribute('data-funds');
    var funds = fundsAttr ? JSON.parse(fundsAttr) : [];

    // Mobile: use modal
    if (isMobileView()) {
      openFundModal(funds);
      return;
    }

    var popup = document.getElementById(popupId);
    if (!popup) return;

    // Close all other popups first
    document.querySelectorAll('.fund-more-popup.open').forEach(function(p) {
      if (p.id !== popupId) p.classList.remove('open');
    });

    var isOpen = popup.classList.toggle('open');
    if (isOpen) {
      // Position the popup near the button
      var rect = btn.getBoundingClientRect();
      var popupH = 260;
      var spaceAbove = rect.top;
      var spaceBelow = window.innerHeight - rect.bottom;

      popup.style.left = '';
      popup.style.right = '';

      // Place above or below depending on space
      if (spaceAbove > popupH || spaceAbove > spaceBelow) {
        popup.style.top = '';
        popup.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
      } else {
        popup.style.bottom = '';
        popup.style.top = (rect.bottom + 4) + 'px';
      }

      // Horizontal: align right edge with button right
      var rightEdge = window.innerWidth - rect.right;
      popup.style.right = Math.max(rightEdge, 8) + 'px';
    }
  };

  // Close fund popups on outside click
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.fund-more-btn') && !e.target.closest('.fund-more-popup')) {
      document.querySelectorAll('.fund-more-popup.open').forEach(function(p) {
        p.classList.remove('open');
      });
    }
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeSectorModal();
  });

  // ─── Summary Cards ────────────────────────────────────────────

  function renderSummaryCards(data) {
    document.getElementById('cardTotalValue').textContent = formatAmount(data.total_portfolio_value);
    document.getElementById('cardCompanyCount').textContent = data.companies.length;
    document.getElementById('cardSectorCount').textContent = Object.keys(data.sector_totals).length;
    if (data.companies.length > 0) {
      var top = data.companies[0];
      document.getElementById('cardTopHolding').textContent = formatPct(top.percentage_of_portfolio);
      var name = top.company_name;
      document.getElementById('cardTopHoldingName').textContent = name.length > 22 ? name.substring(0,20) + '…' : name;
    }
  }

  // ─── Company Table ────────────────────────────────────────────

  var allCompanies = [];
  var filteredCompanies = [];
  var currentPage = 0;
  var PAGE_SIZE = 25;
  var sortCol = 'holding_amount';
  var sortDir = 'desc';

  function sortCompanies(arr, col, dir) {
    return arr.slice().sort(function(a, b) {
      var va = col === 'rank' ? allCompanies.indexOf(a) : a[col];
      var vb = col === 'rank' ? allCompanies.indexOf(b) : b[col];
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return dir === 'asc' ? -1 : 1;
      if (va > vb) return dir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  var VIA_PREVIEW_LIMIT = 2;

  function buildFundTagsHtml(funds, rowIndex) {
    var directTag = '';
    var otherFunds = [];

    funds.forEach(function(f) {
      if (f === 'Direct') {
        directTag = '<span class="fund-tag fund-tag--direct">Direct</span>';
      } else {
        otherFunds.push(f);
      }
    });

    var visibleTags = otherFunds.slice(0, VIA_PREVIEW_LIMIT).map(function(f) {
      return '<span class="fund-tag" title="' + f + '">' + f + '</span>';
    }).join('');

    var moreHtml = '';
    if (otherFunds.length > VIA_PREVIEW_LIMIT) {
      var remaining = otherFunds.slice(VIA_PREVIEW_LIMIT);
      var allFundsJson = JSON.stringify(funds).replace(/"/g, '&quot;');
      moreHtml = '<button class="fund-more-btn" data-popup="fundPopup' + rowIndex + '" data-funds="' + allFundsJson + '" onclick="window.toggleFundPopup(this)">+' + remaining.length + '</button>' +
        '<div class="fund-more-popup" id="fundPopup' + rowIndex + '">' +
        '<div class="fund-more-popup-title">All funds (' + otherFunds.length + ')</div>' +
        '<div class="fund-tags">' +
        otherFunds.map(function(f) {
          return '<span class="fund-tag" title="' + f + '">' + f + '</span>';
        }).join('') +
        '</div></div>';
    }

    return '<div class="fund-tags-wrapper">' +
      '<div class="fund-tags">' + visibleTags + directTag + '</div>' +
      moreHtml + '</div>';
  }

  function renderTable() {
    var start = currentPage * PAGE_SIZE;
    var end = Math.min(start + PAGE_SIZE, filteredCompanies.length);
    var slice = filteredCompanies.slice(start, end);
    var tbody = document.getElementById('companyTableBody');

    tbody.innerHTML = slice.map(function(c, i) {
      var fundTagsHtml = buildFundTagsHtml(c.funds, start + i);
      var maxPct = allCompanies.length > 0 ? allCompanies[0].percentage_of_portfolio : 1;
      var barPct = Math.min((c.percentage_of_portfolio / maxPct) * 100, 100).toFixed(1);
      var sector = c.sector || '—';
      return '<tr>' +
        '<td class="company-name-cell">' + c.company_name + '</td>' +
        '<td>' + (c.instrument_type || '—') + '</td>' +
        '<td>' + sector + '</td>' +
        '<td class="amount-cell">' + formatAmount(c.holding_amount) + '</td>' +
        '<td class="pct-cell"><div class="exposure-pct-bar">' +
          '<div class="exposure-pct-track"><div class="exposure-pct-fill" style="width:' + barPct + '%"></div></div>' +
          '<span class="exposure-pct-text">' + formatPct(c.percentage_of_portfolio) + '</span></div></td>' +
        '<td>' + fundTagsHtml + '</td>' +
        '</tr>';
    }).join('');

    var info = document.getElementById('paginationInfo');
    if (filteredCompanies.length === 0) {
      info.textContent = 'No companies found';
    } else {
      info.textContent = 'Showing ' + (start + 1) + '–' + end + ' of ' + filteredCompanies.length;
    }
    document.getElementById('prevPageBtn').disabled = currentPage === 0;
    document.getElementById('nextPageBtn').disabled = end >= filteredCompanies.length;
  }

  function applyFilterAndSort() {
    var query = (document.getElementById('companySearch').value || '').toLowerCase().trim();
    var filtered = query
      ? allCompanies.filter(function(c) {
          return c.company_name.toLowerCase().includes(query) ||
                 (c.instrument_type || '').toLowerCase().includes(query) ||
                 (c.sector || '').toLowerCase().includes(query);
        })
      : allCompanies.slice();
    filteredCompanies = sortCompanies(filtered, sortCol, sortDir);
    currentPage = 0;
    renderTable();
  }

  function setupTableSort() {
    document.querySelectorAll('.exposure-table thead th[data-col]').forEach(function(th) {
      th.addEventListener('click', function() {
        var col = th.dataset.col;
        if (col === 'funds') return;
        if (sortCol === col) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortCol = col;
          sortDir = col === 'company_name' || col === 'instrument_type' || col === 'sector' ? 'asc' : 'desc';
        }
        document.querySelectorAll('.exposure-table thead th').forEach(function(h) {
          h.classList.remove('sorted');
          var arrow = h.querySelector('.sort-arrow');
          if (arrow) arrow.textContent = '↕';
        });
        th.classList.add('sorted');
        var arrow = th.querySelector('.sort-arrow');
        if (arrow) arrow.textContent = sortDir === 'asc' ? '↑' : '↓';
        applyFilterAndSort();
      });
    });
  }

  // ─── Main: Load data ──────────────────────────────────────────

  function renderDashboard(data) {
    allCompanies = data.companies;
    filteredCompanies = allCompanies.slice();

    renderSummaryCards(data);

    // Initial table sort by holding_amount desc (default)
    sortCol = 'holding_amount';
    sortDir = 'desc';
    filteredCompanies = sortCompanies(allCompanies, sortCol, sortDir);
    renderTable();
    setupTableSort();

    // Pagination
    document.getElementById('prevPageBtn').addEventListener('click', function() {
      if (currentPage > 0) { currentPage--; renderTable(); }
    });
    document.getElementById('nextPageBtn').addEventListener('click', function() {
      if ((currentPage + 1) * PAGE_SIZE < filteredCompanies.length) { currentPage++; renderTable(); }
    });

    // Search
    document.getElementById('companySearch').addEventListener('input', applyFilterAndSort);

    // Charts (defer slightly so layout is stable)
    setTimeout(function() {
      buildTopCompaniesChart(data.companies);
      initSectorEntries(data.sector_totals);
      buildSectorBars(data.sector_totals, data.total_portfolio_value);
    }, 100);
  }

  var POLL_INTERVAL = 3000;
  var refreshUI = new RefreshUI('exposureRefreshBtn', 'exposureStatusTag', 'exposureStatusText');
  var lastPortfolioUpdatedAt = null;
  var relativeStatusTimer = null;

  // ─── Refresh header visibility ─────────────────────────

  function showRefreshHeader() {
    document.getElementById('exposureHeaderRight').style.display = '';
  }

  function hideRefreshHeader() {
    document.getElementById('exposureHeaderRight').style.display = 'none';
  }

  // ─── Market state & relative timestamps ────────────────

  function formatStatusText() {
    if (!lastPortfolioUpdatedAt) return 'updated';
    var relative = typeof Formatter !== 'undefined'
      ? Formatter.formatRelativeTime(lastPortfolioUpdatedAt)
      : '';
    return relative ? 'updated ' + relative : 'updated';
  }

  function refreshRelativeStatusText() {
    var tag = document.getElementById('exposureStatusTag');
    if (!tag || tag.classList.contains('updating')) return;
    refreshUI.setStatusTag('updated', formatStatusText());
  }

  function startRelativeStatusUpdater() {
    if (relativeStatusTimer) clearInterval(relativeStatusTimer);
    relativeStatusTimer = setInterval(refreshRelativeStatusText, 60000);
  }

  function fetchAndApplyMarketStatus() {
    window.metronFetch('/api/status')
      .then(function(r) { return r.json(); })
      .then(function(status) {
        var tag = document.getElementById('exposureStatusTag');
        if (!tag) return;
        tag.classList.toggle('market_closed', status.market_open === false);
        lastPortfolioUpdatedAt = status.exposure_last_updated || null;
        refreshUI.setDoneWithText(formatStatusText());
        startRelativeStatusUpdater();
      })
      .catch(function() { /* non-critical, ignore */ });
  }

  // ─── Data loading with polling ───────────────────────────

  function showNoDataState() {
    document.getElementById('exposureLoading').style.display = 'none';
    document.getElementById('exposureDashboard').style.display = 'none';
    document.getElementById('exposureNoBanner').style.display = 'flex';
    hideRefreshHeader();
    refreshUI.setError();
  }

  function showDashboardState(data) {
    document.getElementById('exposureLoading').style.display = 'none';
    document.getElementById('exposureNoBanner').style.display = 'none';
    document.getElementById('exposureDashboard').style.display = 'block';
    showRefreshHeader();
    renderDashboard(data);
    fetchAndApplyMarketStatus();
  }

  function loadExposureData() {
    document.getElementById('exposureLoading').style.display = 'flex';
    document.getElementById('exposureDashboard').style.display = 'none';
    document.getElementById('exposureNoBanner').style.display = 'none';
    showRefreshHeader();
    refreshUI.setUpdating();

    pollForData();
  }

  function pollForData() {
    window.metronFetch('/api/exposure/data')
      .then(function(r) {
        var status = r.status;
        return r.json().then(function(data) { return { status: status, data: data }; });
      })
      .then(function(result) {
        if (result.status === 202) {
          setTimeout(pollForData, POLL_INTERVAL);
          return;
        }
        if (!result.data.has_data) {
          showNoDataState();
          return;
        }
        showDashboardState(result.data);
      })
      .catch(function(err) {
        showNoDataState();
        console.error('Exposure data fetch failed:', err);
      });
  }

  // ─── Manual refresh ──────────────────────────────────────

  function refreshExposure() {
    showRefreshHeader();
    refreshUI.setUpdating();

    window.metronFetch('/api/exposure/refresh', { method: 'POST' })
      .then(function(r) {
        // 409 = already in progress, still poll
        if (r.status === 409 || r.status === 202) {
          setTimeout(pollForData, POLL_INTERVAL);
          return;
        }
        // Direct response (e.g. no data)
        return r.json().then(function(data) {
          if (!data.has_data) {
            showNoDataState();
          }
        });
      })
      .catch(function(err) {
        refreshUI.setError();
        console.error('Exposure refresh failed:', err);
      });
  }

  // Expose for use by the DOMContentLoaded handler in the template
  window.loadExposureData = loadExposureData;
  window.refreshExposure = refreshExposure;

})();
