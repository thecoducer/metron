/* Metron - Theme Management Module */

class ThemeManager {
  constructor() {
    this.themeIcon = document.getElementById('theme_toggle_icon');
  }

  init() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    this.applyTheme(savedTheme);
  }

  toggle() {
    const body = document.body;
    const newTheme = body.classList.contains('dark-theme') ? 'light' : 'dark';
    this.applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);
  }

  applyTheme(theme) {
    const body = document.body;
    
    // Disable all transitions to prevent flashes during theme switch
    body.classList.add('theme-transitioning');
    
    if (theme === 'dark') {
      body.classList.add('dark-theme');
      if (this.themeIcon) this.themeIcon.textContent = '☀️';
    } else {
      body.classList.remove('dark-theme');
      if (this.themeIcon) this.themeIcon.textContent = '🌙';
    }
    
    // Re-enable transitions after the browser has painted the new theme
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        body.classList.remove('theme-transitioning');
      });
    });
  }
}

export default ThemeManager;
