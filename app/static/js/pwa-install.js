/**
 * Metron PWA Install Prompt
 * Shows a native-feeling bottom sheet on mobile/tablet devices only.
 * Respects user dismissal (won't re-prompt for 30 days).
 */
(function () {
  'use strict';

  const DISMISS_KEY = 'metron_pwa_dismiss';
  const DISMISS_DAYS = 30;
  const IOS_STANDALONE = window.navigator.standalone === true;
  const DISPLAY_STANDALONE = window.matchMedia('(display-mode: standalone)').matches;

  // Already installed or not a touch device → bail
  if (IOS_STANDALONE || DISPLAY_STANDALONE) return;

  // Only show on mobile / tablet (touch + small-to-medium screen)
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const isSmallScreen = window.matchMedia('(max-width: 1024px)').matches;
  if (!isTouchDevice || !isSmallScreen) return;

  // Respect previous dismissal
  const dismissed = localStorage.getItem(DISMISS_KEY);
  if (dismissed) {
    const elapsed = Date.now() - parseInt(dismissed, 10);
    if (elapsed < DISMISS_DAYS * 86400000) return;
  }

  // Platform detection
  const ua = navigator.userAgent;
  const platformHint = navigator.userAgentData ? navigator.userAgentData.platform : ua;
  const isIOS = /iPad|iPhone|iPod/.test(ua) ||
    (/Mac/i.test(platformHint) && navigator.maxTouchPoints > 1);

  let deferredPrompt = null;

  // Capture the beforeinstallprompt event (Chrome/Edge/Samsung)
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    showBanner();
  });

  // On iOS there's no beforeinstallprompt — show after a short delay
  if (isIOS) {
    setTimeout(showBanner, 3000);
  }

  function showBanner() {
    // Don't double-show
    if (document.getElementById('pwa-install-banner')) return;

    // Build the banner
    const banner = document.createElement('div');
    banner.id = 'pwa-install-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', 'Install Metron app');

    const isIOSPrompt = isIOS && !deferredPrompt;

    banner.innerHTML =
      '<div class="pwa-backdrop"></div>' +
      '<div class="pwa-sheet">' +
        '<div class="pwa-handle"></div>' +
        '<div class="pwa-content">' +
          '<div class="pwa-icon">' +
            '<img src="/static/images/icon-192x192.png" width="56" height="56" alt="Metron">' +
          '</div>' +
          '<div class="pwa-text">' +
            '<div class="pwa-title">Add Metron to Home Screen</div>' +
            '<div class="pwa-subtitle">' +
              (isIOSPrompt
                ? 'Tap <span class="pwa-share-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></span> then <strong>"Add to Home Screen"</strong>'
                : 'Install for quick access — no app store needed') +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="pwa-actions">' +
          (isIOSPrompt
            ? '<button class="pwa-btn pwa-btn-dismiss" id="pwaClose">Got it</button>'
            : '<button class="pwa-btn pwa-btn-dismiss" id="pwaClose">Not now</button>' +
              '<button class="pwa-btn pwa-btn-install" id="pwaInstall">Install</button>') +
        '</div>' +
      '</div>';

    document.body.appendChild(banner);

    // Animate in
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        banner.classList.add('pwa-visible');
      });
    });

    // Close handler
    const closeBtn = document.getElementById('pwaClose');
    const backdrop = banner.querySelector('.pwa-backdrop');
    function dismiss() {
      banner.classList.remove('pwa-visible');
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
      setTimeout(function () { banner.remove(); }, 350);
    }
    closeBtn.addEventListener('click', dismiss);
    backdrop.addEventListener('click', dismiss);

    // Install handler (Chrome/Edge)
    const installBtn = document.getElementById('pwaInstall');
    if (installBtn && deferredPrompt) {
      installBtn.addEventListener('click', function () {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (result) {
          if (result.outcome === 'accepted') {
            banner.classList.remove('pwa-visible');
            setTimeout(function () { banner.remove(); }, 350);
          }
          deferredPrompt = null;
        });
      });
    }
  }

  // Hide banner if user installs via browser UI
  window.addEventListener('appinstalled', function () {
    const banner = document.getElementById('pwa-install-banner');
    if (banner) {
      banner.classList.remove('pwa-visible');
      setTimeout(function () { banner.remove(); }, 350);
    }
  });
})();
