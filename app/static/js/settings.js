/* Settings page – client-side logic */

// ─── Theme Switcher ───────────────────────────────────────────

function initThemeSwitcher() {
  const switcher = document.getElementById('themeSwitcher');
  if (!switcher) return;

  const buttons = switcher.querySelectorAll('.theme-option');
  const current = localStorage.getItem('theme') || 'light';

  function setActive(theme) {
    buttons.forEach(b => b.classList.toggle('active', b.dataset.theme === theme));
  }

  function applyTheme(theme) {
    document.body.classList.add('theme-transitioning');
    if (theme === 'dark') {
      document.body.classList.add('dark-theme');
    } else {
      document.body.classList.remove('dark-theme');
    }
    localStorage.setItem('theme', theme);
    setActive(theme);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.body.classList.remove('theme-transitioning');
      });
    });
  }

  setActive(current);
  buttons.forEach(btn => {
    btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
  });
}

// ─── Zerodha Accounts ─────────────────────────────────────────

function initZerodhaAccounts() {
  const listEl = document.getElementById('accountsList');
  const addBtn = document.getElementById('addAccountBtn');
  const formEl = document.getElementById('addAccountForm');
  const saveBtn = document.getElementById('saveAccountBtn');
  const cancelBtn = document.getElementById('cancelAccountBtn');
  const status = document.getElementById('saveStatus');
  const nameInput = document.getElementById('new_account_name');
  const keyInput = document.getElementById('new_api_key');
  const secretInput = document.getElementById('new_api_secret');

  if (!listEl) return;

  // ── Render account chips ──

  function renderAccounts(names) {
    if (!names.length) {
      listEl.innerHTML = '<div class="accounts-empty">No accounts connected yet.</div>';
      return;
    }
    listEl.innerHTML = names.map(name => `
      <span class="account-chip">
        <span class="account-chip-name">${escapeHtml(name)}</span>
        <button class="account-chip-remove" data-name="${escapeHtml(name)}" title="Remove ${escapeHtml(name)}">×</button>
      </span>
    `).join('');

    // Attach remove handlers
    listEl.querySelectorAll('.account-chip-remove').forEach(btn => {
      btn.addEventListener('click', () => removeAccount(btn.dataset.name));
    });
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // ── Load accounts ──

  async function loadAccounts() {
    try {
      const resp = await fetch('/api/settings');
      if (!resp.ok) throw new Error();
      const data = await resp.json();
      renderAccounts(data.zerodha_accounts || []);
    } catch {
      listEl.innerHTML = '<div class="accounts-empty">Failed to load accounts.</div>';
    }
  }

  // ── Remove account ──

  async function removeAccount(name) {
    if (!confirm(`Remove account "${name}"? This will delete the stored API credentials.`)) return;
    try {
      const resp = await fetch(`/api/settings/zerodha/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error();
      await loadAccounts();
    } catch {
      alert('Failed to remove account.');
    }
  }

  // ── Toggle add form ──

  addBtn.addEventListener('click', () => {
    formEl.classList.remove('hidden');
    addBtn.style.display = 'none';
    nameInput.focus();
  });

  cancelBtn.addEventListener('click', () => {
    formEl.classList.add('hidden');
    addBtn.style.display = '';
    clearForm();
  });

  function clearForm() {
    nameInput.value = '';
    keyInput.value = '';
    secretInput.value = '';
    status.textContent = '';
    status.className = 'save-status';
  }

  // ── Save new account ──

  saveBtn.addEventListener('click', async () => {
    const account_name = nameInput.value.trim();
    const api_key = keyInput.value.trim();
    const api_secret = secretInput.value.trim();

    if (!account_name || !api_key || !api_secret) {
      status.textContent = 'All fields are required';
      status.className = 'save-status error';
      return;
    }

    saveBtn.disabled = true;
    status.textContent = '';
    status.className = 'save-status';

    try {
      const resp = await fetch('/api/settings/zerodha', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_name, api_key, api_secret }),
      });
      const result = await resp.json();

      if (!resp.ok) {
        status.textContent = result.error || 'Save failed';
        status.classList.add('error');
        return;
      }

      // Success – reload list, hide form
      await loadAccounts();
      formEl.classList.add('hidden');
      addBtn.style.display = '';
      clearForm();
    } catch {
      status.textContent = 'Failed to save';
      status.classList.add('error');
    } finally {
      saveBtn.disabled = false;
    }
  });

  // Initial load
  loadAccounts();
}

// ─── Init ─────────────────────────────────────────────────────

initThemeSwitcher();
initZerodhaAccounts();
