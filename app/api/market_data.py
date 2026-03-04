"""
Market data client – NSE stock quotes and Yahoo Finance indices / commodities.
"""
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from ..constants import NSE_BASE_URL, NSE_REQUEST_DELAY, NSE_REQUEST_TIMEOUT
from ..logging_config import logger


class MarketDataClient:
    """Client for NSE stock quotes and Yahoo Finance market data."""
    
    def __init__(self):
        """Initialize the NSE API client with configuration."""
        self.base_url = NSE_BASE_URL
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        self.timeout = NSE_REQUEST_TIMEOUT
        self.request_delay = NSE_REQUEST_DELAY
    
    def _create_session(self) -> requests.Session:
        """Create and initialize an NSE session with cookies.
        
        Returns:
            Configured requests.Session instance
        """
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
    
    def fetch_nifty50_symbols(self) -> List[str]:
        """Fetch Nifty 50 constituent symbols from NSE API.
        
        Returns:
            List of stock symbols in the Nifty 50 index
        """
        try:
            session = self._create_session()
            url = f'{self.base_url}/api/equity-stockIndices?index=NIFTY%2050'
            response = session.get(url, headers=self.headers, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                symbols = [
                    item.get('symbol')
                    for item in data.get('data', [])
                    if item.get('symbol') and item.get('symbol') != 'NIFTY 50'
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
    
    def fetch_stock_quote(self, session: requests.Session, symbol: str) -> Dict[str, Any]:
        """Fetch quote data for a single stock symbol.
        
        Args:
            session: Requests session object with active NSE cookies
            symbol: Stock symbol to fetch
            
        Returns:
            Dictionary containing stock quote data
        """
        try:
            encoded_symbol = quote(symbol)
            url = f"{self.base_url}/api/quote-equity?symbol={encoded_symbol}"
            response = session.get(url, headers=self.headers, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                price_info = data.get('priceInfo', {})
                return {
                    'symbol': symbol,
                    'name': data.get('info', {}).get('companyName', symbol),
                    'ltp': price_info.get('lastPrice', 0),
                    'change': price_info.get('change', 0),
                    'pChange': price_info.get('pChange', 0),
                    'open': price_info.get('open', 0),
                    'high': price_info.get('intraDayHighLow', {}).get('max', 0),
                    'low': price_info.get('intraDayHighLow', {}).get('min', 0),
                    'close': price_info.get('previousClose', 0)
                }
            else:
                logger.warning("NSE API returned status %d for %s", response.status_code, symbol)
                return self._empty_stock_data(symbol)
        except Timeout:
            logger.warning("Request timeout for %s (NSE server slow to respond)", symbol)
            return self._empty_stock_data(symbol)
        except ConnectionError:
            logger.warning("Connection error for %s (NSE server unreachable)", symbol)
            return self._empty_stock_data(symbol)
        except RequestException as e:
            logger.warning("Request failed for %s: %s", symbol, str(e))
            return self._empty_stock_data(symbol)
        except Exception as e:
            logger.error("Unexpected error fetching %s: %s", symbol, str(e))
            return self._empty_stock_data(symbol)
        finally:
            time.sleep(self.request_delay)
    
    def _empty_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Return empty stock data structure for error cases.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with zero values for all price fields
        """
        return {
            'symbol': symbol,
            'name': symbol,
            'ltp': 0,
            'change': 0,
            'pChange': 0,
            'open': 0,
            'high': 0,
            'low': 0,
            'close': 0
        }

    # ------------------------------------------------------------------
    # Batch quote fetching (for manual stock/ETF enrichment)
    # ------------------------------------------------------------------

    def fetch_stock_quotes(self, symbols: list, timeout: int = None,
                           cancel: Optional[threading.Event] = None) -> dict:
        """Fetch quotes for multiple symbols in a single NSE session.

        Args:
            symbols: List of NSE stock symbols to fetch.
            timeout: Optional per-request timeout override (seconds).
            cancel:  Optional threading.Event; when set the loop stops early.

        Returns a dict mapping each symbol to its quote data dict.
        Symbols that fail to fetch are omitted from the result.
        """
        if not symbols:
            return {}

        logger.info("Batch quote fetch: %d symbols (timeout=%s)", len(symbols), timeout)

        saved_timeout = self.timeout
        if timeout is not None:
            self.timeout = timeout

        try:
            session = self._create_session()
            logger.info("NSE session created for batch quote fetch")
        except Exception:
            logger.warning("Could not create NSE session for batch quote fetch")
            return {}
        finally:
            if timeout is not None:
                self.timeout = saved_timeout

        result = {}
        failed: list = []
        for symbol in symbols:
            if cancel and cancel.is_set():
                logger.info("Batch quote fetch cancelled after %d/%d symbols",
                            len(result), len(symbols))
                break
            data = self.fetch_stock_quote(session, symbol)
            if data and data.get('ltp'):
                result[symbol] = data
            else:
                failed.append(symbol)

        if failed:
            logger.info("No LTP for %d symbols: %s", len(failed), failed)
        logger.info("Batch quote fetch done: %d/%d symbols successful",
                    len(result), len(symbols))
        return result

    # ------------------------------------------------------------------
    # Market index data (NIFTY 50 + SENSEX) via Yahoo Finance
    # ------------------------------------------------------------------

    _YF_SYMBOLS = {
        'nifty50': ('%5ENSEI', 'NIFTY 50'),
        'sensex':  ('%5EBSESN', 'SENSEX'),
        'sp500':   ('%5EGSPC', 'S&P 500'),
        'gold':    ('GC%3DF', 'GOLD'),
        'silver':  ('SI%3DF', 'SILVER'),
        'usdinr':  ('INR%3DX', 'USD/INR'),
    }

    def fetch_market_indices(self) -> Dict[str, Any]:
        """Fetch NIFTY 50 and SENSEX index data with intraday charts.

        Uses Yahoo Finance for both indices – single reliable source that
        returns price metadata and intraday chart in one request.

        Returns:
            Dictionary with 'nifty50' and 'sensex' keys.
        """
        result: Dict[str, Any] = {
            key: self._empty_index_data(label)
            for key, (_, label) in self._YF_SYMBOLS.items()
        }
        for key, (yf_sym, label) in self._YF_SYMBOLS.items():
            self._fetch_yf_index(result, key, yf_sym, label)
        return result

    def _fetch_yf_index(
        self,
        result: Dict[str, Any],
        key: str,
        yf_symbol: str,
        display_name: str,
    ) -> None:
        """Fetch a single index from Yahoo Finance and populate *result[key]*."""
        try:
            yf_headers = {
                'User-Agent': self.headers['User-Agent'],
                'Accept': 'application/json',
            }
            url = (
                f'https://query1.finance.yahoo.com/v8/finance/chart/'
                f'{yf_symbol}?interval=5m&range=1d'
            )
            resp = requests.get(url, headers=yf_headers, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(
                    "Yahoo Finance returned %d for %s", resp.status_code, display_name
                )
                return

            chart_result = (
                resp.json().get('chart', {}).get('result', [])
            )
            if not chart_result:
                return

            meta = chart_result[0].get('meta', {})
            price = meta.get('regularMarketPrice', 0)
            prev_close = meta.get('previousClose', 0)
            change = round(price - prev_close, 2) if price and prev_close else 0
            pchange = (
                round((change / prev_close) * 100, 2) if prev_close else 0
            )

            # Intraday close prices for sparkline
            quotes = (
                chart_result[0]
                .get('indicators', {})
                .get('quote', [{}])[0]
            )
            closes = quotes.get('close', [])
            valid_closes = [c for c in closes if c is not None]

            chart_data: List[float] = []
            if valid_closes:
                step = max(1, len(valid_closes) // 50)
                chart_data = [round(c, 2) for c in valid_closes[::step]]

            result[key] = {
                'name': display_name,
                'value': round(price, 2),
                'change': change,
                'pChange': pchange,
                'chart': chart_data,
            }
        except Timeout:
            logger.warning("Timeout fetching %s from Yahoo Finance", display_name)
        except ConnectionError:
            logger.warning("Connection error fetching %s", display_name)
        except Exception as e:
            logger.warning("Error fetching %s: %s", display_name, str(e))

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _empty_index_data(name: str) -> Dict[str, Any]:
        """Return empty index data for fallback/error cases."""
        return {
            'name': name,
            'value': 0,
            'change': 0,
            'pChange': 0,
            'chart': [],
        }
