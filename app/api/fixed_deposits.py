"""Fixed Deposits Service"""

from datetime import datetime
from typing import Any, Dict, List

from dateutil.relativedelta import relativedelta

from ..logging_config import logger


def calculate_compound_interest(
    principal: float,
    annual_rate: float,
    time_in_years: float,
    compounding_frequency: int = 4
) -> float:
    """Calculate compound interest.
    
    Args:
        principal: Principal amount deposited
        annual_rate: Annual interest rate (as percentage, e.g., 7.5 for 7.5%)
        time_in_years: Time period in years
        compounding_frequency: Number of times interest is compounded per year (default: 4 for quarterly)
    
    Returns:
        Final amount after compound interest
    """
    if principal <= 0 or annual_rate <= 0 or time_in_years <= 0:
        return principal
    
    # Convert annual rate from percentage to decimal
    rate = annual_rate / 100
    
    # Compound interest formula: A = P(1 + r/n)^(nt)
    # where: A = final amount, P = principal, r = annual rate, n = compounding frequency, t = time in years
    amount = principal * ((1 + rate / compounding_frequency) ** (compounding_frequency * time_in_years))
    
    return amount


def calculate_current_value(fixed_deposits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calculate current value for fixed deposits.
    
    Args:
        fixed_deposits: List of fixed deposit holdings
    
    Returns:
        Enriched holdings with current_value and estimated_returns fields
    """
    enriched_deposits = []
    
    for deposit in fixed_deposits:
        deposit_copy = deposit.copy()
        
        # Parse deposit date: prefer reinvested date, but fall back to original investment date
        deposit_date_str = deposit.get('reinvested_date') or deposit.get('original_investment_date', '')
        deposit_date = None

        if deposit_date_str:
            # Try multiple date formats (Google Sheets may store dates differently)
            for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
                try:
                    deposit_date = datetime.strptime(deposit_date_str, fmt)
                    break
                except (ValueError, TypeError):
                    continue

            if deposit_date is None:
                logger.warning(
                    "Cannot parse deposit date '%s' for %s — skipping",
                    deposit_date_str, deposit.get('bank_name', 'unknown'),
                )
                continue
        
        # Calculate maturity date from deposit tenure (year/month/day)
        deposit_year = deposit.get('deposit_year', 0)
        deposit_month = deposit.get('deposit_month', 0)
        deposit_day_val = deposit.get('deposit_day', 0)

        # Use relativedelta for calendar-accurate date arithmetic.
        # A flat day approximation (years*365 + months*30 + days) drifts
        # because calendar months vary from 28-31 days and years can be 366.
        maturity_date = deposit_date + relativedelta(
            years=int(deposit_year),
            months=int(deposit_month),
            days=int(deposit_day_val),
        )
        maturity_date_str = maturity_date.strftime("%B %d, %Y")
        deposit_copy['maturity_date'] = maturity_date_str
        
        logger.debug(
            "Calculated maturity date for %s: %s (Period: %dy %dm %dd)",
            deposit['bank_name'],
            maturity_date_str,
            int(deposit_year),
            int(deposit_month),
            int(deposit_day_val),
        )
        
        # Get principal and interest rate
        principal = deposit.get('reinvested_amount', 0) or deposit.get('original_amount', 0)
        annual_rate = deposit.get('interest_rate', 0)
        
        # Calculate till today since active deposits are auto-reinvested
        days_elapsed = (datetime.now() - deposit_date).days
        years_elapsed = days_elapsed / 365.0
        
        # Calculate current value with quarterly compound interest
        current_value = calculate_compound_interest(
            principal, 
            annual_rate, 
            years_elapsed, 
            compounding_frequency=4
        )
        
        deposit_copy['current_value'] = current_value
        deposit_copy['estimated_returns'] = current_value - principal
        
        enriched_deposits.append(deposit_copy)

    # Sort by maturity date in ascending order
    enriched_deposits.sort(
        key=lambda d: datetime.strptime(d['maturity_date'], "%B %d, %Y") if d.get('maturity_date') else datetime.max
    )

    return enriched_deposits
