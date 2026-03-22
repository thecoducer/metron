"""Company exposure analysis: per-user LRU cache and data processor.

Builds a breakdown of which companies a user is exposed to across all
asset classes — stocks (direct), ETFs, and mutual funds — by fetching
company-level portfolio data from Zerodha's static CDN and aggregating it
against the user's current holdings values.

Pipeline
--------
1. **Gather** — collect raw (name, sector, instrument_type, amount,
   fund) entries from direct stocks (via NSE cache), MFs, and ETFs
   (via Zerodha CDN).
2. **Normalise** — expand ``Ltd.`` → ``Limited``, uppercase.  Date
   suffixes are preserved (they carry meaningful info for non-equity
   instruments like bonds and certificates of deposit).
3. **Cluster** — pass all unique normalised names to a local
   SentenceTransformer model (``all-MiniLM-L6-v2``) which groups
   remaining near-duplicates that normalisation missed (e.g.
   ``"TATA CONSULTANCY SERV LT"`` ↔ ``"TATA CONSULTANCY SERVICES
   LIMITED"``).
4. **Classify** — use BART-MNLI zero-shot classification to assign
   each company a sub-industry label (e.g. ``"Banking"``,
   ``"Insurance"``).  High-confidence labels replace CDN sectors;
   low-confidence results keep the original CDN sector.  This splits
   companies that share the same cluster and instrument type but are
   different businesses (e.g. ``"HDFC Bank"`` vs
   ``"HDFC Life Insurance"``).
5. **Display name** — pick a clean, mixed-case representative for
   each (cluster, instrument_type, sub_industry) group.
6. **Aggregate** — sum holdings per (cluster, instrument_type,
   sub_industry) and compute portfolio percentages.  Sector labels
   are also clustered.

Non-equity CDN rows (TREPS, CBLO, net-receivable entries, etc.) are
filtered out before aggregation.
"""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import requests
from cachetools import LRUCache

from ..constants import (
    COMPANY_CLASSIFICATION_THRESHOLD,
    COMPANY_HOLDINGS_URL_TEMPLATE,
    HOLDINGS_FETCH_MAX_WORKERS,
    HOLDINGS_FETCH_TIMEOUT,
    MAX_EXPOSURE_CACHE_USERS,
    NON_EQUITY_CDN_PREFIXES,
)
from ..logging_config import logger
from .company_classifier import (
    get_company_classifier,
    get_sector_labels,
    update_sector_labels,
)
from .entity_matcher import get_entity_matcher
from .nse_equity import nse_equity_cache


@dataclass
class CompanyHolding:
    """Aggregated exposure to a single company across all asset classes."""

    company_name: str
    sector: str
    instrument_type: str  # e.g. "Equity", "Certificate of Deposits"
    holding_amount: float  # Total INR value across funds/stocks
    percentage_of_portfolio: float  # % of total portfolio value
    funds: list[str] = field(default_factory=list)  # MF/ETF names contributing


@dataclass
class ExposureResult:
    """Full company exposure analysis result for a user."""

    companies: list[CompanyHolding]
    sector_totals: dict[str, float]  # sector name → total INR value
    fund_totals: dict[str, float]  # fund/source name → total INR value
    total_portfolio_value: float


class ExposureCache:
    """Per-user LRU cache for company exposure analysis results.

    Stores the computed ExposureResult per google_id.  Entries are
    evicted by LRU when the cap is reached.  Callers should invalidate
    the entry when the user refreshes their portfolio data.

    Also tracks which users have an analysis in progress so that the
    route can return 202 and avoid duplicate background work.
    """

    def __init__(self, maxsize: int = MAX_EXPOSURE_CACHE_USERS) -> None:
        self._cache: LRUCache[str, ExposureResult] = LRUCache(maxsize=maxsize)
        self._lock = threading.Lock()
        self._in_progress: set[str] = set()
        self._no_data: set[str] = set()

    def get(self, google_id: str) -> ExposureResult | None:
        """Return the cached result for *google_id*, or None on miss."""
        with self._lock:
            return self._cache.get(google_id)

    def put(self, google_id: str, result: ExposureResult) -> None:
        """Store *result* for *google_id*, refreshing its LRU position."""
        with self._lock:
            self._cache[google_id] = result

    def is_in_progress(self, google_id: str) -> bool:
        """Return True if an analysis is currently running for *google_id*."""
        with self._lock:
            return google_id in self._in_progress

    def set_in_progress(self, google_id: str) -> None:
        """Mark that an analysis has started for *google_id*."""
        with self._lock:
            self._in_progress.add(google_id)

    def clear_in_progress(self, google_id: str) -> None:
        """Mark that the analysis for *google_id* has finished."""
        with self._lock:
            self._in_progress.discard(google_id)

    def has_no_data(self, google_id: str) -> bool:
        """Return True if the last analysis completed but found no data."""
        with self._lock:
            return google_id in self._no_data

    def mark_no_data(self, google_id: str) -> None:
        """Record that analysis ran but produced no result (avoids re-running)."""
        with self._lock:
            self._no_data.add(google_id)

    def invalidate(self, google_id: str) -> None:
        """Remove cached result and no-data flag for *google_id*."""
        with self._lock:
            self._cache.pop(google_id, None)
            self._no_data.discard(google_id)


# Module-level singleton — imported by routes.
exposure_cache = ExposureCache()


# ---------------------------------------------------------------------------
# Name normalisation helpers
# ---------------------------------------------------------------------------

# \bXxx\b matches the word, \.? then optionally consumes a trailing dot so
# "Ltd." and "Ltd" are both fully replaced (no residual dot left behind).
_LTD_RE = re.compile(r"\bLtd\b\.?", re.IGNORECASE)
_PVT_RE = re.compile(r"\bPvt\b\.?", re.IGNORECASE)


def _normalize_name(name: str) -> str:
    """Return a canonical upper-case key for *name*.

    Expands legal-entity abbreviations so that ``"HDFC Bank Ltd."``
    and ``"HDFC Bank Limited"`` map to the same key.  Date suffixes
    (e.g. ``(24/06/2026)``) are **preserved** because they carry
    meaningful information for non-equity instruments like bonds and
    certificates of deposit.
    """
    name = _LTD_RE.sub("Limited", name)
    name = _PVT_RE.sub("Private", name)
    return name.upper().strip()


def _is_non_equity(name: str) -> bool:
    """Return True for cash/repo CDN rows that should be excluded from exposure.

    Checks the normalised name against known non-equity prefixes (TREPS,
    CBLO, net-receivable entries, reverse repos, etc.).
    """
    upper = _normalize_name(name)
    return any(upper.startswith(prefix) for prefix in NON_EQUITY_CDN_PREFIXES)


# ---------------------------------------------------------------------------
# Holdings fetch helpers
# ---------------------------------------------------------------------------


def _fetch_holdings(isin: str) -> tuple[str, list[dict[str, Any]]]:
    """Fetch company-level holdings for *isin* from Zerodha's CDN.

    The CDN JSON has a ``data`` key containing an array of arrays where:
      - row[1]  company name
      - row[2]  sector
      - row[3]  instrument type (e.g. "Equity", "Certificate of Deposits")
      - row[5]  allocation percentage within the fund

    Args:
        isin: ISIN of the mutual fund or ETF.

    Returns:
        Tuple of (isin, holdings_list).  On any error, holdings_list is empty.
    """
    url = COMPANY_HOLDINGS_URL_TEMPLATE.format(isin=isin)
    try:
        resp = requests.get(url, timeout=HOLDINGS_FETCH_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        raw_rows: list[list] = body.get("data", [])
        holdings: list[dict[str, Any]] = []
        for row in raw_rows:
            if len(row) <= 5:
                continue
            try:
                alloc_pct = float(row[5])
            except (TypeError, ValueError):
                continue
            holdings.append(
                {
                    "company_name": str(row[1]).strip(),
                    "sector": str(row[2]).strip(),
                    "instrument_type": str(row[3]).strip() if len(row) > 3 else "Equity",
                    "allocation_pct": alloc_pct,
                }
            )
        logger.debug("Holdings fetch isin=%s rows=%d", isin, len(holdings))
        return isin, holdings
    except Exception as exc:
        logger.warning("Holdings fetch failed isin=%s: %s", isin, exc)
        return isin, []


def _batch_fetch_holdings(isin_list: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Concurrently fetch company holdings for all ISINs in *isin_list*.

    Args:
        isin_list: List of unique ISINs to fetch.

    Returns:
        Dict mapping isin → list of company holding dicts.
    """
    results: dict[str, list[dict[str, Any]]] = {}
    if not isin_list:
        return results

    with ThreadPoolExecutor(max_workers=HOLDINGS_FETCH_MAX_WORKERS) as executor:
        future_to_isin = {executor.submit(_fetch_holdings, isin): isin for isin in isin_list}
        for future in as_completed(future_to_isin):
            isin, holdings = future.result()
            results[isin] = holdings

    populated = sum(1 for h in results.values() if h)
    logger.info(
        "Batch holdings fetch: %d ISINs requested, %d returned data",
        len(isin_list),
        populated,
    )
    return results


# ---------------------------------------------------------------------------
# Core analysis builder
# ---------------------------------------------------------------------------


def _current_value(holding: dict[str, Any]) -> float:
    """Return the current market value of a holding (quantity × last_price)."""
    qty = float(holding.get("quantity") or 0)
    price = float(holding.get("last_price") or 0)
    return qty * price


def _display_name(name: str) -> str:
    """Return a clean, UI-friendly version of *name*.

    Expands legal-entity abbreviations but preserves the original
    letter case and any date suffixes::

        >>> _display_name("HDFC Bank Ltd.")
        'HDFC Bank Limited'
        >>> _display_name("ABC Pvt. Ltd. (24/06/2026)")
        'ABC Private Limited (24/06/2026)'
    """
    name = _LTD_RE.sub("Limited", name)
    name = _PVT_RE.sub("Private", name)
    return name.strip()


def _pick_display_name(names: list[str]) -> str:
    """Pick the best display name from a list of variant names.

    Prefers mixed-case names over all-uppercase, then picks the
    longest (usually the most complete/descriptive).
    """
    cleaned = [_display_name(n) for n in names]
    mixed = [n for n in cleaned if n != n.upper()]
    pool = mixed if mixed else cleaned
    return max(pool, key=len)


@dataclass
class _RawEntry:
    """One raw company holding before deduplication."""

    raw_name: str
    sector: str
    instrument_type: str
    amount: float
    fund_name: str


def _gather_raw_entries(
    mf_by_isin: dict[str, dict[str, Any]],
    etf_by_isin: dict[str, dict[str, Any]],
    stock_holdings: list[dict[str, Any]],
    holdings_data: dict[str, list[dict[str, Any]]],
) -> list[_RawEntry]:
    """Step 1 — gather company names from stocks, MFs, and ETFs.

    Direct stock symbols are resolved to NSE canonical company names
    (e.g. ``HDFCBANK`` → ``HDFC Bank Limited``) via ``nse_equity_cache``.
    MF/ETF company names come from the Zerodha CDN.  Non-equity CDN
    rows (TREPS, CBLO, etc.) are filtered out here.
    """
    entries: list[_RawEntry] = []

    # Mutual funds.
    for isin, mf in mf_by_isin.items():
        fund_name = (mf.get("fund") or mf.get("fund_name") or isin).strip()
        fund_value = _current_value(mf)
        if fund_value <= 0:
            continue
        for row in holdings_data.get(isin, []):
            if _is_non_equity(row["company_name"]):
                continue
            amount = (row["allocation_pct"] / 100.0) * fund_value
            instrument = row.get("instrument_type", "Equity")
            entries.append(_RawEntry(row["company_name"], row["sector"], instrument, amount, fund_name))

    # ETFs (same CDN format as MFs).
    for isin, etf in etf_by_isin.items():
        etf_name = (etf.get("tradingsymbol") or etf.get("fund") or isin).strip()
        etf_value = _current_value(etf)
        if etf_value <= 0:
            logger.debug("  ETF ISIN=%s skipped (zero value)", isin)
            continue
        cdn_rows = holdings_data.get(isin, [])
        if not cdn_rows:
            logger.debug(
                "  ETF ISIN=%s (%s) — no CDN rows",
                isin,
                etf_name,
            )
        for row in cdn_rows:
            if _is_non_equity(row["company_name"]):
                logger.debug(
                    "  ETF ISIN=%s filtered non-equity: %s",
                    isin,
                    row["company_name"],
                )
                continue
            amount = (row["allocation_pct"] / 100.0) * etf_value
            instrument = row.get("instrument_type", "Equity")
            entries.append(_RawEntry(row["company_name"], row["sector"], instrument, amount, etf_name))

    # Direct stocks — resolve symbol → NSE canonical company name.
    for stock in stock_holdings:
        symbol = (stock.get("tradingsymbol") or "").upper().strip()
        stock_value = _current_value(stock)
        if not symbol or stock_value <= 0:
            continue
        equity_info = nse_equity_cache.get(symbol)
        canonical = equity_info.company_name if equity_info else symbol
        entries.append(_RawEntry(canonical, "", "Equity", stock_value, "Direct"))

    logger.debug(
        "Gathered %d raw entries (%d unique companies)",
        len(entries),
        len({e.raw_name for e in entries}),
    )
    return entries


def _merge_similar_sectors(
    sector_totals: dict[str, float],
) -> dict[str, float]:
    """Cluster semantically similar sector names.

    The ``"Unknown"`` bucket is passed through as-is (not clustered).
    """
    known = {k: v for k, v in sector_totals.items() if k != "Unknown"}
    if len(known) <= 1:
        return sector_totals

    matcher = get_entity_matcher()
    names = list(known.keys())
    clusters = matcher.cluster_names(names)

    merged: dict[str, float] = {}
    for name, value in known.items():
        canonical = clusters[name]
        merged[canonical] = merged.get(canonical, 0.0) + value

    if "Unknown" in sector_totals:
        merged["Unknown"] = sector_totals["Unknown"]

    return merged


def build_exposure_data(
    google_id: str,
    stocks_and_etfs: list[dict[str, Any]],
    mf_holdings: list[dict[str, Any]],
) -> ExposureResult | None:
    """Build a company-level exposure analysis for the signed-in user.

    Reads normalised portfolio data (already merged from broker + manual
    sources by the route layer), fetches company-level portfolio data from
    Zerodha's CDN for each MF and ETF, then aggregates the exposure.

    Direct stock symbols are resolved to NSE canonical names via
    ``nse_equity_cache`` before insertion so that e.g. ``HDFCBANK``
    and ``HDFC Bank Ltd.`` (from a fund's CDN data) land on the same key.

    Args:
        google_id: The user's Google ID (used only for logging).
        stocks_and_etfs: Normalised list from ``_build_stocks_data``.
            Each entry has ``tradingsymbol``, ``quantity``, ``last_price``,
            and optionally ``manual_type`` == ``"etfs"`` for ETFs.
        mf_holdings: Normalised list from ``_build_mf_data``.
            Each entry has ``isin``, ``fund``, ``quantity``, ``last_price``.

    Returns:
        ExposureResult if data is available, None when no holdings exist.
    """
    if not stocks_and_etfs and not mf_holdings:
        logger.info("No portfolio data for exposure analysis: user=%s", google_id[:8])
        return None

    # ------------------------------------------------------------------
    # Separate stocks from ETFs and compute totals.
    # ------------------------------------------------------------------
    etf_holdings = [e for e in stocks_and_etfs if e.get("manual_type") == "etfs"]
    stock_holdings = [e for e in stocks_and_etfs if e.get("manual_type") != "etfs"]

    logger.debug(
        "Exposure input: %d stocks, %d ETFs, %d MFs",
        len(stock_holdings),
        len(etf_holdings),
        len(mf_holdings),
    )
    for etf in etf_holdings:
        sym = etf.get("tradingsymbol", "?")
        isin = (etf.get("isin") or "").strip()
        val = _current_value(etf)
        logger.debug("  ETF: symbol=%s isin=%s value=%.0f", sym, isin or "(none)", val)

    stock_total = sum(_current_value(s) for s in stock_holdings)
    etf_total = sum(_current_value(e) for e in etf_holdings)
    mf_total = sum(_current_value(m) for m in mf_holdings)
    total_value = stock_total + etf_total + mf_total

    if total_value <= 0:
        logger.info("Zero portfolio value for user=%s — skipping exposure build", google_id[:8])
        return None

    # ------------------------------------------------------------------
    # Deduplicate MF holdings by ISIN (merge same fund across accounts).
    # ------------------------------------------------------------------
    mf_by_isin: dict[str, dict[str, Any]] = {}
    for mf in mf_holdings:
        isin = (mf.get("isin") or "").strip().upper()
        if not isin:
            continue
        if isin not in mf_by_isin:
            mf_by_isin[isin] = dict(mf)
        else:
            # Accumulate quantity so current_value sums correctly.
            existing = mf_by_isin[isin]
            existing["quantity"] = float(existing.get("quantity") or 0) + float(mf.get("quantity") or 0)

    # Deduplicate ETF holdings by ISIN.
    etf_by_isin: dict[str, dict[str, Any]] = {}
    for etf in etf_holdings:
        isin = (etf.get("isin") or "").strip().upper()
        if not isin:
            logger.debug(
                "  ETF skipped (no ISIN): symbol=%s",
                etf.get("tradingsymbol", "?"),
            )
            continue
        if isin not in etf_by_isin:
            etf_by_isin[isin] = dict(etf)
        else:
            existing = etf_by_isin[isin]
            existing["quantity"] = float(existing.get("quantity") or 0) + float(etf.get("quantity") or 0)

    # ------------------------------------------------------------------
    # Batch-fetch company holdings for all MF + ETF ISINs.
    # ------------------------------------------------------------------
    all_isins = list(set(list(mf_by_isin) + list(etf_by_isin)))
    logger.debug(
        "Fetching CDN holdings: %d MF ISINs, %d ETF ISINs, %d total unique",
        len(mf_by_isin),
        len(etf_by_isin),
        len(all_isins),
    )
    t0 = time.monotonic()
    holdings_data = _batch_fetch_holdings(all_isins)
    logger.info("⏱ CDN fetch: %.1fs", time.monotonic() - t0)
    for isin, rows in holdings_data.items():
        if not rows:
            logger.debug("  CDN empty for ISIN=%s", isin)
        else:
            logger.debug(
                "  CDN ISIN=%s → %d rows (first: %s)",
                isin,
                len(rows),
                rows[0].get("company_name", "?"),
            )

    # ==================================================================
    # Step 1: Gather company names from stocks, MFs, and ETFs.
    # ==================================================================
    raw_entries = _gather_raw_entries(mf_by_isin, etf_by_isin, stock_holdings, holdings_data)
    if not raw_entries:
        logger.info("No company-level data for user=%s", google_id[:8])
        return None

    # Collect unique CDN sectors and update the growing labels file.
    cdn_sectors = {e.sector for e in raw_entries}
    update_sector_labels(cdn_sectors)

    # ==================================================================
    # Step 2: Normalise all names.
    # ==================================================================
    unique_raw_names = list({e.raw_name for e in raw_entries})
    norm_map = {name: _normalize_name(name) for name in unique_raw_names}
    unique_normalized = list(set(norm_map.values()))

    # ==================================================================
    # Step 3: Pass all normalised names to the model for clustering.
    # ==================================================================
    t1 = time.monotonic()
    matcher = get_entity_matcher()
    clusters = matcher.cluster_names(unique_normalized)
    logger.info(
        "⏱ Entity clustering: %.1fs (%d unique names)",
        time.monotonic() - t1,
        len(unique_normalized),
    )

    # raw_name → cluster key
    name_to_cluster: dict[str, str] = {}
    for raw_name in unique_raw_names:
        name_to_cluster[raw_name] = clusters[norm_map[raw_name]]

    # ==================================================================
    # Step 4: Determine sub-industry for each company.
    #
    # Trust the CDN sector when present — it is the authoritative
    # source.  Only invoke the BART-MNLI classifier for companies
    # that have no CDN sector (e.g. direct stock holdings).
    # ==================================================================
    t2 = time.monotonic()
    display_map = {rn: _display_name(rn) for rn in unique_raw_names}

    # Map each display name → its most common CDN sector.
    display_sector_votes: dict[str, dict[str, int]] = {}
    for entry in raw_entries:
        display = display_map[entry.raw_name]
        votes = display_sector_votes.setdefault(display, {})
        s = entry.sector or ""
        votes[s] = votes.get(s, 0) + 1
    display_to_cdn_sector: dict[str, str] = {}
    for display, votes in display_sector_votes.items():
        display_to_cdn_sector[display] = max(votes, key=lambda k: votes[k])

    # Classify only companies missing a CDN sector.
    needs_classification = [d for d, s in display_to_cdn_sector.items() if not s]
    classifications: dict[str, tuple[str, float]] = {}
    if needs_classification:
        all_labels = get_sector_labels()
        if all_labels:
            try:
                classifier = get_company_classifier()
                classifications = classifier.classify_batch(needs_classification, labels=all_labels)
            except Exception as exc:
                logger.warning(
                    "Classification unavailable, using CDN sectors only: %s", exc
                )

    logger.info(
        "⏱ Classification: %.1fs (%d classified, %d used CDN sector)",
        time.monotonic() - t2,
        len(classifications),
        len(display_to_cdn_sector) - len(needs_classification),
    )

    def _effective_sector(raw_name: str, cdn_sector: str) -> str:
        if cdn_sector:
            return cdn_sector
        # Fall back to the voted CDN sector for this display name
        # (another raw variant of the same company may have one).
        display = display_map[raw_name]
        voted = display_to_cdn_sector.get(display, "")
        if voted:
            return voted
        # Last resort: classifier result for companies with no
        # CDN sector at all (e.g. direct stocks).
        if display in classifications:
            label, confidence = classifications[display]
            if confidence >= COMPANY_CLASSIFICATION_THRESHOLD:
                return label
        return "Unknown"

    # ==================================================================
    # Step 5: Group by (cluster, instrument_type, sub_industry) and
    #         pick a clean display name for each group.
    # ==================================================================
    # Build a per-entry sector lookup so we can determine the group key.
    entry_sector: dict[int, str] = {}
    group_members: dict[tuple[str, str, str], list[str]] = {}
    for idx, entry in enumerate(raw_entries):
        cluster_key = name_to_cluster[entry.raw_name]
        sub_industry = _effective_sector(entry.raw_name, entry.sector)
        entry_sector[idx] = sub_industry
        group = (cluster_key, entry.instrument_type, sub_industry)
        group_members.setdefault(group, []).append(entry.raw_name)

    display_for_group: dict[tuple[str, str, str], str] = {
        group: _pick_display_name(members) for group, members in group_members.items()
    }

    # ==================================================================
    # Step 6: Aggregate holdings by (cluster, instrument, sub_industry).
    # ==================================================================
    company_map: dict[tuple[str, str, str], CompanyHolding] = {}
    for idx, entry in enumerate(raw_entries):
        cluster_key = name_to_cluster[entry.raw_name]
        sub_industry = entry_sector[idx]
        key = (cluster_key, entry.instrument_type, sub_industry)
        if key in company_map:
            holding = company_map[key]
            holding.holding_amount += entry.amount
            if entry.fund_name and entry.fund_name not in holding.funds:
                holding.funds.append(entry.fund_name)
        else:
            company_map[key] = CompanyHolding(
                company_name=display_for_group[key],
                sector=sub_industry,
                instrument_type=entry.instrument_type,
                holding_amount=entry.amount,
                percentage_of_portfolio=0.0,
                funds=[entry.fund_name] if entry.fund_name else [],
            )

    # ------------------------------------------------------------------
    # Compute percentages, sort, and build sector totals.
    # ------------------------------------------------------------------
    companies: list[CompanyHolding] = []
    for holding in company_map.values():
        holding.percentage_of_portfolio = (holding.holding_amount / total_value) * 100.0
        companies.append(holding)

    companies.sort(key=lambda c: c.holding_amount, reverse=True)

    sector_totals: dict[str, float] = {}
    for company in companies:
        sector = company.sector or "Unknown"
        sector_totals[sector] = sector_totals.get(sector, 0.0) + company.holding_amount

    t3 = time.monotonic()
    sector_totals = _merge_similar_sectors(sector_totals)
    logger.info("⏱ Sector merge: %.1fs", time.monotonic() - t3)

    # Fund/source allocation — sum amounts per fund name from raw entries.
    fund_totals: dict[str, float] = {}
    for entry in raw_entries:
        fund_totals[entry.fund_name] = fund_totals.get(entry.fund_name, 0.0) + entry.amount

    logger.info(
        "Exposure analysis complete: user=%s companies=%d sectors=%d funds=%d total=%.0f",
        google_id[:8],
        len(companies),
        len(sector_totals),
        len(fund_totals),
        total_value,
    )

    return ExposureResult(
        companies=companies,
        sector_totals=sector_totals,
        fund_totals=fund_totals,
        total_portfolio_value=total_value,
    )
