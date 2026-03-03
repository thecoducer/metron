// User profile dropdown toggle
(function() {
  const avatarBtn = document.getElementById('userAvatarBtn');
  const dropdown = document.getElementById('userDropdown');
  if (avatarBtn && dropdown) {
    avatarBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
  }
})();

// Sign-out handler
function handleLogout() {
  fetch('/auth/logout', { method: 'POST' })
    .then(() => { window.location.href = '/'; })
    .catch(() => { window.location.href = '/'; });
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  const dropdown = document.getElementById('userDropdown');
  const avatarBtn = document.getElementById('userAvatarBtn');
  if (dropdown && avatarBtn && !avatarBtn.contains(event.target) && !dropdown.contains(event.target)) {
    dropdown.classList.remove('open');
  }
});

// ─── Settings Drawer ──────────────────────────────────────────

function openSettingsDrawer() {
  const drawer = document.getElementById('settingsDrawer');
  const backdrop = document.getElementById('drawerBackdrop');
  if (!drawer) return;
  // Close user dropdown first
  const dd = document.getElementById('userDropdown');
  if (dd) dd.classList.remove('open');

  drawer.classList.add('open');
  backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
  initDrawerThemeSwitcher();
  loadDrawerAccounts();
}

function closeSettingsDrawer() {
  const drawer = document.getElementById('settingsDrawer');
  const backdrop = document.getElementById('drawerBackdrop');
  if (!drawer) return;
  drawer.classList.remove('open');
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
}

// Close drawer on Escape key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeSettingsDrawer();
});

// ─── Drawer Theme Switcher ────────────────────────────────────

function initDrawerThemeSwitcher() {
  const switcher = document.getElementById('drawerThemeSwitcher');
  if (!switcher) return;
  const buttons = switcher.querySelectorAll('.drawer-theme-option');
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
    // Also update the portfolio theme icon if it exists
    const themeIcon = document.getElementById('theme_toggle_icon');
    if (themeIcon) themeIcon.textContent = theme === 'dark' ? '☀️' : '🌙';
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

// ─── Drawer Zerodha Accounts ──────────────────────────────────

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function renderDrawerAccounts(names, sessionValidity, loginUrls) {
  const listEl = document.getElementById('drawerAccountsList');
  if (!listEl) return;
  if (!names.length) {
    listEl.innerHTML = '<div class="drawer-accounts-empty">No accounts connected yet.</div>';
    return;
  }
  sessionValidity = sessionValidity || {};
  loginUrls = loginUrls || {};
  listEl.innerHTML = names.map(name => {
    const isValid = sessionValidity[name] === true;
    const loginUrl = loginUrls[name] || '';
    let statusHtml = '';
    if (!isValid && loginUrl) {
      statusHtml = '<a class="drawer-account-login" href="' + escapeHtml(loginUrl) + '" target="_blank" rel="noopener" title="Session expired \u2013 click to log in">Login</a>';
    } else if (!isValid) {
      statusHtml = '<span class="drawer-account-expired" title="Session expired">Expired</span>';
    } else {
      statusHtml = '<span class="drawer-account-active" title="Session active">\u2713</span>';
    }
    return '<span class="drawer-account-chip' + (isValid ? '' : ' expired') + '">' +
      '<span>' + escapeHtml(name) + '</span>' +
      statusHtml +
      '<button class="drawer-account-chip-remove" data-name="' + escapeHtml(name) + '" title="Remove ' + escapeHtml(name) + '">\u00d7</button>' +
    '</span>';
  }).join('');
  listEl.querySelectorAll('.drawer-account-chip-remove').forEach(btn => {
    btn.addEventListener('click', () => removeDrawerAccount(btn.dataset.name));
  });
}

function loadDrawerAccounts() {
  const listEl = document.getElementById('drawerAccountsList');
  if (!listEl) return;
  listEl.innerHTML = '<div class="drawer-accounts-loading">Loading\u2026</div>';
  fetch('/api/settings')
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(data => {
      const names = data.zerodha_accounts || [];
      const validity = data.session_validity || {};
      const loginUrls = data.login_urls || {};
      renderDrawerAccounts(names, validity, loginUrls);
    })
    .catch(() => { listEl.innerHTML = '<div class="drawer-accounts-empty">Failed to load accounts.</div>'; });
}

function removeDrawerAccount(name) {
  if (!confirm('Remove account "' + name + '"? This will delete the stored API credentials.')) return;
  fetch('/api/settings/zerodha/' + encodeURIComponent(name), { method: 'DELETE' })
    .then(r => r.ok ? loadDrawerAccounts() : Promise.reject())
    .catch(() => alert('Failed to remove account.'));
}

// ─── Drawer Add-Account Form ──────────────────────────────────

(function() {
  const addBtn = document.getElementById('drawerAddAccountBtn');
  const formEl = document.getElementById('drawerAddAccountForm');
  const saveBtn = document.getElementById('drawerSaveAccountBtn');
  const cancelBtn = document.getElementById('drawerCancelAccountBtn');
  const status = document.getElementById('drawerSaveStatus');
  const nameInput = document.getElementById('drawer_account_name');
  const keyInput = document.getElementById('drawer_api_key');
  const secretInput = document.getElementById('drawer_api_secret');
  if (!addBtn || !formEl) return;

  function clearForm() {
    if (nameInput) nameInput.value = '';
    if (keyInput) keyInput.value = '';
    if (secretInput) secretInput.value = '';
    if (status) { status.textContent = ''; status.className = 'drawer-save-status'; }
  }

  addBtn.addEventListener('click', () => {
    formEl.classList.remove('hidden');
    addBtn.style.display = 'none';
    if (nameInput) nameInput.focus();
  });

  cancelBtn.addEventListener('click', () => {
    formEl.classList.add('hidden');
    addBtn.style.display = '';
    clearForm();
  });

  saveBtn.addEventListener('click', async () => {
    const account_name = (nameInput.value || '').trim();
    const api_key = (keyInput.value || '').trim();
    const api_secret = (secretInput.value || '').trim();
    if (!account_name || !api_key || !api_secret) {
      status.textContent = 'All fields are required';
      status.className = 'drawer-save-status error';
      return;
    }
    saveBtn.disabled = true;
    status.textContent = '';
    status.className = 'drawer-save-status';
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
      loadDrawerAccounts();
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
})();
