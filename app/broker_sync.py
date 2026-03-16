"""Background sync of broker (Zerodha) portfolio data to Google Sheets.

After a successful broker data fetch, this module persists the holdings
and SIPs to the user's Google Sheet with ``source=zerodha``.  This
allows the app to serve the last-known broker data as a fallback when
broker sessions expire, without requiring the user to re-login.

Design principles:
- Manual entries (source != "zerodha") are NEVER modified.
- Only zerodha-sourced rows are added, updated, or deleted.
- Batch API calls minimise network round-trips.
- Graceful error handling — sync failure never affects the dashboard.
"""

import threading
import time
from typing import Any

from .api.user_sheets import SHEET_CONFIGS
from .constants import BROKER_SYNC_LOCKS_MAX
from .logging_config import logger

# Per-user sync locks — bounded to prevent memory leaks.
_sync_locks: dict[str, threading.Lock] = {}
_sync_locks_guard = threading.Lock()


def _get_sync_lock(google_id: str) -> threading.Lock:
    """Return a per-user lock for serialising broker sync operations."""
    with _sync_locks_guard:
        if len(_sync_locks) >= BROKER_SYNC_LOCKS_MAX:
            keys = list(_sync_locks.keys())[: BROKER_SYNC_LOCKS_MAX // 2]
            for k in keys:
                _sync_locks.pop(k, None)
        return _sync_locks.setdefault(google_id, threading.Lock())


# ── Data transformation helpers ──────────────────────────────


def _format_num(v: Any) -> str:
    """Format a number for sheet storage (integers stay as ints)."""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def _stock_to_row(stock: dict) -> list[str]:
    """Convert a broker stock holding to a sheet row."""
    return [
        stock.get("tradingsymbol", ""),
        _format_num(stock.get("quantity", 0)),
        _format_num(stock.get("average_price", 0)),
        stock.get("exchange", "NSE"),
        stock.get("account", ""),
        "zerodha",
    ]


def _mf_to_row(mf: dict) -> list[str]:
    """Convert a broker MF holding to a sheet row."""
    return [
        mf.get("tradingsymbol", mf.get("fund", "")),
        mf.get("fund", ""),
        _format_num(mf.get("quantity", 0)),
        _format_num(mf.get("average_price", 0)),
        mf.get("account", ""),
        "zerodha",
    ]


def _sip_to_row(sip: dict) -> list[str]:
    """Convert a broker SIP to a sheet row."""
    return [
        sip.get("tradingsymbol", sip.get("fund", "")),
        sip.get("fund", ""),
        _format_num(sip.get("instalment_amount", 0)),
        sip.get("frequency", ""),
        _format_num(sip.get("instalments", -1)),
        _format_num(sip.get("completed_instalments", 0)),
        sip.get("status", ""),
        str(sip.get("next_instalment", "")),
        sip.get("account", ""),
        "zerodha",
    ]


# ── Sheet key extraction (symbol + account) ─────────────────


def _key_from_row(row: list, symbol_idx: int, account_idx: int) -> tuple[str, str]:
    """Extract a (symbol, account) key from a sheet row or values list."""
    symbol = (row[symbol_idx] if len(row) > symbol_idx else "").strip().upper()
    account = (row[account_idx] if len(row) > account_idx else "").strip()
    return (symbol, account)


def _values_changed(current: list, new: list) -> bool:
    """Return True if any value differs (ignoring the source column)."""
    # Compare all columns except the last (source — always "zerodha")
    compare_len = len(new) - 1
    for i in range(compare_len):
        new_val = str(new[i]).strip()
        cur_val = str(current[i]).strip() if i < len(current) else ""
        if new_val != cur_val:
            return True
    return False


# ── Core sync logic ──────────────────────────────────────────


def _sync_one_sheet(
    client,
    spreadsheet_id: str,
    sheet_name: str,
    fields: list[str],
    broker_items: list[dict],
    transform_fn,
    synced_accounts: set[str] | None = None,
) -> dict[str, int]:
    """Sync broker data to a single sheet tab.

    Only rows belonging to *synced_accounts* are eligible for deletion.
    Rows for accounts not in *synced_accounts* are left untouched so
    that an expired session does not wipe previously-synced data.

    Returns a dict with counts: ``{updated, added, deleted}``.
    """
    source_idx = fields.index("source")
    # Determine key column indices (symbol/fund is always first, account varies)
    symbol_idx = 0
    account_idx = fields.index("account")

    # 1. Read current sheet data
    try:
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, sheet_name)
    except Exception:
        logger.warning("Sync: could not read %s, skipping", sheet_name)
        return {"updated": 0, "added": 0, "deleted": 0}

    # 2. Index existing zerodha rows: key → (row_number, current_values)
    existing: dict[tuple, tuple[int, list]] = {}
    if raw and len(raw) >= 2:
        for idx, row in enumerate(raw[1:], start=2):
            source = row[source_idx].strip().lower() if len(row) > source_idx else ""
            if source == "zerodha":
                key = _key_from_row(row, symbol_idx, account_idx)
                existing[key] = (idx, row)

    # 3. Build broker data map: key → row values
    broker_map: dict[tuple, list[str]] = {}
    for item in broker_items:
        row_vals = transform_fn(item)
        key = _key_from_row(row_vals, symbol_idx, account_idx)
        if key[0]:  # Skip entries with empty symbol
            broker_map[key] = row_vals

    # 4. Compute diff
    to_update: list[tuple[int, list[str]]] = []
    to_delete: list[int] = []
    to_append: list[list[str]] = []

    for key, (row_num, current) in existing.items():
        if key in broker_map:
            if _values_changed(current, broker_map[key]):
                to_update.append((row_num, broker_map[key]))
        elif synced_accounts is None or key[1] in synced_accounts:
            # Only delete if the row's account was actually fetched.
            # Rows for accounts not in synced_accounts are preserved
            # (e.g. when that account's token has expired).
            to_delete.append(row_num)

    for key, vals in broker_map.items():
        if key not in existing:
            to_append.append(vals)

    # 5. Apply changes (order: update → delete → append)
    if to_update:
        client.batch_update_rows(spreadsheet_id, sheet_name, to_update)
    if to_delete:
        client.batch_delete_rows(spreadsheet_id, sheet_name, to_delete)
    if to_append:
        client.batch_append_rows(spreadsheet_id, sheet_name, to_append)

    counts = {"updated": len(to_update), "added": len(to_append), "deleted": len(to_delete)}
    if any(counts.values()):
        logger.info("Sync %s: %s", sheet_name, counts)
    return counts


# ── Public API ───────────────────────────────────────────────


def sync_broker_to_sheets(
    google_id: str,
    stocks: list[dict[str, Any]],
    mf_holdings: list[dict[str, Any]],
    sips: list[dict[str, Any]],
    synced_accounts: set[str] | None = None,
) -> None:
    """Sync broker portfolio data to the user's Google Sheet.

    *synced_accounts* is the set of account names whose data was
    actually fetched.  Only rows belonging to these accounts are
    eligible for deletion — rows for other (e.g. expired-session)
    accounts are preserved.

    Runs under a per-user lock to prevent concurrent syncs.
    All errors are caught and logged — callers never need to
    handle exceptions.
    """
    lock = _get_sync_lock(google_id)
    if not lock.acquire(blocking=False):
        logger.info("Broker sync already in progress for user, skipping")
        return

    try:
        _do_sync(google_id, stocks, mf_holdings, sips, synced_accounts)
    except Exception:
        logger.exception("Broker sync failed")
    finally:
        lock.release()


def _do_sync(
    google_id: str,
    stocks: list[dict],
    mf_holdings: list[dict],
    sips: list[dict],
    synced_accounts: set[str] | None = None,
) -> None:
    """Internal sync implementation."""
    t0 = time.monotonic()

    # Get user's Google credentials and spreadsheet ID
    from .fetchers import get_google_creds_dict
    from .firebase_store import get_user

    user = get_user(google_id)
    if not user:
        logger.info("Broker sync: user not found")
        return

    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = get_google_creds_dict({**user, "google_id": google_id})
    if not spreadsheet_id or not creds_dict:
        logger.info("Broker sync: no spreadsheet or credentials")
        return

    from .api.google_auth import credentials_from_dict, persist_refreshed_credentials
    from .api.google_sheets_client import GoogleSheetsClient

    creds = credentials_from_dict(creds_dict)
    client = GoogleSheetsClient(user_credentials=creds)

    # Ensure sheet tabs have the Source column header
    tabs_to_check = [
        (SHEET_CONFIGS[st]["sheet_name"], SHEET_CONFIGS[st]["headers"]) for st in ("stocks", "mutual_funds", "sips")
    ]
    try:
        client.ensure_sheet_tabs(spreadsheet_id, tabs_to_check)
    except Exception:
        logger.warning("Broker sync: could not ensure sheet tabs, continuing anyway")

    # Sync each data type
    sync_configs = [
        ("stocks", stocks, _stock_to_row),
        ("mutual_funds", mf_holdings, _mf_to_row),
        ("sips", sips, _sip_to_row),
    ]

    for sheet_type, items, transform in sync_configs:
        cfg = SHEET_CONFIGS[sheet_type]
        try:
            _sync_one_sheet(
                client,
                spreadsheet_id,
                cfg["sheet_name"],
                cfg["fields"],
                items,
                transform,
                synced_accounts,
            )
        except Exception:
            logger.exception("Broker sync failed for %s", sheet_type)

    # Persist any refreshed Google credentials
    try:
        persist_refreshed_credentials(creds, google_id)
    except Exception:
        logger.debug("Could not persist refreshed credentials after sync")

    logger.info("Broker sync completed in %.1fs", time.monotonic() - t0)


def start_broker_sync_thread(
    google_id: str,
    stocks: list[dict],
    mf_holdings: list[dict],
    sips: list[dict],
    synced_accounts: set[str] | None = None,
) -> None:
    """Fire a background daemon thread for broker → sheets sync."""
    threading.Thread(
        target=sync_broker_to_sheets,
        args=(google_id, stocks, mf_holdings, sips, synced_accounts),
        name=f"BrokerSync-{google_id[:8]}",
        daemon=True,
    ).start()


def delete_account_from_sheets(google_id: str, account_name: str) -> None:
    """Delete all zerodha-sourced rows for *account_name* from the user's sheets.

    Called when the user explicitly removes a broker account from settings.
    Runs synchronously; errors are logged and swallowed.
    """
    from .fetchers import get_google_creds_dict
    from .firebase_store import get_user

    user = get_user(google_id)
    if not user:
        return

    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = get_google_creds_dict({**user, "google_id": google_id})
    if not spreadsheet_id or not creds_dict:
        return

    from .api.google_auth import credentials_from_dict, persist_refreshed_credentials
    from .api.google_sheets_client import GoogleSheetsClient

    creds = credentials_from_dict(creds_dict)
    client = GoogleSheetsClient(user_credentials=creds)

    for sheet_type in ("stocks", "mutual_funds", "sips"):
        cfg = SHEET_CONFIGS[sheet_type]
        fields = cfg["fields"]
        sheet_name = cfg["sheet_name"]
        source_idx = fields.index("source")
        account_idx = fields.index("account")

        try:
            raw = client.fetch_sheet_data_until_blank(spreadsheet_id, sheet_name)
        except Exception:
            logger.warning("delete_account_from_sheets: could not read %s", sheet_name)
            continue

        rows_to_delete: list[int] = []
        if raw and len(raw) >= 2:
            for idx, row in enumerate(raw[1:], start=2):
                source = row[source_idx].strip().lower() if len(row) > source_idx else ""
                acct = row[account_idx].strip() if len(row) > account_idx else ""
                if source == "zerodha" and acct == account_name:
                    rows_to_delete.append(idx)

        if rows_to_delete:
            try:
                client.batch_delete_rows(spreadsheet_id, sheet_name, rows_to_delete)
                logger.info("Deleted %d rows for account %s from %s", len(rows_to_delete), account_name, sheet_name)
            except Exception:
                logger.exception("Failed to delete rows for account %s from %s", account_name, sheet_name)

    try:
        persist_refreshed_credentials(creds, google_id)
    except Exception:
        logger.debug("Could not persist refreshed credentials after account deletion")
