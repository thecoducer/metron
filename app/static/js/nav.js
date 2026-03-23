// Shared navigation utilities (loaded by both portfolio and nifty50 pages)

function openNavDrawer() {
  const drawer = document.getElementById('navDrawer');
  const backdrop = document.getElementById('navDrawerBackdrop');
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer || !backdrop) return;
  drawer.classList.add('open');
  backdrop.classList.add('open');
  document.body.style.overflow = 'hidden';
  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');
}

function closeNavDrawer() {
  const drawer = document.getElementById('navDrawer');
  const backdrop = document.getElementById('navDrawerBackdrop');
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  if (!drawer || !backdrop) return;
  drawer.classList.remove('open');
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
  if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  const dropdown = document.getElementById('userDropdown');
  const avatarBtn = document.getElementById('userAvatarBtn');
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

document.addEventListener('DOMContentLoaded', function() {
  // Nav drawer backdrop click
  const backdrop = document.getElementById('navDrawerBackdrop');
  if (backdrop) {
    backdrop.addEventListener('click', closeNavDrawer);
  }

  // Nav drawer close button
  const closeBtn = document.getElementById('navDrawerClose');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeNavDrawer);
  }

  // User avatar dropdown toggle
  const avatarBtn = document.getElementById('userAvatarBtn');
  const dropdown = document.getElementById('userDropdown');
  if (avatarBtn && dropdown) {
    avatarBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
  }

  // Hamburger opens nav drawer
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      openNavDrawer();
    });
  }
});
