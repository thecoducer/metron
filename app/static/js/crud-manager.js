/* Metron - CRUD Manager for Manual Data Entry
 *
 * Handles Add / Edit / Delete operations for all sheet-backed tables.
 * Uses a bottom drawer form for all screen sizes.
 * Libraries: Tom Select (dropdowns/autocomplete) + Flatpickr (date picker).
 */

import { metronFetch } from './utils.js';

// ── Date format helpers ──────────────────────────────────────────

/** Convert MM/DD/YYYY → YYYY-MM-DD for display. */
function toInputDate(raw) {
  if (!raw) return '';
  const s = String(raw).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const d = new Date(s);
  if (isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Convert YYYY-MM-DD → MM/DD/YYYY for Google Sheets. */
function toSheetDate(isoStr) {
  if (!isoStr) return '';
  const parts = isoStr.split('-');
  if (parts.length !== 3) return isoStr;
  return `${parts[1]}/${parts[2]}/${parts[0]}`;
}

// ── Schema definitions ────────────────────────────────────────────
const SCHEMAS = {
  stocks: {
    label: 'Stock',
    sheetType: 'stocks',
    fields: [
      { key: 'symbol',    label: 'Symbol',    type: 'text',   required: true,  placeholder: 'e.g. RELIANCE', uppercase: true },
      { key: 'qty',       label: 'Quantity',  type: 'number', required: true,  step: '1',    min: '1' },
      { key: 'avg_price', label: 'Avg Price', type: 'number', required: true,  step: '0.01', min: '0' },
      { key: 'exchange',  label: 'Exchange',  type: 'select', required: true,  options: ['NSE', 'BSE'] },
      { key: 'account',   label: 'Account',   type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  etfs: {
    label: 'ETF',
    sheetType: 'etfs',
    fields: [
      { key: 'symbol',    label: 'Symbol',    type: 'text',   required: true,  placeholder: 'e.g. NIFTYBEES', uppercase: true },
      { key: 'qty',       label: 'Quantity',  type: 'number', required: true,  step: '1',    min: '1' },
      { key: 'avg_price', label: 'Avg Price', type: 'number', required: true,  step: '0.01', min: '0' },
      { key: 'exchange',  label: 'Exchange',  type: 'select', required: true,  options: ['NSE', 'BSE'] },
      { key: 'account',   label: 'Account',   type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  mutual_funds: {
    label: 'Mutual Fund',
    sheetType: 'mutual_funds',
    fields: [
      { key: 'fund_name', label: 'Fund Name', type: 'text',   required: true,  placeholder: 'Search fund name…', suggestApi: '/api/mutual_funds/search' },
      { key: 'qty',       label: 'Units',     type: 'number', required: true,  step: '0.001', min: '0' },
      { key: 'avg_nav',   label: 'Avg NAV',   type: 'number', required: true,  step: '0.01',  min: '0' },
      { key: 'account',   label: 'Account',   type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  sips: {
    label: 'SIP',
    sheetType: 'sips',
    fields: [
      { key: 'fund',         label: 'Fund Name',     type: 'text',   required: true,  placeholder: 'Search fund name…', suggestApi: '/api/mutual_funds/search' },
      { key: 'amount',       label: 'Amount',        type: 'number', required: true,  step: '1',    min: '1' },
      { key: 'frequency',    label: 'Frequency',     type: 'select', required: true,  options: ['MONTHLY', 'WEEKLY', 'QUARTERLY'] },
      { key: 'installments', label: 'Installments',  type: 'number', required: false, step: '1',    min: '0', placeholder: '-1 for perpetual' },
      { key: 'completed',    label: 'Completed',     type: 'number', required: false, step: '1',    min: '0' },
      { key: 'status',       label: 'Status',        type: 'select', required: true,  options: ['ACTIVE', 'PAUSED', 'CANCELLED'] },
      { key: 'next_due',     label: 'Next Due Date', type: 'date',   required: false },
      { key: 'account',      label: 'Account',       type: 'text',   required: false, placeholder: 'e.g. Personal' },
    ],
  },
  physical_gold: {
    label: 'Physical Gold',
    sheetType: 'physical_gold',
    fields: [
      { key: 'date',                    label: 'Bought On',     type: 'date',   required: true },
      { key: 'type',                    label: 'Type',          type: 'select', required: true, options: ['Jewellery', 'Coin', 'Bar', 'Biscuit', 'Other'] },
      { key: 'retail_outlet',           label: 'Retail Outlet', type: 'text',   required: false, placeholder: 'e.g. Tanishq' },
      { key: 'purity',                  label: 'Purity',        type: 'select', required: true, options: ['24K', '22K', '18K'] },
      { key: 'weight_gms',              label: 'Weight (gms)',  type: 'number', required: true, step: '0.001', min: '0' },
      { key: 'bought_ibja_rate_per_gm', label: 'IBJA Rate/gm', type: 'number', required: true, step: '0.01',  min: '0' },
    ],
  },
  fixed_deposits: {
    label: 'Fixed Deposit',
    sheetType: 'fixed_deposits',
    fields: [
      { key: 'original_investment_date', label: 'Deposited On',   type: 'date',   required: true },
      { key: 'reinvested_date',          label: 'Reinvested On',  type: 'date',   required: false },
      { key: 'bank_name',                label: 'Bank',           type: 'text',   required: true,  placeholder: 'e.g. SBI' },
      { key: 'deposit_year',             label: 'Tenure Years',   type: 'number', required: true,  step: '1', min: '0' },
      { key: 'deposit_month',            label: 'Tenure Months',  type: 'number', required: true,  step: '1', min: '0' },
      { key: 'deposit_day',              label: 'Tenure Days',    type: 'number', required: true,  step: '1', min: '0' },
      { key: 'original_amount',          label: 'Amount',         type: 'number', required: true,  step: '0.01', min: '0' },
      { key: 'reinvested_amount',        label: 'Reinvested Amt', type: 'number', required: false, step: '0.01', min: '0' },
      { key: 'interest_rate',            label: 'Rate (%)',       type: 'number', required: true,  step: '0.01', min: '0' },
      { key: 'account',                  label: 'Account',        type: 'text',   required: true,  placeholder: 'e.g. Joint' },
    ],
  },
};

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
    this._activeSchemaKey = null;
    this._activeRowNumber = null;
    this._drawerEl = null;
    this._drawerBackdrop = null;
    this._init();
  }

  _init() {
    this._deletePopover = null;
    this._deletePopoverCleanup = null;

    this._toastContainer = document.createElement('div');
    this._toastContainer.className = 'crud-toast-container';
    document.body.appendChild(this._toastContainer);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (this._deletePopover) this._closeDeletePopover();
        else if (this._drawerEl) this._closeDrawer();
      }
    });
  }

  // ── Public API ────────────────────────────────────────────────

  isEditing() { return this._drawerEl !== null; }

  openAdd(schemaKey) {
    const schema = SCHEMAS[schemaKey];
    if (!schema) return;
    this._closeDrawer();
    this._activeSchemaKey = schemaKey;
    this._activeRowNumber = null;
    this._showDrawerForm(schema, schemaKey, null, null);
  }

  openEdit(schemaKey, rowNumber, currentValues) {
    const schema = SCHEMAS[schemaKey];
    if (!schema) return;
    this._closeDrawer();
    this._activeSchemaKey = schemaKey;
    this._activeRowNumber = rowNumber;
    this._showDrawerForm(schema, schemaKey, rowNumber, currentValues);
  }

  async confirmDelete(schemaKey, rowNumber) {
    const schema = SCHEMAS[schemaKey];
    if (!schema) return;
    this._closeDeletePopover();

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

    requestAnimationFrame(() => backdrop.classList.add('open'));

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) this._closeDeletePopover();
    });

    const onEscape = (e) => { if (e.key === 'Escape') this._closeDeletePopover(); };
    document.addEventListener('keydown', onEscape);
    this._deletePopoverCleanup = () => document.removeEventListener('keydown', onEscape);

    dialog.querySelector('.crud-ddlg-cancel').addEventListener('click', () => this._closeDeletePopover());
    dialog.querySelector('.crud-ddlg-confirm').addEventListener('click', async () => {
      const btn = dialog.querySelector('.crud-ddlg-confirm');
      btn.disabled = true;
      btn.textContent = 'Deleting…';
      try {
        const resp = await metronFetch(`/api/sheets/${schema.sheetType}/${rowNumber}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error((await resp.json()).error || 'Delete failed');
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
    if (this._deletePopoverCleanup) { this._deletePopoverCleanup(); this._deletePopoverCleanup = null; }
    const backdrop = this._deletePopover;
    backdrop.classList.remove('open');
    backdrop.classList.add('closing');
    backdrop.addEventListener('animationend', () => backdrop.remove(), { once: true });
    setTimeout(() => { if (backdrop.parentNode) backdrop.remove(); }, 300);
    this._deletePopover = null;
  }

  // ── Drawer form ───────────────────────────────────────────────

  _showDrawerForm(schema, schemaKey, rowNumber, values) {
    const isEdit = rowNumber != null;

    let fieldsHtml = '';
    for (const f of schema.fields) {
      const val = (values && values[f.key] !== undefined) ? values[f.key] : '';
      fieldsHtml += this._buildField(f, val);
    }

    const backdrop = document.createElement('div');
    backdrop.className = 'crud-drawer-backdrop';

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
          <div class="crud-form-fields">${fieldsHtml}</div>
        </form>
      </div>
      <div class="crud-drawer-footer">
        <button type="button" class="crud-drawer-cancel">Cancel</button>
        <button type="button" class="crud-drawer-save">${isEdit ? 'Update' : 'Save'}</button>
      </div>`;

    document.body.appendChild(backdrop);
    document.body.appendChild(drawer);
    this._drawerBackdrop = backdrop;
    this._drawerEl = drawer;
    document.body.style.overflow = 'hidden';

    // Animate open
    requestAnimationFrame(() => {
      backdrop.classList.add('open');
      drawer.classList.add('open');
    });

    this._initSuggestFields(drawer, schema);

    // Wire close handlers
    const cancel = () => this._closeDrawer();
    backdrop.addEventListener('click', cancel);
    drawer.querySelector('.crud-drawer-close').addEventListener('click', cancel);
    drawer.querySelector('.crud-drawer-cancel').addEventListener('click', cancel);

    const form = drawer.querySelector('.crud-drawer-form');
    const save = () => this._handleSave(schema, isEdit, rowNumber, form, drawer);
    drawer.querySelector('.crud-drawer-save').addEventListener('click', save);
    form.addEventListener('submit', (e) => { e.preventDefault(); save(); });
    form.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.tagName !== 'SELECT') { e.preventDefault(); save(); }
    });
  }


  async _handleSave(schema, isEdit, rowNumber, form, drawer) {
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

    // Validate visible required fields
    for (const f of schema.fields) {
      if (f.skipInPayload) continue;
      const fieldWrap = form.querySelector(`[data-field-key="${f.key}"]`);
      if (fieldWrap && fieldWrap.style.display === 'none') continue;
      const el = form.querySelector(`[name="${f.key}"]`);
      const isRequired = el ? el.hasAttribute('required') : f.required;
      if (isRequired && !payload[f.key]) {
        this._toast(`${f.label} is required`, 'error');
        if (fieldWrap) fieldWrap.classList.add('crud-field-error');
        // Remove error on next interaction
        const clearErr = () => fieldWrap?.classList.remove('crud-field-error');
        el?.addEventListener('change', clearErr, { once: true });
        el?.addEventListener('input', clearErr, { once: true });
        return;
      }
    }

    saveBtn.disabled = true;
    drawer.classList.add('saving');

    try {
      const url = isEdit ? `/api/sheets/${schema.sheetType}/${rowNumber}` : `/api/sheets/${schema.sheetType}`;
      const resp = await metronFetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) throw new Error((await resp.json()).error || 'Save failed');
      const result = await resp.json();
      this._closeDrawer();
      this._toast(isEdit ? 'Updated successfully' : 'Added successfully', 'success');
      if (this._onDataChanged) this._onDataChanged(result.data);
    } catch (err) {
      this._toast(err.message, 'error');
      saveBtn.disabled = false;
      drawer.classList.remove('saving');
      if (err.message.includes("doesn't exist on exchange")) {
        const fieldWrap = form.querySelector('[data-field-key="symbol"]');
        fieldWrap?.classList.add('crud-field-error');
      }
    }
  }

  _closeDrawer() {
    if (this._drawerEl) {
      this._drawerEl.classList.remove('open');
      this._drawerBackdrop?.classList.remove('open');
      const el = this._drawerEl;
      const bd = this._drawerBackdrop;
      setTimeout(() => { el?.remove(); bd?.remove(); }, 350);
      this._drawerEl = null;
      this._drawerBackdrop = null;
    }
    document.body.style.overflow = '';
    this._activeSchemaKey = null;
    this._activeRowNumber = null;
  }

  // ── Field builder ─────────────────────────────────────────────

  _buildField(f, value) {
    const req = f.required ? '<span class="crud-req">*</span>' : '';
    const showWhenAttr = f.showWhen ? ` data-show-when="${f.showWhen}"` : '';
    const hideStyle = f.showWhen ? ' style="display:none"' : '';
    let input = '';

    if (f.suggestApi) {
      input = `<input type="text" class="crud-field-input" name="${f.key}" value="${this._esc(String(value || ''))}" placeholder="${this._esc(f.placeholder || 'Search…')}" autocomplete="off" data-suggest-api="${f.suggestApi}" ${f.required ? 'required' : ''}>`;
    } else if (f.type === 'select') {
      const opts = (f.options || []).map(o => {
        const sel = (String(value).toLowerCase() === o.toLowerCase()) ? 'selected' : '';
        return `<option value="${o}" ${sel}>${o}</option>`;
      }).join('');
      input = `<select class="crud-field-select" name="${f.key}" ${f.required ? 'required' : ''}>${opts}</select>`;
    } else if (f.type === 'date') {
      const isoDate = toInputDate(value);
      input = `<input type="date" class="crud-field-input" name="${f.key}" value="${this._esc(isoDate)}" ${f.required ? 'required' : ''}>`;
    } else {
      const attrs = [
        `type="${f.type}"`,
        `class="crud-field-input${f.uppercase ? ' crud-field-input--upper' : ''}"`,
        `name="${f.key}"`,
        `value="${this._esc(String(value || ''))}"`,
        `autocomplete="off"`,
      ];
      if (f.required) attrs.push('required');
      if (f.placeholder) attrs.push(`placeholder="${this._esc(f.placeholder)}"`);
      if (f.step) attrs.push(`step="${f.step}"`);
      if (f.min) attrs.push(`min="${f.min}"`);
      input = `<input ${attrs.join(' ')}>`;
    }

    return `<div class="crud-form-field" data-field-key="${f.key}"${showWhenAttr}${hideStyle}>
      <label class="crud-field-label">${f.label}${req}</label>
      ${input}
    </div>`;
  }

  // ── Suggest-field initializers ────────────────────────────────

  _initSuggestFields(drawer, schema) {
    drawer.querySelectorAll('input[data-suggest-api]').forEach(inp => {
      this._attachSuggest(inp, drawer);
    });
    this._initConditionalFields(drawer, schema);
  }

  _attachSuggest(input, drawer) {
    const list = document.createElement('div');
    list.className = 'crud-suggest-list';
    list.hidden = true;
    drawer.appendChild(list);

    let debounce = null;
    let activeIdx = -1;

    const position = () => {
      const ir = input.getBoundingClientRect();
      const dr = drawer.getBoundingClientRect();
      list.style.top = `${ir.bottom - dr.top + 4}px`;
      list.style.left = `${ir.left - dr.left}px`;
      list.style.width = `${ir.width}px`;
    };

    const hide = () => { list.hidden = true; activeIdx = -1; };

    const select = (text) => {
      input.value = text;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      hide();
    };

    const setActive = (idx) => {
      activeIdx = idx;
      list.querySelectorAll('.crud-suggest-item').forEach((el, i) => {
        el.classList.toggle('active', i === idx);
        if (i === idx) el.scrollIntoView({ block: 'nearest' });
      });
    };

    const show = (items) => {
      list.innerHTML = '';
      activeIdx = -1;
      if (!items.length) { list.hidden = true; return; }
      items.forEach(text => {
        const el = document.createElement('div');
        el.className = 'crud-suggest-item';
        el.textContent = text;
        el.addEventListener('mousedown', e => { e.preventDefault(); select(text); });
        list.appendChild(el);
      });
      position();
      list.hidden = false;
    };

    input.addEventListener('input', () => {
      clearTimeout(debounce);
      const q = input.value.trim();
      if (q.length < 2) { hide(); return; }
      debounce = setTimeout(async () => {
        try {
          const r = await metronFetch(`${input.dataset.suggestApi}?q=${encodeURIComponent(q)}`);
          show((await r.json()).filter(Boolean));
        } catch { hide(); }
      }, 250);
    });

    input.addEventListener('keydown', e => {
      if (list.hidden) return;
      const els = list.querySelectorAll('.crud-suggest-item');
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive(Math.min(activeIdx + 1, els.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(activeIdx - 1, 0)); }
      else if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); select(els[activeIdx].textContent); }
      else if (e.key === 'Escape') { hide(); }
    });

    input.addEventListener('blur', () => setTimeout(hide, 150));
    drawer.querySelector('.crud-drawer-body')?.addEventListener('scroll', () => {
      if (!list.hidden) position();
    });
  }

  // ── Conditional field visibility ──────────────────────────────

  _initConditionalFields(formRow, schema) {
    const conditionalFields = formRow.querySelectorAll('[data-show-when]');
    const hasDynamic = schema.fields.some(f => f.dynamicLabel || f.dynamicRequired || f.dynamicPlaceholder);
    if (!conditionalFields.length && !hasDynamic) return;

    const controlMap = {};
    conditionalFields.forEach(el => {
      const [controlKey, controlValue] = el.dataset.showWhen.split('=');
      if (!controlMap[controlKey]) controlMap[controlKey] = [];
      const fieldDef = schema.fields.find(f => f.key === el.dataset.fieldKey);
      controlMap[controlKey].push({ el, value: controlValue, fieldDef });
    });

    const dynamicFields = schema.fields.filter(f => f.dynamicLabel || f.dynamicRequired || f.dynamicPlaceholder);

    const applyVisibility = () => {
      for (const [controlKey, deps] of Object.entries(controlMap)) {
        const controlEl = formRow.querySelector(`[name="${controlKey}"]`);
        if (!controlEl) continue;
        const currentValue = controlEl.value;

        deps.forEach(({ el, value, fieldDef }) => {
          const visible = currentValue === value;
          el.style.display = visible ? '' : 'none';
          const input = el.querySelector('.crud-field-input, .crud-field-select');
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

        dynamicFields.forEach(f => {
          const fieldEl = formRow.querySelector(`[data-field-key="${f.key}"]`);
          if (!fieldEl) return;
          const input = fieldEl.querySelector('.crud-field-input, .crud-field-select');
          const label = fieldEl.querySelector('.crud-field-label');

          if (f.dynamicRequired) {
            const isReq = currentValue in f.dynamicRequired ? f.dynamicRequired[currentValue] : f.required;
            if (input) { isReq ? input.setAttribute('required', '') : input.removeAttribute('required'); }
          }
          if (f.dynamicLabel && label) {
            const isReq = f.dynamicRequired ? (currentValue in f.dynamicRequired ? f.dynamicRequired[currentValue] : f.required) : f.required;
            label.innerHTML = (f.dynamicLabel[currentValue] || f.label) + (isReq ? '<span class="crud-req">*</span>' : '');
          }
          if (f.dynamicPlaceholder && input) {
            input.placeholder = f.dynamicPlaceholder[currentValue] || '';
          }
        });
      }
    };

    applyVisibility();
    for (const controlKey of Object.keys(controlMap)) {
      formRow.querySelector(`[name="${controlKey}"]`)?.addEventListener('change', applyVisibility);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────

  _getTbody(schemaKey) {
    const id = TBODY_MAP[schemaKey];
    return id ? document.getElementById(id) : null;
  }

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
