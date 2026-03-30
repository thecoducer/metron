// ─── CAS PDF Import ──────────────────────────────────────────
// Handles upload, verification modal, and fund name matching.

import { metronFetch, escapeHtml } from './utils.js';

function initCasImport() {
// ── DOM refs ──
const uploadBtn = document.getElementById('casUploadBtn');
const fileInput = document.getElementById('cas_file');
const passwordInput = document.getElementById('cas_password');
const accountSelect = document.getElementById('cas_account');
const newAccountInput = document.getElementById('cas_new_account');
const addNewBtn = document.getElementById('casAddNewAccount');
const pwToggle = document.getElementById('casPwToggle');
const pwEye = document.getElementById('casPwEye');
const pwEyeOff = document.getElementById('casPwEyeOff');
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
const modalInfo = document.getElementById('casModalInfo');
const schemesContainer = document.getElementById('casSchemesListContainer');
const modalSummary = document.getElementById('casModalSummary');
const modalConfirm = document.getElementById('casModalConfirm');
const modalCancel = document.getElementById('casModalCancel');
const modalClose = document.getElementById('casModalClose');
const confirmBackdrop = document.getElementById('casConfirmBackdrop');
const confirmStay = document.getElementById('casConfirmStay');
const confirmDiscard = document.getElementById('casConfirmDiscard');
const choicePortfolio = document.getElementById('casChoiceAdd');
const choiceTransactions = document.getElementById('casChoiceSkip');
const targetsHint = document.getElementById('casTargetsHint');

if (!uploadBtn || !modal) return;

// Guard against re-initialisation on SPA navigation.
// cas-import.js is a module; the router cache-busts it on every navigation,
// re-executing initCasImport() with a fresh closure (modalOpen = false).
// Without this guard, each run attaches duplicate listeners to the same DOM
// elements — the fresh-closure listener always wins and skips confirmation.
if (modal.dataset.casInitialized) return;
modal.dataset.casInitialized = '1';

// ── Import target toggle handlers ──
function _syncTargetUI() {
  if (choicePortfolio) {
    choicePortfolio.classList.toggle('selected', targetPortfolio === true);
    choicePortfolio.setAttribute('aria-pressed', targetPortfolio === true ? 'true' : 'false');
  }
  if (choiceTransactions) {
    choiceTransactions.classList.toggle('selected', targetTransactions === true);
    choiceTransactions.setAttribute('aria-pressed', targetTransactions === true ? 'true' : 'false');
  }
  const atLeastOne = targetPortfolio === true || targetTransactions === true;
  if (modalConfirm) modalConfirm.disabled = !atLeastOne;
  if (targetsHint) targetsHint.classList.toggle('hidden', atLeastOne || (targetPortfolio === null && targetTransactions === null));
}

function resetImportTargets() {
  targetPortfolio = null;
  targetTransactions = null;
  _syncTargetUI();
}

choicePortfolio?.addEventListener('click', () => {
  // Toggle: null → true → false → true …
  targetPortfolio = targetPortfolio !== true;
  _syncTargetUI();
});

choiceTransactions?.addEventListener('click', () => {
  targetTransactions = targetTransactions !== true;
  _syncTargetUI();
});

let parsedData = null;
let newAccountMode = false;
let modalOpen = false;
// Independent import targets: null = untouched (required), true/false = explicitly set
let targetPortfolio = null;
let targetTransactions = null;

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
    clearStatus();  // file changed — any prior file/upload error is stale
  });
}

// ── Password show/hide toggle ──
if (pwToggle && passwordInput) {
  pwToggle.addEventListener('click', () => {
    const isText = passwordInput.type === 'text';
    passwordInput.type = isText ? 'password' : 'text';
    if (pwEye) pwEye.style.display = isText ? '' : 'none';
    if (pwEyeOff) pwEyeOff.style.display = isText ? 'none' : '';
  });
}
if (passwordInput) {
  passwordInput.addEventListener('input', clearStatus);
}

// ── Account dropdown ──
if (addNewBtn) {
  addNewBtn.addEventListener('click', () => {
    newAccountMode = true;
    newAccountInput.style.display = '';
    newAccountInput.focus();
    accountSelect.value = '';
    addNewBtn.style.display = 'none';
  });
}

if (accountSelect) {
  accountSelect.addEventListener('change', () => {
    if (accountSelect.value) {
      newAccountMode = false;
      newAccountInput.style.display = 'none';
      newAccountInput.value = '';
      if (addNewBtn) addNewBtn.style.display = '';
    }
    clearStatus();
  });
}

if (newAccountInput) {
  newAccountInput.addEventListener('input', clearStatus);
}

// ── Enter key triggers upload ──
[passwordInput, newAccountInput].forEach(el => {
  if (el) el.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); uploadBtn.click(); }
  });
});

function getSelectedAccount() {
  if (newAccountMode) return newAccountInput?.value?.trim();
  return accountSelect?.value?.trim();
}

function populateAccountDropdown() {
  if (!accountSelect) return;
  const accounts = new Set();

  // Prefer live data from portfolioApp
  const holdings = window.portfolioApp?.dataManager?.getMFHoldings?.() || [];
  holdings.forEach(m => { if (m.account) accounts.add(m.account); });

  const prev = accountSelect.value;
  const sorted = Array.from(accounts).sort();
  accountSelect.innerHTML =
    '<option value="">-- Select account --</option>' +
    sorted.map(a => '<option value="' + escapeHtml(a) + '">' + escapeHtml(a) + '</option>').join('');

  if (prev && sorted.includes(prev)) accountSelect.value = prev;
}


// Populate on drawer open; clear errors on drawer close
const origOpen = window.openSettingsDrawer;
if (origOpen) {
  window.openSettingsDrawer = function () {
    origOpen();
    populateAccountDropdown();
  };
}

const origClose = window.closeSettingsDrawer;
if (origClose) {
  window.closeSettingsDrawer = function () {
    origClose();
    resetUploadForm();
  };
}

// ── Progress helpers (use style.display — no .hidden class dependency) ──
function showProgress(pct, text) {
  progress.style.display = '';
  progressBar.style.width = pct + '%';
  progressText.textContent = text;
}

function hideProgress() {
  progress.style.display = 'none';
  progressBar.style.width = '0%';
}

function setStatus(msg, isError) {
  uploadStatus.textContent = msg;
  uploadStatus.className = 'drawer-save-status' + (isError ? ' error' : ' success');
}

function clearStatus() {
  if (!uploadStatus) return;
  uploadStatus.textContent = '';
  uploadStatus.className = 'drawer-save-status';
}

// ── Upload handler ──
uploadBtn.addEventListener('click', async () => {
  const file = fileInput?.files?.[0];
  if (!file) { setStatus('Please select a PDF file', true); return; }

  if (file.size > 15 * 1024 * 1024) {
    setStatus('File too large. Maximum size is 15 MB.', true);
    return;
  }

  const password = passwordInput?.value?.trim();
  if (!password) { setStatus('Password is required', true); return; }
  const account = getSelectedAccount();
  if (!account) { setStatus('Account name is required', true); return; }

  clearStatus();
  uploadBtn.disabled = true;
  showProgress(10, 'Uploading PDF...');

  const formData = new FormData();
  formData.append('file', file);
  formData.append('password', password);

  try {
    showProgress(30, 'Parsing PDF...');
    const resp = await metronFetch('/api/cas/upload', { method: 'POST', body: formData });
    showProgress(80, 'Processing...');
    const data = await resp.json();
    if (!resp.ok) {
      setStatus(data.error || 'Upload failed', true);
      hideProgress();
      uploadBtn.disabled = false;
      return;
    }

    showProgress(100, 'Done!');
    parsedData = data;
    parsedData._account = account;

    setTimeout(() => {
      hideProgress();
      uploadBtn.disabled = false;
      openVerificationModal(data, account);
      resetUploadForm();
    }, 400);

  } catch {
    setStatus('Upload failed. Please try again.', true);
    hideProgress();
    uploadBtn.disabled = false;
  }
});

// ── Verification Modal ──
function openVerificationModal(data, account) {
  if (typeof window.closeSettingsDrawer === 'function') window.closeSettingsDrawer();

  modalInfo.innerHTML =
    '<div class="cas-info-row">' +
      '<span class="cas-info-label">Period:</span>' +
      '<span class="cas-info-value">' + escapeHtml(data.statement_from + ' – ' + data.statement_to) + '</span>' +
    '</div>' +
    '<div class="cas-info-row">' +
      '<span class="cas-info-label">Account:</span>' +
      '<span class="cas-info-value">' + escapeHtml(account) + '</span>' +
    '</div>';

  schemesContainer.innerHTML = '';

  // Sort: active funds first, redeemed last
  const schemes = [...(data.schemes || [])];
  const active = schemes.filter(s => s.units > 0);
  const redeemed = schemes.filter(s => s.units <= 0);

  active.forEach(scheme => renderSchemeCard(scheme, schemes.indexOf(scheme)));

  if (redeemed.length) {
    const divider = document.createElement('div');
    divider.className = 'cas-redeemed-divider';
    divider.textContent = 'Redeemed';
    schemesContainer.appendChild(divider);
    redeemed.forEach(scheme => renderSchemeCard(scheme, schemes.indexOf(scheme)));
  }

  // Summary: invested = units × avg_nav (excludes stamp duty)
  const totalInvested = active.reduce((s, sc) => {
    const avg = sc.units > 0 ? (sc.avg_nav || round4(sc.cost / sc.units)) : 0;
    return s + sc.units * avg;
  }, 0);

  modalSummary.innerHTML =
    '<span>' + active.length + ' active fund' + (active.length !== 1 ? 's' : '') + '</span>' +
    '<span>Invested: ' + formatCurrency(totalInvested) + '</span>';

  resetImportTargets();
  modal.classList.remove('hidden');
  modalBackdrop.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  modalOpen = true;
}

function renderSchemeCard(scheme, idx) {
  const isRedeemed = scheme.units <= 0;
  const defaultUnits = isRedeemed ? 0 : scheme.units;
  const defaultAvgNav = (!isRedeemed && scheme.units > 0) ? (scheme.avg_nav || round4(scheme.cost / scheme.units)) : 0;
  const initialInvested = defaultUnits * defaultAvgNav;

  const wrapper = document.createElement('div');
  wrapper.className = isRedeemed ? 'cas-scheme-redeemed' : '';

  const card = document.createElement('div');
  card.className = 'cas-scheme-card';
  card.dataset.idx = idx;

  card.innerHTML =
    '<div class="cas-scheme-name-field">' +
      '<label class="cas-field-label">Fund Name</label>' +
      '<div class="cas-suggest-wrapper">' +
        '<input type="text" class="cas-scheme-input" ' +
          'value="' + escapeHtml(scheme.scheme_name) + '" ' +
          'data-isin="' + escapeHtml(scheme.isin) + '" ' +
          'data-idx="' + idx + '" ' +
          'placeholder="Search fund name...">' +
        '<div class="cas-suggest-list" style="display:none"></div>' +
      '</div>' +
      '<span class="cas-scheme-isin">ISIN: ' + escapeHtml(scheme.isin) + '</span>' +
      '<span class="cas-isin-error-msg"></span>' +
    '</div>' +
    '<div class="cas-scheme-details">' +
      '<div class="cas-detail">' +
        '<label class="cas-detail-label" for="cas-units-' + idx + '">Quantity</label>' +
        (isRedeemed
          ? '<span class="cas-detail-value cas-zero">0 (redeemed)</span>'
          : '<input type="number" id="cas-units-' + idx + '" class="cas-edit-num cas-units-input" ' +
              'value="' + defaultUnits + '" step="0.001" min="0">') +
      '</div>' +
      '<div class="cas-detail">' +
        '<label class="cas-detail-label" for="cas-avg-' + idx + '">Avg Price</label>' +
        (isRedeemed
          ? '<span class="cas-detail-value cas-zero">—</span>'
          : '<input type="number" id="cas-avg-' + idx + '" class="cas-edit-num cas-avgnav-input" ' +
              'value="' + defaultAvgNav + '" step="0.01" min="0">') +
      '</div>' +
      '<div class="cas-detail">' +
        '<span class="cas-detail-label">Invested</span>' +
        '<span class="cas-detail-value cas-invested-val">' +
          (isRedeemed ? formatCurrency(0) : formatCurrency(initialInvested)) +
        '</span>' +
      '</div>' +
      '<div class="cas-detail">' +
        '<span class="cas-detail-label">Txns</span>' +
        '<span class="cas-detail-value">' + scheme.transaction_count + '</span>' +
      '</div>' +
    '</div>';

  wrapper.appendChild(card);
  schemesContainer.appendChild(wrapper);

  // Reactive invested = units × avg_nav
  if (!isRedeemed) {
    const unitsInput = card.querySelector('.cas-units-input');
    const avgNavInput = card.querySelector('.cas-avgnav-input');
    const investedSpan = card.querySelector('.cas-invested-val');
    const updateInvested = () => {
      const u = parseFloat(unitsInput.value) || 0;
      const a = parseFloat(avgNavInput.value) || 0;
      investedSpan.textContent = formatCurrency(u * a);
    };
    unitsInput.addEventListener('input', updateInvested);
    avgNavInput.addEventListener('input', updateInvested);
  }

  setupAutocomplete(card.querySelector('.cas-scheme-input'), card.querySelector('.cas-suggest-list'));
}

function showConfirmDialog() {
  confirmBackdrop?.classList.remove('hidden');
}

function hideConfirmDialog() {
  confirmBackdrop?.classList.add('hidden');
}

function closeModal(force = false) {
  if (!force && modalOpen) {
    showConfirmDialog();
    return;
  }
  hideConfirmDialog();
  modalOpen = false;
  parsedData = null;
  modal.classList.add('hidden');
  modalBackdrop.classList.add('hidden');
  document.body.style.overflow = '';
}

confirmStay?.addEventListener('click', hideConfirmDialog);
confirmDiscard?.addEventListener('click', () => {
  hideConfirmDialog();
  closeModal(true);
});

modalClose?.addEventListener('click', () => closeModal());
modalCancel?.addEventListener('click', () => closeModal());
modalBackdrop?.addEventListener('click', e => {
  if (e.target === modalBackdrop) closeModal();
});

// Close any open autocomplete when clicking elsewhere in the modal
modal.addEventListener('mousedown', e => {
  if (!e.target.closest('.cas-suggest-wrapper')) {
    modal.querySelectorAll('.cas-suggest-list').forEach(l => { l.style.display = 'none'; });
  }
});

// ── Autocomplete for fund names ──
function setupAutocomplete(input, list) {
  if (!input || !list) return;
  let debounce = null;
  let activeIdx = -1;

  const hide = () => { list.style.display = 'none'; activeIdx = -1; };
  const isHidden = () => list.style.display === 'none';

  const setActive = idx => {
    const items = list.querySelectorAll('.cas-suggest-item');
    items.forEach(el => el.classList.remove('active'));
    if (items[idx]) { items[idx].classList.add('active'); activeIdx = idx; }
  };

  const showIsinError = msg => {
    const errSpan = input.closest('.cas-scheme-name-field')?.querySelector('.cas-isin-error-msg');
    if (errSpan) { errSpan.textContent = msg; errSpan.style.display = ''; }
    const card = input.closest('.cas-scheme-card');
    if (card) card.classList.add('cas-scheme-isin-error');
  };

  const clearIsinError = () => {
    const errSpan = input.closest('.cas-scheme-name-field')?.querySelector('.cas-isin-error-msg');
    if (errSpan) { errSpan.textContent = ''; errSpan.style.display = 'none'; }
    const card = input.closest('.cas-scheme-card');
    if (card) card.classList.remove('cas-scheme-isin-error');
  };

  const select = async (text) => {
    input.value = text;
    hide();
    clearIsinError();

    // Validate ISIN and update AMC header
    const cardIsin = (input.dataset.isin || '').toUpperCase();
    try {
      const r = await metronFetch('/api/mutual_funds/isin?name=' + encodeURIComponent(text));
      const info = await r.json();
      if (info.isin) {
        if (info.isin.toUpperCase() !== cardIsin) {
          showIsinError(
            'ISIN mismatch: selected fund is ' + info.isin + ', but PDF has ' + cardIsin + '. Please pick the correct fund.'
          );
        }
      }
    } catch { /* best-effort */ }
  };

  const showItems = items => {
    list.innerHTML = '';
    if (!items.length) { hide(); return; }
    items.forEach(text => {
      const el = document.createElement('div');
      el.className = 'cas-suggest-item';
      el.textContent = text;
      el.addEventListener('mousedown', e => { e.preventDefault(); select(text); });
      list.appendChild(el);
    });
    list.style.display = '';
  };

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    clearIsinError();
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    debounce = setTimeout(async () => {
      try {
        const r = await metronFetch('/api/mutual_funds/search?q=' + encodeURIComponent(q));
        const results = await r.json();
        showItems(results.filter(Boolean));
      } catch { hide(); }
    }, 200);
  });

  input.addEventListener('keydown', e => {
    if (isHidden()) return;
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

  // Block submit if no target selected
  if (targetPortfolio !== true && targetTransactions !== true) {
    const choiceEl = document.getElementById('casPortfolioChoice');
    if (choiceEl) choiceEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    choiceEl?.classList.add('cas-choice-required');
    if (targetsHint) targetsHint.classList.remove('hidden');
    setTimeout(() => choiceEl?.classList.remove('cas-choice-required'), 400);
    return;
  }

  // Block submit if any ISIN errors exist
  const errorCards = schemesContainer.querySelectorAll('.cas-scheme-isin-error');
  if (errorCards.length) {
    errorCards[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }

  const account = parsedData._account;
  const schemes = parsedData.schemes
    .map((scheme, idx) => {
      const card = schemesContainer.querySelector('[data-idx="' + idx + '"]');
      const nameInput = card?.querySelector('.cas-scheme-input');
      const unitsInput = card?.querySelector('.cas-units-input');
      const avgNavInput = card?.querySelector('.cas-avgnav-input');
      return {
        isin: scheme.isin,
        fund_name: (nameInput?.value || scheme.scheme_name).trim(),
        units: unitsInput ? parseFloat(unitsInput.value) || 0 : scheme.units,
        avg_nav: avgNavInput ? parseFloat(avgNavInput.value) || 0 : (scheme.avg_nav || round4(scheme.cost / scheme.units)),
        transactions: scheme.transactions,
      };
    });

  if (!schemes.filter(s => s.units > 0).length) {
    alert('No active funds to import.');
    return;
  }

  modalConfirm.disabled = true;
  modalConfirm.textContent = 'Saving\u2026';

  try {
    const resp = await metronFetch('/api/cas/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account,
        schemes,
        add_to_portfolio: targetPortfolio === true,
        add_transactions: targetTransactions === true,
      }),
    });
    const result = await resp.json();
    if (!resp.ok) {
      alert(result.error || 'Failed to save');
      modalConfirm.disabled = false;
      modalConfirm.textContent = 'Confirm & Import';
      return;
    }

    closeModal(true);  // force-close — import is confirmed
    modalConfirm.disabled = false;
    modalConfirm.textContent = 'Confirm & Import';

    showToast(
      'Imported ' + result.added + ' fund(s)' +
      (result.updated ? ', updated ' + result.updated : '') + '.',
      'success'
    );

    // Refresh MF table (portfolio page)
    if (typeof window.portfolioApp?.updateData === 'function') {
      window.portfolioApp.updateData();
      showTxnNudge();
    }

    // Refresh transaction data (transactions page)
    if (typeof window.reloadTransactions === 'function') {
      window.reloadTransactions();
    }

  } catch {
    alert('Failed to save. Please try again.');
    modalConfirm.disabled = false;
    modalConfirm.textContent = 'Confirm & Import';
  }
});

function resetUploadForm() {
  if (fileInput) fileInput.value = '';
  if (passwordInput) {
    passwordInput.value = '';
    passwordInput.type = 'password';
    if (pwEye) pwEye.style.display = '';
    if (pwEyeOff) pwEyeOff.style.display = 'none';
  }
  if (fileLabel) fileLabel.querySelector('span').textContent = 'Choose PDF file';
  clearStatus();
  newAccountMode = false;
  if (newAccountInput) { newAccountInput.value = ''; newAccountInput.style.display = 'none'; }
  if (addNewBtn) addNewBtn.style.display = '';
  if (accountSelect) accountSelect.value = '';
}

// ── Toast notification — reuses the app's crud-toast system ──
function showToast(message, type) {
  const container =
    document.querySelector('.crud-toast-container') ||
    (() => {
      const c = document.createElement('div');
      c.className = 'crud-toast-container';
      document.body.appendChild(c);
      return c;
    })();

  const icon =
    type === 'success'
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

  const toast = document.createElement('div');
  toast.className = 'crud-toast crud-toast-' + (type === 'success' ? 'success' : 'error');
  toast.innerHTML = icon + '<span>' + escapeHtml(message) + '</span>';
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }, 4000);
}

// ── Transaction nudge (portfolio page only) ──
function showTxnNudge() {
  const nudge = document.getElementById('mfTxnNudge');
  if (!nudge) return;
  nudge.classList.remove('hidden', 'fade-out');
  // Force reflow so the pop animation replays
  void nudge.offsetWidth;
  nudge.style.animation = '';
  setTimeout(() => {
    nudge.classList.add('fade-out');
    setTimeout(() => nudge.classList.add('hidden'), 450);
  }, 5000);
}

// ── Helpers ──
function round4(n) { return Math.round((n || 0) * 10000) / 10000; }

function formatCurrency(val) {
  if (typeof window.formatMoney === 'function') return window.formatMoney(val);
  return '\u20b9' + Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
} // end initCasImport

initCasImport();

