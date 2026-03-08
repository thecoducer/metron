"""Provident Fund (EPF) Calculation Service.

Implements Indian Employee Provident Fund interest calculation across
multiple company stints.  Key rules modelled:

1. Employee contributes a fixed monthly amount during each employment.
2. The annual interest rate is declared by EPFO (government) and applies
   to the **entire accumulated balance**, not just the current company's
   contributions.
3. Interest accrues monthly on the running balance but is compounded
   (credited) at the end of each financial year (March 31).
4. During gaps between jobs, no contributions are made but the existing
   balance continues to earn interest at the last known rate.
5. An entry with no end date means the employee is currently employed.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from dateutil.rrule import MONTHLY, rrule

from ..constants import EPF_HISTORICAL_RATES, EPF_DEFAULT_RATE
from ..logging_config import logger
from ..utils import parse_date


def _get_epf_rate(year: int, month: int) -> float:
    """Return the official EPF interest rate for the FY containing (year, month)."""
    fy_start = year if month >= 4 else year - 1
    return EPF_HISTORICAL_RATES.get(fy_start, EPF_DEFAULT_RATE)


# ── Date helpers ──────────────────────────────────────────────────

def _month_range(start: date, end: date):
    """Yield (year, month) tuples from *start* through *end* inclusive."""
    for dt in rrule(MONTHLY, dtstart=start.replace(day=1), until=end.replace(day=1)):
        yield dt.year, dt.month


# ── Core calculation ─────────────────────────────────────────────

def calculate_pf_corpus(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enrich PF entries with calculated values.

    Each entry describes a company stint with fields:
        company_name, start_date, end_date (optional),
        monthly_contribution, interest_rate (annual %).

    Returns a new list of entries enriched with:
        - months_worked: number of contribution months
        - total_contribution: total money contributed in this stint
        - opening_balance: PF balance when this stint started
        - closing_balance: balance at the end of this stint (with interest)
        - interest_earned: interest earned during this stint (on full balance)
        - corpus_value: final accumulated PF balance across all stints
    """
    if not entries:
        return []

    # Parse dates and filter out unparseable entries
    parsed: List[Tuple[Dict[str, Any], date, Optional[date]]] = []
    for entry in entries:
        start = parse_date(entry.get("start_date", ""))
        if not start:
            # Past employer entries can omit date — default to today
            is_past = float(entry.get("opening_balance", 0) or 0) > 0 and float(entry.get("monthly_contribution", 0) or 0) <= 0
            if is_past:
                start = date.today()
            else:
                logger.warning(
                    "PF: skipping entry for '%s' — cannot parse start_date '%s'",
                    entry.get("company_name", "?"), entry.get("start_date"),
                )
                continue
        end = parse_date(entry.get("end_date", ""))
        parsed.append((entry, start, end))

    if not parsed:
        return []

    # Sort by start date
    parsed.sort(key=lambda t: t[1])

    today = date.today()

    # Build a timeline: for each month from earliest start to today,
    # determine the active entry (contribution + rate).
    earliest = parsed[0][1]

    # Build a lookup: for each month, which entry is active?
    # An entry is "active" for a month if that month falls within
    # [start_month, end_month].  If entries overlap, the later entry wins.
    month_info: Dict[Tuple[int, int], Tuple[float, float, int]] = {}
    # Maps (year, month) → (contribution, rate, entry_index)

    for idx, (entry, start, end) in enumerate(parsed):
        contribution = float(entry.get("monthly_contribution", 0) or 0)
        rate = float(entry.get("interest_rate", 0) or 0)
        effective_end = end if end else today
        # Clamp future end dates to today
        if effective_end > today:
            effective_end = today
        for ym in _month_range(start, effective_end):
            month_info[ym] = (contribution, rate, idx)

    # Walk month-by-month from earliest start to today
    balance = 0.0
    accrued_interest_fy = 0.0
    last_rate = parsed[0][0].get("interest_rate", 0) or 0
    last_rate = float(last_rate)

    # Per-entry accumulators
    entry_data = []
    for idx, (entry, start, end) in enumerate(parsed):
        entry_data.append({
            "opening_balance": 0.0,
            "total_contribution": 0.0,
            "interest_earned": 0.0,
            "closing_balance": 0.0,
            "months_worked": 0,
            "rate_sum": 0.0,
            "rate_months": 0,
        })

    # Track which entry index is active each month for per-entry accounting
    prev_entry_idx = -1

    for ym in _month_range(earliest, today):
        info = month_info.get(ym)
        if info:
            contribution, rate, entry_idx = info
            # Auto-rate: when user sets rate to 0, use official EPFO rate
            if rate <= 0:
                rate = _get_epf_rate(ym[0], ym[1])
            last_rate = rate
        else:
            # Gap between jobs: no contribution, balance still earns interest
            contribution = 0.0
            rate = last_rate
            entry_idx = prev_entry_idx if prev_entry_idx >= 0 else 0

        # Track opening balance when we first enter a new entry
        if entry_idx != prev_entry_idx and entry_idx >= 0 and entry_idx < len(entry_data):
            # Credit any uncredited FY interest before recording opening balance
            # of the new entry (so the opening balance is accurate)
            if prev_entry_idx >= 0:
                ed = entry_data[prev_entry_idx]
                ed["closing_balance"] = balance + accrued_interest_fy

            # Inject lump sum for past employer entries (opening_balance field)
            lump_sum = float(parsed[entry_idx][0].get("opening_balance", 0) or 0)
            if lump_sum > 0:
                balance += lump_sum
                # If user provided actual_contribution, use it as cost basis;
                # otherwise treat the full lump sum as contribution (conservative).
                actual = float(parsed[entry_idx][0].get("actual_contribution", 0) or 0)
                if actual > 0:
                    entry_data[entry_idx]["total_contribution"] += actual
                else:
                    entry_data[entry_idx]["total_contribution"] += lump_sum

            entry_data[entry_idx]["opening_balance"] = balance + accrued_interest_fy

        # Add contribution
        balance += contribution

        if entry_idx >= 0 and entry_idx < len(entry_data):
            ed = entry_data[entry_idx]
            if info:
                ed["total_contribution"] += contribution
                ed["months_worked"] += 1
                ed["rate_sum"] += rate
                ed["rate_months"] += 1

        # Monthly interest accrual (EPF: interest accrues monthly,
        # compounded annually at end of financial year).
        # Only accrue interest for completed months; the current month
        # is still in progress so no interest should be recognised yet.
        is_current_month = (ym[0] == today.year and ym[1] == today.month)
        if not is_current_month:
            monthly_interest = balance * (rate / 12.0 / 100.0)
            accrued_interest_fy += monthly_interest

            if entry_idx >= 0 and entry_idx < len(entry_data):
                entry_data[entry_idx]["interest_earned"] += monthly_interest

            # Credit interest at the end of financial year (March)
            if ym[1] == 3:
                balance += accrued_interest_fy
                accrued_interest_fy = 0.0

        prev_entry_idx = entry_idx

    # Add any uncredited interest for the current partial FY
    balance += accrued_interest_fy

    # Finalize the last active entry
    if prev_entry_idx >= 0 and prev_entry_idx < len(entry_data):
        entry_data[prev_entry_idx]["closing_balance"] = balance

    # Build enriched result
    enriched = []
    total_contributions = 0.0
    for idx, (entry, start, end) in enumerate(parsed):
        copy = dict(entry)
        ed = entry_data[idx]

        effective_end = end if end else today
        if effective_end > today:
            effective_end = today

        original_rate = float(entry.get("interest_rate", 0) or 0)
        copy["auto_rate"] = original_rate <= 0
        if copy["auto_rate"] and ed["rate_months"] > 0:
            copy["effective_rate"] = round(ed["rate_sum"] / ed["rate_months"], 2)
        else:
            copy["effective_rate"] = round(original_rate, 2)
        copy["start_date_parsed"] = start.strftime("%B %d, %Y")
        copy["end_date_parsed"] = end.strftime("%B %d, %Y") if end else ""
        copy["is_current"] = end is None
        copy["is_past_employer"] = float(entry.get("opening_balance", 0) or 0) > 0 and float(entry.get("monthly_contribution", 0) or 0) <= 0
        copy["actual_contribution"] = float(entry.get("actual_contribution", 0) or 0)
        copy["months_worked"] = ed["months_worked"]
        copy["total_contribution"] = round(ed["total_contribution"], 2)
        copy["opening_balance"] = round(ed["opening_balance"], 2)
        copy["closing_balance"] = round(ed["closing_balance"], 2)
        copy["interest_earned"] = round(ed["interest_earned"], 2)

        total_contributions += ed["total_contribution"]

        enriched.append(copy)

    # Tag the final corpus value on each entry for the summary card
    corpus = round(balance, 2)
    total_interest = round(corpus - total_contributions, 2)
    for entry in enriched:
        entry["corpus_value"] = corpus
        entry["total_corpus_contributions"] = round(total_contributions, 2)
        entry["total_corpus_interest"] = total_interest

    logger.info(
        "PF calculation: %d entries, corpus=%.2f, contributions=%.2f, interest=%.2f",
        len(enriched), corpus, total_contributions, total_interest,
    )

    return enriched


def resolve_epf_rate(start_date_str: str, end_date_str: str = "") -> Optional[float]:
    """Compute the weighted-average EPFO rate for a date range.

    Used to fill in the interest rate when the user leaves it blank.
    Returns ``None`` if the start date cannot be parsed.
    """
    start = parse_date(start_date_str)
    if not start:
        return None
    end = parse_date(end_date_str) if end_date_str else None
    effective_end = end or date.today()
    if effective_end > date.today():
        effective_end = date.today()

    rate_sum = 0.0
    rate_count = 0
    for year, month in _month_range(start, effective_end):
        rate_sum += _get_epf_rate(year, month)
        rate_count += 1

    if rate_count == 0:
        return None
    return round(rate_sum / rate_count, 2)
