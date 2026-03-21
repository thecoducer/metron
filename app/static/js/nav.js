// Shared navigation utilities (loaded by both portfolio and nifty50 pages)

function openNavDrawer() {
  var drawer = document.getElementById('navDrawer');
  var backdrop = document.getElementById('navDrawerBackdrop');
  var hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer || !backdrop) return;
  drawer.classList.add('open');
  backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');
}

function closeNavDrawer() {
  var drawer = document.getElementById('navDrawer');
  var backdrop = document.getElementById('navDrawerBackdrop');
  var hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer || !backdrop) return;
  drawer.classList.remove('open');
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  var dropdown = document.getElementById('userDropdown');
  var avatarBtn = document.getElementById('userAvatarBtn');
  if (dropdown && avatarBtn && !avatarBtn.contains(event.target) && !dropdown.contains(event.target)) {
    dropdown.classList.remove('open');
  }
});

// Escape key closes nav drawer (and settings drawer if open)
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeNavDrawer();
  }
});

// Nav drawer backdrop click
(function() {
  var backdrop = document.getElementById('navDrawerBackdrop');
  if (backdrop) {
    backdrop.addEventListener('click', closeNavDrawer);
  }
})();

// Nav drawer close button
(function() {
  var closeBtn = document.getElementById('navDrawerClose');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeNavDrawer);
  }
})();

// User avatar dropdown toggle
(function() {
  var avatarBtn = document.getElementById('userAvatarBtn');
  var dropdown = document.getElementById('userDropdown');
  if (avatarBtn && dropdown) {
    avatarBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
  }
})();

// Hamburger opens nav drawer
(function() {
  var hamburgerBtn = document.getElementById('hamburgerBtn');
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      openNavDrawer();
    });
  }
})();
