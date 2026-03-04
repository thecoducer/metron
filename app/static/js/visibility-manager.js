/* Metron - Visibility Management Module */

class PrivacyManager {
  constructor() {
    this.privacyIcon = document.getElementById('privacy_toggle_icon');
    this.privacyBtn = document.getElementById('privacy_toggle_btn');
    this.privacyLabel = document.getElementById('privacy_toggle_label');
    this.isPrivacyMode = false;
  }

  init() {
    const savedPrivacy = localStorage.getItem('privacyMode') || 'off';
    this.applyPrivacyMode(savedPrivacy === 'on');
  }

  toggle() {
    this.isPrivacyMode = !this.isPrivacyMode;
    this.applyPrivacyMode(this.isPrivacyMode);
    localStorage.setItem('privacyMode', this.isPrivacyMode ? 'on' : 'off');
  }

  applyPrivacyMode(enabled) {
    this.isPrivacyMode = enabled;
    const body = document.body;
    
    if (this.privacyBtn) {
      this.privacyBtn.classList.toggle('active', enabled);
    }
    if (this.privacyLabel) {
      this.privacyLabel.classList.toggle('toggle-on', enabled);
    }
    if (enabled) {
      body.classList.add('privacy-mode');
      // Eye-off icon
      if (this.privacyIcon) {
        this.privacyIcon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>';
      }
    } else {
      body.classList.remove('privacy-mode');
      // Eye icon
      if (this.privacyIcon) {
        this.privacyIcon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>';
      }
    }
  }
}

export default PrivacyManager;
