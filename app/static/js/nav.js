// Navigation menu toggle (shared between portfolio and nifty50 pages)
function toggleNavMenu(event) {
  event.stopPropagation();
  const menu = document.getElementById('navMenu');
  menu.classList.toggle('active');
}

// Close menu when clicking outside
document.addEventListener('click', function(event) {
  const menu = document.getElementById('navMenu');
  if (menu && !menu.contains(event.target)) {
    menu.classList.remove('active');
  }
});
