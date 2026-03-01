"""
Google Sheets API client for fetching physical gold holdings data.
"""
from typing import Any, Dict, List

from ..constants import GOOGLE_SHEETS_SCOPES, GOOGLE_SHEETS_TIMEOUT
from ..error_handler import (APIError, DataError, ErrorHandler, NetworkError,
                             retry_on_transient_error)
from ..logging_config import logger

try:
    import httplib2
    from google.oauth2 import service_account
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    logger.warning("Google Sheets API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")


class GoogleSheetsClient:
    """Client for fetching data from Google Sheets."""
    
    SCOPES = GOOGLE_SHEETS_SCOPES
    TIMEOUT_SECONDS = GOOGLE_SHEETS_TIMEOUT
    
    def __init__(self, credentials_file: str = None):
        """Initialize Google Sheets client.
        
        Args:
            credentials_file: Path to service account credentials JSON file
        """
        if not GOOGLE_SHEETS_AVAILABLE:
            raise ImportError("Google Sheets libraries not installed")
        
        if not credentials_file:
            raise ValueError("Credentials file is required")
            
        self.credentials_file = credentials_file
        self.credentials = None
        self.service = None
        self._is_authenticated = False
    
    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API (cached for connection pooling)."""
        if self._is_authenticated and self.service:
            return True
        
        try:
            if not self.credentials:
                self.credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_file, scopes=self.SCOPES)
            
            http = httplib2.Http(timeout=self.TIMEOUT_SECONDS, cache=None)
            self.service = build('sheets', 'v4', 
                                http=AuthorizedHttp(self.credentials, http=http), 
                                cache_discovery=False)
            self._is_authenticated = True
            logger.info("Successfully authenticated with Google Sheets API")
            return True
        except Exception as e:
            logger.exception("Failed to authenticate with Google Sheets")
            raise
    
    def fetch_sheet_data(self, spreadsheet_id: str, range_name: str,
                         max_retries: int = 2) -> List[List[Any]]:
        """Fetch data from Google Sheet with retry logic."""
        self.authenticate()
        
        @retry_on_transient_error(max_retries=max_retries, delay=1.0)
        def _fetch():
            return self._fetch_sheet_data_impl(spreadsheet_id, range_name)
        
        try:
            return _fetch()
        except Exception as e:
            ErrorHandler.log_error(e, context=f"Fetching Google Sheets range {range_name}")
            raise
    
    def _fetch_sheet_data_impl(self, spreadsheet_id: str, range_name: str) -> List[List[Any]]:
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name).execute()
            values = result.get('values', [])
            logger.info("Fetched %d rows from Google Sheets range %s", len(values), range_name)
            return values
        except HttpError as e:
            status = e.resp.status if hasattr(e, 'resp') else None
            error_type = "transient error" if status and status >= 500 else "error"
            raise APIError(f"Google Sheets API {error_type}", status_code=status, original_error=e)
        except OSError as e:
            if e.errno == 49:
                logger.warning("Network port exhaustion - usually temporary")
            raise NetworkError(f"Network connection error: {e}", original_error=e)
        except Exception as e:
            logger.exception("Unexpected error fetching Google Sheets data")
            raise
    
    def fetch_sheet_data_until_blank(self, spreadsheet_id: str, sheet_name: str,
                                      max_rows: int = 1000, max_retries: int = 2) -> List[List[Any]]:
        """Fetch data from sheet, trimming at first completely empty row."""
        raw_data = self.fetch_sheet_data(spreadsheet_id, f"{sheet_name}!A1:Z{max_rows}", max_retries)
        
        if not raw_data or len(raw_data) < 2:
            return raw_data
        
        trimmed_data = [raw_data[0]]
        for row in raw_data[1:]:
            if not row or all(not v or str(v).strip() == '' for v in row):
                break
            trimmed_data.append(row)
        
        logger.info("Fetched and trimmed to %d rows", len(trimmed_data))
        return trimmed_data
    
    def batch_fetch_sheet_data(self, spreadsheet_id: str, ranges: List[str],
                               max_retries: int = 2) -> Dict[str, List[List[Any]]]:
        """Fetch multiple ranges in a single batch request."""
        self.authenticate()
        
        @retry_on_transient_error(max_retries=max_retries, delay=1.0)
        def _batch_fetch():
            return self._batch_fetch_impl(spreadsheet_id, ranges)
        
        try:
            return _batch_fetch()
        except Exception as e:
            ErrorHandler.log_error(e, context=f"Batch fetching ranges: {ranges}")
            raise
    
    def _batch_fetch_impl(self, spreadsheet_id: str, ranges: List[str]) -> Dict[str, List[List[Any]]]:
        try:
            result = self.service.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id, ranges=ranges).execute()
            
            batch_data = {}
            for vr in result.get('valueRanges', []):
                batch_data[vr.get('range', '')] = vr.get('values', [])
                logger.info("Batch fetched %d rows from range %s", len(vr.get('values', [])), vr.get('range'))
            return batch_data
        except HttpError as e:
            status = e.resp.status if hasattr(e, 'resp') else None
            error_type = "transient error" if status and status >= 500 else "error"
            raise APIError(f"Google Sheets API {error_type}", status_code=status, original_error=e)
        except OSError as e:
            if e.errno == 49:
                logger.warning("Network port exhaustion - usually temporary")
            raise NetworkError(f"Network connection error: {e}", original_error=e)
        except Exception as e:
            logger.exception("Unexpected error batch fetching Google Sheets data")
            raise
    
    @staticmethod
    def parse_number(value: Any) -> float:
        """Parse cell value to float, handling various formats."""
        if not value or value == '':
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                cleaned = value.strip().translate(str.maketrans('', '', '₹,%s '))
                return float(cleaned)
            except (ValueError, AttributeError):
                return 0.0
        return 0.0
    
    @staticmethod
    def parse_yes_no(value: Any) -> bool:
        """Parse cell value to boolean for Yes/No fields."""
        return isinstance(value, str) and value.strip().lower() in ('yes', 'y', 'true', '1')


class GoogleSheetsService:
    """Base class for services that fetch and parse data from Google Sheets."""

    entity_name: str = "items"

    def __init__(self, google_sheets_client: GoogleSheetsClient):
        """Initialize service with Google Sheets client."""
        self.client = google_sheets_client

    @staticmethod
    def _safe_get(row: List[Any], index: int, default: Any = '', parser=None) -> Any:
        """Safely get a cell value from a row with optional parsing.

        Args:
            row: Row data from Google Sheets
            index: Column index
            default: Default value if index is out of range
            parser: Optional callable to parse the value

        Returns:
            Parsed cell value, or default if index is out of range
        """
        if len(row) <= index:
            return default
        return parser(row[index]) if parser else row[index]

    def _parse_row(self, row: List[Any], idx: int) -> Dict[str, Any]:
        """Parse a single row. Subclasses must override this."""
        raise NotImplementedError

    def _fetch_and_parse(
        self,
        spreadsheet_id: str,
        range_name: str,
    ) -> List[Dict[str, Any]]:
        """Fetch sheet data and parse rows using the subclass parser.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The A1 notation range to fetch

        Returns:
            List of parsed row dictionaries
        """
        raw_data = self.client.fetch_sheet_data(spreadsheet_id, range_name)

        if not raw_data or len(raw_data) < 2:
            logger.info("No %s data found", self.entity_name)
            return []

        items = []
        for idx, row in enumerate(raw_data[1:], start=2):  # Skip header
            if not row or not any(row):
                continue
            try:
                items.append(self._parse_row(row, idx))
            except Exception as e:
                logger.warning("Error parsing %s row %d: %s", self.entity_name, idx, e)

        logger.info("Parsed %d %s", len(items), self.entity_name)
        return items

    def _fetch_and_parse_until_blank(self, spreadsheet_id: str, sheet_name: str) -> List[Dict[str, Any]]:
        """Fetch and parse sheet data until blank row."""
        raw_data = self.client.fetch_sheet_data_until_blank(spreadsheet_id, sheet_name)
        return self._parse_rows(raw_data)

    def _parse_rows(self, raw_data: List[List[Any]]) -> List[Dict[str, Any]]:
        """Trim empty rows and parse data."""
        if not raw_data or len(raw_data) < 2:
            return []

        trimmed_data = [raw_data[0]]
        for row in raw_data[1:]:
            if not row or all(not v or str(v).strip() == '' for v in row):
                break
            trimmed_data.append(row)

        items = []
        for idx, row in enumerate(trimmed_data[1:], start=2):
            if not row or not any(row):
                continue
            try:
                items.append(self._parse_row(row, idx))
            except Exception as e:
                logger.warning("Error parsing %s row %d: %s", self.entity_name, idx, e)
        return items

    def _parse_batch_data(self, raw_data: List[List[Any]]) -> List[Dict[str, Any]]:
        """Parse batch-fetched sheet data, trimming at first empty row."""
        return self._parse_rows(raw_data)


class PhysicalGoldService(GoogleSheetsService):
    entity_name = "physical gold holdings"

    def fetch_holdings(self, spreadsheet_id: str, range_name: str = 'Sheet1!A:F') -> List[Dict[str, Any]]:
        """Fetch physical gold holdings from Google Sheets."""
        sheet_name = range_name.split('!')[0] if '!' in range_name else range_name
        return self._fetch_and_parse_until_blank(spreadsheet_id, sheet_name)

    def _parse_row(self, row: List[Any], idx: int) -> Dict[str, Any]:
        g = self._safe_get
        p = GoogleSheetsClient.parse_number
        return {
            'date': g(row, 0),
            'type': g(row, 1),
            'retail_outlet': g(row, 2),
            'purity': g(row, 3),
            'weight_gms': g(row, 4, 0, p),
            'bought_ibja_rate_per_gm': g(row, 5, 0, p),
            'row_number': idx,
        }


class FixedDepositsService(GoogleSheetsService):
    entity_name = "fixed deposits"

    def fetch_deposits(self, spreadsheet_id: str, range_name: str = 'FixedDeposits!A:K') -> List[Dict[str, Any]]:
        """Fetch fixed deposits from Google Sheets."""
        sheet_name = range_name.split('!')[0] if '!' in range_name else range_name
        return self._fetch_and_parse_until_blank(spreadsheet_id, sheet_name)

    def _parse_row(self, row: List[Any], idx: int) -> Dict[str, Any]:
        g = self._safe_get
        p = GoogleSheetsClient.parse_number
        b = GoogleSheetsClient.parse_yes_no

        deposit = {
            'original_investment_date': g(row, 0),
            'reinvested_date': g(row, 1),
            'bank_name': g(row, 2),
            'deposit_year': g(row, 3, 0, p),
            'deposit_month': g(row, 4, 0, p),
            'deposit_day': g(row, 5, 0, p),
            'original_amount': g(row, 6, 0, p),
            'reinvested_amount': g(row, 7, 0, p),
            'interest_rate': g(row, 8, 0, p),
            'redeemed': g(row, 9, False, b),
            'account': g(row, 10),
        }
        if not deposit['bank_name']:
            raise DataError("Missing bank name in fixed deposit row")
        if deposit['interest_rate'] <= 0:
            raise DataError(f"Invalid interest rate for deposit at {deposit['bank_name']}")
        return deposit
