"""CAS (CAMS/KFintech) PDF processing and transaction storage."""

import threading
import time
from typing import Any

from .api.google_sheets_client import is_blank_row
from .api.user_sheets import SheetConfig
from .logging_config import logger

# ---------------------------------------------------------------------------
# In-memory CAS transaction storage (per-user)
# ---------------------------------------------------------------------------

_cas_transactions_lock = threading.Lock()
_cas_transactions: dict[str, list[dict]] = {}
_cas_scheme_summaries: dict[str, list[dict]] = {}


def store_transactions(
    google_id: str,
    account: str,
    transactions: list[dict],
    scheme_summaries: list[dict] | None = None,
) -> list[dict]:
    """Store CAS transactions and scheme summaries.

    Replaces existing entries for this account.
    Returns the tagged transactions (with account field set).
    """
    with _cas_transactions_lock:
        existing = _cas_transactions.get(google_id, [])
        kept = [t for t in existing if t.get("account") != account]
        tagged = [{"account": account, **t} for t in transactions]
        _cas_transactions[google_id] = kept + tagged

        if scheme_summaries is not None:
            existing_schemes = _cas_scheme_summaries.get(google_id, [])
            kept_schemes = [s for s in existing_schemes if s.get("account") != account]
            tagged_schemes = [{"account": account, **s} for s in scheme_summaries]
            _cas_scheme_summaries[google_id] = kept_schemes + tagged_schemes

    return tagged


def get_transactions(google_id: str) -> list[dict]:
    """Retrieve stored CAS transactions for a user."""
    with _cas_transactions_lock:
        return list(_cas_transactions.get(google_id, []))


def get_scheme_summaries(google_id: str) -> list[dict]:
    """Retrieve stored CAS scheme summaries for a user."""
    with _cas_transactions_lock:
        return list(_cas_scheme_summaries.get(google_id, []))


def has_cached_transactions(google_id: str) -> bool:
    """Check if in-memory transaction data exists for a user."""
    with _cas_transactions_lock:
        return bool(_cas_transactions.get(google_id))


def clear_transactions(google_id: str) -> None:
    """Clear in-memory transaction cache for a user (force reload on next access)."""
    with _cas_transactions_lock:
        _cas_transactions.pop(google_id, None)
        _cas_scheme_summaries.pop(google_id, None)


def ensure_transactions_loaded(google_id: str) -> None:
    """Ensure transaction data is in memory, loading from sheet if needed."""
    if not has_cached_transactions(google_id):
        load_transactions_from_sheet(google_id)


# ---------------------------------------------------------------------------
# Google Sheets sync (background, non-blocking)
# ---------------------------------------------------------------------------

_TXN_SYNC_LOCKS: dict[str, threading.Lock] = {}
_TXN_SYNC_LOCKS_GUARD = threading.Lock()
_TXN_SYNC_LOCKS_MAX = 256


def _get_sync_lock(google_id: str) -> threading.Lock:
    """Get or create a per-user sync lock (bounded to avoid leaks)."""
    with _TXN_SYNC_LOCKS_GUARD:
        lock = _TXN_SYNC_LOCKS.get(google_id)
        if lock is None:
            if len(_TXN_SYNC_LOCKS) >= _TXN_SYNC_LOCKS_MAX:
                _TXN_SYNC_LOCKS.clear()
            lock = threading.Lock()
            _TXN_SYNC_LOCKS[google_id] = lock
        return lock


def _txn_to_row(t: dict) -> list[Any]:
    """Convert a transaction dict to a sheet row."""

    def _num(key: str) -> str:
        v = t.get(key)
        return str(v) if v is not None else ""

    return [
        t.get("isin") or "",
        t.get("fund_name") or "",
        t.get("date") or "",
        t.get("type") or "",
        _num("amount"),
        _num("units"),
        _num("nav"),
        _num("balance"),
        t.get("account") or "",
    ]


def sync_transactions_to_sheet(
    google_id: str,
    account: str,
    transactions: list[dict],
) -> None:
    """Sync CAS transactions for *account* to the user's Google Sheet.

    Deletes existing rows for this account, then appends new ones.
    Runs under a per-user lock; skips if already in progress.
    All errors are caught and logged — never propagated.
    """
    lock = _get_sync_lock(google_id)
    if not lock.acquire(blocking=False):
        logger.info("Transaction sync already in progress for user, skipping")
        return

    try:
        _do_txn_sync(google_id, account, transactions)
    except Exception:
        logger.exception("Transaction sync failed for account=%s", account)
    finally:
        lock.release()


def _do_txn_sync(
    google_id: str,
    account: str,
    transactions: list[dict],
) -> None:
    """Internal sync: delete stale rows for account, append new ones."""
    t0 = time.monotonic()

    from .api.google_auth import credentials_from_dict
    from .api.google_sheets_client import GoogleSheetsClient
    from .api.user_sheets import SHEET_CONFIGS
    from .fetchers import get_google_creds_dict
    from .firebase_store import get_user

    user = get_user(google_id)
    if not user:
        logger.info("Txn sync: user not found")
        return

    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = get_google_creds_dict({**user, "google_id": google_id})
    if not spreadsheet_id or not creds_dict:
        logger.info("Txn sync: no spreadsheet or credentials")
        return

    creds = credentials_from_dict(creds_dict)
    client = GoogleSheetsClient(user_credentials=creds)

    cfg = SHEET_CONFIGS["transactions"]
    client.ensure_sheet_tab(spreadsheet_id, cfg["sheet_name"], cfg["headers"])

    # Delete existing rows for this account
    raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"], max_rows=10000)
    rows_to_delete = _find_stale_txn_rows(raw, cfg, account)
    if rows_to_delete:
        client.batch_delete_rows(spreadsheet_id, cfg["sheet_name"], rows_to_delete)
        logger.info(
            "Txn sync: deleted %d stale rows for account=%s",
            len(rows_to_delete),
            account,
        )

    # Append new rows
    new_rows = [_txn_to_row(t) for t in transactions]
    if new_rows:
        client.batch_append_rows(spreadsheet_id, cfg["sheet_name"], new_rows)

    logger.info(
        "Txn sync: appended %d rows for account=%s (%.1fs)",
        len(new_rows),
        account,
        time.monotonic() - t0,
    )


def _find_stale_txn_rows(
    raw: list[list[str]] | None,
    cfg: SheetConfig,
    account: str,
) -> list[int]:
    """Find row indices of existing transaction rows for the account."""
    rows_to_delete: list[int] = []
    if not raw or len(raw) < 2:
        return rows_to_delete

    fields = cfg["fields"]
    account_idx = fields.index("account") if "account" in fields else -1
    if account_idx < 0:
        return rows_to_delete

    for idx, row in enumerate(raw[1:], start=2):
        if is_blank_row(row):
            break
        row_account = row[account_idx].strip() if account_idx < len(row) else ""
        if row_account == account:
            rows_to_delete.append(idx)

    return rows_to_delete


def start_txn_sync_thread(
    google_id: str,
    account: str,
    transactions: list[dict],
) -> None:
    """Fire a background daemon thread for transaction → sheet sync."""
    threading.Thread(
        target=sync_transactions_to_sheet,
        args=(google_id, account, transactions),
        name=f"TxnSync-{google_id[:8]}",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Load transactions from Google Sheets (cold-start hydration)
# ---------------------------------------------------------------------------


def load_transactions_from_sheet(google_id: str) -> bool:
    """Load all CAS transactions from the user's Google Sheet into memory.

    Called when the transactions page is loaded but the in-memory cache
    is empty (e.g. after server restart).

    Returns True if data was loaded, False otherwise.
    """
    from .api.google_auth import credentials_from_dict
    from .api.google_sheets_client import GoogleSheetsClient
    from .api.user_sheets import SHEET_CONFIGS
    from .fetchers import get_google_creds_dict
    from .firebase_store import get_user

    user = get_user(google_id)
    if not user:
        return False

    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = get_google_creds_dict({**user, "google_id": google_id})
    if not spreadsheet_id or not creds_dict:
        return False

    creds = credentials_from_dict(creds_dict)
    client = GoogleSheetsClient(user_credentials=creds)
    cfg = SHEET_CONFIGS["transactions"]

    try:
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"], max_rows=10000)
    except Exception:
        logger.debug("Txn load: Transactions sheet not found or empty")
        return False

    if not raw or len(raw) < 2:
        return False

    fields = cfg["fields"]
    numeric_fields = frozenset(("amount", "units", "nav", "balance"))
    transactions_by_account: dict[str, list[dict]] = {}

    for row in raw[1:]:
        if is_blank_row(row):
            break
        entry: dict[str, Any] = {}
        for fi, fname in enumerate(fields):
            val = row[fi] if fi < len(row) else ""
            if fname in numeric_fields:
                try:
                    entry[fname] = float(val) if val else None
                except (ValueError, TypeError):
                    entry[fname] = None
            else:
                entry[fname] = val
        account = (entry.get("account") or "").strip()
        if account:
            transactions_by_account.setdefault(account, []).append(entry)

    if not transactions_by_account:
        return False

    # Load scheme summaries from MF holdings sheet to support analytics
    scheme_summaries = _load_scheme_summaries_from_sheet(client, spreadsheet_id)

    with _cas_transactions_lock:
        all_txns: list[dict] = []
        for txns in transactions_by_account.values():
            all_txns.extend(txns)
        _cas_transactions[google_id] = all_txns
        if scheme_summaries:
            _cas_scheme_summaries[google_id] = scheme_summaries

    logger.info("Txn load: loaded %d transactions from sheet", len(all_txns))
    return True


def _load_scheme_summaries_from_sheet(
    client: Any,
    spreadsheet_id: str,
) -> list[dict]:
    """Load scheme summaries from the MutualFunds sheet (CAMS rows only)."""
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS["mutual_funds"]
    try:
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"])
    except Exception:
        return []

    if not raw or len(raw) < 2:
        return []

    fields = cfg["fields"]
    summaries: list[dict] = []
    for row in raw[1:]:
        if is_blank_row(row):
            break
        entry: dict[str, Any] = {}
        for fi, fname in enumerate(fields):
            entry[fname] = row[fi] if fi < len(row) else ""
        source = (entry.get("source") or "").strip()
        if source != "cams":
            continue
        isin = (entry.get("isin") or "").strip()
        if not isin:
            continue
        try:
            qty = float(entry.get("qty") or 0)
            avg_nav = float(entry.get("avg_nav") or 0)
            latest_nav = float(entry.get("latest_nav") or 0)
        except (ValueError, TypeError):
            continue
        summaries.append(
            {
                "isin": isin,
                "fund_name": (entry.get("fund_name") or "").strip(),
                "units": qty,
                "avg_nav": avg_nav,
                "cost": qty * avg_nav,
                "latest_nav": latest_nav,
                "account": (entry.get("account") or "").strip(),
            }
        )
    return summaries


# Types excluded from transaction views
_EXCLUDED_TYPES = frozenset(("STAMP_DUTY_TAX", "STT_TAX"))


def _is_purchase(t: dict) -> bool:
    tx_type = t.get("type") or ""
    return "PURCHASE" in tx_type or "SWITCH_IN" in tx_type


def _is_redemption(t: dict) -> bool:
    tx_type = t.get("type") or ""
    return "REDEMPTION" in tx_type or "SWITCH_OUT" in tx_type


def _compute_summary(transactions: list[dict], schemes: list[dict]) -> dict[str, Any]:
    """Compute summary card data."""
    total_purchases = sum(abs(t.get("amount") or 0) for t in transactions if _is_purchase(t))
    total_redeemed = sum(abs(t.get("amount") or 0) for t in transactions if _is_redemption(t))
    total_current_invested = (
        sum(s.get("cost") or 0 for s in schemes) if schemes else _compute_remaining_cost_basis(transactions)
    )
    unique_funds = len({t.get("isin") for t in transactions if t.get("isin")})
    return {
        "total_purchases": round(total_purchases, 2),
        "total_redeemed": round(total_redeemed, 2),
        "total_current_invested": round(total_current_invested, 2),
        "transaction_count": len(transactions),
        "unique_funds": unique_funds,
    }


def _compute_remaining_cost_basis(transactions: list[dict]) -> float:
    """Average-cost method to compute remaining invested amount."""
    by_isin: dict[str, list[dict]] = {}
    for t in transactions:
        isin = t.get("isin")
        if isin:
            by_isin.setdefault(isin, []).append(t)

    total = 0.0
    for txns in by_isin.values():
        txns.sort(key=lambda x: x.get("date") or "")
        avg_cost_per_unit = 0.0
        holding_units = 0.0
        cost_basis = 0.0

        for t in txns:
            amount = abs(t.get("amount") or 0)
            units = abs(t.get("units") or 0)

            if _is_purchase(t):
                if units > 0:
                    cost_basis += amount
                    holding_units += units
                    avg_cost_per_unit = cost_basis / holding_units if holding_units > 0 else 0
            elif _is_redemption(t):
                if units > 0:
                    cost_basis -= avg_cost_per_unit * units
                    holding_units -= units

        total += max(0.0, cost_basis)
    return total


def _compute_period(transactions: list[dict]) -> dict[str, Any]:
    """Compute date range and duration."""
    dates = sorted(d for t in transactions if (d := t.get("date")))
    if not dates:
        return {}
    first = dates[0]
    last = dates[-1]

    # Parse YYYY-MM-DD
    fy, fm = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    total_months = (ly - fy) * 12 + (lm - fm)
    return {
        "first_date": first,
        "last_date": last,
        "duration_years": total_months // 12,
        "duration_months": total_months % 12,
    }


def _attach_fifo_pnl(transactions: list[dict]) -> None:
    """Attach FIFO-based P&L to each sell transaction in-place.

    Adds ``pl_amount`` and ``pl_pct`` fields to redemption transactions.
    Each account's FIFO queue is tracked independently.
    """
    by_acct_fund: dict[str, list[dict]] = {}
    sorted_txns = sorted(transactions, key=lambda t: t.get("date") or "")
    for t in sorted_txns:
        isin = t.get("isin")
        if isin:
            acct = t.get("account") or ""
            key = f"{acct}|{isin}"
            by_acct_fund.setdefault(key, []).append(t)

    for _group_key, txns in by_acct_fund.items():
        queue: list[dict[str, float]] = []
        for t in txns:
            units = t.get("units") or 0
            nav = t.get("nav") or 0
            if _is_purchase(t) and units > 0 and nav > 0:
                queue.append({"units": float(units), "nav": float(nav)})
            elif _is_redemption(t) and units:
                remaining = abs(float(units))
                cost_basis = 0.0
                while remaining > 0 and queue:
                    lot = queue[0]
                    take = min(remaining, lot["units"])
                    cost_basis += take * lot["nav"]
                    lot["units"] -= take
                    remaining -= take
                    if lot["units"] <= 0.0001:
                        queue.pop(0)
                if remaining <= 0.0001 and cost_basis > 0:
                    sell_amt = abs(t.get("amount") or 0)
                    pl = sell_amt - cost_basis
                    t["pl_amount"] = round(pl, 2)
                    t["pl_pct"] = round(pl / cost_basis * 100, 1)


def _compute_monthly_buy_sell(
    transactions: list[dict],
) -> list[dict[str, Any]]:
    """Aggregate buy/sell amounts by month."""
    monthly: dict[str, dict[str, float]] = {}
    for t in transactions:
        month = (t.get("date") or "")[:7]
        if len(month) < 7:
            continue
        if month not in monthly:
            monthly[month] = {"buy": 0.0, "sell": 0.0}
        amt = abs(t.get("amount") or 0)
        if _is_purchase(t):
            monthly[month]["buy"] += amt
        elif _is_redemption(t):
            monthly[month]["sell"] += amt

    return [{"month": m, "buy": round(d["buy"], 2), "sell": round(d["sell"], 2)} for m, d in sorted(monthly.items())]


def _compute_cumulative_timeline(
    transactions: list[dict],
) -> list[dict[str, Any]]:
    """Compute cumulative purchase amount over time."""
    purchases = sorted(
        (t for t in transactions if _is_purchase(t)),
        key=lambda t: t.get("date") or "",
    )
    if not purchases:
        return []

    cumulative = 0.0
    by_date: dict[str, float] = {}
    for t in purchases:
        cumulative += abs(t.get("amount") or 0)
        by_date[t.get("date") or ""] = cumulative

    return [{"date": d, "value": round(v, 2)} for d, v in sorted(by_date.items())]


def _compute_heatmap(transactions: list[dict]) -> list[dict[str, Any]]:
    """Monthly purchase count for SIP heatmap."""
    by_month: dict[str, int] = {}
    for t in transactions:
        if not _is_purchase(t):
            continue
        month = (t.get("date") or "")[:7]
        if len(month) >= 7:
            by_month[month] = by_month.get(month, 0) + 1

    return [{"month": m, "count": c} for m, c in sorted(by_month.items())]


def get_transaction_data(
    google_id: str,
    page: int | None = None,
    per_page: int = 50,
    account: str | None = None,
) -> dict[str, Any]:
    """Build the enriched transaction response payload.

    Lazily loads data from the Google Sheet if the in-memory cache
    is empty (e.g. after a server restart).

    Returns precomputed summary, period, chart data, and FIFO cost map
    so the frontend only handles rendering.
    """
    ensure_transactions_loaded(google_id)

    all_txns = get_transactions(google_id)
    transactions = [t for t in all_txns if t.get("type") not in _EXCLUDED_TYPES]
    schemes = get_scheme_summaries(google_id)

    # Apply account filter
    if account:
        transactions = [t for t in transactions if t.get("account") == account]
        schemes = [s for s in schemes if s.get("account") == account]

    if not transactions:
        return {
            "transactions": [],
            "schemes": [],
            "has_data": False,
            "total": 0,
        }

    total = len(transactions)

    # Precompute all analytics from the full (account-filtered) set
    summary = _compute_summary(transactions, schemes)
    period = _compute_period(transactions)
    _attach_fifo_pnl(transactions)
    monthly_buy_sell = _compute_monthly_buy_sell(transactions)
    cumulative_timeline = _compute_cumulative_timeline(transactions)
    heatmap = _compute_heatmap(transactions)

    # Collect unique accounts for the filter dropdown
    accounts = sorted({t.get("account") for t in all_txns if t.get("account")})

    base: dict[str, Any] = {
        "transactions": transactions,
        "schemes": schemes,
        "has_data": True,
        "total": total,
        "accounts": accounts,
        "summary": summary,
        "period": period,
        "monthly_buy_sell": monthly_buy_sell,
        "cumulative_timeline": cumulative_timeline,
        "heatmap": heatmap,
    }

    if page is not None:
        page = max(page, 1)
        per_page = min(per_page, 200)
        start = (page - 1) * per_page
        base["transactions"] = transactions[start : start + per_page]
        base["page"] = page
        base["per_page"] = per_page
        base["total_pages"] = (total + per_page - 1) // per_page

    return base


def process_upload(file_bytes: bytes, password: str) -> dict[str, Any]:
    """Parse a CAS PDF and return serialised result.

    Raises ValueError for invalid input or empty results.
    """
    from .api.cas_parser import parse_cas_pdf, serialise_parse_result

    result = parse_cas_pdf(file_bytes, password)
    if not result.schemes:
        raise ValueError("No mutual fund schemes found in the PDF.")
    return serialise_parse_result(result)


def confirm_import(
    client: Any,
    spreadsheet_id: str,
    google_id: str,
    account: str,
    schemes: list[dict],
    user: dict[str, Any],
    add_to_portfolio: bool = True,
    add_transactions: bool = True,
) -> dict[str, Any]:
    """Save verified CAS data to Google Sheets and update caches.

    Re-upload logic:
      - All CAMS rows for this account are deleted first, then replaced.
      - Only rows with source="cams" for the matching account are removed.
      - Rows from other sources (manual, zerodha, etc.) are untouched.

    add_to_portfolio: write holdings to the mutual_funds sheet.
    add_transactions: write transaction history to the transactions sheet/cache.

    Returns result dict with status, counts, and optionally refreshed data.
    """
    from .api.mf_market_data import mf_market_cache
    from .api.user_sheets import SHEET_CONFIGS
    from .services import _build_data_for_type, _refresh_single_sheet_cache

    added = 0
    rows_to_delete: list[int] = []
    cfg = SHEET_CONFIGS["mutual_funds"]

    if add_to_portfolio:
        client.ensure_sheet_tab(spreadsheet_id, cfg["sheet_name"], cfg["headers"])
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"])

        rows_to_delete = _find_stale_cams_rows(raw, cfg, account)

        if rows_to_delete:
            try:
                client.batch_delete_rows(spreadsheet_id, cfg["sheet_name"], rows_to_delete)
                logger.info(
                    "CAS confirm: deleted %d stale cams rows for account=%s",
                    len(rows_to_delete),
                    account,
                )
            except Exception:
                logger.exception(
                    "Failed to delete stale cams rows for account=%s",
                    account,
                )

    new_rows, all_transactions, scheme_sums = _build_cas_rows(schemes, mf_market_cache, account)

    if add_to_portfolio:
        if new_rows:
            client.batch_append_rows(spreadsheet_id, cfg["sheet_name"], new_rows)
            added = len(new_rows)
        _refresh_single_sheet_cache(client, spreadsheet_id, google_id, "mutual_funds")

    if add_transactions and all_transactions:
        # Hydrate cache from sheet first so other accounts' data is
        # preserved (handles server-restart → import scenario).
        ensure_transactions_loaded(google_id)
        tagged = store_transactions(google_id, account, all_transactions, scheme_sums)
        start_txn_sync_thread(google_id, account, tagged)

    logger.info(
        "CAS confirm: deleted=%d added=%d transactions=%d account=%s add_to_portfolio=%s add_transactions=%s",
        len(rows_to_delete),
        added,
        len(all_transactions),
        account,
        add_to_portfolio,
        add_transactions,
    )

    refreshed = _build_data_for_type(user, "mutual_funds") if add_to_portfolio else {}
    return {
        "status": "saved",
        "added": added,
        "updated": len(rows_to_delete),
        "has_transactions": bool(all_transactions),
        **refreshed,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_stale_cams_rows(
    raw: list[list[str]] | None,
    cfg: SheetConfig,
    account: str,
) -> list[int]:
    """Find row indices of existing CAMS entries for the given account."""
    rows_to_delete: list[int] = []
    if not raw or len(raw) < 2:
        return rows_to_delete

    fields = cfg["fields"]
    for idx, row in enumerate(raw[1:], start=2):
        if is_blank_row(row):
            break
        entry: dict[str, Any] = {}
        for fi, fname in enumerate(fields):
            entry[fname] = row[fi] if fi < len(row) else ""
        row_source = (entry.get("source") or "").strip()
        row_account = (entry.get("account") or "").strip()
        if row_source == "cams" and row_account == account:
            rows_to_delete.append(idx)

    return rows_to_delete


def _build_cas_rows(
    schemes: list[dict],
    mf_market_cache: Any,
    account: str,
) -> tuple[list[list[Any]], list[dict], list[dict]]:
    """Build sheet rows, transactions, and scheme summaries from CAS schemes.

    Returns (new_rows, all_transactions, scheme_summaries).
    """
    new_rows: list[list[Any]] = []
    all_transactions: list[dict] = []
    scheme_summaries: list[dict] = []

    for scheme in schemes:
        isin = (scheme.get("isin") or "").strip().upper()
        fund_name = (scheme.get("fund_name") or "").strip()
        units = float(scheme.get("units") or 0)
        avg_nav_raw = scheme.get("avg_nav")
        avg_nav = round(float(avg_nav_raw), 4) if avg_nav_raw is not None else 0.0
        transactions = scheme.get("transactions", [])

        if not isin:
            continue

        latest_nav = ""
        nav_date = ""
        cache_info = mf_market_cache.get_by_isin(isin)
        if cache_info:
            latest_nav = cache_info.latest_nav
            nav_date = cache_info.nav_updated_date
            if not fund_name:
                fund_name = cache_info.scheme_name

        for txn in transactions:
            all_transactions.append({"isin": isin, "fund_name": fund_name, **txn})

        if units <= 0:
            continue

        scheme_summaries.append(
            {
                "isin": isin,
                "fund_name": fund_name,
                "units": units,
                "avg_nav": avg_nav,
                "cost": units * avg_nav,
                "latest_nav": (float(latest_nav) if latest_nav else 0.0),
            }
        )

        new_rows.append(
            [
                isin,
                fund_name,
                str(units),
                str(avg_nav),
                account,
                "cams",
                latest_nav,
                nav_date,
            ]
        )

    return new_rows, all_transactions, scheme_summaries
