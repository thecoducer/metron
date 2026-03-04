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
      { key: 'symbol',    label: 'Symbol',    type: 'text',   required: true, placeholder: 'e.g. RELIANCE' },
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
      { key: 'symbol',    label: 'Symbol',    type: 'text',   required: true, placeholder: 'e.g. NIFTYBEES' },
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
      { key: 'redeemed',               label: 'Redeemed?',       type: 'select', required: true, options: ['No', 'Yes'] },
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
    this._modalEl = null;
    this._backdropEl = null;
    this._init();
  }

  // ── Bootstrap ────────────────────────────────────────────────

  _init() {
    // Backdrop + modal kept only for delete confirmation
    this._backdropEl = document.createElement('div');
    this._backdropEl.className = 'crud-backdrop';
    this._backdropEl.addEventListener('click', () => this._closeModal());

    this._modalEl = document.createElement('div');
    this._modalEl.className = 'crud-modal';

    document.body.appendChild(this._backdropEl);
    document.body.appendChild(this._modalEl);

    // Toast container
    this._toastContainer = document.createElement('div');
    this._toastContainer.className = 'crud-toast-container';
    document.body.appendChild(this._toastContainer);

    // Global keyboard handler
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (this._backdropEl.classList.contains('open')) this._closeModal();
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

    this._modalEl.innerHTML = `
      <div class="crud-modal-header">
        <h3>Delete ${schema.label}</h3>
        <button class="crud-close-btn" title="Close">&times;</button>
      </div>
      <div class="crud-modal-body crud-confirm-body">
        <svg class="crud-warn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
        <p>Are you sure you want to delete this entry?<br><span class="crud-confirm-sub">This action cannot be undone.</span></p>
      </div>
      <div class="crud-modal-footer">
        <button class="crud-btn crud-btn-cancel">Cancel</button>
        <button class="crud-btn crud-btn-danger" id="crud-confirm-delete">Delete</button>
      </div>`;

    this._openModal();

    this._modalEl.querySelector('.crud-close-btn').addEventListener('click', () => this._closeModal());
    this._modalEl.querySelector('.crud-btn-cancel').addEventListener('click', () => this._closeModal());
    this._modalEl.querySelector('#crud-confirm-delete').addEventListener('click', async () => {
      const btn = this._modalEl.querySelector('#crud-confirm-delete');
      btn.disabled = true;
      btn.textContent = 'Deleting…';
      try {
        const resp = await metronFetch(`/api/sheets/${schema.sheetType}/${rowNumber}`, { method: 'DELETE' });
        if (!resp.ok) {
          const d = await resp.json();
          throw new Error(d.error || 'Delete failed');
        }
        const result = await resp.json();
        this._closeModal();
        this._toast('Deleted successfully', 'success');
        if (this._onDataChanged) this._onDataChanged(result.data);
      } catch (err) {
        this._toast(err.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Delete';
      }
    });
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

    let fieldsHtml = '';
    for (const f of schema.fields) {
      const val = (values && values[f.key] !== undefined) ? values[f.key] : '';
      fieldsHtml += this._buildInlineField(f, val);
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

  _buildInlineField(f, value) {
    const req = f.required ? '<span class="crud-req">*</span>' : '';
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
        `class="crud-inline-input"`,
        `name="${f.key}"`,
        `value="${this._esc(displayValue)}"`,
      ];
      if (f.required) attrs.push('required');
      if (f.placeholder) attrs.push(`placeholder="${this._esc(f.placeholder)}"`);
      if (f.step) attrs.push(`step="${f.step}"`);
      if (f.min) attrs.push(`min="${f.min}"`);
      input = `<input ${attrs.join(' ')}>`;
    }

    return `<div class="crud-inline-field">
      <label class="crud-inline-label">${f.label}${req}</label>
      ${input}
    </div>`;
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
    saveBtn.classList.add('saving');

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
      // Remove the hidden original data row (may have been replaced by
      // _updateTbodyContent during a refresh, so look it up fresh).
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
      saveBtn.classList.remove('saving');
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

  // ── Modal (delete confirmation only) ───────────────────────

  _openModal() {
    this._backdropEl.classList.add('open');
    this._modalEl.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  _closeModal() {
    this._backdropEl.classList.remove('open');
    this._modalEl.classList.remove('open');
    document.body.style.overflow = '';
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
