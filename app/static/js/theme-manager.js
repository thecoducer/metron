/* Metron - Theme Management Module */

class ThemeManager {
  constructor() {
    this.themeIcon = document.getElementById('theme_toggle_icon');
    this.themeLabel = document.getElementById('theme_toggle_label');
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
    } else {
      body.classList.remove('dark-theme');
    }

    // Update toggle switch
    if (this.themeLabel) {
      this.themeLabel.classList.toggle('toggle-on', theme === 'dark');
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
