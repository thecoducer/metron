// Lightweight SPA router for Metron
// Intercepts sidebar nav clicks and swaps page content without full reload.
// Keeps the sidebar, backdrop, and theme state persistent.
(function() {
  'use strict';

  var SPA_ROUTES = ['/', '/exposure', '/nifty50', '/mutual-funds/transactions'];

  var SHARED_SCRIPT_PATTERNS = [
    '/static/js/nav.js',
    '/static/js/router.js',
    '/static/js/pwa-install.js'
  ];

  var SHARED_CSS_PATTERNS = [
    '/static/css/styles.css',
    '/static/css/nav-header.css',
    '/static/css/pwa-install.css',
    'fonts.googleapis.com'
  ];

  var isNavigating = false;
  var abortController = null;

  // ─── Helpers ──────────────────────────────────────────

  function isSpaRoute(href) {
    try {
      var u = new URL(href, location.origin);
      if (u.origin !== location.origin) return false;
      return SPA_ROUTES.indexOf(u.pathname) !== -1;
    } catch (e) { return false; }
  }

  function isSharedScript(src) {
    if (!src) return false;
    for (var i = 0; i < SHARED_SCRIPT_PATTERNS.length; i++) {
      if (src.indexOf(SHARED_SCRIPT_PATTERNS[i]) !== -1) return true;
    }
    return false;
  }

  function isSkippableInline(text) {
    if (!text) return false;
    var t = text.trim();
    // Skip theme init and service worker registration
    if (t.length < 200 && t.indexOf("localStorage.getItem('theme')") !== -1) return true;
    if (t.indexOf('serviceWorker') !== -1 && t.indexOf('register') !== -1 && t.length < 150) return true;
    return false;
  }

  function isSharedCss(href) {
    if (!href) return false;
    for (var i = 0; i < SHARED_CSS_PATTERNS.length; i++) {
      if (href.indexOf(SHARED_CSS_PATTERNS[i]) !== -1) return true;
    }
    return false;
  }

  // ─── Progress bar ─────────────────────────────────────

  var progressEl = null;

  function getProgressBar() {
    if (!progressEl) {
      progressEl = document.createElement('div');
      progressEl.className = 'spa-progress';
      document.body.appendChild(progressEl);
    }
    return progressEl;
  }

  function startProgress() {
    var bar = getProgressBar();
    bar.style.transition = 'none';
    bar.style.width = '0%';
    bar.style.opacity = '1';
    // Force reflow
    void bar.offsetWidth;
    bar.style.transition = 'width .6s cubic-bezier(.4,0,.2,1)';
    bar.style.width = '70%';
  }

  function finishProgress() {
    var bar = getProgressBar();
    bar.style.transition = 'width .15s ease-out, opacity .3s ease .15s';
    bar.style.width = '100%';
    bar.style.opacity = '0';
  }

  // ─── Cleanup ──────────────────────────────────────────

  function cleanupCurrentPage() {
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

  function syncCss(newDoc) {
    // Collect current and new stylesheet hrefs
    var current = {};
    document.querySelectorAll('link[rel="stylesheet"]').forEach(function(l) {
      var h = l.getAttribute('href');
      if (h) current[h] = l;
    });

    var needed = {};
    newDoc.querySelectorAll('link[rel="stylesheet"]').forEach(function(l) {
      var h = l.getAttribute('href');
      if (h) needed[h] = true;
    });

    // Remove page-specific CSS not needed by new page
    Object.keys(current).forEach(function(href) {
      if (!isSharedCss(href) && !needed[href]) {
        current[href].remove();
      }
    });

    // Add new CSS
    Object.keys(needed).forEach(function(href) {
      if (!current[href]) {
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        document.head.appendChild(link);
      }
    });
  }

  // ─── Script execution ────────────────────────────────

  function executeScripts(newDoc) {
    var scripts = [];
    newDoc.querySelectorAll('body script').forEach(function(s) {
      var src = s.getAttribute('src');
      if (src && isSharedScript(src)) return;
      if (!src && isSkippableInline(s.textContent)) return;
      scripts.push({ src: src, type: s.type || '', text: s.textContent, attrs: s.attributes });
    });

    return new Promise(function(resolve) {
      var idx = 0;

      function next() {
        if (idx >= scripts.length) { resolve(); return; }
        var info = scripts[idx++];
        var el = document.createElement('script');
        el.setAttribute('data-spa', '1');

        // Copy attributes
        for (var i = 0; i < info.attrs.length; i++) {
          var a = info.attrs[i];
          if (a.name === 'src') continue; // handled below
          el.setAttribute(a.name, a.value);
        }

        if (info.src) {
          var finalSrc = info.src;
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
      var href = link.getAttribute('href');
      var active = false;
      if (path === '/' || path === '/mutual-funds/transactions') {
        active = href === '/';
      } else {
        active = href === path;
      }
      link.classList.toggle('active', active);
    });
  }

  // ─── Swap outside-container elements ──────────────────

  var OUTSIDE_SELECTORS = [
    '.settings-drawer',
    '#drawerBackdrop',
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

    var refNode = document.getElementById('navDrawerBackdrop') ||
                  document.getElementById('navDrawer');

    // Insert new outside-container elements from fetched page
    var newBody = newDoc.querySelector('body');
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
    var targetPath = new URL(url, location.origin).pathname;
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
      var doc = new DOMParser().parseFromString(html, 'text/html');

      // 1. Cleanup previous page JS
      cleanupCurrentPage();

      // 2. Title
      document.title = doc.title || 'Metron';

      // 3. CSS
      syncCss(doc);

      // 4. Swap container content
      var newContainer = doc.querySelector('.container');
      var curContainer = document.querySelector('.container');
      if (newContainer && curContainer) {
        curContainer.innerHTML = newContainer.innerHTML;
        // Preserve or update container-level attributes
        var style = newContainer.getAttribute('style');
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

      // 8. Execute scripts
      return executeScripts(doc);
    })
    .then(function() {
      // 9. Push state
      if (doPush !== false) {
        history.pushState({ metronSpa: true }, '', url);
      }

      // 10. Scroll to top
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
    var link = e.target.closest('a[href]');
    if (!link) return;
    // Don't intercept modified clicks (new tab, etc.)
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (link.target === '_blank') return;

    var href = link.getAttribute('href');
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
})();
