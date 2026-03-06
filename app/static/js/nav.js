// Shared navigation utilities (loaded by both portfolio and nifty50 pages)

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  var dropdown = document.getElementById('userDropdown');
  var avatarBtn = document.getElementById('userAvatarBtn');
  if (dropdown && avatarBtn && !avatarBtn.contains(event.target) && !dropdown.contains(event.target)) {
    dropdown.classList.remove('open');
  }
});

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
