"""Service wiring, per-user lifecycle, and status helpers."""

import threading
from typing import Any

from cachetools import LRUCache

from .api import AuthenticationManager, HoldingsService, SIPService, ZerodhaAPIClient
from .logging_config import logger
from .utils import SessionManager, StateManager, format_timestamp, is_market_open_ist

# Core service singletons
session_manager = SessionManager()
state_manager = StateManager()
auth_manager = AuthenticationManager(session_manager)
holdings_service = HoldingsService()
sip_service = SIPService()
zerodha_client = ZerodhaAPIClient(auth_manager, holdings_service, sip_service)

# User lifecycle tracking — bounded LRU to prevent unbounded growth.
_loaded_users_lock = threading.Lock()
_loaded_users: LRUCache[str, None] = LRUCache(maxsize=1000)


def ensure_user_loaded(google_id: str, *, force: bool = False) -> None:
    """Load user's Zerodha sessions from Firestore (idempotent).

    Args:
        google_id: The user's Google ID.
        force: When True, re-run even if the user was previously loaded.
               Use after PIN verification to load Zerodha sessions that
               were skipped on the initial PIN-less page load.
    """
    if not google_id:
        return
    with _loaded_users_lock:
        if not force and google_id in _loaded_users:
            logger.debug("ensure_user_loaded: already loaded")
            return
        _loaded_users[google_id] = None

    logger.info("ensure_user_loaded: loading, force=%s", force)
    session_manager.load_user(google_id)

    # Only fetch data if PIN is in server memory — no data fetching
    # before PIN verification (global market data included).
    if not session_manager.get_pin(google_id):
        logger.info("ensure_user_loaded: no PIN in memory, skipping background fetch")
        return

    from .fetchers import run_background_fetch

    run_background_fetch(google_id=google_id)


def get_user_accounts(google_id: str) -> list[dict[str, str]]:
    """Return the list of Zerodha accounts for *google_id*, or [] if unavailable."""
    if not google_id:
        return []
    pin = session_manager.get_pin(google_id)
    if not pin:
        return []
    try:
        from .firebase_store import get_zerodha_accounts

        return get_zerodha_accounts(google_id, pin)
    except Exception:
        logger.exception("Failed to fetch Zerodha accounts")
        return []


def get_authenticated_accounts(google_id: str) -> list[dict[str, str]]:
    """Return only the Zerodha accounts with a valid (non-expired) session."""
    return [acc for acc in get_user_accounts(google_id) if session_manager.is_valid(google_id, acc["name"])]


def _build_status_response(google_id: str | None = None) -> dict[str, Any]:
    """Build status dict for the API, scoped to *google_id* if provided."""
    accounts = get_user_accounts(google_id) if google_id else []

    authenticated, unauthenticated, login_urls, session_validity = [], [], {}, {}
    for acc in accounts:
        name = acc["name"]
        if session_manager.is_valid(google_id, name):
            authenticated.append(name)
            session_validity[name] = True
        else:
            try:
                from kiteconnect import KiteConnect

                url = KiteConnect(api_key=acc["api_key"]).login_url()
            except Exception:
                url = None
            unauthenticated.append({"name": name, "login_url": url})
            login_urls[name] = url
            session_validity[name] = False

    portfolio_state = state_manager.get_portfolio_state(google_id) if google_id else None
    portfolio_updated = state_manager.get_portfolio_last_updated(google_id) if google_id else None
    user_error = state_manager.get_user_last_error(google_id) if google_id else None
    manual_ltp_state = state_manager.get_manual_ltp_state(google_id) if google_id else None
    manual_ltp_updated = state_manager.get_manual_ltp_last_updated(google_id) if google_id else None
    sheets_state = state_manager.get_sheets_state(google_id) if google_id else None
    sheets_updated = state_manager.get_sheets_last_updated(google_id) if google_id else None
    exposure_updated = state_manager.get_exposure_last_updated(google_id) if google_id else None

    response = {
        "last_error": user_error or state_manager.last_error,
        "market_open": is_market_open_ist(),
        "has_zerodha_accounts": len(accounts) > 0,
        "authenticated_accounts": authenticated,
        "unauthenticated_accounts": unauthenticated,
        "session_validity": session_validity,
        "login_urls": login_urls,
        "portfolio_state": portfolio_state,
        "portfolio_last_updated": format_timestamp(portfolio_updated),
        "manual_ltp_state": manual_ltp_state,
        "manual_ltp_last_updated": format_timestamp(manual_ltp_updated),
        "sheets_state": sheets_state,
        "sheets_last_updated": format_timestamp(sheets_updated),
        "exposure_last_updated": format_timestamp(exposure_updated),
    }
    for st in StateManager.GLOBAL_STATE_TYPES:
        response[f"{st}_state"] = getattr(state_manager, f"{st}_state")
        response[f"{st}_last_updated"] = format_timestamp(getattr(state_manager, f"{st}_last_updated"))
    return response


# ---------------------------------------------------------------------------
# Portfolio data builders (moved from routes.py)
# ---------------------------------------------------------------------------


def _enrich_manual_entries_with_ltp(entries: list) -> None:
    """Apply cached LTPs to manual entries (read-only, never fetches)."""
    from .cache import manual_ltp_cache

    symbols = list({e["tradingsymbol"] for e in entries if e["tradingsymbol"]})
    if not symbols:
        return

    enriched = 0
    for sym in symbols:
        cached = manual_ltp_cache.get(sym)
        if not cached or not cached.get("ltp"):
            continue
        for entry in entries:
            if entry["tradingsymbol"] == sym:
                entry["last_price"] = cached["ltp"]
                entry["day_change"] = cached.get("change", 0)
                entry["day_change_percentage"] = cached.get("pChange", 0)
                enriched += 1

    if enriched:
        logger.debug("Manual LTP enrichment: %d/%d symbols from cache", enriched, len(symbols))
    else:
        logger.debug("Manual LTP enrichment: %d symbols, all uncached", len(symbols))


def _build_stocks_data(user) -> list:
    """Build merged broker + manual stocks list with live LTPs.

    When broker is connected (live data in cache), broker entries take
    precedence and zerodha-sourced sheet rows are skipped.  When broker
    is offline, persisted zerodha entries from sheets serve as fallback.
    """
    from .cache import portfolio_cache
    from .fetchers import _fetch_manual_entries

    google_id = user["google_id"]
    user_data = portfolio_cache.get(google_id)
    connected_accounts = user_data.connected_accounts

    # Only use cached broker data when at least one broker session is live;
    # when all offline, synced sheet data is the sole source of truth.
    broker_stocks = []
    if connected_accounts:
        for s in user_data.stocks:
            s.setdefault("source", "zerodha")
            broker_stocks.append(s)
        for s in user_data.etfs:
            # Tag ETFs so the frontend can classify without ISIN/symbol heuristics.
            s.setdefault("source", "zerodha")
            s.setdefault("manual_type", "etfs")
            broker_stocks.append(s)

    sheet_entries = []
    for sheet_type in ("stocks", "etfs"):
        entries = _fetch_manual_entries(user, sheet_type)
        for m in entries:
            source = m.get("source", "manual")

            # Skip persisted zerodha rows only for accounts with a live session;
            # rows for disconnected accounts serve as fallback.
            if source == "zerodha" and m.get("account", "") in connected_accounts:
                continue

            qty = float(m.get("qty") or 0)
            avg = float(m.get("avg_price") or 0)
            sheet_entries.append(
                {
                    "tradingsymbol": (m.get("symbol") or "").upper(),
                    "quantity": qty,
                    "average_price": avg,
                    "last_price": avg,  # fallback; enriched below
                    "invested": qty * avg,
                    "exchange": m.get("exchange", "NSE"),
                    "account": m.get("account", "Manual") if source == "manual" else m.get("account", ""),
                    "day_change": 0,
                    "day_change_percentage": 0,
                    "isin": (m.get("isin") or "").strip().upper(),
                    "source": source,
                    "row_number": m.get("row_number"),
                    "manual_type": sheet_type,
                }
            )

    # Enrich sheet entries (both manual and zerodha-fallback) with LTP
    if sheet_entries:
        _enrich_manual_entries_with_ltp(sheet_entries)

    broker_stocks.extend(sheet_entries)
    return sorted(broker_stocks, key=lambda x: x.get("tradingsymbol", ""))


def _autofill_mf_nav_from_cache(fields: list[str], values: list) -> None:
    """Populate ISIN, latest NAV and NAV date from the MF market cache when the fund name matches.

    Looks up the fund name ("fund_name" field) in the in-memory mf_market_cache.
    If an exact match is found, fills in any empty isin, latest_nav and
    nav_updated_date columns so manual entries have up-to-date NAV data.

    Args:
        fields: Ordered list of field names for the mutual_funds sheet config.
        values: Mutable list of column values aligned with *fields*.
    """
    from .api.mf_market_data import mf_market_cache
    from .utils import format_date_for_sheet

    if not mf_market_cache.is_populated:
        return

    fund_name_idx = fields.index("fund_name") if "fund_name" in fields else -1
    if fund_name_idx < 0 or fund_name_idx >= len(values):
        return

    fund_name = str(values[fund_name_idx]).strip()
    isin = mf_market_cache.get_isin_for_name(fund_name)
    if not isin:
        return

    scheme = mf_market_cache.get_by_isin(isin)
    if not scheme:
        return

    # Only fill fields that are empty — never overwrite user-provided data.
    for field_key, value in [
        ("isin", scheme.isin),
        ("latest_nav", scheme.latest_nav),
        ("nav_updated_date", format_date_for_sheet(scheme.nav_updated_date)),
    ]:
        if field_key in fields:
            idx = fields.index(field_key)
            if idx < len(values) and not values[idx]:
                values[idx] = value

    logger.debug("MF cache autofill: fund_name=%s isin=%s nav=%s", fund_name, scheme.isin, scheme.latest_nav)


def _normalize_mf_names(holdings: list[dict]) -> None:
    """Replace broker/sheet fund names with canonical names from mfapi.in.

    mfapi.in names take precedence over broker-reported names.  Equality is
    established via ISIN so entries that share an ISIN always display the
    same canonical name regardless of their source.
    """
    from .api.mf_market_data import mf_market_cache

    if not mf_market_cache.is_populated:
        return

    for mf in holdings:
        isin = (mf.get("isin") or "").upper()
        if not isin:
            continue
        scheme = mf_market_cache.get_by_isin(isin)
        if scheme:
            mf["fund"] = scheme.scheme_name.upper()


def _build_mf_data(user) -> list:
    """Build merged broker + manual mutual fund holdings list.

    Zerodha-sourced sheet entries are used as fallback when broker is offline.
    """
    from .cache import portfolio_cache
    from .fetchers import _fetch_manual_entries

    google_id = user["google_id"]
    user_data = portfolio_cache.get(google_id)
    connected_accounts = user_data.connected_accounts
    broker_mf = list(user_data.mf_holdings) if connected_accounts else []

    for mf in broker_mf:
        mf.setdefault("source", "zerodha")

    entries = _fetch_manual_entries(user, "mutual_funds")
    for m in entries:
        source = m.get("source", "manual")
        if source == "zerodha" and m.get("account", "") in connected_accounts:
            continue

        qty = float(m.get("qty") or 0)
        avg = float(m.get("avg_nav") or 0)
        # Column 0 is now "ISIN" (renamed from "Fund") — stores ISIN / trading symbol.
        isin = (m.get("isin") or "").upper()
        fund_name = m.get("fund_name") or isin
        # Use stored latest NAV if available, otherwise fall back to avg NAV.
        latest_nav = float(m.get("latest_nav") or 0)
        nav_date = m.get("nav_updated_date") or None
        broker_mf.append(
            {
                "fund": fund_name,
                "isin": isin,
                "quantity": qty,
                "average_price": avg,
                "last_price": latest_nav if latest_nav else avg,
                "invested": qty * avg,
                "account": m.get("account", "Manual") if source == "manual" else m.get("account", ""),
                "last_price_date": nav_date,
                "source": source,
                "row_number": m.get("row_number"),
            }
        )
    _normalize_mf_names(broker_mf)
    return sorted(broker_mf, key=lambda x: x.get("fund", ""))


def _build_sips_data(user) -> list:
    """Build merged broker + manual SIPs list.

    Zerodha-sourced sheet entries are used as fallback when broker is offline.
    """
    from .cache import portfolio_cache
    from .fetchers import _fetch_manual_entries

    google_id = user["google_id"]
    user_data = portfolio_cache.get(google_id)
    connected_accounts = user_data.connected_accounts
    broker_sips = list(user_data.sips) if connected_accounts else []

    for sip in broker_sips:
        sip.setdefault("source", "zerodha")

    entries = _fetch_manual_entries(user, "sips")
    for m in entries:
        source = m.get("source", "manual")
        if source == "zerodha" and m.get("account", "") in connected_accounts:
            continue

        fund_id = (m.get("fund") or "").upper()
        fund_display = m.get("fund_name") or fund_id
        broker_sips.append(
            {
                "fund": fund_display,
                "tradingsymbol": fund_id,
                "instalment_amount": float(m.get("amount") or 0),
                "frequency": m.get("frequency", "MONTHLY"),
                "instalments": int(m.get("installments") or -1),
                "completed_instalments": int(m.get("completed") or 0),
                "status": (m.get("status") or "ACTIVE").upper(),
                "next_instalment": m.get("next_due", ""),
                "account": m.get("account", "Manual") if source == "manual" else m.get("account", ""),
                "source": source,
                "row_number": m.get("row_number"),
            }
        )
    return sorted(broker_sips, key=lambda x: x.get("status", ""))


def _build_gold_data(user) -> list:
    """Build enriched physical gold holdings list."""
    from .api.physical_gold import enrich_holdings_with_prices
    from .cache import market_cache
    from .fetchers import _fetch_user_sheets_data

    gold, _ = _fetch_user_sheets_data(user)
    if gold is not None:
        enriched = enrich_holdings_with_prices(gold, market_cache.gold_prices)
        return sorted(enriched, key=lambda x: x.get("date", ""))
    return []


def _build_fd_data(user) -> list:
    """Build fixed deposits list."""
    from .fetchers import _fetch_user_sheets_data

    _, deposits = _fetch_user_sheets_data(user)
    if deposits is not None:
        return sorted(deposits, key=lambda x: x.get("deposited_on", ""))
    return []


def _serialise_exposure(result: Any) -> dict:
    """Convert an ExposureResult to a JSON-serialisable dict."""
    return {
        "has_data": True,
        "total_portfolio_value": result.total_portfolio_value,
        "sector_totals": result.sector_totals,
        "fund_totals": result.fund_totals,
        "companies": [
            {
                "company_name": c.company_name,
                "instrument_type": c.instrument_type,
                "sector": c.sector or "Unknown",
                "holding_amount": round(c.holding_amount, 2),
                "percentage_of_portfolio": round(c.percentage_of_portfolio, 4),
                "funds": c.funds,
            }
            for c in result.companies
        ],
    }


def _refresh_single_sheet_cache(client: Any, spreadsheet_id: str, google_id: str, sheet_type: str) -> None:
    """Re-fetch and re-cache a single sheet type after a CRUD mutation.

    Reads only the affected sheet from Google Sheets (not all 6),
    preserving cache entries for every other type.
    """
    from .api.google_sheets_client import is_blank_row
    from .api.user_sheets import SHEET_CONFIGS
    from .cache import user_sheets_cache

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return

    try:
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"])
    except Exception:
        logger.exception("Error re-reading %s after CRUD", sheet_type)
        user_sheets_cache.invalidate(google_id)
        return

    if sheet_type == "physical_gold":
        from .api.google_sheets_client import PhysicalGoldService

        svc = PhysicalGoldService(client)
        parsed = svc._parse_batch_data(raw)
        user_sheets_cache.put(google_id, physical_gold=parsed)

    elif sheet_type == "fixed_deposits":
        from .api.fixed_deposits import calculate_current_value
        from .api.google_sheets_client import FixedDepositsService

        svc = FixedDepositsService(client)
        parsed = calculate_current_value(svc._parse_batch_data(raw))
        user_sheets_cache.put(google_id, fixed_deposits=parsed)

    else:
        # Manual types: stocks, etfs, mutual_funds, sips
        rows: list[dict[str, Any]] = []
        if raw and len(raw) >= 2:
            fields = cfg["fields"]
            for idx, row in enumerate(raw[1:], start=2):
                if is_blank_row(row):
                    break
                entry: dict[str, Any] = {"row_number": idx}
                for fi, fname in enumerate(fields):
                    entry[fname] = row[fi] if fi < len(row) else ""
                # Default empty/missing source to "manual"
                if not entry.get("source"):
                    entry["source"] = "manual"
                rows.append(entry)
        user_sheets_cache.put_manual(google_id, sheet_type, rows)


# Mapping: sheet_type → frontend data key for CRUD response
_SHEET_TYPE_DATA_KEY = {
    "stocks": "stocks",
    "etfs": "stocks",  # ETFs merge into the stocks table
    "mutual_funds": "mfHoldings",
    "sips": "sips",
    "physical_gold": "physicalGold",
    "fixed_deposits": "fixedDeposits",
}


def _build_data_for_type(user, sheet_type: str) -> dict:
    """Build and return ``{data_key: [rows]}`` for a single sheet type.

    Called after a CRUD mutation so the response can carry the refreshed
    dataset and the frontend can skip a full ``/api/all_data`` call.
    """
    data_key = _SHEET_TYPE_DATA_KEY.get(sheet_type)
    if not data_key:
        return {}

    builders = {
        "stocks": _build_stocks_data,
        "mfHoldings": _build_mf_data,
        "sips": _build_sips_data,
        "physicalGold": _build_gold_data,
        "fixedDeposits": _build_fd_data,
    }
    builder = builders.get(data_key)
    if not builder:  # pragma: no cover – all valid data_keys have builders
        return {}

    try:
        return {data_key: builder(user)}
    except Exception:
        logger.exception("Error building data for %s after CRUD", sheet_type)
        return {}
