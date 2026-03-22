// Sign-out handler
function handleLogout() {
  window.metronFetch('/api/auth/logout', { method: 'POST' })
    .then(() => { window.location.href = '/'; })
    .catch(() => { window.location.href = '/'; });
}

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

// Open settings drawer when Enter/Space pressed on login banner
document.addEventListener('keydown', function(e) {
  if ((e.key === 'Enter' || e.key === ' ') && document.activeElement && document.activeElement.id === 'loginBanner') {
    e.preventDefault();
    openSettingsDrawer();
  }
});

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
  window.metronFetch('/api/settings')
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
  window.metronFetch('/api/settings/zerodha/' + encodeURIComponent(name), { method: 'DELETE' })
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
      // Ensure user has a security PIN before saving credentials.
      // If no PIN is set up, the setup overlay will show first.
      if (typeof window.checkAndPromptPin === 'function') {
        const pinOk = await window.checkAndPromptPin();
        // checkAndPromptPin returns false when no accounts exist AND no
        // PIN has been set.  In that case, prompt for PIN setup explicitly
        // before the first save (the save needs a PIN on the backend).
        if (!pinOk && typeof window.showPinSetup === 'function') {
          await window.showPinSetup();
        }
      }

      const resp = await window.metronFetch('/api/settings/zerodha', {
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

// ─── Connect Broker Nudge Dismiss ─────────────────────────────

(function() {
  const dismissBtn = document.getElementById('connectNudgeDismiss');
  const nudge = document.getElementById('connectNudge');
  if (!dismissBtn || !nudge) return;

  dismissBtn.addEventListener('click', () => {
    nudge.classList.add('dismissing');
    localStorage.setItem('metron_connect_nudge_dismissed', '1');
    nudge.addEventListener('animationend', () => {
      nudge.style.display = 'none';
    }, { once: true });
  });
})();

// ─── Setup Guide Expand/Collapse ──────────────────────────────

(function() {
  const guide = document.getElementById('setupGuide');
  const toggle = document.getElementById('setupGuideToggle');
  if (!guide || !toggle) return;

  toggle.addEventListener('click', () => {
    const isOpen = guide.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });
})();

// ─── App Tour ─────────────────────────────────────────────────

(function() {
  const TOUR_KEY = 'metron_tour_done';
  const isFirstVisit = !localStorage.getItem(TOUR_KEY);

  // Hide "NEW" badge if tour was already done
  if (!isFirstVisit) {
    const badge = document.getElementById('tourBadge');
    if (badge) badge.style.display = 'none';
  }

  const STEPS = [
    {
      target: '#combined_summary',
      iconClass: 'tour-icon-wallet',
      title: 'Your net worth',
      desc: 'Total invested value, current value, and overall returns — all in one place. Hit refresh to pull the latest data from your broker.',
      position: 'bottom',
    },
    {
      target: '.overview-top-right',
      iconClass: 'tour-icon-refresh',
      title: 'Refresh & status',
      desc: 'Hit refresh to fetch the latest data.<br><br><strong>Status dot:</strong> <span style="color:#f59e0b">●</span>&nbsp;updating, <span style="color:#22c55e">●</span>&nbsp;market open, <span style="color:#ef4444">●</span>&nbsp;market closed. Shows how long ago data was last refreshed.',
      position: 'bottom-end',
    },
    {
      target: '#indexTickers',
      iconClass: 'tour-icon-trending',
      title: 'Live market indices',
      desc: 'NIFTY 50, SENSEX and other key indices with mini sparkline charts — updates in real-time during market hours.',
      position: 'bottom',
    },
    {
      target: '#data-container-summary',
      iconClass: 'tour-icon-barchart',
      title: 'Asset allocation',
      desc: 'See how your money is spread across asset classes. <strong>Click a segment</strong> on the bar or a label below it to jump directly to that section.',
      position: 'bottom',
    },
    {
      target: '#stocks-section .crud-add-btn, #stocks-section',
      iconClass: 'tour-icon-pencil',
      title: 'Add, edit & delete data',
      desc: 'Use the <strong>+ Add</strong> button to manually enter holdings. Each row has edit and delete icons on the right. Broker-synced data appears automatically — manual entries are marked with a <span style="opacity:.7">person</span> icon.',
      position: 'bottom-start',
    },
    {
      target: '#stocks-section',
      iconClass: 'tour-icon-clipboard',
      title: 'Holdings tables',
      desc: 'Stocks, ETFs and Mutual Funds each have their own sortable table. Click any <strong>column header</strong> to sort. Same symbol from multiple accounts is grouped automatically — click to expand.',
      position: 'bottom',
    },
    {
      target: '#gold_summary, #physical-gold-section',
      iconClass: 'tour-icon-medal',
      title: 'Gold & physical gold',
      desc: 'Your total gold holdings — broken down by ETFs, physical gold, and SGBs with a proportion bar. Physical gold is valued using <strong>IBJA rates</strong> (India Bullion and Jewellers Association). Look for the <span style="color:#0d9488">ℹ</span> icon on each table for more details.',
      position: 'bottom',
    },
    {
      target: '#fixed-deposits-section',
      iconClass: 'tour-icon-safe',
      title: 'Fixed Deposits',
      desc: 'Track your fixed deposits with auto-renewal support. Switch between <strong>By Maturity</strong> and <strong>By Bank</strong> views for FDs. A <span style="color:#f59e0b;font-weight:700">!</span> icon warns when deposits exceed the \u20b95L DICGC insurance limit.',
      position: 'bottom',
    },
    {
      target: '#sips-section',
      iconClass: 'tour-icon-calendar',
      title: 'SIP tracker',
      desc: 'See all your SIPs with a rhythm summary showing total monthly and annual outflow. The frequency breakdown shows how much goes weekly, monthly, or quarterly.',
      position: 'bottom',
    },
    {
      target: '.section-info-btn',
      iconClass: 'tour-icon-info',
      title: 'Table info guides',
      desc: 'Each table has an <span style="color:#0d9488;font-weight:600">ℹ</span> button next to the heading. Click it to learn what the table shows, how to add entries, and what each column means.',
      position: 'bottom-start',
    },
    {
      target: '.nav-tabs',
      iconClass: 'tour-icon-compass',
      title: 'Navigation',
      desc: 'Switch between your <strong>Portfolio</strong> dashboard and the <strong>Nifty 50</strong> index tracker.',
      position: 'bottom-start',
    },
    {
      target: '#userAvatarBtn',
      iconClass: 'tour-icon-gear',
      title: 'Settings & preferences',
      desc: 'Tap your avatar for theme toggle, privacy mode, and short numbers. Open <strong>Settings</strong> to connect broker accounts with a step-by-step setup wizard.',
      position: 'bottom-end',
    },
  ];

  let currentStep = 0;
  const overlay = document.getElementById('appTourOverlay');
  const tooltip = document.getElementById('appTourTooltip');
  const content = document.getElementById('appTourContent');
  const progress = document.getElementById('appTourProgress');
  const nextBtn = document.getElementById('appTourNext');
  const skipBtn = document.getElementById('appTourSkip');

  if (!overlay || !tooltip) return;

  function findTarget(selectorStr) {
    const selectors = selectorStr.split(',').map(s => s.trim());
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) return el;
    }
    // Return first match even if hidden
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  // Ensure arrow element exists inside tooltip
  let arrowEl = tooltip.querySelector('.app-tour-arrow');
  if (!arrowEl) {
    arrowEl = document.createElement('div');
    arrowEl.className = 'app-tour-arrow';
    tooltip.appendChild(arrowEl);
  }

  function positionTooltip(rect, position) {
    const gap = 16;
    const tw = tooltip.offsetWidth;
    const th = tooltip.offsetHeight;
    let top, left;
    let arrowSide; // 'top' = arrow sticks out of top edge, 'bottom' = out of bottom

    switch (position) {
      case 'bottom':
      case 'bottom-start':
      case 'bottom-end':
        top = rect.bottom + gap;
        arrowSide = 'top';
        break;
      case 'top':
        top = rect.top - th - gap;
        arrowSide = 'bottom';
        break;
      default:
        top = rect.bottom + gap;
        arrowSide = 'top';
    }

    switch (position) {
      case 'bottom-start':
        left = rect.left;
        break;
      case 'bottom-end':
        left = rect.right - tw;
        break;
      default:
        left = rect.left + rect.width / 2 - tw / 2;
    }

    // Clamp to viewport
    left = Math.max(12, Math.min(left, window.innerWidth - tw - 12));
    top = Math.max(12, Math.min(top, window.innerHeight - th - 12));

    tooltip.style.top = top + 'px';
    tooltip.style.left = left + 'px';
    tooltip.setAttribute('data-arrow', arrowSide);

    // Position arrow horizontally to point at center of target
    const targetCenterX = rect.left + rect.width / 2;
    const arrowLeft = Math.max(18, Math.min(targetCenterX - left - 7, tw - 26));
    arrowEl.style.left = arrowLeft + 'px';
  }

  function renderProgress() {
    progress.innerHTML = STEPS.map((_, i) => {
      let cls = 'app-tour-dot';
      if (i < currentStep) cls += ' done';
      else if (i === currentStep) cls += ' active';
      return '<span class="' + cls + '"></span>';
    }).join('');
  }

  // Smoothly scroll element into view, then invoke callback after scroll settles
  function scrollToElement(el, callback) {
    const rect = el.getBoundingClientRect();
    const inView = rect.top >= 0 && rect.bottom <= window.innerHeight;
    if (inView) {
      callback();
      return;
    }
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // Wait for smooth scroll to finish, then fire callback
    let lastY = window.scrollY;
    let settled = 0;
    const check = () => {
      if (Math.abs(window.scrollY - lastY) < 1) {
        settled++;
        if (settled >= 3) { callback(); return; }
      } else {
        settled = 0;
      }
      lastY = window.scrollY;
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  }

  function showStep(index) {
    if (index >= STEPS.length) {
      endTour();
      return;
    }
    currentStep = index;
    const step = STEPS[index];
    const el = findTarget(step.target);
    if (!el || !el.getBoundingClientRect) {
      showStep(index + 1);
      return;
    }

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      showStep(index + 1);
      return;
    }

    // Hide tooltip during scroll transition
    tooltip.classList.remove('active');

    scrollToElement(el, () => _renderStep(step, el));
  }

  function _renderStep(step, el) {
    const rect = el.getBoundingClientRect();

    content.innerHTML =
      '<span class="tour-tip-icon ' + step.iconClass + '"></span>' +
      '<div class="tour-tip-title">' + step.title + '</div>' +
      '<p class="tour-tip-desc">' + step.desc + '</p>';

    renderProgress();

    nextBtn.textContent = currentStep === STEPS.length - 1 ? 'Done' : 'Next';

    overlay.classList.add('active');

    requestAnimationFrame(() => {
      tooltip.classList.add('active');
      positionTooltip(rect, step.position);
    });
  }

  function endTour() {
    overlay.classList.remove('active');
    tooltip.classList.remove('active');
    localStorage.setItem(TOUR_KEY, '1');
  }

  nextBtn.addEventListener('click', () => showStep(currentStep + 1));
  skipBtn.addEventListener('click', endTour);
  overlay.addEventListener('click', endTour);

  // Expose globally so the menu button can trigger it
  window.startAppTour = function() {
    // Close the user dropdown first
    const dd = document.getElementById('userDropdown');
    if (dd) dd.classList.remove('open');
    // Scroll to top first for a clean start
    window.scrollTo({ top: 0, behavior: 'smooth' });
    currentStep = 0;
    setTimeout(() => showStep(0), 400);
  };

  // Auto-start for first-time visitors — generous delay so UI settles.
  // If the PIN overlay is active, wait for it to close before starting.
  if (isFirstVisit) {
    const tourDelay = window.__INITIAL_DATA__ ? 2500 : 4500;
    setTimeout(() => {
      const pinOverlay = document.getElementById('pinOverlay');
      if (pinOverlay && pinOverlay.style.display !== 'none' && pinOverlay.style.display !== '') {
        // PIN flow is active — observe until it's dismissed, then start tour
        const obs = new MutationObserver(() => {
          if (pinOverlay.style.display === 'none' || pinOverlay.style.display === '') {
            obs.disconnect();
            setTimeout(() => showStep(0), 600);
          }
        });
        obs.observe(pinOverlay, { attributes: true, attributeFilter: ['style'] });
      } else {
        showStep(0);
      }
    }, tourDelay);
  }
})();

// ─── Security PIN Management ──────────────────────────────────

(function() {
  const overlay  = document.getElementById('pinOverlay');
  const title    = document.getElementById('pinTitle');
  const subtitle = document.getElementById('pinSubtitle');
  const inputRow = document.getElementById('pinInputRow');
  const confirmGroup = document.getElementById('pinConfirmGroup');
  const confirmRow = document.getElementById('pinConfirmRow');
  const errorEl  = document.getElementById('pinError');
  const forgotBtn = document.getElementById('pinForgotBtn');
  const logoutBtn = document.getElementById('pinLogoutBtn');
  const footerLinks = document.getElementById('pinFooterLinks');
  const infoEl   = document.getElementById('pinInfo');
  const pinCheck1 = document.getElementById('pinCheck1');
  const pinCheck2 = document.getElementById('pinCheck2');
  const fieldLabel1 = document.getElementById('pinFieldLabel1');
  const resetDialog = document.getElementById('pinResetDialog');
  const resetCancel = document.getElementById('pinResetCancel');
  const resetConfirm = document.getElementById('pinResetConfirm');
  const resetInput = document.getElementById('pinResetInput');
  const resetCheck = document.getElementById('pinResetCheck');

  if (!overlay) return;

  let mode = 'verify'; // 'verify' | 'setup'
  let _onComplete = null;
  let _wrongAttempts = 0;

  const _wrongPinMessages = [
    'Hmm, that\'s not it.',
    'Nope — give it another shot.',
    'Still not right. Think carefully…',
    'That PIN doesn\'t ring a bell.',
    'Three strikes? Keep trying.',
    'The vault remains sealed.',
    'Not quite. You\'ve got this.',
    'Wrong key, wrong door.',
  ];

  // ── Helpers ──

  function getDigits(row) {
    return Array.from(row.querySelectorAll('.pin-digit')).map(i => i.value).join('');
  }

  function clearRow(row) {
    row.querySelectorAll('.pin-digit').forEach(i => {
      i.value = '';
      i.classList.remove('pin-digit-filled');
    });
  }

  function clearAll() {
    clearRow(inputRow);
    if (confirmRow) clearRow(confirmRow);
    errorEl.textContent = '';
    errorEl.classList.remove('pin-error-active');
  }

  function showError(html) {
    errorEl.classList.remove('pin-error-active');
    // Force reflow to re-trigger animation
    void errorEl.offsetWidth;
    errorEl.innerHTML = html;
    if (html) errorEl.classList.add('pin-error-active');
  }

  function flashError(row) {
    // Shake the row
    row.classList.add('pin-shake');
    // Red-flash each digit
    row.querySelectorAll('.pin-digit').forEach(d => d.classList.add('pin-digit-error'));
    // Remove classes after animation completes so it can re-trigger
    setTimeout(() => {
      row.classList.remove('pin-shake');
      row.querySelectorAll('.pin-digit').forEach(d => d.classList.remove('pin-digit-error'));
    }, 600);
  }

  function wireDigitInputs(row, { onRowComplete } = {}) {
    const inputs = row.querySelectorAll('.pin-digit');
    inputs.forEach((inp, i) => {
      inp.addEventListener('input', () => {
        inp.value = inp.value.replace(/[^a-zA-Z0-9]/g, '').slice(-1);
        // Toggle filled-state styling
        inp.classList.toggle('pin-digit-filled', !!inp.value);
        updateSubmitState();
        if (inp.value && i < inputs.length - 1) {
          inputs[i + 1].focus();
        } else if (inp.value && i === inputs.length - 1 && onRowComplete) {
          onRowComplete();
        }
      });
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !inp.value && i > 0) {
          inputs[i - 1].focus();
          inputs[i - 1].value = '';
          inputs[i - 1].classList.remove('pin-digit-filled');
          updateSubmitState();
        }
        if (e.key === 'Enter') handlePinSubmit();
      });
      inp.addEventListener('paste', (e) => {
        e.preventDefault();
        const paste = (e.clipboardData.getData('text') || '').replace(/[^a-zA-Z0-9]/g, '').slice(0, 6);
        for (let j = 0; j < paste.length && (i + j) < inputs.length; j++) {
          inputs[i + j].value = paste[j];
          inputs[i + j].classList.toggle('pin-digit-filled', !!paste[j]);
        }
        const nextEmpty = Array.from(inputs).findIndex(el => !el.value);
        if (nextEmpty >= 0) {
          inputs[nextEmpty].focus();
        } else {
          inputs[inputs.length - 1].focus();
          if (onRowComplete) onRowComplete();
        }
        updateSubmitState();
      });
    });
  }

  function updateCheckmarks() {
    const pin = getDigits(inputRow);
    const confirm = confirmRow ? getDigits(confirmRow) : '';
    if (pinCheck1) pinCheck1.classList.toggle('done', pin.length === 6);
    if (pinCheck2) pinCheck2.classList.toggle('done', confirm.length === 6);
  }

  wireDigitInputs(inputRow, {
    onRowComplete: () => {
      if (mode === 'verify') handlePinSubmit();
      else if (mode === 'setup') confirmRow.querySelector('.pin-digit')?.focus();
    },
  });
  if (confirmRow) wireDigitInputs(confirmRow, {
    onRowComplete: () => { if (mode === 'setup') handlePinSubmit(); },
  });

  function updateSubmitState() {
    updateCheckmarks();
  }

  let _lockoutTimer = null;

  function startLockout(seconds) {
    inputRow.querySelectorAll('.pin-digit').forEach(d => d.disabled = true);
    if (footerLinks) footerLinks.style.display = '';

    function tick() {
      if (seconds <= 0) {
        clearInterval(_lockoutTimer);
        _lockoutTimer = null;
        inputRow.querySelectorAll('.pin-digit').forEach(d => d.disabled = false);
        errorEl.textContent = '';
        clearAll();
        inputRow.querySelector('.pin-digit')?.focus();
        return;
      }
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      const timeStr = mins > 0
        ? `${mins}m ${secs.toString().padStart(2, '0')}s`
        : `${secs}s`;
      showError('<span class="pin-lockout-msg">Try again in <strong>' + timeStr + '</strong></span>');
      seconds--;
    }

    tick();
    _lockoutTimer = setInterval(tick, 1000);
  }

  function setLoading(loading) {
    inputRow.querySelectorAll('.pin-digit').forEach(d => { d.disabled = loading; });
    inputRow.classList.toggle('pin-loading', loading);
    if (mode === 'setup' && confirmRow) {
      confirmRow.querySelectorAll('.pin-digit').forEach(d => { d.disabled = loading; });
      confirmRow.classList.toggle('pin-loading', loading);
    }
  }

  // ── Show / Hide ──

  function showOverlay(overlayMode, onComplete) {
    mode = overlayMode;
    _onComplete = onComplete;
    clearAll();

    if (mode === 'setup') {
      title.textContent = 'Create PIN';
      if (subtitle) { subtitle.style.display = ''; subtitle.textContent = 'Choose a 6-character alphanumeric PIN to secure your data. This PIN is never stored — remember it carefully.'; }
      if (infoEl) infoEl.style.display = '';
      confirmGroup.style.display = '';
      if (fieldLabel1) fieldLabel1.parentElement.style.display = '';
      if (footerLinks) footerLinks.style.display = 'none';
      if (pinCheck1) pinCheck1.classList.remove('done');
      if (pinCheck2) pinCheck2.classList.remove('done');
    } else {
      title.textContent = 'Enter PIN';
      if (subtitle) subtitle.style.display = 'none';
      confirmGroup.style.display = 'none';
      if (fieldLabel1) fieldLabel1.parentElement.style.display = 'none';
      if (footerLinks) footerLinks.style.display = '';
      if (infoEl) infoEl.style.display = 'none';
      _wrongAttempts = 0;
      if (pinCheck1) pinCheck1.classList.remove('done');
    }

    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    // Focus first input after transition
    requestAnimationFrame(() => {
      const first = inputRow.querySelector('.pin-digit');
      if (first) first.focus();
    });
  }

  function hideOverlay() {
    const wasVisible = overlay.style.display !== 'none';

    if (wasVisible) {
      // Animate the PIN overlay out
      overlay.classList.add('pin-exit');

      // After the exit animation, reveal dashboard with entrance animation
      const onExit = () => {
        overlay.removeEventListener('animationend', onExit);
        overlay.style.display = 'none';
        overlay.classList.remove('pin-exit');
        document.body.style.overflow = '';

        // Reveal the dashboard with staggered entrance animation
        const container = document.querySelector('.container');
        if (container) {
          container.style.visibility = '';
          container.classList.add('dash-entrance');
          // Clean up after all animations complete
          setTimeout(() => container.classList.remove('dash-entrance'), 1200);
        }
      };
      overlay.addEventListener('animationend', onExit);
    } else {
      // Overlay was already hidden (e.g. already verified) — just ensure dashboard is visible
      overlay.style.display = 'none';
      document.body.style.overflow = '';
      const container = document.querySelector('.container');
      if (container) container.style.visibility = '';
    }

    if (_lockoutTimer) { clearInterval(_lockoutTimer); _lockoutTimer = null; }
    inputRow.querySelectorAll('.pin-digit').forEach(d => d.disabled = false);
    clearAll();
  }

  // ── Submit ──

  async function handlePinSubmit() {
    const pin = getDigits(inputRow);
    if (pin.length !== 6) return;

    if (mode === 'setup') {
      const confirm = getDigits(confirmRow);
      if (confirm.length !== 6) return;
      if (pin !== confirm) {
        showError('<span class="pin-mismatch-msg">PINs do not match — try again</span>');
        flashError(confirmRow);
        clearRow(confirmRow);
        updateCheckmarks();
        confirmRow.querySelector('.pin-digit')?.focus();
        return;
      }
    }

    setLoading(true);
    try {
      const endpoint = mode === 'setup' ? '/api/pin/setup' : '/api/pin/verify';
      const resp = await window.metronFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        if (data.locked && data.retry_after) {
          console.debug('[PIN] Locked out for', data.retry_after, 's');
          flashError(inputRow);
          clearAll();
          startLockout(data.retry_after);
          return;
        }
        if (mode === 'verify') {
          _wrongAttempts = data.attempts || (_wrongAttempts + 1);
          console.debug('[PIN] Verify failed: attempt', _wrongAttempts);
          const msg = _wrongPinMessages[(_wrongAttempts - 1) % _wrongPinMessages.length];
          showError(msg + (_wrongAttempts >= 2
            ? ' <span class="pin-attempt-count">' + _wrongAttempts + ' attempt' + (_wrongAttempts !== 1 ? 's' : '') + '</span>'
            : ''));
        } else {
          showError(data.error || 'Setup failed');
        }
        flashError(mode === 'setup' ? confirmRow : inputRow);
        clearAll();
        requestAnimationFrame(() => inputRow.querySelector('.pin-digit')?.focus());
        return;
      }
      _wrongAttempts = 0;
      console.debug('[PIN]', mode === 'setup' ? 'PIN created' : 'PIN verified OK');
      hideOverlay();
      if (_onComplete) _onComplete();
    } catch {
      showError('Network error — try again');
    } finally {
      setLoading(false);
    }
  }

  // ── Forgot PIN ──

  forgotBtn.addEventListener('click', () => {
    resetInput.value = '';
    resetConfirm.disabled = true;
    resetInput.classList.remove('matched');
    if (resetCheck) resetCheck.classList.remove('done');
    resetDialog.style.display = 'flex';
    requestAnimationFrame(() => resetInput.focus());
  });

  resetInput.addEventListener('input', () => {
    const matched = resetInput.value.trim().toLowerCase() === 'reset';
    resetConfirm.disabled = !matched;
    resetInput.classList.toggle('matched', matched);
    if (resetCheck) resetCheck.classList.toggle('done', matched);
  });

  resetInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !resetConfirm.disabled) resetConfirm.click();
  });

  resetCancel.addEventListener('click', () => {
    resetDialog.style.display = 'none';
  });

  resetConfirm.addEventListener('click', async () => {
    resetConfirm.disabled = true;
    resetConfirm.textContent = 'Resetting…';
    try {
      const resp = await window.metronFetch('/api/pin/reset', { method: 'POST' });
      if (!resp.ok) throw new Error();
      console.debug('[PIN] Reset complete — switching to setup mode');
      // Close reset dialog and transition directly to setup mode
      // (no reload — avoids dashboard flash)
      resetDialog.style.display = 'none';
      showOverlay('setup', () => {
        // After new PIN is set, reload to fetch fresh data
        window.location.reload();
      });
    } catch {
      alert('Reset failed — please try again.');
    } finally {
      resetConfirm.disabled = false;
      resetConfirm.textContent = 'Reset Everything';
    }
  });

  // ── Logout ──

  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      logoutBtn.disabled = true;
      logoutBtn.textContent = 'Logging out…';
      try {
        await window.metronFetch('/api/auth/logout', { method: 'POST' });
      } finally {
        window.location.href = '/';
      }
    });
  }

  // ── Keyboard: close reset dialog on Escape ──
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && resetDialog.style.display !== 'none') {
      resetDialog.style.display = 'none';
    }
  });

  // ── Global API: check PIN and show overlay if needed ──

  /**
   * Check PIN status and show the overlay if needed.
   * Returns a promise that resolves when the user is either:
   *  a) already PIN-verified, or
   *  b) has just completed PIN entry/setup via the overlay
   * Returns false if no PIN is needed (no Zerodha accounts).
   */
  window.checkAndPromptPin = async function() {
    try {
      const resp = await window.metronFetch('/api/pin/status');
      if (!resp.ok) return false;
      const data = await resp.json();

      if (data.pin_verified) {
        console.debug('[PIN] Already verified');
        hideOverlay();
        return true;
      }

      return new Promise((resolve) => {
        const overlayMode = data.has_pin ? 'verify' : 'setup';
        showOverlay(overlayMode, () => resolve(true));
      });
    } catch {
      return false;
    }
  };

  /**
   * Show the PIN setup overlay for newly added accounts.
   * Called from the settings drawer when adding the first Zerodha account
   * without a PIN set up yet.
   */
  window.showPinSetup = function() {
    return new Promise((resolve) => {
      showOverlay('setup', () => resolve(true));
    });
  };
})();
