// Shared navigation utilities (loaded by both portfolio and nifty50 pages)

var _desktopSidebarMQ = window.matchMedia('(min-width: 1025px)');

function isDesktopSidebar() {
  return _desktopSidebarMQ.matches;
}

function openNavDrawer() {
  var drawer = document.getElementById('navDrawer');
  var hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer) return;

  drawer.classList.add('open');

  if (isDesktopSidebar()) {
    document.body.classList.add('sidebar-open');
    localStorage.setItem('sidebarOpen', 'true');
  } else {
    var backdrop = document.getElementById('navDrawerBackdrop');
    if (backdrop) backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');
}

function closeNavDrawer() {
  var drawer = document.getElementById('navDrawer');
  var hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer) return;

  drawer.classList.remove('open');

  if (isDesktopSidebar()) {
    document.body.classList.remove('sidebar-open');
    localStorage.setItem('sidebarOpen', 'false');
  } else {
    var backdrop = document.getElementById('navDrawerBackdrop');
    if (backdrop) backdrop.classList.remove('open');
    document.body.style.overflow = '';
  }

  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
}

function toggleNavDrawer() {
  var drawer = document.getElementById('navDrawer');
  if (!drawer) return;
  if (drawer.classList.contains('open')) {
    closeNavDrawer();
  } else {
    openNavDrawer();
  }
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  var dropdown = document.getElementById('userDropdown');
  var avatarBtn = document.getElementById('userAvatarBtn');
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
  var drawer = document.getElementById('navDrawer');
  if (!drawer) return;
  var backdrop = document.getElementById('navDrawerBackdrop');
  var hamburgerBtn = document.getElementById('hamburgerBtn');

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
  var backdrop = document.getElementById('navDrawerBackdrop');
  if (backdrop) {
    backdrop.addEventListener('click', closeNavDrawer);
  }

  // Nav drawer close button (mobile, hidden on desktop via CSS)
  var closeBtn = document.getElementById('navDrawerClose');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeNavDrawer);
  }

  // Bind header events (avatar dropdown, hamburger)
  bindNavHeaderEvents();

  // Restore sidebar state on desktop page load
  if (isDesktopSidebar() && localStorage.getItem('sidebarOpen') === 'true') {
    var drawer = document.getElementById('navDrawer');
    if (drawer) {
      var hamburgerBtn = document.getElementById('hamburgerBtn');
      var header = document.querySelector('header');
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
  var avatarBtn = document.getElementById('userAvatarBtn');
  var dropdown = document.getElementById('userDropdown');
  if (avatarBtn && dropdown) {
    avatarBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
  }

  // Hamburger: toggle on desktop, open drawer on mobile
  var hamburgerBtn = document.getElementById('hamburgerBtn');
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
}
window.bindNavHeaderEvents = bindNavHeaderEvents;
