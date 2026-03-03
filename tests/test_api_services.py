"""
Unit tests for API services
"""
import unittest
from unittest.mock import Mock, patch

from app.api.auth import AuthenticationManager
from app.api.holdings import HoldingsService


class MockKiteConnect:
    """Mock KiteConnect API for testing"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self._access_token = None
        self._mock_holdings = []
        self._mock_mf_holdings = []
        self._mock_mf_instruments = []
        self._mock_mf_sips = []
        self._mock_profile = {"user_id": "TEST123", "user_name": "Test User"}
    
    def set_access_token(self, access_token: str):
        """Mock setting access token"""
        self._access_token = access_token
    
    def holdings(self):
        """Mock holdings API call"""
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_holdings
    
    def mf_holdings(self):
        """Mock MF holdings API call"""
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_mf_holdings
    
    def mf_instruments(self):
        """Mock MF instruments API call"""
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_mf_instruments
    
    def mf_sips(self, sip_id=None):
        """Mock MF SIPs API call"""
        if not self._access_token:
            raise Exception("Not authenticated")
        if sip_id:
            return [sip for sip in self._mock_mf_sips if sip.get('sip_id') == sip_id]
        return self._mock_mf_sips
    
    def profile(self):
        """Mock profile API call"""
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_profile
    
    def login_url(self):
        """Mock login URL generation"""
        return f"https://kite.zerodha.com/connect/login?api_key={self.api_key}"
    
    def generate_session(self, request_token: str, api_secret: str):
        """Mock session generation"""
        return {
            "user_id": "TEST123",
            "access_token": f"mock_token_{request_token}",
            "refresh_token": "mock_refresh_token"
        }
    
    def renew_access_token(self, refresh_token: str, api_secret: str):
        """Mock token renewal"""
        return {
            "access_token": f"renewed_{refresh_token}",
            "refresh_token": "new_refresh_token"
        }


class TestHoldingsService(unittest.TestCase):
    """Test HoldingsService class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.service = HoldingsService()
    
    def test_add_account_info(self):
        """Test adding account information to holdings"""
        holdings = [
            {"quantity": 10, "average_price": 100.0},
            {"quantity": 5, "average_price": 200.0}
        ]
        
        self.service.add_account_info(holdings, "TestAccount")
        
        self.assertEqual(holdings[0]["account"], "TestAccount")
        self.assertEqual(holdings[0]["invested"], 1000.0)
        self.assertEqual(holdings[1]["invested"], 1000.0)
    
    def test_add_account_info_missing_fields(self):
        """Test adding account info with missing fields"""
        holdings = [
            {},  # No quantity or average_price
        ]
        
        self.service.add_account_info(holdings, "TestAccount")
        
        self.assertEqual(holdings[0]["account"], "TestAccount")
        self.assertEqual(holdings[0]["invested"], 0.0)
    
    def test_add_account_info_with_t1_quantity(self):
        """Test adding account info includes T1 quantity"""
        holdings = [
            {"quantity": 10, "t1_quantity": 5, "average_price": 100.0}
        ]
        
        self.service.add_account_info(holdings, "TestAccount")
        
        # Total quantity should include T1
        self.assertEqual(holdings[0]["quantity"], 15)
        self.assertEqual(holdings[0]["invested"], 1500.0)
    
    def test_merge_holdings_single_account(self):
        """Test merging holdings from single account"""
        stock_holdings = [[{"symbol": "RELIANCE"}]]
        mf_holdings = [[{"symbol": "MF1"}]]
        
        merged_stocks, merged_mfs = self.service.merge_holdings(stock_holdings, mf_holdings)
        
        self.assertEqual(len(merged_stocks), 1)
        self.assertEqual(len(merged_mfs), 1)
    
    def test_merge_holdings_multiple_accounts(self):
        """Test merging holdings from multiple accounts"""
        stock_holdings = [
            [{"symbol": "RELIANCE"}],
            [{"symbol": "TCS"}]
        ]
        mf_holdings = [
            [{"symbol": "MF1"}],
            [{"symbol": "MF2"}]
        ]
        
        merged_stocks, merged_mfs = self.service.merge_holdings(stock_holdings, mf_holdings)
        
        self.assertEqual(len(merged_stocks), 2)
        self.assertEqual(len(merged_mfs), 2)
    
    def test_merge_holdings_empty_lists(self):
        """Test merging empty holdings lists"""
        merged_stocks, merged_mfs = self.service.merge_holdings([], [])
        
        self.assertEqual(len(merged_stocks), 0)
        self.assertEqual(len(merged_mfs), 0)
    
    @patch('app.api.holdings.HoldingsService._add_nav_dates')
    def test_fetch_holdings(self, mock_add_nav_dates):
        """Test fetching holdings from KiteConnect"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        mock_kite._mock_holdings = [{
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 10,
            "average_price": 2500.0,
            "last_price": 2600.0
        }]
        mock_kite._mock_mf_holdings = [{
            "tradingsymbol": "MF1",
            "folio": "12345",
            "quantity": 100.5,
            "average_price": 25.5
        }]
        
        stocks, mfs = self.service.fetch_holdings(mock_kite)
        
        self.assertEqual(len(stocks), 1)
        self.assertEqual(stocks[0]["tradingsymbol"], "RELIANCE")
        self.assertEqual(len(mfs), 1)
        self.assertEqual(mfs[0]["tradingsymbol"], "MF1")
        mock_add_nav_dates.assert_called_once()
    
    def test_add_nav_dates_with_instruments(self):
        """Test adding NAV dates to MF holdings"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        mock_kite._mock_mf_instruments = [
            {
                "tradingsymbol": "MF1",
                "name": "Test Mutual Fund",
                "last_price": 25.5,
                "last_price_date": "2025-11-22"
            }
        ]
        
        mf_holdings = [{"tradingsymbol": "MF1", "quantity": 100}]
        self.service._add_nav_dates(mf_holdings, mock_kite)
        
        self.assertEqual(mf_holdings[0]["last_price_date"], "2025-11-22")
    
    def test_add_nav_dates_missing_instrument(self):
        """Test adding NAV dates when instrument not found"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        mock_kite._mock_mf_instruments = []
        
        mf_holdings = [{"tradingsymbol": "MF1"}]
        self.service._add_nav_dates(mf_holdings, mock_kite)
        
        self.assertIsNone(mf_holdings[0].get("last_price_date"))
    
    def test_add_nav_dates_api_error(self):
        """Test handling API error when fetching instruments"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        
        # Make mf_instruments raise an exception
        def raise_error():
            raise Exception("API Error")
        mock_kite.mf_instruments = raise_error
        
        mf_holdings = [{"tradingsymbol": "MF1"}]
        # Should handle gracefully without raising
        self.service._add_nav_dates(mf_holdings, mock_kite)
        
        self.assertIsNone(mf_holdings[0].get("last_price_date"))


class TestAuthenticationManager(unittest.TestCase):
    """Test AuthenticationManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.session_manager = Mock()
        self.auth_manager = AuthenticationManager(self.session_manager)
    
    def test_try_cached_token_valid(self):
        """Test using valid cached token with KiteConnect"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        self.session_manager.is_valid.return_value = True
        self.session_manager.get_token.return_value = "cached_token_123"
        
        result = self.auth_manager._try_cached_token(mock_kite, "user123", "TestAccount")
        
        self.assertTrue(result)
        self.assertEqual(mock_kite._access_token, "cached_token_123")
    
    def test_try_cached_token_none(self):
        """Test when no cached token exists"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        self.session_manager.is_valid.return_value = False
        
        result = self.auth_manager._try_cached_token(mock_kite, "user123", "TestAccount")
        
        self.assertFalse(result)
        self.assertIsNone(mock_kite._access_token)
    
    def test_try_cached_token_invalid(self):
        """Test when cached token exists and is set"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        self.session_manager.is_valid.return_value = True
        self.session_manager.get_token.return_value = "some_token"
        
        result = self.auth_manager._try_cached_token(mock_kite, "user123", "TestAccount")
        
        # Since implementation doesn't validate in _try_cached_token, it returns True
        self.assertTrue(result)
        self.assertEqual(mock_kite._access_token, "some_token")
    
    def test_generate_session_mock(self):
        """Test mocked session generation"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        
        session_data = mock_kite.generate_session("request_token_123", "api_secret_456")
        
        self.assertIn("access_token", session_data)
        self.assertIn("request_token_123", session_data["access_token"])
        self.assertEqual(session_data["user_id"], "TEST123")
    
    def test_renew_access_token_mock(self):
        """Test mocked token renewal"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        
        renewed_data = mock_kite.renew_access_token("old_refresh_token", "api_secret")
        
        self.assertIn("access_token", renewed_data)
        self.assertIn("old_refresh_token", renewed_data["access_token"])
    

    def test_validate_token_success(self):
        """Test successful token validation"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("valid_token")
        
        result = self.auth_manager._validate_token(mock_kite, "user123", "TestAccount")
        
        self.assertTrue(result)
    
    def test_validate_token_failure(self):
        """Test failed token validation"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        # No access token set
        
        result = self.auth_manager._validate_token(mock_kite, "user123", "TestAccount")
        
        self.assertFalse(result)
    
    def test_store_token(self):
        """Test storing access token"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        
        self.auth_manager._store_token(mock_kite, "user123", "TestAccount", "new_access_token")
        
        self.assertEqual(mock_kite._access_token, "new_access_token")
        self.session_manager.set_token.assert_called_once_with(
            "user123", "TestAccount", "new_access_token"
        )
        self.session_manager.save.assert_called_once_with("user123")
    
    def test_try_renew_token_success(self):
        """Test successful token renewal"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        self.session_manager.get_token.return_value = "old_token"
        
        result = self.auth_manager._try_renew_token(mock_kite, "user123", "TestAccount", "api_secret")
        
        self.assertTrue(result)
        self.assertIsNotNone(mock_kite._access_token)
        self.session_manager.save.assert_called()
    
    def test_try_renew_token_failure(self):
        """Test failed token renewal"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        self.session_manager.get_token.return_value = "old_token"
        
        # Make renew_access_token fail
        def raise_error(*args):
            raise Exception("Renewal failed")
        mock_kite.renew_access_token = raise_error
        
        result = self.auth_manager._try_renew_token(mock_kite, "user123", "TestAccount", "api_secret")
        
        self.assertFalse(result)
    
    @patch('app.api.auth.KiteConnect')
    def test_authenticate_with_cached_token(self, mock_kite_class):
        """Test authenticate using cached token"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite_class.return_value = mock_kite
        
        self.session_manager.is_valid.return_value = True
        self.session_manager.get_token.return_value = "cached_token"
        
        account_config = {
            "name": "TestAccount",
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "google_id": "user123"
        }
        
        kite = self.auth_manager.authenticate(account_config)
        
        self.assertIsNotNone(kite)
        self.assertEqual(kite._access_token, "cached_token")
    
    @patch('app.api.auth.KiteConnect')
    def test_authenticate_raises_when_no_valid_session(self, mock_kite_class):
        """Test authenticate raises RuntimeError when cached + renewal fail"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite_class.return_value = mock_kite
        
        self.session_manager.is_valid.return_value = False
        self.session_manager.get_token.return_value = None
        
        account_config = {
            "name": "TestAccount",
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "google_id": "user123"
        }
        
        with self.assertRaises(RuntimeError) as ctx:
            self.auth_manager.authenticate(account_config)
        self.assertIn("Session expired", str(ctx.exception))


class TestSIPService(unittest.TestCase):
    """Test SIPService class"""
    
    def setUp(self):
        """Set up test fixtures"""
        from app.api.sips import SIPService
        self.service = SIPService()
    
    def test_fetch_sips(self):
        """Test fetching SIPs from KiteConnect"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        mock_kite._mock_mf_sips = [
            {
                "sip_id": "SIP001",
                "tradingsymbol": "INF174K01LS2",
                "fund": "HDFC Equity Fund",
                "instalment_amount": 5000,
                "frequency": "monthly",
                "instalments": 12,
                "completed_instalments": 5,
                "status": "ACTIVE",
                "next_instalment": "2025-12-01"
            }
        ]
        
        sips = self.service.fetch_sips(mock_kite)
        
        self.assertEqual(len(sips), 1)
        self.assertEqual(sips[0]["sip_id"], "SIP001")
        self.assertEqual(sips[0]["instalment_amount"], 5000)
        self.assertEqual(sips[0]["status"], "ACTIVE")
    
    def test_fetch_sips_empty(self):
        """Test fetching SIPs when none exist"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        mock_kite._mock_mf_sips = []
        
        sips = self.service.fetch_sips(mock_kite)
        
        self.assertEqual(len(sips), 0)
    
    def test_fetch_sips_api_error(self):
        """Test handling API error when fetching SIPs"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        
        # Make mf_sips raise an exception
        def raise_error(*args, **kwargs):
            raise Exception("API Error")
        mock_kite.mf_sips = raise_error
        
        sips = self.service.fetch_sips(mock_kite)
        
        # Should handle gracefully and return empty list
        self.assertEqual(len(sips), 0)
    
    def test_add_account_info(self):
        """Test adding account information to SIPs"""
        sips = [
            {"sip_id": "SIP001", "instalment_amount": 5000},
            {"sip_id": "SIP002", "instalment_amount": 3000}
        ]
        
        self.service.add_account_info(sips, "Account1")
        
        self.assertEqual(sips[0]["account"], "Account1")
        self.assertEqual(sips[1]["account"], "Account1")
    
    def test_merge_sips_single_account(self):
        """Test merging SIPs from single account"""
        all_sips = [
            [{"sip_id": "SIP001"}, {"sip_id": "SIP002"}]
        ]
        
        merged = self.service.merge_items(all_sips)
        
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["sip_id"], "SIP001")
        self.assertEqual(merged[1]["sip_id"], "SIP002")
    
    def test_merge_sips_multiple_accounts(self):
        """Test merging SIPs from multiple accounts"""
        all_sips = [
            [{"sip_id": "SIP001", "account": "Account1"}],
            [{"sip_id": "SIP002", "account": "Account2"}],
            [{"sip_id": "SIP003", "account": "Account3"}]
        ]
        
        merged = self.service.merge_items(all_sips)
        
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]["account"], "Account1")
        self.assertEqual(merged[1]["account"], "Account2")
        self.assertEqual(merged[2]["account"], "Account3")
    
    def test_merge_sips_empty_lists(self):
        """Test merging empty SIP lists"""
        all_sips = [[], [], []]
        
        merged = self.service.merge_items(all_sips)
        
        self.assertEqual(len(merged), 0)


if __name__ == '__main__':
    unittest.main()
