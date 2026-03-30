// Lightweight SPA router for Metron
// Intercepts sidebar nav clicks and swaps page content without full reload.
// Keeps the sidebar, backdrop, and theme state persistent.
(function() {
  'use strict';

  const SPA_ROUTES = ['/', '/exposure', '/nifty50', '/mutual-funds/transactions'];

  const SHARED_SCRIPT_PATTERNS = [
    '/static/js/nav.js',
    '/static/js/router.js',
    '/static/js/pwa-install.js'
  ];

  const SHARED_CSS_PATTERNS = [
    '/static/css/styles.css',
    '/static/css/nav-header.css',
    '/static/css/pwa-install.css',
    'fonts.googleapis.com'
  ];

  let isNavigating = false;
  let abortController = null;

  // ─── Helpers ──────────────────────────────────────────

  function isSpaRoute(href) {
    try {
      const u = new URL(href, location.origin);
      if (u.origin !== location.origin) return false;
      return SPA_ROUTES.indexOf(u.pathname) !== -1;
    } catch (e) { return false; }
  }

  function isSharedScript(src) {
    if (!src) return false;
    for (let i = 0; i < SHARED_SCRIPT_PATTERNS.length; i++) {
      if (src.indexOf(SHARED_SCRIPT_PATTERNS[i]) !== -1) return true;
    }
    return false;
  }

  function isSkippableInline(text) {
    if (!text) return false;
    const t = text.trim();
    // Skip theme init and service worker registration
    if (t.length < 200 && t.indexOf("localStorage.getItem('theme')") !== -1) return true;
    if (t.indexOf('serviceWorker') !== -1 && t.indexOf('register') !== -1 && t.length < 150) return true;
    return false;
  }

  function isSharedCss(href) {
    if (!href) return false;
    for (let i = 0; i < SHARED_CSS_PATTERNS.length; i++) {
      if (href.indexOf(SHARED_CSS_PATTERNS[i]) !== -1) return true;
    }
    return false;
  }

  // ─── Progress bar ─────────────────────────────────────

  let progressEl = null;

  function getProgressBar() {
    if (!progressEl) {
      progressEl = document.createElement('div');
      progressEl.className = 'spa-progress';
      document.body.appendChild(progressEl);
    }
    return progressEl;
  }

  function startProgress() {
    const bar = getProgressBar();
    bar.style.transition = 'none';
    bar.style.width = '0%';
    bar.style.opacity = '1';
    // Force reflow
    void bar.offsetWidth;
    bar.style.transition = 'width .6s cubic-bezier(.4,0,.2,1)';
    bar.style.width = '70%';
  }

  function finishProgress() {
    const bar = getProgressBar();
    bar.style.transition = 'width .15s ease-out, opacity .3s ease .15s';
    bar.style.width = '100%';
    bar.style.opacity = '0';
  }

  // ─── Body-node tracking ───────────────────────────────
  // Automatically tracks every element page scripts append to <body>.
  // No manual marking needed — the observer handles it generically.
  // Starts at router init to catch initial page scripts, and restarts
  // before each SPA page's scripts so new pages are tracked too.

  let _spaBodyNodes = [];
  let _bodyObserver = null;

  function startTrackingBodyNodes() {
    if (_bodyObserver) _bodyObserver.disconnect();
    _spaBodyNodes = [];
    // Tag names to ignore: script/link/style are infrastructure managed
    // by cleanupCurrentPage and syncCss — don't let the observer touch them.
    const SKIP_TAGS = { SCRIPT: 1, LINK: 1, STYLE: 1 };
    // Nav drawer and backdrop are part of the page shell (rendered after the
    // script tags in the HTML), so the observer fires for them on initial load.
    // Exclude them so they are never treated as page-owned nodes and removed.
    const SKIP_IDS = { navDrawer: 1, navDrawerBackdrop: 1 };

    _bodyObserver = new MutationObserver(function(mutations) {
      for (let i = 0; i < mutations.length; i++) {
        const added = mutations[i].addedNodes;
        for (let j = 0; j < added.length; j++) {
          const n = added[j];
          if (n.nodeType !== 1) continue;           // elements only
          if (n === progressEl) continue;            // router's progress bar
          if (SKIP_TAGS[n.tagName]) continue;        // scripts / stylesheets
          if (SKIP_IDS[n.id]) continue;              // persistent shell elements
          _spaBodyNodes.push(n);
        }
      }
    });
    _bodyObserver.observe(document.body, { childList: true });
  }

  function cleanupTrackedBodyNodes() {
    if (_bodyObserver) {
      _bodyObserver.disconnect();
      _bodyObserver = null;
    }
    for (let i = 0; i < _spaBodyNodes.length; i++) {
      const el = _spaBodyNodes[i];
      if (el.parentNode) el.remove();
    }
    _spaBodyNodes = [];
    // Restore any scroll lock a page script may have applied
    document.body.style.overflow = '';
  }

  // ─── Cleanup ──────────────────────────────────────────

  function cleanupCurrentPage() {
    // Stop observing and remove all body elements the current page added
    cleanupTrackedBodyNodes();

    // Remove dynamically-added scripts from previous SPA navigation
    document.querySelectorAll('script[data-spa]').forEach(function(s) {
      s.remove();
    });

    // Portfolio
    if (window.portfolioApp) {
      try {
        window.portfolioApp._disposed = true;
        if (window.portfolioApp.relativeStatusTimer) {
          clearInterval(window.portfolioApp.relativeStatusTimer);
        }
        if (window.portfolioApp.indexTicker &&
            window.portfolioApp.indexTicker.cleanup) {
          window.portfolioApp.indexTicker.cleanup();
        }
      } catch (e) { /* best-effort */ }
      delete window.portfolioApp;
    }

    // Nifty50
    if (window.nifty50App) {
      try { window.nifty50App.cleanup(); } catch (e) {}
      delete window.nifty50App;
    }

    // Exposure
    if (typeof window.cleanupExposure === 'function') {
      try { window.cleanupExposure(); } catch (e) {}
    }
    delete window.loadExposureData;
    delete window.refreshExposure;
    delete window.cleanupExposure;

    // Transactions
    if (typeof window.cleanupTransactions === 'function') {
      try { window.cleanupTransactions(); } catch (e) {}
    }
    delete window.cleanupTransactions;

    // Shared
    delete window.__INITIAL_DATA__;
    delete window.__TABLE_ROW_LIMIT__;
  }

  // ─── CSS sync ─────────────────────────────────────────

  // Returns a Promise that resolves once all newly-added stylesheets have loaded.
  function syncCss(newDoc) {
    const current = {};
    document.querySelectorAll('link[rel="stylesheet"]').forEach(function(l) {
      const h = l.getAttribute('href');
      if (h) current[h] = l;
    });

    const needed = {};
    newDoc.querySelectorAll('link[rel="stylesheet"]').forEach(function(l) {
      const h = l.getAttribute('href');
      if (h) needed[h] = true;
    });

    // Remove page-specific CSS not needed by new page
    Object.keys(current).forEach(function(href) {
      if (!isSharedCss(href) && !needed[href]) {
        current[href].remove();
      }
    });

    // Add new CSS and collect load promises for sheets not yet present
    const pending = [];
    Object.keys(needed).forEach(function(href) {
      if (!current[href]) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        pending.push(new Promise(function(resolve) {
          link.onload = resolve;
          link.onerror = resolve; // don't block on 404
        }));
        document.head.appendChild(link);
      }
    });

    return Promise.all(pending);
  }

  // ─── Script execution ────────────────────────────────

  function executeScripts(newDoc) {
    const scripts = [];
    newDoc.querySelectorAll('body script').forEach(function(s) {
      const src = s.getAttribute('src');
      if (src && isSharedScript(src)) return;
      if (!src && isSkippableInline(s.textContent)) return;
      scripts.push({ src: src, type: s.type || '', text: s.textContent, attrs: s.attributes });
    });

    return new Promise(function(resolve) {
      let idx = 0;

      function next() {
        if (idx >= scripts.length) { resolve(); return; }
        const info = scripts[idx++];
        const el = document.createElement('script');
        el.setAttribute('data-spa', '1');

        // Copy attributes
        for (let i = 0; i < info.attrs.length; i++) {
          const a = info.attrs[i];
          if (a.name === 'src') continue; // handled below
          el.setAttribute(a.name, a.value);
        }

        if (info.src) {
          let finalSrc = info.src;
          // Cache-bust modules so browser re-executes them
          if (info.type === 'module') {
            finalSrc += (finalSrc.indexOf('?') === -1 ? '?' : '&') + '_v=' + Date.now();
          }
          el.src = finalSrc;

          if (info.type === 'module') {
            // Modules load async - don't block on them
            document.body.appendChild(el);
            next();
          } else {
            el.onload = next;
            el.onerror = next;
            document.body.appendChild(el);
          }
        } else {
          // Inline script - executes synchronously
          el.textContent = info.text;
          document.body.appendChild(el);
          next();
        }
      }

      next();
    });
  }

  // ─── Sidebar active state ────────────────────────────

  function updateSidebarActive(path) {
    document.querySelectorAll('.nav-drawer-link').forEach(function(link) {
      const href = link.getAttribute('href');
      let active = false;
      active = href === path;
      link.classList.toggle('active', active);
    });
  }

  // ─── Swap outside-container elements ──────────────────

  const OUTSIDE_SELECTORS = [
    '.settings-drawer',
    '#drawerBackdrop',
    '#casModal',
    '#casModalBackdrop',
    '.app-tour-overlay',
    '.app-tour-tooltip',
    '.pin-overlay',
    'footer.mf-footer'
  ];

  function swapOutsideElements(newDoc) {
    // Remove current outside-container page-specific elements
    OUTSIDE_SELECTORS.forEach(function(sel) {
      document.querySelectorAll(sel).forEach(function(el) { el.remove(); });
    });

    const refNode = document.getElementById('navDrawerBackdrop') ||
                  document.getElementById('navDrawer');

    // Insert new outside-container elements from fetched page
    const newBody = newDoc.querySelector('body');
    if (!newBody) return;

    OUTSIDE_SELECTORS.forEach(function(sel) {
      newBody.querySelectorAll(sel).forEach(function(el) {
        if (refNode) {
          refNode.parentNode.insertBefore(el, refNode);
        } else {
          document.body.appendChild(el);
        }
      });
    });
  }

  // ─── Main navigate ───────────────────────────────────

  function navigateTo(url, doPush) {
    const targetPath = new URL(url, location.origin).pathname;
    if (targetPath === location.pathname) return;
    if (isNavigating) return;
    isNavigating = true;

    if (abortController) abortController.abort();
    abortController = new AbortController();

    startProgress();

    fetch(url, {
      signal: abortController.signal,
      headers: { 'X-Requested-With': 'MetronApp' }
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.text();
    })
    .then(function(html) {
      const doc = new DOMParser().parseFromString(html, 'text/html');

      // 1. Cleanup previous page JS and all body elements it created
      cleanupCurrentPage();

      // 2. Title
      document.title = doc.title || 'Metron';

      // 3. CSS – wait for new sheets to load before swapping content (prevents FOUC)
      return syncCss(doc).then(function() {
        // 4. Swap container content
        const newContainer = doc.querySelector('.container');
        const curContainer = document.querySelector('.container');
        if (newContainer && curContainer) {
          curContainer.innerHTML = newContainer.innerHTML;
          // Preserve or update container-level attributes
          const style = newContainer.getAttribute('style');
          if (style) {
            curContainer.setAttribute('style', style);
          } else {
            curContainer.removeAttribute('style');
          }
        }

        // 5. Swap outside-container elements
        swapOutsideElements(doc);

        // 6. Update sidebar
        updateSidebarActive(targetPath);

        // 7. Re-bind nav header events
        if (typeof window.bindNavHeaderEvents === 'function') {
          window.bindNavHeaderEvents();
        }

        // 8. Start tracking body mutations before scripts run so any elements
        //    they append to <body> are automatically captured for later cleanup
        startTrackingBodyNodes();

        // 9. Execute scripts
        return executeScripts(doc);
      });
    })
    .then(function() {
      // 10. Push state
      if (doPush !== false) {
        history.pushState({ metronSpa: true }, '', url);
      }

      // 11. Scroll to top
      window.scrollTo(0, 0);
    })
    .catch(function(err) {
      if (err.name === 'AbortError') return;
      console.error('SPA nav failed, falling back:', err);
      location.href = url;
    })
    .finally(function() {
      finishProgress();
      isNavigating = false;
    });
  }

  // ─── Event interception ───────────────────────────────

  document.addEventListener('click', function(e) {
    if (e.defaultPrevented) return;
    const link = e.target.closest('a[href]');
    if (!link) return;
    // Don't intercept modified clicks (new tab, etc.)
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (link.target === '_blank') return;

    const href = link.getAttribute('href');
    if (href && isSpaRoute(href)) {
      e.preventDefault();
      // Close mobile nav drawer if it's open
      if (typeof closeNavDrawer === 'function' && !isDesktopSidebar()) {
        closeNavDrawer();
      }
      navigateTo(href);
    }
  });

  // ─── Browser back/forward ─────────────────────────────

  window.addEventListener('popstate', function() {
    if (isSpaRoute(location.href)) {
      navigateTo(location.href, false);
    }
  });

  // Mark initial load in history
  history.replaceState({ metronSpa: true }, '', location.href);

  // Start tracking body mutations from the initial page's scripts so the
  // first navigation cleans them up automatically (e.g. fundModalOverlay).
  startTrackingBodyNodes();

  // ─── CSS preloading ───────────────────────────────────
  // After the page is idle, fetch all other SPA routes in the background
  // and preload their page-specific CSS so navigation is instant with no FOUC.

  function preloadSpaAssets() {
    const currentPath = location.pathname;
    const otherRoutes = SPA_ROUTES.filter(function(r) { return r !== currentPath; });

    otherRoutes.forEach(function(route) {
      fetch(route, {
        headers: { 'X-Requested-With': 'MetronApp' }
      })
      .then(function(r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function(html) {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        doc.querySelectorAll('link[rel="stylesheet"]').forEach(function(l) {
          const href = l.getAttribute('href');
          if (!href || isSharedCss(href)) return;
          // Skip if already loaded or preloaded
          if (document.querySelector('link[href="' + href + '"]')) return;
          const preload = document.createElement('link');
          preload.rel = 'preload';
          preload.as = 'style';
          preload.href = href;
          document.head.appendChild(preload);
        });
      })
      .catch(function() { /* best-effort, ignore failures */ });
    });
  }

  // Defer until the browser is idle so it doesn't compete with main content
  if (window.requestIdleCallback) {
    window.requestIdleCallback(preloadSpaAssets, { timeout: 3000 });
  } else {
    setTimeout(preloadSpaAssets, 2000);
  }
})();
