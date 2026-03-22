"""
Market data client – Yahoo Finance stock/ETF quotes and index/commodity data.
NSE is used only for fetching the Nifty 50 constituent symbol list.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from ..constants import (
    NSE_BASE_URL,
    NSE_REQUEST_TIMEOUT,
    YF_BASE_URL,
    YF_BATCH_MAX_WORKERS,
    YF_MAX_RETRIES,
    YF_RETRY_BASE_DELAY,
)
from ..logging_config import logger


class MarketDataClient:
    """Client for stock/ETF quotes and market index data.

    NSE India is used for individual symbol lookups (returns LTP + ISIN).
    Yahoo Finance is used for bulk async LTP fetching (batch-capable).
    """

    # Shared NSE session across all instances (cookies persist between calls).
    _nse_session: "requests.Session | None" = None
    _nse_session_lock = threading.Lock()

    def __init__(self):
        """Initialize the market data client."""
        self.base_url = NSE_BASE_URL
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{NSE_BASE_URL}/",
        }
        self.timeout = NSE_REQUEST_TIMEOUT

    def _create_session(self) -> requests.Session:
        """Create and initialise an NSE session by visiting the homepage for cookies."""
        try:
            session = requests.Session()
            session.get(self.base_url, headers=self.headers, timeout=self.timeout)
            return session
        except Timeout:
            logger.warning("NSE website is slow to respond (timeout after %ds)", self.timeout)
            raise
        except ConnectionError:
            logger.warning("Cannot connect to NSE website (network issue)")
            raise
        except Exception as e:
            logger.error("Error creating NSE session: %s", str(e))
            raise

    def _get_nse_session(self) -> "requests.Session":
        """Return the shared NSE session, creating it if absent."""
        with MarketDataClient._nse_session_lock:
            if MarketDataClient._nse_session is None:
                MarketDataClient._nse_session = self._create_session()
            return MarketDataClient._nse_session

    def _refresh_nse_session(self) -> "requests.Session":
        """Force-create a fresh NSE session (called on cookie expiry / 403)."""
        with MarketDataClient._nse_session_lock:
            MarketDataClient._nse_session = self._create_session()
            return MarketDataClient._nse_session

    def fetch_nifty50_symbols(self) -> list[str]:
        """Fetch Nifty 50 constituent symbols from NSE API.

        Returns:
            List of stock symbols in the Nifty 50 index
        """
        try:
            session = self._create_session()
            url = f"{self.base_url}/api/equity-stockIndices?index=NIFTY%2050"
            response = session.get(url, headers=self.headers, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                symbols = [
                    item.get("symbol")
                    for item in data.get("data", [])
                    if item.get("symbol") and item.get("symbol") != "NIFTY 50"
                ]
                return symbols
            else:
                logger.warning("Failed to fetch Nifty 50 symbols: HTTP %s", response.status_code)
                return []

        except Timeout:
            logger.warning("NSE website timeout while fetching Nifty 50 symbols (server slow)")
            return []
        except ConnectionError:
            logger.warning("Cannot connect to NSE website to fetch Nifty 50 symbols")
            return []
        except Exception as e:
            logger.error("Error fetching Nifty 50 symbols: %s", str(e))
            return []

    # ------------------------------------------------------------------
    # NSE India – Single symbol quote (LTP + ISIN)
    # ------------------------------------------------------------------

    def fetch_nse_quote(self, symbol: str) -> dict[str, Any] | None:
        """Fetch quote data + ISIN for a single NSE stock/ETF symbol.

        Uses the NSE ``quote-equity`` endpoint which returns both price data
        and the ISIN in one call.  Retries once with a fresh session on 403
        (expired cookie).

        Returns a dict with ``ltp``, ``change``, ``pChange``, ``isin`` and
        ``symbol``, or ``None`` on any failure.
        """
        url = f"{self.base_url}/api/quote-equity?symbol={quote(symbol)}"
        logger.debug("Fetching NSE quote for %s", symbol)

        for attempt in range(2):
            try:
                session = self._get_nse_session() if attempt == 0 else self._refresh_nse_session()
                resp = session.get(url, headers=self.headers, timeout=self.timeout)

                if resp.status_code == 403 and attempt == 0:
                    logger.debug("NSE 403 for %s — refreshing session and retrying", symbol)
                    continue

                if resp.status_code != 200:
                    logger.warning("NSE HTTP %d for %s", resp.status_code, symbol)
                    return None

                data = resp.json()
                price_info = data.get("priceInfo", {})
                ltp = price_info.get("lastPrice", 0)
                if not ltp:
                    return None

                return {
                    "symbol": symbol,
                    "ltp": round(float(ltp), 2),
                    "change": round(float(price_info.get("change", 0)), 2),
                    "pChange": round(float(price_info.get("pChange", 0)), 2),
                    "isin": data.get("info", {}).get("isin", "").strip().upper(),
                }

            except (Timeout, ConnectionError) as e:
                logger.warning("NSE quote network error for %s: %s", symbol, e)
                return None
            except Exception as e:
                logger.error("Unexpected NSE quote error for %s: %s", symbol, e, exc_info=True)
                return None

        return None

    # ------------------------------------------------------------------
    # Yahoo Finance – Stock / ETF quotes
    # ------------------------------------------------------------------

    @staticmethod
    def _nse_to_yf_symbol(symbol: str) -> str:
        """Convert an NSE symbol to its Yahoo Finance equivalent (.NS suffix)."""
        return f"{symbol}.NS"

    @staticmethod
    def _yf_to_nse_symbol(yf_symbol: str) -> str:
        """Strip the .NS suffix to recover the original NSE symbol."""
        return yf_symbol.removesuffix(".NS")

    def _fetch_yf_stock_quote(self, symbol: str) -> dict[str, Any]:
        """Fetch a single stock quote from Yahoo Finance with retry logic.

        Uses the v8/finance/chart endpoint (same as market-index fetching)
        with exponential-backoff retries on transient failures.

        Args:
            symbol: NSE stock/ETF symbol (e.g. ``INFY``, ``NIFTYBEES``).

        Returns:
            Dictionary with quote data (same shape as ``_empty_stock_data``).
        """
        yf_symbol = self._nse_to_yf_symbol(symbol)
        encoded = quote(yf_symbol, safe="")
        url = f"{YF_BASE_URL}/v8/finance/chart/{encoded}?interval=5m&range=1d"
        yf_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Accept": "application/json",
        }

        logger.debug("Fetching Yahoo Finance quote for %s (url=%s)", symbol, url)

        for attempt in range(1, YF_MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=yf_headers, timeout=self.timeout)

                if resp.status_code == 429:
                    delay = YF_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Yahoo Finance rate-limited for %s, retry in %.1fs (%d/%d)",
                        symbol,
                        delay,
                        attempt,
                        YF_MAX_RETRIES,
                    )
                    time.sleep(delay)
                    continue

                if resp.status_code != 200:
                    if attempt < YF_MAX_RETRIES:
                        delay = YF_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            "Yahoo Finance HTTP %d for %s, retry in %.1fs (%d/%d)",
                            resp.status_code,
                            symbol,
                            delay,
                            attempt,
                            YF_MAX_RETRIES,
                        )
                        time.sleep(delay)
                        continue
                    logger.warning(
                        "Yahoo Finance HTTP %d for %s after %d attempts",
                        resp.status_code,
                        symbol,
                        YF_MAX_RETRIES,
                    )
                    return self._empty_stock_data(symbol)

                chart_result = resp.json().get("chart", {}).get("result", [])
                if not chart_result:
                    logger.warning(
                        "Yahoo Finance returned empty chart data for %s",
                        symbol,
                    )
                    return self._empty_stock_data(symbol)

                parsed = self._parse_yf_chart(symbol, chart_result[0])
                logger.debug(
                    "Yahoo Finance quote for %s: ltp=%s change=%s",
                    symbol,
                    parsed.get("ltp"),
                    parsed.get("change"),
                )
                return parsed

            except Timeout as e:
                if attempt < YF_MAX_RETRIES:
                    delay = YF_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Timeout fetching %s, retry in %.1fs (%d/%d): %s",
                        symbol,
                        delay,
                        attempt,
                        YF_MAX_RETRIES,
                        e,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "Timeout fetching %s after %d attempts: %s",
                    symbol,
                    YF_MAX_RETRIES,
                    e,
                )
            except ConnectionError as e:
                if attempt < YF_MAX_RETRIES:
                    delay = YF_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Connection error for %s, retry in %.1fs (%d/%d): %s",
                        symbol,
                        delay,
                        attempt,
                        YF_MAX_RETRIES,
                        e,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "Connection error for %s after %d attempts: %s",
                    symbol,
                    YF_MAX_RETRIES,
                    e,
                )
            except RequestException as e:
                logger.warning("Request failed for %s: %s", symbol, e)
            except Exception as e:
                logger.error(
                    "Unexpected error fetching %s from Yahoo Finance: %s",
                    symbol,
                    e,
                    exc_info=True,
                )

            return self._empty_stock_data(symbol)

        # All retry attempts exhausted (e.g. all were 429s)
        logger.warning(
            "All %d retry attempts exhausted for %s (rate-limited)",
            YF_MAX_RETRIES,
            symbol,
        )
        return self._empty_stock_data(symbol)

    @staticmethod
    def _parse_yf_chart(symbol: str, chart_data: dict) -> dict[str, Any]:
        """Extract quote fields from a Yahoo Finance v8/chart result entry."""
        meta = chart_data.get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
        change = round(price - prev_close, 2) if price and prev_close else 0
        pchange = round((change / prev_close) * 100, 2) if prev_close else 0

        # Extract intraday OHLC from chart indicators
        quotes = chart_data.get("indicators", {}).get("quote", [{}])[0]
        opens = [v for v in (quotes.get("open") or []) if v is not None]
        highs = [v for v in (quotes.get("high") or []) if v is not None]
        lows = [v for v in (quotes.get("low") or []) if v is not None]

        return {
            "symbol": symbol,
            "name": meta.get("shortName") or meta.get("longName") or symbol,
            "ltp": round(price, 2) if price else 0,
            "change": change,
            "pChange": pchange,
            "open": round(opens[0], 2) if opens else 0,
            "high": round(max(highs), 2) if highs else 0,
            "low": round(min(lows), 2) if lows else 0,
            "close": round(prev_close, 2) if prev_close else 0,
        }

    def fetch_stock_quote(self, symbol: str) -> dict[str, Any]:
        """Fetch quote data for a single stock symbol via Yahoo Finance.

        Args:
            symbol: NSE stock/ETF symbol.

        Returns:
            Dictionary containing stock quote data.
        """
        logger.info("Fetching stock quote for %s", symbol)
        data = self._fetch_yf_stock_quote(symbol)
        if data.get("ltp"):
            logger.info("Stock quote for %s: ltp=%s", symbol, data["ltp"])
        else:
            logger.warning("No LTP returned for %s", symbol)
        return data

    def _empty_stock_data(self, symbol: str) -> dict[str, Any]:
        """Return empty stock data structure for error cases.

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with zero values for all price fields
        """
        return {
            "symbol": symbol,
            "name": symbol,
            "ltp": 0,
            "change": 0,
            "pChange": 0,
            "open": 0,
            "high": 0,
            "low": 0,
            "close": 0,
        }

    # ------------------------------------------------------------------
    # Batch quote fetching via Yahoo Finance (concurrent)
    # ------------------------------------------------------------------

    def fetch_stock_quotes(
        self, symbols: list, timeout: int | None = None, cancel: threading.Event | None = None
    ) -> dict:
        """Fetch quotes for multiple symbols concurrently via Yahoo Finance.

        Uses a thread pool to fetch quotes in parallel. Each individual
        symbol request has its own retry logic with exponential backoff.

        Args:
            symbols: List of NSE stock/ETF symbols to fetch.
            timeout: Optional per-request timeout override (seconds).
            cancel:  Optional threading.Event; when set pending work stops.

        Returns:
            Dict mapping each successfully-resolved symbol to its quote data.
            Symbols that fail are omitted from the result.
        """
        if not symbols:
            return {}

        logger.info(
            "Yahoo Finance batch fetch: %d symbols (timeout=%s)",
            len(symbols),
            timeout,
        )

        saved_timeout = self.timeout
        if timeout is not None:
            self.timeout = timeout

        try:
            result: dict[str, Any] = {}
            failed: list = []

            with ThreadPoolExecutor(max_workers=YF_BATCH_MAX_WORKERS) as executor:
                future_to_sym = {}
                for sym in symbols:
                    if cancel and cancel.is_set():
                        break
                    future_to_sym[executor.submit(self._fetch_yf_stock_quote, sym)] = sym

                logger.debug(
                    "Submitted %d symbols to thread pool (workers=%d)",
                    len(future_to_sym),
                    YF_BATCH_MAX_WORKERS,
                )

                for future in as_completed(future_to_sym):
                    if cancel and cancel.is_set():
                        logger.info(
                            "Batch fetch cancelled after %d/%d symbols",
                            len(result),
                            len(symbols),
                        )
                        break
                    sym = future_to_sym[future]
                    try:
                        data = future.result()
                        if data and data.get("ltp"):
                            result[sym] = data
                        else:
                            logger.debug("No LTP in response for %s", sym)
                            failed.append(sym)
                    except Exception as exc:
                        logger.error(
                            "Yahoo Finance fetch error for %s: %s",
                            sym,
                            exc,
                            exc_info=True,
                        )
                        failed.append(sym)

            if failed:
                logger.info("No LTP for %d symbols: %s", len(failed), failed)
            logger.info(
                "Yahoo Finance batch fetch done: %d/%d symbols successful",
                len(result),
                len(symbols),
            )
            return result
        finally:
            if timeout is not None:
                self.timeout = saved_timeout

    # ------------------------------------------------------------------
    # Market index data (NIFTY 50 + SENSEX) via Yahoo Finance
    # ------------------------------------------------------------------

    _YF_SYMBOLS = {
        "nifty50": ("%5ENSEI", "NIFTY 50"),
        "sensex": ("%5EBSESN", "SENSEX"),
        "sp500": ("%5EGSPC", "S&P 500"),
        "gold": ("GC%3DF", "GOLD"),
        "silver": ("SI%3DF", "SILVER"),
        "usdinr": ("INR%3DX", "USD/INR"),
    }

    def fetch_market_indices(self) -> dict[str, Any]:
        """Fetch NIFTY 50 and SENSEX index data with intraday charts.

        Uses Yahoo Finance for both indices – single reliable source that
        returns price metadata and intraday chart in one request.

        Returns:
            Dictionary with 'nifty50' and 'sensex' keys.
        """
        logger.info("Fetching market indices: %s", list(self._YF_SYMBOLS.keys()))
        result: dict[str, Any] = {key: self._empty_index_data(label) for key, (_, label) in self._YF_SYMBOLS.items()}
        for key, (yf_sym, label) in self._YF_SYMBOLS.items():
            self._fetch_yf_index(result, key, yf_sym, label)
        fetched = [k for k, v in result.items() if v.get("value")]
        logger.info(
            "Market indices fetched: %d/%d successful (%s)",
            len(fetched),
            len(self._YF_SYMBOLS),
            fetched,
        )
        return result

    def _fetch_yf_index(
        self,
        result: dict[str, Any],
        key: str,
        yf_symbol: str,
        display_name: str,
    ) -> None:
        """Fetch a single index from Yahoo Finance and populate *result[key]*."""
        try:
            yf_headers = {
                "User-Agent": self.headers["User-Agent"],
                "Accept": "application/json",
            }
            url = f"{YF_BASE_URL}/v8/finance/chart/{yf_symbol}?interval=5m&range=1d"
            logger.debug("Fetching index %s from Yahoo Finance", display_name)
            resp = requests.get(url, headers=yf_headers, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(
                    "Yahoo Finance returned HTTP %d for %s",
                    resp.status_code,
                    display_name,
                )
                return

            chart_result = resp.json().get("chart", {}).get("result", [])
            if not chart_result:
                logger.warning(
                    "Yahoo Finance returned empty chart data for index %s",
                    display_name,
                )
                return

            meta = chart_result[0].get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("previousClose", 0)
            change = round(price - prev_close, 2) if price and prev_close else 0
            pchange = round((change / prev_close) * 100, 2) if prev_close else 0

            # Intraday close prices for sparkline
            quotes = chart_result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = quotes.get("close", [])
            valid_closes = [c for c in closes if c is not None]

            chart_data: list[float] = []
            if valid_closes:
                step = max(1, len(valid_closes) // 50)
                chart_data = [round(c, 2) for c in valid_closes[::step]]

            result[key] = {
                "name": display_name,
                "value": round(price, 2),
                "change": change,
                "pChange": pchange,
                "chart": chart_data,
            }
            logger.debug(
                "Index %s fetched: value=%s change=%s",
                display_name,
                round(price, 2),
                change,
            )
        except Timeout as e:
            logger.warning(
                "Timeout fetching %s from Yahoo Finance: %s",
                display_name,
                e,
            )
        except ConnectionError as e:
            logger.warning(
                "Connection error fetching %s from Yahoo Finance: %s",
                display_name,
                e,
            )
        except Exception as e:
            logger.error(
                "Unexpected error fetching index %s: %s",
                display_name,
                e,
                exc_info=True,
            )

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _empty_index_data(name: str) -> dict[str, Any]:
        """Return empty index data for fallback/error cases."""
        return {
            "name": name,
            "value": 0,
            "change": 0,
            "pChange": 0,
            "chart": [],
        }
