/**
 * Shared refresh button & status tag UI helpers.
 *
 * Used by both the portfolio page (app.js) and the exposure page
 * (exposure.js) to manage refresh button state and status indicators.
 *
 * Usage:
 *   var ui = new RefreshUI('myRefreshBtn', 'myStatusTag', 'myStatusText');
 *   ui.setUpdating();        // button spins, tag shows "updating"
 *   ui.setDone();            // button stops, tag shows "updated"
 *   ui.setDoneWithText(t);   // button stops, tag shows custom text
 *   ui.setError();           // button stops, tag hidden
 */

// eslint-disable-next-line no-unused-vars
function RefreshUI(btnId, tagId, textId) {
  this.btnId = btnId;
  this.tagId = tagId;
  this.textId = textId;
}

RefreshUI.prototype.setButtonLoading = function(loading) {
  var btn = document.getElementById(this.btnId);
  if (!btn) return;
  if (loading) {
    btn.disabled = true;
    btn.classList.add('loading');
  } else {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
};

RefreshUI.prototype.setStatusTag = function(state, text) {
  var tag = document.getElementById(this.tagId);
  var textEl = document.getElementById(this.textId);
  if (!tag) return;
  tag.style.display = 'inline-flex';
  // Toggle state classes without wiping base classes
  tag.classList.remove('updating', 'updated');
  tag.classList.add(state);
  if (textEl) textEl.textContent = text;
};

RefreshUI.prototype.hideStatusTag = function() {
  var tag = document.getElementById(this.tagId);
  if (tag) tag.style.display = 'none';
};

RefreshUI.prototype.setUpdating = function() {
  this.setButtonLoading(true);
  this.setStatusTag('updating', 'updating');
};

RefreshUI.prototype.setDone = function() {
  this.setButtonLoading(false);
  this.setStatusTag('updated', 'updated');
};

RefreshUI.prototype.setDoneWithText = function(text) {
  this.setButtonLoading(false);
  this.setStatusTag('updated', text);
};

RefreshUI.prototype.setError = function() {
  this.setButtonLoading(false);
  this.hideStatusTag();
};
