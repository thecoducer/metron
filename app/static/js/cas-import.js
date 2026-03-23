// ─── CAS PDF Import ──────────────────────────────────────────
// Handles upload, verification modal, and fund name matching.

(function () {
  const metronFetch = window.metronFetch;
  if (!metronFetch) return;

  // ── DOM refs ──
  const uploadBtn = document.getElementById('casUploadBtn');
  const fileInput = document.getElementById('cas_file');
  const passwordInput = document.getElementById('cas_password');
  const accountSelect = document.getElementById('cas_account');
  const newAccountInput = document.getElementById('cas_new_account');
  const toggleNewBtn = document.getElementById('casToggleNewAccount');
  const uploadStatus = document.getElementById('casUploadStatus');
  const progress = document.getElementById('casProgress');
  const progressBar = document.getElementById('casProgressBar');
  const progressText = document.getElementById('casProgressText');
  const fileLabel = document.getElementById('casFileLabel');
  const casGuideToggle = document.getElementById('casGuideToggle');
  const casGuide = document.getElementById('casGuide');

  // Modal refs
  const modal = document.getElementById('casModal');
  const modalBackdrop = document.getElementById('casModalBackdrop');
  const modalBody = document.getElementById('casModalBody');
  const modalInfo = document.getElementById('casModalInfo');
  const schemesContainer = document.getElementById('casSchemesListContainer');
  const modalSummary = document.getElementById('casModalSummary');
  const modalConfirm = document.getElementById('casModalConfirm');
  const modalCancel = document.getElementById('casModalCancel');
  const modalClose = document.getElementById('casModalClose');

  if (!uploadBtn || !modal) return;

  let parsedData = null;
  let isNewAccount = false;

  // ── Setup guide toggle ──
  if (casGuideToggle && casGuide) {
    casGuideToggle.addEventListener('click', () => {
      const isOpen = casGuide.classList.toggle('open');
      casGuideToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
  }

  // ── File input display ──
  if (fileInput && fileLabel) {
    fileInput.addEventListener('change', () => {
      const name = fileInput.files?.[0]?.name;
      fileLabel.querySelector('span').textContent = name || 'Choose PDF file';
    });
  }

  // ── New account toggle ──
  if (toggleNewBtn) {
    toggleNewBtn.addEventListener('click', () => {
      isNewAccount = !isNewAccount;
      accountSelect.classList.toggle('hidden', isNewAccount);
      newAccountInput.classList.toggle('hidden', !isNewAccount);
      toggleNewBtn.textContent = isNewAccount ? 'Select existing' : '+ New';
      if (isNewAccount) newAccountInput.focus();
    });
  }

  // ── Populate account dropdown from existing MF data ──
  function populateAccountDropdown() {
    if (!accountSelect) return;
    const accounts = new Set();
    // Collect account names from the MF table
    document.querySelectorAll('#mf_holdings_tbody tr').forEach(row => {
      const accountCell = row.querySelector('td:last-child');
      if (accountCell) {
        const txt = accountCell.textContent.trim();
        if (txt && txt !== '-') accounts.add(txt);
      }
    });
    // Also get from all_data if available
    const allData = window.__INITIAL_DATA__ || window.__ALL_DATA__;
    if (allData?.mfHoldings) {
      allData.mfHoldings.forEach(m => {
        if (m.account) accounts.add(m.account);
      });
    }
    const opts = '<option value="">-- Select or type new --</option>' +
      Array.from(accounts).sort().map(a =>
        '<option value="' + escapeHtml(a) + '">' + escapeHtml(a) + '</option>'
      ).join('');
    accountSelect.innerHTML = opts;
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // Populate on drawer open
  const origOpen = window.openSettingsDrawer;
  if (origOpen) {
    window.openSettingsDrawer = function () {
      origOpen();
      populateAccountDropdown();
    };
  }

  // ── Progress helpers ──
  function showProgress(pct, text) {
    progress.classList.remove('hidden');
    progressBar.style.width = pct + '%';
    progressText.textContent = text;
  }

  function hideProgress() {
    progress.classList.add('hidden');
    progressBar.style.width = '0%';
  }

  function setStatus(msg, isError) {
    uploadStatus.textContent = msg;
    uploadStatus.className = 'drawer-save-status' + (isError ? ' error' : ' success');
  }

  function setBtnLoading(btn, loading) {
    const textEl = btn.querySelector('.cas-btn-text');
    const spinnerEl = btn.querySelector('.cas-btn-spinner');
    if (textEl) textEl.classList.toggle('hidden', loading);
    if (spinnerEl) spinnerEl.classList.toggle('hidden', !loading);
    btn.disabled = loading;
  }

  // ── Upload handler ──
  uploadBtn.addEventListener('click', async () => {
    const file = fileInput?.files?.[0];
    if (!file) { setStatus('Please select a PDF file', true); return; }
    const password = passwordInput?.value?.trim();
    if (!password) { setStatus('Password is required', true); return; }
    const account = isNewAccount
      ? newAccountInput?.value?.trim()
      : accountSelect?.value?.trim();
    if (!account) { setStatus('Account name is required', true); return; }

    setStatus('', false);
    setBtnLoading(uploadBtn, true);
    showProgress(10, 'Uploading PDF...');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('password', password);

    try {
      showProgress(30, 'Parsing PDF...');
      const resp = await metronFetch('/api/cas/upload', {
        method: 'POST',
        body: formData,
      });
      showProgress(70, 'Processing...');
      const data = await resp.json();
      if (!resp.ok) {
        setStatus(data.error || 'Upload failed', true);
        hideProgress();
        setBtnLoading(uploadBtn, false);
        return;
      }

      showProgress(100, 'Done!');
      parsedData = data;
      parsedData._account = account;

      setTimeout(() => {
        hideProgress();
        setBtnLoading(uploadBtn, false);
        openVerificationModal(data, account);
      }, 500);

    } catch (err) {
      setStatus('Upload failed. Please try again.', true);
      hideProgress();
      setBtnLoading(uploadBtn, false);
    }
  });

  // ── Verification Modal ──
  function openVerificationModal(data, account) {
    // Close settings drawer
    if (typeof closeSettingsDrawer === 'function') closeSettingsDrawer();

    modalInfo.innerHTML =
      '<div class="cas-info-row">' +
        '<span class="cas-info-label">Investor</span>' +
        '<span class="cas-info-value">' + escapeHtml(data.investor_name) + '</span>' +
      '</div>' +
      '<div class="cas-info-row">' +
        '<span class="cas-info-label">Period</span>' +
        '<span class="cas-info-value">' + escapeHtml(data.statement_from + ' to ' + data.statement_to) + '</span>' +
      '</div>' +
      '<div class="cas-info-row">' +
        '<span class="cas-info-label">Account</span>' +
        '<span class="cas-info-value">' + escapeHtml(account) + '</span>' +
      '</div>';

    // Render schemes
    schemesContainer.innerHTML = '';
    const schemes = data.schemes || [];

    schemes.forEach((scheme, idx) => {
      const card = document.createElement('div');
      card.className = 'cas-scheme-card';
      card.dataset.idx = idx;

      const unitsDisplay = scheme.units > 0
        ? scheme.units.toFixed(3)
        : '<span class="cas-zero">0 (fully redeemed)</span>';

      card.innerHTML =
        '<div class="cas-scheme-header">' +
          '<span class="cas-scheme-amc">' + escapeHtml(scheme.amc) + '</span>' +
          '<span class="cas-scheme-type">' + escapeHtml(scheme.scheme_type) + '</span>' +
        '</div>' +
        '<div class="cas-scheme-name-field">' +
          '<label class="cas-scheme-label">Fund Name</label>' +
          '<div class="cas-suggest-wrapper">' +
            '<input type="text" class="cas-scheme-input" ' +
              'value="' + escapeHtml(scheme.scheme_name) + '" ' +
              'data-isin="' + escapeHtml(scheme.isin) + '" ' +
              'data-idx="' + idx + '" ' +
              'placeholder="Search fund name...">' +
            '<div class="cas-suggest-list hidden"></div>' +
          '</div>' +
          '<span class="cas-scheme-isin">ISIN: ' + escapeHtml(scheme.isin) + '</span>' +
        '</div>' +
        '<div class="cas-scheme-details">' +
          '<div class="cas-detail"><span class="cas-detail-label">Units</span><span class="cas-detail-value">' + unitsDisplay + '</span></div>' +
          '<div class="cas-detail"><span class="cas-detail-label">Cost</span><span class="cas-detail-value">' + formatCurrency(scheme.cost) + '</span></div>' +
          '<div class="cas-detail"><span class="cas-detail-label">Value</span><span class="cas-detail-value">' + formatCurrency(scheme.current_value) + '</span></div>' +
          '<div class="cas-detail"><span class="cas-detail-label">Transactions</span><span class="cas-detail-value">' + scheme.transaction_count + '</span></div>' +
        '</div>';

      schemesContainer.appendChild(card);

      // Set up autocomplete on the input
      const input = card.querySelector('.cas-scheme-input');
      const suggestList = card.querySelector('.cas-suggest-list');
      setupAutocomplete(input, suggestList);
    });

    // Summary
    const totalCost = schemes.reduce((s, sc) => s + sc.cost, 0);
    const totalValue = schemes.reduce((s, sc) => s + sc.current_value, 0);
    const totalReturn = totalValue - totalCost;
    const returnPct = totalCost > 0 ? ((totalReturn / totalCost) * 100) : 0;
    const returnClass = totalReturn >= 0 ? 'cas-positive' : 'cas-negative';

    modalSummary.innerHTML =
      '<span>' + schemes.length + ' funds</span>' +
      '<span>Invested: ' + formatCurrency(totalCost) + '</span>' +
      '<span>Current: ' + formatCurrency(totalValue) + '</span>' +
      '<span class="' + returnClass + '">Returns: ' + formatCurrency(totalReturn) + ' (' + returnPct.toFixed(1) + '%)</span>';

    // Show modal
    modal.classList.remove('hidden');
    modalBackdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    modal.classList.add('hidden');
    modalBackdrop.classList.add('hidden');
    document.body.style.overflow = '';
  }

  modalClose?.addEventListener('click', closeModal);
  modalCancel?.addEventListener('click', closeModal);
  modalBackdrop?.addEventListener('click', closeModal);

  // ── Autocomplete for fund names ──
  function setupAutocomplete(input, list) {
    let debounce = null;
    let activeIdx = -1;

    const hide = () => { list.classList.add('hidden'); activeIdx = -1; };

    const setActive = (idx) => {
      const items = list.querySelectorAll('.cas-suggest-item');
      items.forEach(el => el.classList.remove('active'));
      if (items[idx]) { items[idx].classList.add('active'); activeIdx = idx; }
    };

    const select = (text) => {
      input.value = text;
      hide();
      input.dispatchEvent(new Event('change'));
    };

    const show = (items) => {
      list.innerHTML = '';
      if (!items.length) { hide(); return; }
      items.forEach(text => {
        const el = document.createElement('div');
        el.className = 'cas-suggest-item';
        el.textContent = text;
        el.addEventListener('mousedown', e => { e.preventDefault(); select(text); });
        list.appendChild(el);
      });
      list.classList.remove('hidden');
    };

    input.addEventListener('input', () => {
      clearTimeout(debounce);
      const q = input.value.trim();
      if (q.length < 2) { hide(); return; }
      debounce = setTimeout(async () => {
        try {
          const r = await metronFetch('/api/mutual_funds/search?q=' + encodeURIComponent(q));
          show((await r.json()).filter(Boolean));
        } catch { hide(); }
      }, 200);
    });

    input.addEventListener('keydown', e => {
      if (list.classList.contains('hidden')) return;
      const els = list.querySelectorAll('.cas-suggest-item');
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive(Math.min(activeIdx + 1, els.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(activeIdx - 1, 0)); }
      else if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); select(els[activeIdx].textContent); }
      else if (e.key === 'Escape') { hide(); }
    });

    input.addEventListener('blur', () => setTimeout(hide, 150));
  }

  // ── Confirm & Import ──
  modalConfirm?.addEventListener('click', async () => {
    if (!parsedData) return;

    const account = parsedData._account;
    const schemes = parsedData.schemes.map((scheme, idx) => {
      const input = schemesContainer.querySelector(`[data-idx="${idx}"]`);
      const fundName = input ? input.value.trim() : scheme.scheme_name;
      return {
        isin: scheme.isin,
        fund_name: fundName,
        units: scheme.units,
        cost: scheme.cost,
        transactions: scheme.transactions,
      };
    });

    // Filter out fully redeemed funds (0 units)
    const activeSchemes = schemes.filter(s => s.units > 0);

    setBtnLoading(modalConfirm, true);

    try {
      const resp = await metronFetch('/api/cas/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account, schemes: activeSchemes }),
      });
      const result = await resp.json();
      if (!resp.ok) {
        alert(result.error || 'Failed to save');
        setBtnLoading(modalConfirm, false);
        return;
      }

      closeModal();
      setBtnLoading(modalConfirm, false);

      // Show success notification
      showToast(
        'Imported ' + result.added + ' new fund(s)' +
        (result.updated ? ', updated ' + result.updated : '') + '.',
        'success'
      );

      // Refresh MF data on the page
      if (result.mfHoldings && typeof window.updateTableData === 'function') {
        window.updateTableData('mfHoldings', result.mfHoldings);
      } else {
        // Fallback: reload all data
        if (typeof window.fetchAllData === 'function') window.fetchAllData();
      }

      // Show transaction nudge if transactions exist
      if (result.has_transactions) {
        showTransactionNudge();
      }

      // Reset form
      resetUploadForm();

    } catch (err) {
      alert('Failed to save. Please try again.');
      setBtnLoading(modalConfirm, false);
    }
  });

  function resetUploadForm() {
    if (fileInput) fileInput.value = '';
    if (passwordInput) passwordInput.value = '';
    if (fileLabel) fileLabel.querySelector('span').textContent = 'Choose PDF file';
    if (uploadStatus) { uploadStatus.textContent = ''; uploadStatus.className = 'drawer-save-status'; }
    parsedData = null;
  }

  // ── Toast notification ──
  function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = 'cas-toast cas-toast-' + (type || 'info');
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('visible'));
    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // ── Transaction nudge ──
  function showTransactionNudge() {
    const existing = document.getElementById('casTransactionNudge');
    if (existing) return;
    const mfSection = document.getElementById('mf-holdings-section') ||
      document.querySelector('[id*="mutual"]');
    if (!mfSection) return;

    const nudge = document.createElement('div');
    nudge.id = 'casTransactionNudge';
    nudge.className = 'cas-transaction-nudge';
    nudge.innerHTML =
      '<div class="cas-nudge-content">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>' +
        '</svg>' +
        '<span>View transaction history for your imported mutual funds</span>' +
        '<a href="/transactions" class="cas-nudge-link">View Transactions</a>' +
      '</div>' +
      '<button class="cas-nudge-dismiss" title="Dismiss">&times;</button>';

    mfSection.parentNode.insertBefore(nudge, mfSection);

    nudge.querySelector('.cas-nudge-dismiss').addEventListener('click', () => {
      nudge.classList.add('dismissing');
      nudge.addEventListener('animationend', () => nudge.remove(), { once: true });
    });
  }
  // Expose for external use
  window.showTransactionNudge = showTransactionNudge;

  // ── Format helpers ──
  function formatCurrency(val) {
    if (typeof window.formatMoney === 'function') return window.formatMoney(val);
    return '\u20b9' + Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // Check for existing CAS transactions on load and show nudge
  async function checkExistingTransactions() {
    try {
      const resp = await metronFetch('/api/cas/transactions');
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.has_data) showTransactionNudge();
    } catch { /* ignore */ }
  }

  // Run after initial data load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(checkExistingTransactions, 3000));
  } else {
    setTimeout(checkExistingTransactions, 3000);
  }
})();
