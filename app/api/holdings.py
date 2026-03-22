"""
Holdings management service.
"""

from datetime import datetime
from typing import Any

from kiteconnect import KiteConnect
from requests.exceptions import ConnectionError, ReadTimeout

from ..logging_config import logger
from .base_service import BaseDataService


class HoldingsService(BaseDataService):
    """Service for fetching and managing holdings data."""

    def __init__(self):
        self.mf_instruments_cache = None
        self.mf_instruments_cache_time = None

    def fetch_holdings(self, kite: KiteConnect) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Fetch stock and MF holdings from KiteConnect.

        Args:
            kite: Authenticated KiteConnect instance

        Returns:
            Tuple of (stock_holdings, mf_holdings)

        Raises:
            ReadTimeout, ConnectionError: On network issues
            Exception: On other API errors
        """
        try:
            stock_holdings: list[dict[str, Any]] = kite.holdings() or []  # type: ignore[assignment]
            mf_holdings: list[dict[str, Any]] = kite.mf_holdings() or []  # type: ignore[assignment]
            self._add_nav_dates(mf_holdings, kite)
            self._normalise_mf_fields(mf_holdings)
            return stock_holdings, mf_holdings
        except (ReadTimeout, ConnectionError) as e:
            logger.warning("Kite API timeout while fetching holdings: %s", str(e))
            raise
        except Exception as e:
            logger.exception("Unexpected error fetching holdings: %s", e)
            raise

    def _add_nav_dates(self, mf_holdings: list[dict[str, Any]], kite: KiteConnect) -> None:
        """
        Add NAV date information to MF holdings by fetching instrument data.

        Args:
            mf_holdings: List of MF holdings to enrich
            kite: Authenticated KiteConnect instance
        """
        try:
            if not self.mf_instruments_cache:
                # Only keep the two fields we need to avoid storing ~15K full dicts
                raw = kite.mf_instruments()
                self.mf_instruments_cache = {
                    inst["tradingsymbol"]: inst.get("last_price_date") for inst in raw if "tradingsymbol" in inst
                }
                self.mf_instruments_cache_time = datetime.now()

            for holding in mf_holdings:
                symbol = holding.get("tradingsymbol")
                if symbol and symbol in self.mf_instruments_cache:
                    nav_date = self.mf_instruments_cache[symbol]
                    holding["last_price_date"] = nav_date if nav_date is not None else holding.get("last_price_date")
                else:
                    # Set to None if symbol not found in instruments
                    holding.setdefault("last_price_date", None)

        except Exception as e:
            logger.exception("Error fetching MF instruments for NAV dates: %s", e)
            # Ensure all holdings have last_price_date field
            for holding in mf_holdings:
                holding.setdefault("last_price_date", None)

    def _normalise_mf_fields(self, mf_holdings: list[dict[str, Any]]) -> None:
        """Normalise broker MF holdings to a broker-agnostic schema.

        Zerodha stores the fund ISIN in ``tradingsymbol``.  This method
        promotes it to ``isin`` and removes ``tradingsymbol`` so the rest
        of the codebase only needs to deal with one field.
        """
        for mf in mf_holdings:
            if not mf.get("isin"):
                mf["isin"] = str(mf.get("tradingsymbol") or "").strip().upper()
            mf.pop("tradingsymbol", None)

    def add_account_info(self, items: list[dict[str, Any]], account_name: str) -> None:
        """Add account name and calculate invested amount for holdings.

        T1 quantity (unsettled shares) is added to the main quantity for accurate totals.
        Invested amount is calculated as: (quantity + t1_quantity) * average_price

        Args:
            items: List of holdings to enrich
            account_name: Name of the account
        """
        super().add_account_info(items, account_name)

        for holding in items:
            # Include T1 (unsettled) quantity in total quantity
            base_quantity = holding.get("quantity", 0)
            t1_quantity = holding.get("t1_quantity", 0)
            total_quantity = base_quantity + t1_quantity

            holding["quantity"] = total_quantity
            holding["invested"] = total_quantity * holding.get("average_price", 0)

    def merge_holdings(
        self, all_stock_holdings: list[list[dict[str, Any]]], all_mf_holdings: list[list[dict[str, Any]]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Merge holdings from multiple accounts.

        Args:
            all_stock_holdings: List of stock holdings lists
            all_mf_holdings: List of MF holdings lists

        Returns:
            Tuple of (merged_stock_holdings, merged_mf_holdings)
        """
        return self.merge_items(all_stock_holdings), self.merge_items(all_mf_holdings)
