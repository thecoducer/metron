"""Zerodha API client for fetching portfolio data."""

import threading
import time
from typing import Any

from ..logging_config import logger


class ZerodhaAPIClient:
    """Client for Zerodha KiteConnect API operations."""

    def __init__(self, auth_manager, holdings_service, sip_service):
        """Initialize the client with required service dependencies.

        Args:
            auth_manager: AuthenticationManager instance
            holdings_service: HoldingsService instance
            sip_service: SIPService instance
        """
        self.auth_manager = auth_manager
        self.holdings_service = holdings_service
        self.sip_service = sip_service

    def fetch_account_data(
        self,
        account_config: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetch holdings and SIPs for a single authenticated account.

        Args:
            account_config: Account configuration dict with name and credentials

        Returns:
            Tuple of (stock_holdings, mf_holdings, sips)

        Raises:
            RuntimeError: If authentication fails
            Exception: Propagated from KiteConnect API calls
        """
        kite = self.auth_manager.authenticate(account_config)
        stock_holdings, mf_holdings = self.holdings_service.fetch_holdings(kite)
        sips = self.sip_service.fetch_sips(kite)
        return stock_holdings, mf_holdings, sips

    def _process_account(
        self,
        account_config: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str | None]:
        """Fetch data for a single account and add account info.

        Args:
            account_config: Account configuration dict with name and credentials

        Returns:
            Tuple of (stock_holdings, mf_holdings, sips, error_message)
            error_message is None if no errors occurred
        """
        account_name = account_config["name"]
        t0 = time.monotonic()
        try:
            stock_holdings, mf_holdings, sips = self.fetch_account_data(account_config)
            self.holdings_service.add_account_info(stock_holdings, account_name)
            self.holdings_service.add_account_info(mf_holdings, account_name)
            self.sip_service.add_account_info(sips, account_name)
            logger.info(
                "Account %s fetched in %.2fs: stocks=%d mf=%d sips=%d",
                account_name,
                time.monotonic() - t0,
                len(stock_holdings),
                len(mf_holdings),
                len(sips),
            )
            return stock_holdings, mf_holdings, sips, None
        except Exception as e:
            logger.error("Error fetching holdings for %s in %.2fs: %s", account_name, time.monotonic() - t0, e)
            return [], [], [], str(e)

    def fetch_all_accounts_data(
        self,
        accounts_config: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str | None]:
        """Fetch holdings and SIPs for all accounts in parallel.

        All accounts passed here are expected to have valid sessions.

        Args:
            accounts_config: List of account configuration dicts (pre-filtered
                as authenticated)

        Returns:
            Tuple of (merged_stock_holdings, merged_mf_holdings, merged_sips, error_message)
            error_message is None if no errors occurred
        """
        if not accounts_config:
            return [], [], [], None

        n = len(accounts_config)
        _ResultSlot = tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str | None]
        results: list[_ResultSlot | None] = [None] * n  # Each slot: (stocks, mfs, sips, error)
        t0 = time.monotonic()

        def _fetch_one(idx: int, account_config: dict[str, Any]):
            results[idx] = self._process_account(account_config)

        if n == 1:
            # Single account — avoid threading overhead
            _fetch_one(0, accounts_config[0])
        else:
            logger.info("Parallel fetch for %d authenticated accounts", n)
            threads = [
                threading.Thread(target=_fetch_one, args=(i, acc), daemon=True) for i, acc in enumerate(accounts_config)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Collect results
        all_stock_holdings = []
        all_mf_holdings = []
        all_sips = []
        first_error = None
        error_count = 0

        for result_slot in results:
            if result_slot is None:
                continue
            stocks, mfs, sips, err = result_slot
            all_stock_holdings.append(stocks)
            all_mf_holdings.append(mfs)
            all_sips.append(sips)
            if err:
                error_count += 1
                if not first_error:
                    first_error = err

        merged_stocks, merged_mfs = self.holdings_service.merge_holdings(all_stock_holdings, all_mf_holdings)
        merged_sips = self.sip_service.merge_items(all_sips)

        logger.info(
            "fetch_all_accounts: %d accounts in %.2fs → stocks=%d mf=%d sips=%d errors=%d",
            n,
            time.monotonic() - t0,
            len(merged_stocks),
            len(merged_mfs),
            len(merged_sips),
            error_count,
        )

        return merged_stocks, merged_mfs, merged_sips, first_error
