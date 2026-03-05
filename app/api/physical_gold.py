"""Physical Gold Holdings Service"""

from typing import Any, Dict, List


def enrich_holdings_with_prices(holdings: List[Dict[str, Any]], gold_prices_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Enrich physical gold holdings with latest IBJA prices and calculate P/L.
    
    Args:
        holdings: List of physical gold holdings
        gold_prices_data: Dict containing 'prices' and 'date' from IBJA
    
    Returns:
        Enriched holdings with latest_ibja_price_per_gm, pl, and pl_pct fields (excluding Jewellery type)
    """
    enriched_holdings = []
    
    gold_prices = gold_prices_data.get('prices', {}) if gold_prices_data else {}
    
    for holding in holdings:
        # Exclude "Jewellery" type
        # if holding.get('type', '').lower() == 'jewellery':
        #     continue
            
        holding_copy = holding.copy()
        purity = holding.get('purity', '')
        
        latest_price_per_gm = None
        if gold_prices:
            if '999' in purity or '24K' in purity:
                latest_price_per_gm = gold_prices.get('999', {}).get('pm')
            elif '916' in purity or '22K' in purity:
                latest_price_per_gm = gold_prices.get('916', {}).get('pm')
            elif '750' in purity or '18K' in purity:
                latest_price_per_gm = gold_prices.get('750', {}).get('pm')
        
        holding_copy['latest_ibja_price_per_gm'] = latest_price_per_gm
        
        # Calculate P/L based on IBJA rates
        pl = 0
        pl_pct = 0
        if latest_price_per_gm and holding.get('bought_ibja_rate_per_gm') and holding.get('weight_gms'):
            invested = holding['bought_ibja_rate_per_gm'] * holding['weight_gms']
            current = latest_price_per_gm * holding['weight_gms']
            pl = current - invested
            pl_pct = (pl / invested * 100) if invested else 0
        
        holding_copy['pl'] = pl
        holding_copy['pl_pct'] = pl_pct
        
        enriched_holdings.append(holding_copy)
    
    return enriched_holdings


def calculate_totals(holdings: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate total investment and metrics for physical gold.
    
    Args:
        holdings: List of physical gold holdings
    
    Returns:
        Dictionary with total metrics
    """
    total_weight = sum(h.get('weight_gms', 0) for h in holdings)
    total_invested = sum(
        h.get('weight_gms', 0) * h.get('bought_ibja_rate_per_gm', 0) 
        for h in holdings
    )
    
    return {
        'total_weight_gms': total_weight,
        'total_invested': total_invested,
        'count': len(holdings)
    }
