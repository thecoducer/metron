/* Metron - CRUD Manager for Manual Data Entry
 *
 * Handles Add / Edit / Delete operations for all sheet-backed tables.
 * Add and Edit use contextual inline form rows inside the table itself,
 * keeping the user in context. Delete uses a lightweight confirmation dialog.
 */

import { metronFetch } from './utils.js';

// ── Date format helpers ──────────────────────────────────────────
// Google Sheets stores dates as MM/DD/YYYY.
// HTML <input type="date"> uses YYYY-MM-DD.

/** Convert MM/DD/YYYY (or similar) → YYYY-MM-DD for <input type="date">. */
function toInputDate(raw) {
  if (!raw) return '';
  const s = String(raw).trim();
  // Already YYYY-MM-DD?
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  // Try parsing as a date string
  const d = new Date(s);
  if (isNaN(d.getTime())) return '';
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/** Convert YYYY-MM-DD (from input) → MM/DD/YYYY for Google Sheets storage. */
function toSheetDate(isoStr) {
  if (!isoStr) return '';
  const parts = isoStr.split('-');
  if (parts.length !== 3) return isoStr;
  return `${parts[1]}/${parts[2]}/${parts[0]}`;
}

// ── Schema definitions per table type ────────────────────────────
const SCHEMAS = {
  stocks: {
    label: 'Stock',
    sheetType: 'stocks',
    fields: [
      { key: 'symbol',    label: 'Symbol',    type: 'text',   required: true, placeholder: 'e.g. RELIANCE', uppercase: true },
      { key: 'isin',      label: 'ISIN',      type: 'text',   required: false, placeholder: 'e.g. INE002A01018', uppercase: true },
      { key: 'qty',       label: 'Quantity',   type: 'number', required: true, step: '1',   min: '1' },
      { key: 'avg_price', label: 'Avg Price',  type: 'number', required: true, step: '0.01', min: '0' },
      { key: 'exchange',  label: 'Exchange',   type: 'select', required: true, options: ['NSE', 'BSE'] },
      { key: 'account',   label: 'Account',    type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  etfs: {
    label: 'ETF',
    sheetType: 'etfs',
    fields: [
      { key: 'symbol',    label: 'Symbol',    type: 'text',   required: true, placeholder: 'e.g. NIFTYBEES', uppercase: true },
      { key: 'isin',      label: 'ISIN',      type: 'text',   required: false, placeholder: 'e.g. INF204KB15I9', uppercase: true },
      { key: 'qty',       label: 'Quantity',   type: 'number', required: true, step: '1',   min: '1' },
      { key: 'avg_price', label: 'Avg Price',  type: 'number', required: true, step: '0.01', min: '0' },
      { key: 'exchange',  label: 'Exchange',   type: 'select', required: true, options: ['NSE', 'BSE'] },
      { key: 'account',   label: 'Account',    type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  mutual_funds: {
    label: 'Mutual Fund',
    sheetType: 'mutual_funds',
    fields: [
      { key: 'fund',     label: 'Fund Name', type: 'text',   required: true, placeholder: 'e.g. AXIS BLUECHIP FUND' },
      { key: 'qty',      label: 'Units',     type: 'number', required: true, step: '0.001', min: '0' },
      { key: 'avg_nav',  label: 'Avg NAV',   type: 'number', required: true, step: '0.01',  min: '0' },
      { key: 'account',  label: 'Account',   type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  sips: {
    label: 'SIP',
    sheetType: 'sips',
    fields: [
      { key: 'fund',         label: 'Fund Name',    type: 'text',   required: true, placeholder: 'e.g. AXIS BLUECHIP FUND' },
      { key: 'amount',       label: 'Amount',        type: 'number', required: true, step: '1', min: '1' },
      { key: 'frequency',    label: 'Frequency',     type: 'select', required: true, options: ['MONTHLY', 'WEEKLY', 'QUARTERLY'] },
      { key: 'installments', label: 'Installments',  type: 'number', required: false, step: '1', min: '0', placeholder: '-1 for perpetual' },
      { key: 'completed',    label: 'Completed',     type: 'number', required: false, step: '1', min: '0' },
      { key: 'status',       label: 'Status',        type: 'select', required: true, options: ['ACTIVE', 'PAUSED', 'CANCELLED'] },
      { key: 'next_due',     label: 'Next Due Date', type: 'date',   required: false },
      { key: 'account',      label: 'Account',       type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  physical_gold: {
    label: 'Physical Gold',
    sheetType: 'physical_gold',
    fields: [
      { key: 'date',                   label: 'Bought On',          type: 'date',   required: true },
      { key: 'type',                   label: 'Type',               type: 'select', required: true, options: ['Jewellery', 'Coin', 'Bar', 'Biscuit', 'Other'] },
      { key: 'retail_outlet',          label: 'Retail Outlet',      type: 'text',   required: false, placeholder: 'e.g. Tanishq' },
      { key: 'purity',                 label: 'Purity',             type: 'select', required: true, options: ['24K', '22K', '18K'] },
      { key: 'weight_gms',             label: 'Weight (gms)',       type: 'number', required: true, step: '0.001', min: '0' },
      { key: 'bought_ibja_rate_per_gm', label: 'IBJA Rate/gm',     type: 'number', required: true, step: '0.01',  min: '0' },
    ],
  },
  fixed_deposits: {
    label: 'Fixed Deposit',
    sheetType: 'fixed_deposits',
    fields: [
      { key: 'original_investment_date', label: 'Deposited On',   type: 'date',   required: true },
      { key: 'reinvested_date',          label: 'Reinvested On',  type: 'date',   required: false },
      { key: 'bank_name',               label: 'Bank',            type: 'text',   required: true, placeholder: 'e.g. SBI' },
      { key: 'deposit_year',            label: 'Tenure Years',    type: 'number', required: true, step: '1', min: '0' },
      { key: 'deposit_month',           label: 'Tenure Months',   type: 'number', required: true, step: '1', min: '0' },
      { key: 'deposit_day',             label: 'Tenure Days',     type: 'number', required: true, step: '1', min: '0' },
      { key: 'original_amount',         label: 'Amount',          type: 'number', required: true, step: '0.01', min: '0' },
      { key: 'reinvested_amount',       label: 'Reinvested Amt',  type: 'number', required: false, step: '0.01', min: '0' },
      { key: 'interest_rate',           label: 'Rate (%)',        type: 'number', required: true, step: '0.01', min: '0' },
      { key: 'account',                label: 'Account',          type: 'text',   required: true, placeholder: 'e.g. Joint' },
    ],
  },
};

// ── Map schema keys → target <tbody> element IDs ─────────────────
const TBODY_MAP = {
  stocks: 'tbody',
  etfs: 'etf_tbody',
  mutual_funds: 'mf_tbody',
  sips: 'sips_tbody',
  physical_gold: 'physical_gold_table_body',
  fixed_deposits: 'fixed_deposits_table_body',
};


class CrudManager {
  constructor(onDataChanged) {
    this._onDataChanged = onDataChanged;
    this._activeFormRow = null;      // current inline form <tr>
    this._activeOriginalRow = null;  // original <tr> hidden during edit
    this._activeSchemaKey = null;    // schemaKey of the active inline form
    this._activeRowNumber = null;    // row number being edited (null for add)
    this._init();
  }

  // ── Bootstrap ────────────────────────────────────────────────

  _init() {
    // Delete confirmation popover (replaces full-page modal)
    this._deletePopover = null;
    this._deletePopoverCleanup = null;

    // Toast container
    this._toastContainer = document.createElement('div');
    this._toastContainer.className = 'crud-toast-container';
    document.body.appendChild(this._toastContainer);

    // Global keyboard handler
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (this._deletePopover) this._closeDeletePopover();
        else if (this._drawerEl) this._closeDrawer();
        else if (this._activeFormRow) this._cancelInline();
      }
    });
  }

  // ── Public API ───────────────────────────────────────────────

  /** Returns true when an inline add/edit form is currently open. */
  isEditing() {
    return this._activeFormRow !== null || this._drawerEl !== null;
  }

  openAdd(schemaKey) {
    const schema = SCHEMAS[schemaKey];
    if (!schema) return;
    this._cancelInline();
    this._activeSchemaKey = schemaKey;
    this._activeRowNumber = null;
    this._showInlineForm(schema, schemaKey, null, null);
  }

  openEdit(schemaKey, rowNumber, currentValues) {
    const schema = SCHEMAS[schemaKey];
    if (!schema) return;
    this._cancelInline();
    this._activeSchemaKey = schemaKey;
    this._activeRowNumber = rowNumber;
    const tbody = this._getTbody(schemaKey);
    const existingRow = tbody?.querySelector(
      `tr[data-manual-row="${rowNumber}"][data-schema="${schemaKey}"]`
    );
    this._showInlineForm(schema, schemaKey, rowNumber, currentValues, existingRow);
  }

  async confirmDelete(schemaKey, rowNumber) {
    const schema = SCHEMAS[schemaKey];
    if (!schema) return;

    // Close any existing dialog first
    this._closeDeletePopover();

    // Create centered confirmation dialog
    const backdrop = document.createElement('div');
    backdrop.className = 'crud-delete-backdrop';

    const dialog = document.createElement('div');
    dialog.className = 'crud-delete-dialog';
    dialog.innerHTML = `
      <div class="crud-delete-dialog-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          <line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
        </svg>
      </div>
      <div class="crud-delete-dialog-title">Delete this entry?</div>
      <div class="crud-delete-dialog-sub">This action cannot be undone.</div>
      <div class="crud-delete-dialog-actions">
        <button class="crud-ddlg-btn crud-ddlg-cancel">Cancel</button>
        <button class="crud-ddlg-btn crud-ddlg-confirm">Delete</button>
      </div>`;

    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);
    this._deletePopover = backdrop;

    // Animate in
    requestAnimationFrame(() => backdrop.classList.add('open'));

    // Close on backdrop click
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) this._closeDeletePopover();
    });

    // Close on Escape
    const onEscape = (e) => {
      if (e.key === 'Escape') this._closeDeletePopover();
    };
    document.addEventListener('keydown', onEscape);
    this._deletePopoverCleanup = () => {
      document.removeEventListener('keydown', onEscape);
    };

    // Wire buttons
    dialog.querySelector('.crud-ddlg-cancel').addEventListener('click', () => this._closeDeletePopover());
    dialog.querySelector('.crud-ddlg-confirm').addEventListener('click', async () => {
      const btn = dialog.querySelector('.crud-ddlg-confirm');
      btn.disabled = true;
      btn.textContent = 'Deleting…';
      try {
        const resp = await metronFetch(`/api/sheets/${schema.sheetType}/${rowNumber}`, { method: 'DELETE' });
        if (!resp.ok) {
          const d = await resp.json();
          throw new Error(d.error || 'Delete failed');
        }
        const result = await resp.json();
        this._closeDeletePopover();
        this._toast('Deleted successfully', 'success');
        if (this._onDataChanged) this._onDataChanged(result.data);
      } catch (err) {
        this._toast(err.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Delete';
      }
    });
  }

  _closeDeletePopover() {
    if (!this._deletePopover) return;
    if (this._deletePopoverCleanup) {
      this._deletePopoverCleanup();
      this._deletePopoverCleanup = null;
    }
    const backdrop = this._deletePopover;
    backdrop.classList.remove('open');
    backdrop.classList.add('closing');
    backdrop.addEventListener('animationend', () => backdrop.remove(), { once: true });
    // Fallback removal
    setTimeout(() => { if (backdrop.parentNode) backdrop.remove(); }, 300);
    this._deletePopover = null;
  }

  // ── Inline form ──────────────────────────────────────────────

  _isMobileOrTablet() {
    return window.innerWidth <= 768;
  }

  _showInlineForm(schema, schemaKey, rowNumber, values, existingRow) {
    if (this._isMobileOrTablet()) {
      this._showDrawerForm(schema, schemaKey, rowNumber, values, existingRow);
      return;
    }
    this._showInlineFormDesktop(schema, schemaKey, rowNumber, values, existingRow);
  }

  _showDrawerForm(schema, schemaKey, rowNumber, values, existingRow) {
    const isEdit = rowNumber != null;

    // Collect suggestions
    const tbody = this._getTbody(schemaKey);
    const suggestions = {};
    for (const f of schema.fields) {
      if (f.datalistFrom) {
        const existing = new Set();
        let colIdx = 0;
        for (const sf of schema.fields) {
          if (sf.key === f.datalistFrom) break;
          if (!sf.skipInPayload) colIdx++;
        }
        if (tbody) {
          tbody.querySelectorAll(`tr[data-schema="${schemaKey}"]`).forEach(row => {
            const cell = row.children[colIdx];
            if (cell) {
              const clone = cell.cloneNode(true);
              clone.querySelectorAll('.badge').forEach(b => b.remove());
              const v = clone.textContent.trim();
              if (v && v !== '-') existing.add(v);
            }
          });
        }
        suggestions[f.key] = [...existing].sort();
      }
    }
    this._fieldSuggestions = suggestions;

    // Build fields HTML
    let fieldsHtml = '';
    for (const f of schema.fields) {
      let val;
      if (f.defaultFn && typeof f.defaultFn === 'function') {
        val = f.defaultFn(values);
      } else {
        val = (values && values[f.key] !== undefined) ? values[f.key] : '';
      }
      fieldsHtml += this._buildInlineField(f, val, suggestions[f.key]);
    }

    // Create backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'crud-drawer-backdrop';

    // Create drawer
    const drawer = document.createElement('div');
    drawer.className = 'crud-drawer';
    drawer.innerHTML = `
      <div class="crud-drawer-handle"></div>
      <div class="crud-drawer-header">
        <h3 class="crud-drawer-title">${isEdit ? 'Edit' : 'Add'} ${schema.label}</h3>
        <button class="crud-drawer-close" aria-label="Close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <div class="crud-drawer-body">
        <form class="crud-drawer-form" autocomplete="off">
          <div class="crud-inline-fields">${fieldsHtml}</div>
        </form>
      </div>
      <div class="crud-drawer-footer">
        <button type="button" class="crud-drawer-cancel">Cancel</button>
        <button type="button" class="crud-drawer-save">${isEdit ? 'Update' : 'Save'}</button>
      </div>`;

    document.body.appendChild(backdrop);
    document.body.appendChild(drawer);

    // Store references
    this._drawerBackdrop = backdrop;
    this._drawerEl = drawer;
    if (isEdit && existingRow) {
      this._activeOriginalRow = existingRow;
    }

    // Prevent body scroll
    document.body.style.overflow = 'hidden';

    // Animate open
    requestAnimationFrame(() => {
      backdrop.classList.add('open');
      drawer.classList.add('open');
    });

    // Focus first input
    const firstInput = drawer.querySelector('input, select');
    if (firstInput) setTimeout(() => firstInput.focus(), 300);

    // Wire suggestions
    if (this._fieldSuggestions) {
      drawer.querySelectorAll('input.crud-inline-input').forEach(inp => {
        const items = this._fieldSuggestions[inp.name];
        if (items && items.length) this._initSuggestDropdown(inp, items);
      });
    }

    // Wire conditional fields
    this._initConditionalFields(drawer, schema);

    // Wire buttons
    const form = drawer.querySelector('.crud-drawer-form');
    const cancel = () => this._closeDrawer();
    backdrop.addEventListener('click', cancel);
    drawer.querySelector('.crud-drawer-close').addEventListener('click', cancel);
    drawer.querySelector('.crud-drawer-cancel').addEventListener('click', cancel);

    drawer.querySelector('.crud-drawer-save').addEventListener('click', () => {
      this._handleDrawerSave(schema, isEdit, rowNumber, form, drawer);
    });

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      this._handleDrawerSave(schema, isEdit, rowNumber, form, drawer);
    });

    form.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.tagName !== 'SELECT') {
        e.preventDefault();
        this._handleDrawerSave(schema, isEdit, rowNumber, form, drawer);
      }
    });
  }

  async _handleDrawerSave(schema, isEdit, rowNumber, form, drawer) {
    const saveBtn = drawer.querySelector('.crud-drawer-save');
    const payload = {};
    for (const f of schema.fields) {
      if (f.skipInPayload) continue;
      const fieldWrap = form.querySelector(`[data-field-key="${f.key}"]`);
      const isHidden = fieldWrap && fieldWrap.style.display === 'none';
      const el = form.querySelector(`[name="${f.key}"]`);
      let val = el ? el.value.trim() : '';
      if (isHidden) val = '';
      if (f.type === 'date' && val) val = toSheetDate(val);
      if (f.uppercase) val = val.toUpperCase();
      payload[f.key] = val;
    }

    for (const f of schema.fields) {
      if (f.skipInPayload) continue;
      const fieldWrap = form.querySelector(`[data-field-key="${f.key}"]`);
      const isHidden = fieldWrap && fieldWrap.style.display === 'none';
      if (isHidden) continue;
      const el = form.querySelector(`[name="${f.key}"]`);
      const isRequired = el ? el.hasAttribute('required') : f.required;
      if (isRequired && !payload[f.key]) {
        this._toast(`${f.label} is required`, 'error');
        if (el) {
          el.focus();
          el.classList.add('crud-inline-input-error');
          el.addEventListener('input', () => el.classList.remove('crud-inline-input-error'), { once: true });
        }
        return;
      }
    }

    saveBtn.disabled = true;
    drawer.classList.add('saving');

    try {
      const url = isEdit
        ? `/api/sheets/${schema.sheetType}/${rowNumber}`
        : `/api/sheets/${schema.sheetType}`;
      const method = isEdit ? 'PUT' : 'POST';

      const resp = await metronFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const d = await resp.json();
        throw new Error(d.error || 'Save failed');
      }

      const result = await resp.json();
      this._closeDrawer();
      this._toast(isEdit ? 'Updated successfully' : 'Added successfully', 'success');
      if (this._onDataChanged) this._onDataChanged(result.data);
    } catch (err) {
      this._toast(err.message, 'error');
      saveBtn.disabled = false;
      drawer.classList.remove('saving');
      if (err.message.includes("doesn't exist on exchange")) {
        const symbolEl = form.querySelector('[name="symbol"]');
        if (symbolEl) {
          symbolEl.focus();
          symbolEl.classList.add('crud-inline-input-error');
          symbolEl.addEventListener('input', () => symbolEl.classList.remove('crud-inline-input-error'), { once: true });
        }
      }
    }
  }

  _closeDrawer() {
    if (this._drawerEl) {
      this._drawerEl.classList.remove('open');
      if (this._drawerBackdrop) this._drawerBackdrop.classList.remove('open');
      setTimeout(() => {
        if (this._drawerEl) { this._drawerEl.remove(); this._drawerEl = null; }
        if (this._drawerBackdrop) { this._drawerBackdrop.remove(); this._drawerBackdrop = null; }
      }, 300);
    }
    document.body.style.overflow = '';
    this._activeOriginalRow = null;
    this._activeSchemaKey = null;
    this._activeRowNumber = null;
    this._activeFormRow = null;
  }

  _showInlineFormDesktop(schema, schemaKey, rowNumber, values, existingRow) {
    const tbody = this._getTbody(schemaKey);
    if (!tbody) return;

    const isEdit = rowNumber != null;
    const table = tbody.closest('table');
    const colCount = table?.querySelector('thead tr')?.children.length || 10;

    // Build the form row
    const tr = document.createElement('tr');
    tr.className = 'crud-inline-row';

    const td = document.createElement('td');
    td.setAttribute('colspan', colCount);

    // Collect existing values for datalist suggestions from table rows
    const suggestions = {};
    for (const f of schema.fields) {
      if (f.datalistFrom) {
        const existing = new Set();
        // Count only non-virtual fields to map to actual table columns
        let colIdx = 0;
        for (const sf of schema.fields) {
          if (sf.key === f.datalistFrom) break;
          if (!sf.skipInPayload) colIdx++;
        }
        tbody.querySelectorAll(`tr[data-schema="${schemaKey}"]`).forEach(row => {
          const cell = row.children[colIdx];
          if (cell) {
            // Clone and strip badge/tag elements to get clean text
            const clone = cell.cloneNode(true);
            clone.querySelectorAll('.badge').forEach(b => b.remove());
            const v = clone.textContent.trim();
            if (v && v !== '-') existing.add(v);
          }
        });
        suggestions[f.key] = [...existing].sort();
      }
    }

    this._fieldSuggestions = suggestions;
    let fieldsHtml = '';
    for (const f of schema.fields) {
      let val;
      if (f.defaultFn && typeof f.defaultFn === 'function') {
        val = f.defaultFn(values);
      } else {
        val = (values && values[f.key] !== undefined) ? values[f.key] : '';
      }
      fieldsHtml += this._buildInlineField(f, val, suggestions[f.key]);
    }

    td.innerHTML = `
      <form class="crud-inline-form" autocomplete="off">
        <div class="crud-inline-fields">${fieldsHtml}</div>
        <div class="crud-inline-actions">
          <button type="submit" class="crud-inline-save" title="${isEdit ? 'Update' : 'Save'}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
          <button type="button" class="crud-inline-cancel" title="Cancel">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </form>`;

    tr.appendChild(td);

    // Position the form row
    if (isEdit && existingRow) {
      existingRow.style.display = 'none';
      existingRow.parentNode.insertBefore(tr, existingRow.nextSibling);
      this._activeOriginalRow = existingRow;
    } else {
      // For add: hide the empty-state CTA row if present, insert form at top
      const emptyRow = tbody.querySelector('.crud-empty-cta-row');
      if (emptyRow) emptyRow.style.display = 'none';
      tbody.insertBefore(tr, tbody.firstChild);
    }

    this._activeFormRow = tr;

    // Animate in + scroll into view
    requestAnimationFrame(() => {
      tr.classList.add('open');
      tr.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    // Focus first input
    const firstInput = tr.querySelector('input, select');
    if (firstInput) setTimeout(() => firstInput.focus(), 100);

    // Wire up custom suggestion dropdowns
    if (this._fieldSuggestions) {
      tr.querySelectorAll('input.crud-inline-input').forEach(inp => {
        const items = this._fieldSuggestions[inp.name];
        if (items && items.length) this._initSuggestDropdown(inp, items);
      });
    }

    // Wire up conditional field visibility (showWhen / dynamicLabel)
    this._initConditionalFields(tr, schema);

    // Event handlers
    const form = tr.querySelector('.crud-inline-form');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      this._handleInlineSave(schema, isEdit, rowNumber, form);
    });

    tr.querySelector('.crud-inline-cancel').addEventListener('click', () => this._cancelInline());

    // Enter submits (except inside select)
    form.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.tagName !== 'SELECT') {
        e.preventDefault();
        this._handleInlineSave(schema, isEdit, rowNumber, form);
      }
    });
  }

  _buildInlineField(f, value, datalistItems) {
    const req = f.required ? '<span class="crud-req">*</span>' : '';
    const hasSuggestions = datalistItems && datalistItems.length > 0;
    let input = '';

    if (f.type === 'select') {
      const opts = (f.options || []).map(o => {
        const sel = (String(value).toLowerCase() === o.toLowerCase()) ? 'selected' : '';
        return `<option value="${o}" ${sel}>${o}</option>`;
      }).join('');
      input = `<select class="crud-inline-input" name="${f.key}" ${f.required ? 'required' : ''}>${opts}</select>`;
    } else {
      // For date fields, convert MM/DD/YYYY → YYYY-MM-DD for the HTML input
      const displayValue = f.type === 'date' ? toInputDate(value) : String(value);
      const attrs = [
        `type="${f.type}"`,
        `class="crud-inline-input${f.uppercase ? ' crud-inline-input-uppercase' : ''}"`,
        `name="${f.key}"`,
        `value="${this._esc(displayValue)}"`,
        `autocomplete="off"`,
      ];
      if (f.required) attrs.push('required');
      if (f.placeholder) attrs.push(`placeholder="${this._esc(f.placeholder)}"`);
      if (f.step) attrs.push(`step="${f.step}"`);
      if (f.min) attrs.push(`min="${f.min}"`);
      input = `<input ${attrs.join(' ')}>`;
    }

    const showWhenAttr = f.showWhen ? ` data-show-when="${f.showWhen}"` : '';
    const hideStyle = f.showWhen ? ' style="display:none"' : '';
    const wrapClass = hasSuggestions ? 'crud-inline-field crud-suggest-wrap' : 'crud-inline-field';

    return `<div class="${wrapClass}" data-field-key="${f.key}"${showWhenAttr}${hideStyle}>
      <label class="crud-inline-label">${f.label}${req}</label>
      ${input}
    </div>`;
  }

  /**
   * Wire up conditional field visibility based on showWhen, dynamicLabel,
   * dynamicRequired, and dynamicPlaceholder.
   * showWhen format: "fieldKey=value" — field is visible only when the
   * control field has the specified value.
   */
  _initConditionalFields(formRow, schema) {
    const conditionalFields = formRow.querySelectorAll('[data-show-when]');
    const hasDynamicProps = schema.fields.some(f => f.dynamicLabel || f.dynamicRequired || f.dynamicPlaceholder);
    if (!conditionalFields.length && !hasDynamicProps) return;

    // Collect control fields and their dependents
    const controlMap = {};  // controlKey → [{ el, value, fieldDef }]
    conditionalFields.forEach(el => {
      const [controlKey, controlValue] = el.dataset.showWhen.split('=');
      if (!controlMap[controlKey]) controlMap[controlKey] = [];
      const fieldDef = schema.fields.find(f => f.key === el.dataset.fieldKey);
      controlMap[controlKey].push({ el, value: controlValue, fieldDef });
    });

    // Collect fields with dynamic properties (label, required, placeholder)
    const dynamicFields = schema.fields.filter(f => f.dynamicLabel || f.dynamicRequired || f.dynamicPlaceholder);

    // Ensure control keys from dynamicRequired/dynamicLabel/dynamicPlaceholder are tracked
    for (const f of dynamicFields) {
      for (const prop of [f.dynamicLabel, f.dynamicRequired, f.dynamicPlaceholder]) {
        if (!prop) continue;
        // The keys of these maps are the control field values; the control field
        // itself is inferred from the showWhen fields. For PF, it's 'entry_type'.
      }
    }

    const applyVisibility = () => {
      for (const [controlKey, deps] of Object.entries(controlMap)) {
        const controlEl = formRow.querySelector(`[name="${controlKey}"]`);
        if (!controlEl) continue;
        const currentValue = controlEl.value;

        deps.forEach(({ el, value, fieldDef }) => {
          const visible = currentValue === value;
          el.style.display = visible ? '' : 'none';
          // Toggle required + disabled based on visibility.
          // Disabled fields are excluded from browser constraint
          // validation, preventing "not focusable" errors on hidden
          // inputs that still carry min/step constraints.
          const input = el.querySelector('.crud-inline-input');
          if (input && fieldDef) {
            if (visible) {
              input.removeAttribute('disabled');
              if (fieldDef.required) input.setAttribute('required', '');
            } else {
              input.removeAttribute('required');
              input.setAttribute('disabled', '');
            }
          }
        });

        // Handle dynamic properties for always-visible fields
        dynamicFields.forEach(f => {
          const fieldEl = formRow.querySelector(`[data-field-key="${f.key}"]`);
          if (!fieldEl) return;
          const input = fieldEl.querySelector('.crud-inline-input');
          const label = fieldEl.querySelector('.crud-inline-label');

          // Dynamic required
          if (f.dynamicRequired && currentValue in f.dynamicRequired) {
            const isReq = f.dynamicRequired[currentValue];
            if (input) {
              if (isReq) input.setAttribute('required', '');
              else input.removeAttribute('required');
            }
          } else if (f.dynamicRequired && input) {
            // Revert to schema default
            if (f.required) input.setAttribute('required', '');
            else input.removeAttribute('required');
          }

          // Dynamic label
          if (f.dynamicLabel && label) {
            const dynamicText = f.dynamicLabel[currentValue];
            const isReq = f.dynamicRequired ? (currentValue in f.dynamicRequired ? f.dynamicRequired[currentValue] : f.required) : f.required;
            const req = isReq ? '<span class="crud-req">*</span>' : '';
            label.innerHTML = (dynamicText || f.label) + req;
          }

          // Dynamic placeholder
          if (f.dynamicPlaceholder && input) {
            const ph = f.dynamicPlaceholder[currentValue] || '';
            input.placeholder = ph;
          }
        });
      }
    };

    // Apply initial state
    applyVisibility();

    // Listen for changes on control fields
    for (const controlKey of Object.keys(controlMap)) {
      const controlEl = formRow.querySelector(`[name="${controlKey}"]`);
      if (controlEl) {
        controlEl.addEventListener('change', applyVisibility);
      }
    }
  }

  _initSuggestDropdown(inp, items) {
    if (!items || !items.length) return;

    const wrap = inp.closest('.crud-suggest-wrap');
    const dropdown = document.createElement('div');
    dropdown.className = 'crud-suggest-dropdown';
    wrap.appendChild(dropdown);

    const render = (filter) => {
      const q = (filter || '').toLowerCase();
      const matches = q ? items.filter(v => v.toLowerCase().includes(q)) : items;
      if (!matches.length) { dropdown.classList.remove('open'); return; }
      dropdown.innerHTML = matches.map(v =>
        `<div class="crud-suggest-item">${this._esc(v)}</div>`
      ).join('');
      dropdown.classList.add('open');
    };

    inp.addEventListener('focus', () => { if (inp.value) render(inp.value); });
    inp.addEventListener('input', () => {
      if (inp.value) render(inp.value);
      else dropdown.classList.remove('open');
    });

    dropdown.addEventListener('mousedown', (e) => {
      e.preventDefault();            // keep focus on input
      const item = e.target.closest('.crud-suggest-item');
      if (item) {
        inp.value = item.textContent;
        dropdown.classList.remove('open');
      }
    });

    inp.addEventListener('blur', () => {
      setTimeout(() => dropdown.classList.remove('open'), 150);
    });
  }

  // ── Save (create / update) ─────────────────────────────────

  async _handleInlineSave(schema, isEdit, rowNumber, form) {
    const saveBtn = form.querySelector('.crud-inline-save');

    // Gather values, converting date inputs back to MM/DD/YYYY for Sheets
    const payload = {};
    for (const f of schema.fields) {
      if (f.skipInPayload) continue;
      const fieldWrap = form.querySelector(`[data-field-key="${f.key}"]`);
      const isHidden = fieldWrap && fieldWrap.style.display === 'none';
      const el = form.querySelector(`[name="${f.key}"]`);
      let val = el ? el.value.trim() : '';
      // Hidden fields get default empty values
      if (isHidden) val = '';
      if (f.type === 'date' && val) val = toSheetDate(val);
      if (f.uppercase) val = val.toUpperCase();
      payload[f.key] = val;
    }

    // Validate required fields (only visible ones, respecting dynamic required state)
    for (const f of schema.fields) {
      if (f.skipInPayload) continue;
      const fieldWrap = form.querySelector(`[data-field-key="${f.key}"]`);
      const isHidden = fieldWrap && fieldWrap.style.display === 'none';
      if (isHidden) continue;
      const el = form.querySelector(`[name="${f.key}"]`);
      const isRequired = el ? el.hasAttribute('required') : f.required;
      if (isRequired && !payload[f.key]) {
        this._toast(`${f.label} is required`, 'error');
        const el = form.querySelector(`[name="${f.key}"]`);
        if (el) {
          el.focus();
          el.classList.add('crud-inline-input-error');
          el.addEventListener('input', () => el.classList.remove('crud-inline-input-error'), { once: true });
        }
        return;
      }
    }

    saveBtn.disabled = true;
    const formRow = form.closest('.crud-inline-row');
    if (formRow) formRow.classList.add('saving');

    try {
      const url = isEdit
        ? `/api/sheets/${schema.sheetType}/${rowNumber}`
        : `/api/sheets/${schema.sheetType}`;
      const method = isEdit ? 'PUT' : 'POST';

      const resp = await metronFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const d = await resp.json();
        throw new Error(d.error || 'Save failed');
      }

      const result = await resp.json();

      // Remove form row immediately
      if (this._activeFormRow) this._activeFormRow.remove();
      this._activeFormRow = null;
      const origRow = this._activeOriginalRow
        || this._findOriginalRow();
      if (origRow) origRow.remove();
      this._activeOriginalRow = null;
      this._activeSchemaKey = null;
      this._activeRowNumber = null;

      this._toast(isEdit ? 'Updated successfully' : 'Added successfully', 'success');
      if (this._onDataChanged) this._onDataChanged(result.data);
    } catch (err) {
      this._toast(err.message, 'error');
      saveBtn.disabled = false;
      if (formRow) {
        formRow.classList.remove('saving');
      }
      // Highlight the symbol field on validation errors
      if (err.message.includes("doesn't exist on exchange")) {
        const symbolEl = form.querySelector('[name="symbol"]');
        if (symbolEl) {
          symbolEl.focus();
          symbolEl.classList.add('crud-inline-input-error');
          symbolEl.addEventListener('input', () => symbolEl.classList.remove('crud-inline-input-error'), { once: true });
        }
      }
    }
  }

  // ── Cancel inline form ─────────────────────────────────────

  _cancelInline() {
    // Close drawer if open
    if (this._drawerEl) {
      this._closeDrawer();
      return;
    }
    if (this._activeFormRow) {
      this._activeFormRow.remove();
      this._activeFormRow = null;
    }
    // Unhide the original data row. Prefer the live reference, but fall
    // back to a DOM lookup in case _updateTbodyContent replaced it.
    const origRow = this._activeOriginalRow
      || this._findOriginalRow();
    if (origRow) {
      origRow.style.display = '';
    }
    this._activeOriginalRow = null;
    this._activeSchemaKey = null;
    this._activeRowNumber = null;
    // Re-show empty CTA if the tbody has no visible data rows
    document.querySelectorAll('.crud-empty-cta-row').forEach(row => {
      const tbody = row.closest('tbody');
      if (!tbody) return;
      // Check if tbody has any visible rows other than the CTA row itself
      const visibleDataRows = Array.from(tbody.children).filter(
        r => r !== row && r.style.display !== 'none'
      );
      if (visibleDataRows.length === 0) {
        row.style.display = '';
      }
    });
  }

  _getTbody(schemaKey) {
    const id = TBODY_MAP[schemaKey];
    return id ? document.getElementById(id) : null;
  }

  /**
   * Look up the hidden original data row in the DOM by schema key and
   * row number.  Used as a fallback when the stored _activeOriginalRow
   * reference has been replaced by a table re-render.
   */
  _findOriginalRow() {
    if (this._activeRowNumber == null || !this._activeSchemaKey) return null;
    const tbody = this._getTbody(this._activeSchemaKey);
    if (!tbody) return null;
    return tbody.querySelector(
      `tr[data-manual-row="${this._activeRowNumber}"][data-schema="${this._activeSchemaKey}"]`
    );
  }

  // ── Toast notifications ────────────────────────────────────

  _toast(message, type = 'info') {
    const el = document.createElement('div');
    el.className = `crud-toast crud-toast-${type}`;

    const icon = type === 'success'
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

    el.innerHTML = `${icon}<span>${this._esc(message)}</span>`;
    this._toastContainer.appendChild(el);

    requestAnimationFrame(() => el.classList.add('show'));

    setTimeout(() => {
      el.classList.remove('show');
      el.addEventListener('transitionend', () => el.remove());
    }, 3000);
  }

  _esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
}

export { CrudManager, SCHEMAS };
export default CrudManager;
