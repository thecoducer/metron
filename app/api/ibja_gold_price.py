"""
Gold price fetching service from IBJA rates.
"""

from typing import Any

import requests
from bs4 import BeautifulSoup

from ..constants import IBJA_BASE_URL, IBJA_GOLD_PRICE_TIMEOUT, IBJA_GOLD_PURITIES
from ..error_handler import ErrorHandler
from ..logging_config import logger


class GoldPriceService:
    """Service for fetching current gold prices from ibjarates.com"""

    BASE_URL = IBJA_BASE_URL
    TIMEOUT = IBJA_GOLD_PRICE_TIMEOUT
    PURITIES = IBJA_GOLD_PURITIES

    def __init__(self):
        """Initialize the gold price service."""
        self.headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    def fetch_gold_prices(self) -> dict[str, Any] | None:
        """Fetch latest available gold prices for different purities.

        Returns:
            Dict with 'prices' key, or None if fetch fails.
            Prices are per gram in INR.
        """
        try:
            return self._fetch_gold_prices_impl()
        except Exception as e:
            wrapped_error = ErrorHandler.wrap_external_api_error(e, "IBJA Gold Price API")
            ErrorHandler.log_error(wrapped_error, context="fetch_gold_prices")
            return None

    def _fetch_gold_prices_impl(self) -> dict[str, Any] | None:
        """Internal implementation of gold price fetching."""
        logger.info("Fetching gold prices from %s", self.BASE_URL)

        response = requests.get(self.BASE_URL, headers=self.headers, timeout=self.TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        prices = {}

        for purity in self.PURITIES:
            span_elem = soup.find("span", id=f"GoldRatesCompare{purity}")
            if not span_elem:
                logger.warning("Could not find span element for purity %s", purity)
                continue

            try:
                price_per_gram = float(span_elem.get_text(strip=True))
                prices[purity] = {"am": price_per_gram, "pm": price_per_gram}
                logger.debug("Gold %s: ₹%s/gram", purity, price_per_gram)
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse price for %s: %s", purity, e)

        if not prices:
            logger.error("No valid gold prices found")
            return None

        logger.info("Successfully fetched prices for %d gold purities", len(prices))
        return {"prices": prices}

    def _get_price_by_purity(self, purity: str, time_of_day: str = "pm") -> float | None:
        """Get gold price for a specific purity.

        Args:
            purity: Gold purity code (e.g., '999', '916')
            time_of_day: 'am' or 'pm' (default: 'pm')

        Returns:
            Price per gram in INR, or None if unavailable
        """
        result = self.fetch_gold_prices()
        if not result or "prices" not in result or purity not in result["prices"]:
            return None

        time_key = time_of_day.lower() if time_of_day.lower() in ["am", "pm"] else "pm"
        return result["prices"][purity].get(time_key)

    def get_24k_price(self, time_of_day: str = "pm") -> float | None:
        """Get the current 24K (999 purity) gold price."""
        return self._get_price_by_purity("999", time_of_day)

    def get_22k_price(self, time_of_day: str = "pm") -> float | None:
        """Get the current 22K (916 purity) gold price."""
        return self._get_price_by_purity("916", time_of_day)

    def get_18k_price(self, time_of_day: str = "pm") -> float | None:
        """Get the current 18K (750 purity) gold price."""
        return self._get_price_by_purity("750", time_of_day)


# Singleton instance
_gold_price_service = None


def get_gold_price_service() -> GoldPriceService:
    """Get or create the singleton gold price service instance."""
    global _gold_price_service
    if _gold_price_service is None:
        _gold_price_service = GoldPriceService()
    return _gold_price_service


if __name__ == "__main__":
    """CLI interface for testing gold price fetching."""
    import logging
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    service = GoldPriceService()
    result = service.fetch_gold_prices()

    if result and "prices" in result:
        prices = result["prices"]
        print(f"\n✅ Successfully fetched {len(prices)} gold purities:")
        for purity in sorted(prices.keys(), key=int, reverse=True):
            print(f"  Gold {purity}: ₹{prices[purity]['pm']:,.2f}/gram")
    else:
        print("\n❌ Failed to fetch gold prices")
        sys.exit(1)
