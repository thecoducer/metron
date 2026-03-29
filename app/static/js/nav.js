// Shared navigation utilities (loaded by both portfolio and nifty50 pages)

var _desktopSidebarMQ = window.matchMedia('(min-width: 1025px)');

function isDesktopSidebar() {
  return _desktopSidebarMQ.matches;
}

function openNavDrawer() {
  const drawer = document.getElementById('navDrawer');
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer) return;

  drawer.classList.add('open');

  if (isDesktopSidebar()) {
    document.body.classList.add('sidebar-open');
    localStorage.setItem('sidebarOpen', 'true');
  } else {
    const backdrop = document.getElementById('navDrawerBackdrop');
    if (backdrop) backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');
}

function closeNavDrawer() {
  const drawer = document.getElementById('navDrawer');
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer) return;

  drawer.classList.remove('open');

  if (isDesktopSidebar()) {
    document.body.classList.remove('sidebar-open');
    localStorage.setItem('sidebarOpen', 'false');
  } else {
    const backdrop = document.getElementById('navDrawerBackdrop');
    if (backdrop) backdrop.classList.remove('open');
    document.body.style.overflow = '';
  }

  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
}

function toggleNavDrawer() {
  const drawer = document.getElementById('navDrawer');
  if (!drawer) return;
  if (drawer.classList.contains('open')) {
    closeNavDrawer();
  } else {
    openNavDrawer();
  }
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  const dropdown = document.getElementById('userDropdown');
  const avatarBtn = document.getElementById('userAvatarBtn');
  if (dropdown && avatarBtn && !avatarBtn.contains(event.target) && !dropdown.contains(event.target)) {
    dropdown.classList.remove('open');
  }
});

// Escape key closes nav drawer/sidebar
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeNavDrawer();
  }
});

// Handle breakpoint changes between desktop sidebar and mobile drawer
_desktopSidebarMQ.addEventListener('change', function(e) {
  const drawer = document.getElementById('navDrawer');
  if (!drawer) return;
  const backdrop = document.getElementById('navDrawerBackdrop');
  const hamburgerBtn = document.getElementById('hamburgerBtn');

  if (e.matches) {
    // Entered desktop — clean up mobile drawer state
    if (backdrop) backdrop.classList.remove('open');
    document.body.style.overflow = '';
    // Restore saved sidebar state
    if (localStorage.getItem('sidebarOpen') === 'true') {
      drawer.classList.add('open');
      document.body.classList.add('sidebar-open');
      if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');
    } else {
      drawer.classList.remove('open');
      if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
    }
  } else {
    // Entered mobile — clean up sidebar state
    document.body.classList.remove('sidebar-open');
    drawer.classList.remove('open');
    if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
  }
});

document.addEventListener('DOMContentLoaded', function() {
  // Nav drawer backdrop click (mobile)
  const backdrop = document.getElementById('navDrawerBackdrop');
  if (backdrop) {
    backdrop.addEventListener('click', closeNavDrawer);
  }

  // Nav drawer close button (mobile, hidden on desktop via CSS)
  const closeBtn = document.getElementById('navDrawerClose');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeNavDrawer);
  }

  // Bind header events (avatar dropdown, hamburger)
  bindNavHeaderEvents();

  // Restore sidebar state on desktop page load
  if (isDesktopSidebar() && localStorage.getItem('sidebarOpen') === 'true') {
    const drawer = document.getElementById('navDrawer');
    if (drawer) {
      const hamburgerBtn = document.getElementById('hamburgerBtn');
      const header = document.querySelector('header');
      // Disable transitions to avoid slide-in animation on load
      drawer.style.transition = 'none';
      document.body.style.transition = 'none';
      if (header) header.style.transition = 'none';

      drawer.classList.add('open');
      document.body.classList.add('sidebar-open');
      if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');

      // Re-enable transitions after layout settles
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          drawer.style.transition = '';
          document.body.style.transition = '';
          if (header) header.style.transition = '';
        });
      });
    }
  }
});

// Re-bind header events after SPA content swap.
// Call this whenever the header DOM is replaced.
function bindNavHeaderEvents() {
  // User avatar dropdown toggle
  const avatarBtn = document.getElementById('userAvatarBtn');
  const dropdown = document.getElementById('userDropdown');
  if (avatarBtn && dropdown) {
    avatarBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
  }

  // Hamburger: toggle on desktop, open drawer on mobile
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (isDesktopSidebar()) {
        toggleNavDrawer();
      } else {
        openNavDrawer();
      }
    });
  }

  // Restore sidebar state after SPA navigation.
  // DOMContentLoaded handles initial page load; this handles subsequent SPA swaps.
  if (isDesktopSidebar()) {
    const drawer = document.getElementById('navDrawer');
    if (drawer) {
      const isOpen = localStorage.getItem('sidebarOpen') === 'true';
      // Apply without transition so the sidebar doesn't animate in during navigation
      drawer.style.transition = 'none';
      document.body.style.transition = 'none';
      drawer.classList.toggle('open', isOpen);
      document.body.classList.toggle('sidebar-open', isOpen);
      if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          drawer.style.transition = '';
          document.body.style.transition = '';
        });
      });
    }
  }
}
window.bindNavHeaderEvents = bindNavHeaderEvents;
