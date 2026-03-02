"""
Unit tests for API client modules (Market Data and Zerodha)
"""
import unittest
from unittest.mock import Mock, patch

from app.api.market_data import MarketDataClient
from app.api.zerodha_client import ZerodhaAPIClient
from app.constants import NSE_BASE_URL, NSE_REQUEST_DELAY, NSE_REQUEST_TIMEOUT


class TestMarketDataClient(unittest.TestCase):
    """Test Market Data client"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.client = MarketDataClient()
    
    def test_init(self):
        """Test MarketDataClient initialization"""
        self.assertEqual(self.client.base_url, NSE_BASE_URL)
        self.assertIn('User-Agent', self.client.headers)
        self.assertEqual(self.client.timeout, NSE_REQUEST_TIMEOUT)
        self.assertEqual(self.client.request_delay, NSE_REQUEST_DELAY)
    
    @patch('app.api.market_data.requests.Session')
    def test_create_session_success(self, mock_session_class):
        """Test successful session creation"""
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.get.return_value = Mock(status_code=200)
        
        session = self.client._create_session()
        
        self.assertEqual(session, mock_session)
        mock_session.get.assert_called_once_with(
            self.client.base_url,
            headers=self.client.headers,
            timeout=self.client.timeout
        )
    
    @patch('app.api.market_data.requests.Session')
    def test_create_session_failure(self, mock_session_class):
        """Test session creation with error"""
        mock_session_class.return_value.get.side_effect = Exception("Network error")
        
        with self.assertRaises(Exception):
            self.client._create_session()
    
    @patch.object(MarketDataClient, '_create_session')
    def test_fetch_nifty50_symbols_success(self, mock_create_session):
        """Test successful Nifty 50 symbols fetch"""
        mock_session = Mock()
        mock_create_session.return_value = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'symbol': 'RELIANCE'},
                {'symbol': 'TCS'},
                {'symbol': 'NIFTY 50'},  # Should be filtered out
                {'symbol': 'INFY'}
            ]
        }
        mock_session.get.return_value = mock_response
        
        symbols = self.client.fetch_nifty50_symbols()
        
        self.assertEqual(len(symbols), 3)
        self.assertIn('RELIANCE', symbols)
        self.assertIn('TCS', symbols)
        self.assertIn('INFY', symbols)
        self.assertNotIn('NIFTY 50', symbols)
    
    @patch.object(MarketDataClient, '_create_session')
    def test_fetch_nifty50_symbols_http_error(self, mock_create_session):
        """Test Nifty 50 symbols fetch with HTTP error"""
        mock_session = Mock()
        mock_create_session.return_value = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_session.get.return_value = mock_response
        
        symbols = self.client.fetch_nifty50_symbols()
        
        self.assertEqual(symbols, [])
    
    @patch.object(MarketDataClient, '_create_session')
    def test_fetch_nifty50_symbols_exception(self, mock_create_session):
        """Test Nifty 50 symbols fetch with exception"""
        mock_create_session.side_effect = Exception("Connection failed")
        
        symbols = self.client.fetch_nifty50_symbols()
        
        self.assertEqual(symbols, [])
    
    @patch('time.sleep')
    def test_fetch_stock_quote_success(self, mock_sleep):
        """Test successful stock quote fetch"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'info': {'companyName': 'Reliance Industries'},
            'priceInfo': {
                'lastPrice': 2500.50,
                'change': 25.50,
                'pChange': 1.03,
                'open': 2480.00,
                'previousClose': 2475.00,
                'intraDayHighLow': {
                    'max': 2510.00,
                    'min': 2475.00
                }
            }
        }
        mock_session.get.return_value = mock_response
        
        quote = self.client.fetch_stock_quote(mock_session, 'RELIANCE')
        
        self.assertEqual(quote['symbol'], 'RELIANCE')
        self.assertEqual(quote['name'], 'Reliance Industries')
        self.assertEqual(quote['ltp'], 2500.50)
        self.assertEqual(quote['change'], 25.50)
        self.assertEqual(quote['pChange'], 1.03)
        self.assertEqual(quote['open'], 2480.00)
        self.assertEqual(quote['high'], 2510.00)
        self.assertEqual(quote['low'], 2475.00)
        self.assertEqual(quote['close'], 2475.00)
        
        # Verify rate limiting delay
        mock_sleep.assert_called_once_with(0.2)
    
    @patch('time.sleep')
    def test_fetch_stock_quote_http_error(self, mock_sleep):
        """Test stock quote fetch with HTTP error"""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response
        
        quote = self.client.fetch_stock_quote(mock_session, 'INVALID')
        
        # Should return empty stock data
        self.assertEqual(quote['symbol'], 'INVALID')
        self.assertEqual(quote['ltp'], 0)
        self.assertEqual(quote['change'], 0)
    
    @patch('time.sleep')
    def test_fetch_stock_quote_exception(self, mock_sleep):
        """Test stock quote fetch with exception"""
        mock_session = Mock()
        mock_session.get.side_effect = Exception("Network error")
        
        quote = self.client.fetch_stock_quote(mock_session, 'TCS')
        
        # Should return empty stock data
        self.assertEqual(quote['symbol'], 'TCS')
        self.assertEqual(quote['name'], 'TCS')
        self.assertEqual(quote['ltp'], 0)
    
    def test_empty_stock_data(self):
        """Test _empty_stock_data helper"""
        empty_data = self.client._empty_stock_data('TEST')
        
        self.assertEqual(empty_data['symbol'], 'TEST')
        self.assertEqual(empty_data['name'], 'TEST')
        self.assertEqual(empty_data['ltp'], 0)
        self.assertEqual(empty_data['change'], 0)
        self.assertEqual(empty_data['pChange'], 0)
        self.assertEqual(empty_data['open'], 0)
        self.assertEqual(empty_data['high'], 0)
        self.assertEqual(empty_data['low'], 0)
        self.assertEqual(empty_data['close'], 0)


class TestZerodhaAPIClient(unittest.TestCase):
    """Test Zerodha API client"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_auth_manager = Mock()
        self.mock_holdings_service = Mock()
        self.mock_sip_service = Mock()
        
        self.zerodha_client = ZerodhaAPIClient(
            self.mock_auth_manager,
            self.mock_holdings_service,
            self.mock_sip_service
        )
    
    def test_init(self):
        """Test ZerodhaAPIClient initialization"""
        self.assertEqual(self.zerodha_client.auth_manager, self.mock_auth_manager)
        self.assertEqual(self.zerodha_client.holdings_service, self.mock_holdings_service)
        self.assertEqual(self.zerodha_client.sip_service, self.mock_sip_service)
    
    def test_fetch_account_data_success(self):
        """Test successful account data fetch"""
        mock_kite = Mock()
        self.mock_auth_manager.authenticate.return_value = mock_kite
        self.mock_holdings_service.fetch_holdings.return_value = (
            [{'stock': 'data'}],
            [{'mf': 'data'}]
        )
        self.mock_sip_service.fetch_sips.return_value = [{'sip': 'data'}]
        
        account_config = {'name': 'test_account'}
        stocks, mfs, sips = self.zerodha_client.fetch_account_data(account_config)
        
        self.assertEqual(len(stocks), 1)
        self.assertEqual(len(mfs), 1)
        self.assertEqual(len(sips), 1)
        self.mock_auth_manager.authenticate.assert_called_once_with(account_config)
    
    def test_fetch_account_data_exception(self):
        """Test account data fetch with exception"""
        self.mock_auth_manager.authenticate.side_effect = Exception("Auth failed")
        
        account_config = {'name': 'test_account'}
        
        with self.assertRaises(Exception):
            self.zerodha_client.fetch_account_data(account_config)
    
    @patch('threading.Thread')
    def test_fetch_all_accounts_data_success(self, mock_thread_class):
        """Test successful fetch for multiple accounts"""
        # Mock thread execution to run synchronously for testing
        def run_thread_func(target, args, daemon):
            target(*args)
            return Mock(start=Mock(), join=Mock())
        
        mock_thread_class.side_effect = lambda target, args, daemon: \
            Mock(start=Mock(side_effect=lambda: target(*args)), join=Mock())
        
        # Set up mock returns
        self.mock_auth_manager.authenticate.return_value = Mock()
        self.mock_holdings_service.fetch_holdings.return_value = (
            [{'stock': 'A'}],
            [{'mf': 'A'}]
        )
        self.mock_sip_service.fetch_sips.return_value = [{'sip': 'A'}]
        self.mock_holdings_service.add_account_info.return_value = None
        self.mock_sip_service.add_account_info.return_value = None
        self.mock_holdings_service.merge_holdings.return_value = (
            [{'stock': 'merged'}],
            [{'mf': 'merged'}]
        )
        self.mock_sip_service.merge_items.return_value = [{'sip': 'merged'}]
        
        accounts_config = [
            {'name': 'Account1'},
            {'name': 'Account2'}
        ]
        
        stocks, mfs, sips, error = self.zerodha_client.fetch_all_accounts_data(
            accounts_config
        )
        
        # Verify threads were created
        self.assertEqual(mock_thread_class.call_count, 2)
        
        # Verify merge was called
        self.mock_holdings_service.merge_holdings.assert_called_once()
        self.mock_sip_service.merge_items.assert_called_once()
    
    def test_fetch_all_accounts_data_empty_list(self):
        """Test fetch with empty accounts list"""
        self.mock_holdings_service.merge_holdings.return_value = ([], [])
        self.mock_sip_service.merge_items.return_value = []
        
        stocks, mfs, sips, error = self.zerodha_client.fetch_all_accounts_data(
            []
        )
        
        self.assertEqual(stocks, [])
        self.assertEqual(mfs, [])
        self.assertEqual(sips, [])


if __name__ == '__main__':
    unittest.main()
