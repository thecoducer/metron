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
  provident_fund: {
    label: 'Provident Fund',
    sheetType: 'provident_fund',
    fields: [
      { key: 'company_name',        label: 'Company',            type: 'text',   required: true, placeholder: 'e.g. Infosys', datalistFrom: 'company_name' },
      { key: 'start_date',          label: 'Start Date',         type: 'date',   required: true },
      { key: 'end_date',            label: 'End Date',           type: 'date',   required: false },
      { key: 'monthly_contribution', label: 'Monthly Contribution', type: 'number', required: true, step: '1', min: '1' },
      { key: 'interest_rate',       label: 'Interest Rate (%)',  type: 'number', required: false, step: '0.01', min: '0', placeholder: '0 = Auto (EPFO rate)' },
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
  provident_fund: 'provident_fund_table_body',
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
        else if (this._activeFormRow) this._cancelInline();
      }
    });
  }

  // ── Public API ───────────────────────────────────────────────

  /** Returns true when an inline add/edit form is currently open. */
  isEditing() {
    return this._activeFormRow !== null;
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

    // Close any existing popover first
    this._closeDeletePopover();

    // Find the delete button that was clicked to anchor the popover
    const tbody = this._getTbody(schemaKey);
    const row = tbody?.querySelector(`tr[data-manual-row="${rowNumber}"][data-schema="${schemaKey}"]`);
    const anchor = row?.querySelector('.crud-delete-btn') || row;

    // Create the popover element
    const popover = document.createElement('div');
    popover.className = 'crud-delete-popover';
    popover.innerHTML = `
      <div class="crud-delete-popover-arrow"></div>
      <div class="crud-delete-popover-body">
        <span class="crud-delete-popover-text">Are you sure?</span>
        <div class="crud-delete-popover-actions">
          <button class="crud-dpop-btn crud-dpop-cancel">Cancel</button>
          <button class="crud-dpop-btn crud-dpop-confirm">Confirm</button>
        </div>
      </div>`;

    document.body.appendChild(popover);
    this._deletePopover = popover;

    // Position the popover above the anchor
    this._positionPopover(popover, anchor);

    // Animate in
    requestAnimationFrame(() => popover.classList.add('open'));

    // Close on outside click
    const onOutsideClick = (e) => {
      if (!popover.contains(e.target) && !anchor.contains(e.target)) {
        this._closeDeletePopover();
      }
    };
    setTimeout(() => document.addEventListener('click', onOutsideClick, { capture: true }), 0);
    this._deletePopoverCleanup = () => {
      document.removeEventListener('click', onOutsideClick, { capture: true });
    };

    // Wire buttons
    popover.querySelector('.crud-dpop-cancel').addEventListener('click', () => this._closeDeletePopover());
    popover.querySelector('.crud-dpop-confirm').addEventListener('click', async () => {
      const btn = popover.querySelector('.crud-dpop-confirm');
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

  _positionPopover(popover, anchor) {
    const rect = anchor.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    const gap = 8;

    // Default: position above the anchor, centered horizontally
    let top = rect.top - popoverRect.height - gap + window.scrollY;
    let left = rect.left + rect.width / 2 - popoverRect.width / 2 + window.scrollX;

    // If it would go off-screen top, show below instead
    if (top - window.scrollY < 8) {
      top = rect.bottom + gap + window.scrollY;
      popover.classList.add('below');
    }

    // Clamp horizontal to viewport
    const maxLeft = window.innerWidth - popoverRect.width - 8 + window.scrollX;
    left = Math.max(8 + window.scrollX, Math.min(left, maxLeft));

    popover.style.top = `${top}px`;
    popover.style.left = `${left}px`;

    // Adjust arrow to point at anchor center
    const arrowOffset = rect.left + rect.width / 2 - left;
    const arrow = popover.querySelector('.crud-delete-popover-arrow');
    if (arrow) arrow.style.left = `${arrowOffset}px`;
  }

  _closeDeletePopover() {
    if (!this._deletePopover) return;
    if (this._deletePopoverCleanup) {
      this._deletePopoverCleanup();
      this._deletePopoverCleanup = null;
    }
    const popover = this._deletePopover;
    popover.classList.remove('open');
    popover.classList.add('closing');
    popover.addEventListener('animationend', () => popover.remove(), { once: true });
    // Fallback removal
    setTimeout(() => { if (popover.parentNode) popover.remove(); }, 300);
    this._deletePopover = null;
  }

  // ── Inline form ──────────────────────────────────────────────

  _showInlineForm(schema, schemaKey, rowNumber, values, existingRow) {
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
        const colIdx = schema.fields.findIndex(sf => sf.key === f.datalistFrom);
        tbody.querySelectorAll(`tr[data-schema="${schemaKey}"]`).forEach(row => {
          const cell = row.children[colIdx];
          if (cell) {
            const v = cell.textContent.trim();
            if (v && v !== '-') existing.add(v);
          }
        });
        suggestions[f.key] = [...existing].sort();
      }
    }

    this._fieldSuggestions = suggestions;
    let fieldsHtml = '';
    for (const f of schema.fields) {
      const val = (values && values[f.key] !== undefined) ? values[f.key] : '';
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

    return `<div class="${hasSuggestions ? 'crud-inline-field crud-suggest-wrap' : 'crud-inline-field'}">
      <label class="crud-inline-label">${f.label}${req}</label>
      ${input}
    </div>`;
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
      const el = form.querySelector(`[name="${f.key}"]`);
      let val = el ? el.value.trim() : '';
      if (f.type === 'date' && val) val = toSheetDate(val);
      if (f.uppercase) val = val.toUpperCase();
      payload[f.key] = val;
    }

    // Validate required fields
    for (const f of schema.fields) {
      if (f.required && !payload[f.key]) {
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
