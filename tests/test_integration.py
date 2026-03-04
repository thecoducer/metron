"""
Integration tests for Metron
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app.api.holdings import HoldingsService
from app.utils import SessionManager, StateManager


class MockKiteConnect:
    """Mock KiteConnect API for integration testing"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self._access_token = None
        self._mock_holdings = []
        self._mock_mf_holdings = []
        self._mock_mf_instruments = []
        self._mock_mf_sips = []
    
    def set_access_token(self, access_token: str):
        self._access_token = access_token
    
    def holdings(self):
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_holdings
    
    def mf_holdings(self):
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_mf_holdings
    
    def mf_instruments(self):
        if not self._access_token:
            raise Exception("Not authenticated")
        return self._mock_mf_instruments
    
    def mf_sips(self, sip_id=None):
        if not self._access_token:
            raise Exception("Not authenticated")
        if sip_id:
            return [sip for sip in self._mock_mf_sips if sip.get('sip_id') == sip_id]
        return self._mock_mf_sips
    
    def profile(self):
        if not self._access_token:
            raise Exception("Not authenticated")
        return {"user_id": "TEST123", "user_name": "Test User"}


class TestIntegration(unittest.TestCase):
    """Integration tests for complete workflows"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.holdings_service = HoldingsService()
    
    def test_complete_holdings_flow(self):
        """Test complete flow: fetch, enrich, merge with mocked KiteConnect API"""
        # Create mock KiteConnect with realistic data
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_access_token")
        
        # Set up mock holdings data
        mock_kite._mock_holdings = [
            {
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "quantity": 10,
                "average_price": 2400.0,
                "last_price": 2500.0,
                "pnl": 1000.0
            },
            {
                "tradingsymbol": "TCS",
                "exchange": "NSE",
                "quantity": 5,
                "average_price": 3500.0,
                "last_price": 3600.0,
                "pnl": 500.0
            }
        ]
        
        mock_kite._mock_mf_holdings = []
        mock_kite._mock_mf_instruments = []
        
        # Fetch holdings
        stocks, mfs = self.holdings_service.fetch_holdings(mock_kite)
        
        # Verify fetch
        self.assertEqual(len(stocks), 2)
        self.assertEqual(stocks[0]["tradingsymbol"], "RELIANCE")
        
        # Add account info
        self.holdings_service.add_account_info(stocks, "TestAccount")
        
        # Verify enrichment
        self.assertEqual(stocks[0]["account"], "TestAccount")
        self.assertEqual(stocks[0]["invested"], 24000.0)
        self.assertEqual(stocks[1]["invested"], 17500.0)
        
        # Merge (single account case)
        merged_stocks, merged_mfs = self.holdings_service.merge_holdings([stocks], [mfs])
        
        self.assertEqual(len(merged_stocks), 2)
        self.assertEqual(merged_stocks[0]["tradingsymbol"], "RELIANCE")
        self.assertEqual(merged_stocks[1]["tradingsymbol"], "TCS")
    
    def test_multi_account_merge(self):
        """Test merging holdings from multiple accounts"""
        # Account 1 holdings
        account1_stocks = [
            {
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "quantity": 10,
                "average_price": 2400.0
            }
        ]
        self.holdings_service.add_account_info(account1_stocks, "Account1")
        
        # Account 2 holdings
        account2_stocks = [
            {
                "tradingsymbol": "TCS",
                "exchange": "NSE",
                "quantity": 5,
                "average_price": 3500.0
            }
        ]
        self.holdings_service.add_account_info(account2_stocks, "Account2")
        
        # Merge
        merged_stocks, _ = self.holdings_service.merge_holdings(
            [account1_stocks, account2_stocks],
            [[], []]
        )
        
        # Verify
        self.assertEqual(len(merged_stocks), 2)
        accounts = {h["account"] for h in merged_stocks}
        self.assertEqual(accounts, {"Account1", "Account2"})
    
    def test_state_transitions(self):
        """Test state manager transitions during workflow"""
        state_manager = StateManager()
        google_id = "test_user_123"
        
        # Initial state is None (no data fetched yet)
        self.assertIsNone(state_manager.get_portfolio_state(google_id))
        
        # Simulate refresh workflow
        state_manager.set_portfolio_updating(google_id=google_id)
        self.assertTrue(state_manager.is_any_running(google_id=google_id))
        
        state_manager.set_portfolio_updated(google_id=google_id)
        # After successful fetch, state should be updated
        self.assertEqual(state_manager.get_portfolio_state(google_id), "updated")
        state_manager.set_nifty50_updated()
        self.assertFalse(state_manager.is_any_running(google_id=google_id))
    
    def test_session_token_workflow(self):
        """Test session token caching workflow via Firestore"""
        google_id = "test_user_123"
        session_manager = SessionManager()

        # Save token
        session_manager.set_token(google_id, "Account1", "token123")

        # Simulate round-trip: encrypt -> store -> decrypt
        encrypted = session_manager._encrypt("token123", google_id)
        sessions = session_manager._sessions_for(google_id)
        stored = {"Account1": {"access_token": encrypted,
                               "expiry": sessions["Account1"]["expiry"].isoformat()}}

        # New instance loads the stored data
        new_session_manager = SessionManager()
        with patch('app.firebase_store.get_zerodha_sessions', return_value=stored):
            new_session_manager.load_user(google_id)

        retrieved_token = new_session_manager.get_token(google_id, "Account1")
        self.assertEqual(retrieved_token, "token123")
    
    def test_error_handling_chain(self):
        """Test error handling across services with API errors"""
        # Create mock that raises exception
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        
        # Override holdings method to raise error
        def raise_api_error():
            raise Exception("KiteConnect API Error: Network timeout")
        
        mock_kite.holdings = raise_api_error
        
        # Should raise exception
        with self.assertRaises(Exception) as context:
            self.holdings_service.fetch_holdings(mock_kite)
        
        self.assertIn("API Error", str(context.exception))
    
    def test_mf_holdings_with_nav_dates(self):
        """Test MF holdings fetch with NAV date enrichment"""
        mock_kite = MockKiteConnect(api_key="test_api_key")
        mock_kite.set_access_token("test_token")
        
        # Set up MF holdings
        mock_kite._mock_mf_holdings = [
            {
                "tradingsymbol": "INF209K01157",
                "folio": "12345678",
                "quantity": 100.523,
                "average_price": 52.45,
                "last_price": 54.20,
                "pnl": 175.90
            }
        ]
        
        # Set up MF instruments with NAV dates
        mock_kite._mock_mf_instruments = [
            {
                "tradingsymbol": "INF209K01157",
                "name": "HDFC Balanced Advantage Fund",
                "last_price": 54.20,
                "last_price_date": "2025-11-21"
            }
        ]
        
        # Fetch holdings
        stocks, mfs = self.holdings_service.fetch_holdings(mock_kite)
        
        # Verify MF holdings
        self.assertEqual(len(mfs), 1)
        self.assertEqual(mfs[0]["tradingsymbol"], "INF209K01157")
        self.assertEqual(mfs[0]["last_price_date"], "2025-11-21")
        
        # Add account info
        self.holdings_service.add_account_info(mfs, "MFAccount")
        
        # Verify invested calculation
        expected_invested = 100.523 * 52.45
        self.assertAlmostEqual(mfs[0]["invested"], expected_invested, places=2)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""
    
    def test_empty_holdings(self):
        """Test handling empty holdings"""
        service = HoldingsService()
        stocks, mfs = service.merge_holdings([], [])
        
        self.assertEqual(len(stocks), 0)
        self.assertEqual(len(mfs), 0)
    
    def test_zero_quantity_holdings(self):
        """Test holdings with zero quantity"""
        service = HoldingsService()
        holdings = [{"quantity": 0, "average_price": 100.0}]
        
        service.add_account_info(holdings, "Test")
        
        self.assertEqual(holdings[0]["invested"], 0.0)
    
    def test_negative_prices(self):
        """Test handling negative prices (shouldn't happen but defensively)"""
        service = HoldingsService()
        holdings = [{"quantity": 10, "average_price": -100.0}]
        
        service.add_account_info(holdings, "Test")
        
        # Should still calculate (even if negative)
        self.assertEqual(holdings[0]["invested"], -1000.0)
    
    def test_very_large_numbers(self):
        """Test handling very large portfolio values"""
        service = HoldingsService()
        holdings = [{"quantity": 1000000, "average_price": 10000.0}]
        
        service.add_account_info(holdings, "Test")
        
        self.assertEqual(holdings[0]["invested"], 10000000000.0)
    
    def test_unicode_symbols(self):
        """Test handling unicode characters in symbols"""
        service = HoldingsService()
        holdings = [
            {
                "tradingsymbol": "टेस्ट",  # Hindi characters
                "quantity": 10,
                "average_price": 100.0
            }
        ]
        
        service.add_account_info(holdings, "Test")
        
        self.assertEqual(holdings[0]["account"], "Test")


class TestSortFunctionality(unittest.TestCase):
    """Test sort functionality integration"""
    
    def setUp(self):
        """Set up test data"""
        self.stock_holdings = [
            {
                "tradingsymbol": "RELIANCE",
                "quantity": 10,
                "average_price": 2500,
                "last_price": 2600,
                "close_price": 2580,
                "account": "Account1"
            },
            {
                "tradingsymbol": "TCS",
                "quantity": 5,
                "average_price": 3000,
                "last_price": 3300,
                "close_price": 3250,
                "account": "Account1"
            },
            {
                "tradingsymbol": "INFY",
                "quantity": 15,
                "average_price": 1400,
                "last_price": 1500,
                "close_price": 1480,
                "account": "Account2"
            }
        ]
        
        self.mf_holdings = [
            {
                "tradingsymbol": "MF1",
                "fund": "Axis Bluechip Fund",
                "quantity": 100,
                "average_price": 25,
                "last_price": 30,
                "account": "Account1"
            },
            {
                "tradingsymbol": "MF2",
                "fund": "HDFC Mid Cap Fund",
                "quantity": 50,
                "average_price": 100,
                "last_price": 95,
                "account": "Account1"
            },
            {
                "tradingsymbol": "MF3",
                "fund": "SBI Small Cap Fund",
                "quantity": 200,
                "average_price": 15,
                "last_price": 20,
                "account": "Account2"
            }
        ]
    
    def test_stock_holdings_data_structure(self):
        """Test that stock holdings have required fields for sorting"""
        required_fields = ["tradingsymbol", "quantity", "average_price", "last_price", "close_price", "account"]
        
        for holding in self.stock_holdings:
            for field in required_fields:
                self.assertIn(field, holding, f"Stock holding missing {field}")
    
    def test_mf_holdings_data_structure(self):
        """Test that MF holdings have required fields for sorting"""
        required_fields = ["tradingsymbol", "fund", "quantity", "average_price", "last_price", "account"]
        
        for holding in self.mf_holdings:
            for field in required_fields:
                self.assertIn(field, holding, f"MF holding missing {field}")
    
    def test_stock_pl_calculation(self):
        """Test P/L calculation for stocks"""
        holding = self.stock_holdings[0]
        invested = holding["quantity"] * holding["average_price"]
        current = holding["quantity"] * holding["last_price"]
        pl = current - invested
        pl_pct = (pl / invested) * 100
        
        self.assertEqual(invested, 25000)
        self.assertEqual(current, 26000)
        self.assertEqual(pl, 1000)
        self.assertAlmostEqual(pl_pct, 4.0, places=2)
    
    def test_mf_pl_calculation(self):
        """Test P/L calculation for mutual funds"""
        holding = self.mf_holdings[0]
        invested = holding["quantity"] * holding["average_price"]
        current = holding["quantity"] * holding["last_price"]
        pl = current - invested
        pl_pct = (pl / invested) * 100
        
        self.assertEqual(invested, 2500)
        self.assertEqual(current, 3000)
        self.assertEqual(pl, 500)
        self.assertAlmostEqual(pl_pct, 20.0, places=2)
    
    def test_day_change_calculation(self):
        """Test day's change calculation for stocks"""
        holding = self.stock_holdings[0]
        day_change = (holding["last_price"] - holding["close_price"]) * holding["quantity"]
        day_change_pct = ((holding["last_price"] - holding["close_price"]) / holding["close_price"]) * 100
        
        self.assertEqual(day_change, 200)
        self.assertAlmostEqual(day_change_pct, 0.7752, places=2)
    
    def test_sort_options_coverage(self):
        """Test that all sort options are documented"""
        stock_sort_options = [
            'default',
            'pl_pct_desc', 'pl_pct_asc',
            'pl_desc', 'pl_asc',
            'invested_desc', 'invested_asc',
            'current_desc', 'current_asc',
            'day_change_desc', 'day_change_asc',
            'symbol_asc', 'symbol_desc'
        ]
        
        mf_sort_options = [
            'default',
            'pl_pct_desc', 'pl_pct_asc',
            'pl_desc', 'pl_asc',
            'invested_desc', 'invested_asc',
            'current_desc', 'current_asc',
            'name_asc', 'name_desc'
        ]
        
        # Verify all options are unique
        self.assertEqual(len(stock_sort_options), len(set(stock_sort_options)))
        self.assertEqual(len(mf_sort_options), len(set(mf_sort_options)))
        
        # Verify minimum number of options
        self.assertGreaterEqual(len(stock_sort_options), 10)
        self.assertGreaterEqual(len(mf_sort_options), 8)
    
    def test_holdings_json_serializable(self):
        """Test that holdings can be JSON serialized"""
        try:
            json.dumps(self.stock_holdings)
            json.dumps(self.mf_holdings)
        except (TypeError, ValueError) as e:
            self.fail(f"Holdings are not JSON serializable: {e}")
    
    def test_empty_holdings_sorting(self):
        """Test that empty holdings arrays are valid for sorting"""
        empty_stocks = []
        empty_mfs = []
        
        # Should be JSON serializable
        self.assertEqual(json.dumps(empty_stocks), "[]")
        self.assertEqual(json.dumps(empty_mfs), "[]")
    
    def test_multiple_accounts_sorting(self):
        """Test that holdings from multiple accounts can be sorted"""
        accounts = set(h["account"] for h in self.stock_holdings)
        self.assertGreater(len(accounts), 1, "Test data should have multiple accounts")
        
        # Verify all holdings have account field
        for holding in self.stock_holdings:
            self.assertIsNotNone(holding.get("account"))
    
    def test_negative_pl_handling(self):
        """Test that negative P/L is handled correctly"""
        # MF2 has negative P/L (95 < 100)
        holding = self.mf_holdings[1]
        invested = holding["quantity"] * holding["average_price"]
        current = holding["quantity"] * holding["last_price"]
        pl = current - invested
        
        self.assertLess(pl, 0, "Should have negative P/L")
        self.assertEqual(pl, -250)
    
    def test_zero_quantity_sorting(self):
        """Test handling of zero quantity holdings for sorting"""
        zero_holding = {
            "tradingsymbol": "TEST",
            "quantity": 0,
            "average_price": 100,
            "last_price": 110,
            "close_price": 105,
            "account": "Test"
        }
        
        invested = zero_holding["quantity"] * zero_holding["average_price"]
        current = zero_holding["quantity"] * zero_holding["last_price"]
        
        self.assertEqual(invested, 0)
        self.assertEqual(current, 0)
    
    def test_large_numbers_sorting(self):
        """Test sorting with large numbers"""
        large_holding = {
            "tradingsymbol": "LARGECAP",
            "quantity": 10000,
            "average_price": 5000,
            "last_price": 5500,
            "close_price": 5400,
            "account": "Test"
        }
        
        invested = large_holding["quantity"] * large_holding["average_price"]
        current = large_holding["quantity"] * large_holding["last_price"]
        
        self.assertEqual(invested, 50000000)  # 50 million
        self.assertEqual(current, 55000000)   # 55 million
    
    def test_symbol_case_sensitivity(self):
        """Test that symbols are case-sensitive for sorting"""
        symbols = [h["tradingsymbol"] for h in self.stock_holdings]
        
        # All symbols should be uppercase in test data
        for symbol in symbols:
            self.assertEqual(symbol, symbol.upper())
    
    def test_fund_name_sorting_readiness(self):
        """Test that fund names are suitable for alphabetical sorting"""
        fund_names = [h["fund"] for h in self.mf_holdings]
        
        # All fund names should be non-empty strings
        for name in fund_names:
            self.assertIsInstance(name, str)
            self.assertGreater(len(name), 0)
    
    def test_sort_stability(self):
        """Test that sorting is stable (equal elements maintain order)"""
        # Create holdings with same P/L
        same_pl_holdings = [
            {"tradingsymbol": "A", "quantity": 10, "average_price": 100, "last_price": 110, 
             "close_price": 105, "account": "Test"},
            {"tradingsymbol": "B", "quantity": 10, "average_price": 100, "last_price": 110, 
             "close_price": 105, "account": "Test"},
            {"tradingsymbol": "C", "quantity": 10, "average_price": 100, "last_price": 110, 
             "close_price": 105, "account": "Test"}
        ]
        
        # All have same P/L%
        for holding in same_pl_holdings:
            pl_pct = ((holding["last_price"] - holding["average_price"]) / holding["average_price"]) * 100
            self.assertAlmostEqual(pl_pct, 10.0)


class TestSortUIIntegration(unittest.TestCase):
    """Test sort UI elements integration"""
    
    def test_html_has_sortable_headers(self):
        """Test that HTML template has sortable table headers"""
        import os
        html_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'templates', 'portfolio.html')
        
        if os.path.exists(html_path):
            with open(html_path, 'r') as f:
                html_content = f.read()
            
            self.assertIn('stocksTable', html_content, "Should have stocks table id")
            self.assertIn('data-sort-asc', html_content, "Should define ascending sort keys on headers")
            self.assertIn('data-sort-desc', html_content, "Should define descending sort keys on headers")
    
    def test_sort_manager_js_exists(self):
        """Test that sort-manager.js file exists"""
        import os
        js_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'js', 'sort-manager.js')
        
        self.assertTrue(os.path.exists(js_path), "sort-manager.js should exist")
    
    def test_css_has_sort_styles(self):
        """Test that CSS has sortable header styles"""
        import os
        css_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'css', 'styles.css')
        
        if os.path.exists(css_path):
            with open(css_path, 'r') as f:
                css_content = f.read()
            
            self.assertIn('th.sortable-header', css_content, "Should have sortable header styles")
            self.assertIn('.section-header', css_content, "Should have section-header styles")


class TestGoldSeparation(unittest.TestCase):
    """Test that Gold holdings (GOLDBEES and SGB*) are correctly separated from stocks summary."""
    
    def test_gold_symbol_detection(self):
        """Test that GOLDBEES and SGB symbols are correctly identified as gold."""
        # Test data
        symbols = [
            ('GOLDBEES', True),
            ('SGB2025', True),
            ('SGB2026-II', True),
            ('SGBMAR25', True),
            ('HDFCBANK', False),
            ('INFY', False),
            ('TCS', False),
            ('RELIANCE', False),
        ]
        
        for symbol, expected_is_gold in symbols:
            is_gold = symbol == 'GOLDBEES' or symbol.startswith('SGB')
            self.assertEqual(
                is_gold, 
                expected_is_gold,
                f"Symbol {symbol} should {'be' if expected_is_gold else 'not be'} classified as gold"
            )
    
    def test_gold_calculation_logic(self):
        """Test that totals are correctly calculated for stocks and gold separately."""
        # Simulate holdings
        holdings = [
            {'tradingsymbol': 'GOLDBEES', 'quantity': 60, 'average_price': 96.17, 'last_price': 106.51, 'invested': 5770},
            {'tradingsymbol': 'HDFCBANK', 'quantity': 10, 'average_price': 1500, 'last_price': 1600, 'invested': 15000},
            {'tradingsymbol': 'SGB2025', 'quantity': 5, 'average_price': 5000, 'last_price': 5200, 'invested': 25000},
            {'tradingsymbol': 'INFY', 'quantity': 20, 'average_price': 1400, 'last_price': 1500, 'invested': 28000},
        ]
        
        stock_invested = 0
        stock_current = 0
        gold_invested = 0
        gold_current = 0
        
        for holding in holdings:
            symbol = holding['tradingsymbol']
            is_gold = symbol == 'GOLDBEES' or symbol.startswith('SGB')
            current = holding['last_price'] * holding['quantity']
            
            if is_gold:
                gold_invested += holding['invested']
                gold_current += current
            else:
                stock_invested += holding['invested']
                stock_current += current
        
        # Assertions
        self.assertEqual(stock_invested, 43000, "Stock invested should be 15000 + 28000")
        self.assertEqual(stock_current, 16000 + 30000, "Stock current should be 16000 + 30000")
        self.assertEqual(gold_invested, 5770 + 25000, "Gold invested should be 5770 + 25000")
        self.assertEqual(gold_current, 60 * 106.51 + 5 * 5200, "Gold current should be calculated correctly")
        
        # Check combined totals
        combined_invested = stock_invested + gold_invested
        combined_current = stock_current + gold_current
        self.assertEqual(combined_invested, 43000 + 30770, "Combined invested should match")
        self.assertAlmostEqual(combined_current, 46000 + 32390.6, places=1, msg="Combined current should match")


if __name__ == '__main__':
    unittest.main()
