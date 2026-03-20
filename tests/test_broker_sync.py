"""Tests for the broker → Google Sheets sync module."""

import threading
import unittest
from unittest.mock import Mock, patch

from app.broker_sync import (
    _do_sync,
    _etf_to_row,
    _format_num,
    _key_from_row,
    _mf_to_row,
    _sip_to_row,
    _stock_to_row,
    _sync_one_sheet,
    _values_changed,
    delete_account_from_sheets,
    is_etf_holding,
    start_broker_sync_thread,
    sync_broker_to_sheets,
)


class TestFormatNum(unittest.TestCase):
    def test_integer_float(self):
        self.assertEqual(_format_num(10.0), "10")

    def test_fractional_float(self):
        self.assertEqual(_format_num(10.5), "10.5")

    def test_integer(self):
        self.assertEqual(_format_num(10), "10")

    def test_zero(self):
        self.assertEqual(_format_num(0), "0")


class TestIsEtfHolding(unittest.TestCase):
    """Tests for the ETF detection helper."""

    def test_inf_isin_is_etf(self):
        """Holdings with INF ISIN prefix are ETFs (when manual_type absent)."""
        self.assertTrue(is_etf_holding({"tradingsymbol": "NIFTYBEES", "isin": "INF204KB14I2"}))

    def test_ine_isin_is_stock(self):
        """Holdings with INE ISIN prefix are equities."""
        self.assertFalse(is_etf_holding({"tradingsymbol": "INFY", "isin": "INE009A01021"}))

    def test_bees_suffix_fallback(self):
        """When ISIN absent, BEES suffix identifies ETF."""
        self.assertTrue(is_etf_holding({"tradingsymbol": "GOLDBEES", "isin": ""}))

    def test_etf_suffix_fallback(self):
        """When ISIN absent, ETF suffix identifies ETF."""
        self.assertTrue(is_etf_holding({"tradingsymbol": "LIQUIDETF", "isin": ""}))

    def test_plain_stock_no_isin(self):
        """Plain stock symbol without ISIN is not an ETF."""
        self.assertFalse(is_etf_holding({"tradingsymbol": "HDFCBANK", "isin": ""}))

    def test_missing_isin_key(self):
        """Missing isin key treated as empty string."""
        self.assertFalse(is_etf_holding({"tradingsymbol": "TCS"}))

    def test_gold_etf_inf_isin(self):
        """GOLDBEES with INF ISIN detected via ISIN (not symbol suffix)."""
        self.assertTrue(is_etf_holding({"tradingsymbol": "GOLDBEES", "isin": "INF204KB14I2"}))

    def test_silver_etf_inf_isin(self):
        """Silver ETF with INF ISIN is an ETF."""
        self.assertTrue(is_etf_holding({"tradingsymbol": "SILVERBEES", "isin": "INF204KB15I9"}))


class TestEtfToRow(unittest.TestCase):
    def test_etf_to_row(self):
        """ETF row has same structure as stock row with zerodha source."""
        etf = {
            "tradingsymbol": "NIFTYBEES",
            "quantity": 50,
            "average_price": 200.5,
            "exchange": "NSE",
            "account": "MyAccount",
            "isin": "INF204KB14I2",
        }
        row = _etf_to_row(etf)
        self.assertEqual(row, ["NIFTYBEES", "50", "200.5", "NSE", "MyAccount", "INF204KB14I2", "zerodha"])

    def test_etf_to_row_missing_isin(self):
        """ETF without ISIN still produces valid row."""
        etf = {
            "tradingsymbol": "GOLDBEES",
            "quantity": 10,
            "average_price": 5000,
            "exchange": "NSE",
            "account": "MyAcc",
        }
        row = _etf_to_row(etf)
        self.assertEqual(row[0], "GOLDBEES")
        self.assertEqual(row[5], "")  # empty ISIN
        self.assertEqual(row[6], "zerodha")


class TestTransformFunctions(unittest.TestCase):
    def test_stock_to_row(self):
        stock = {
            "tradingsymbol": "HDFCBANK",
            "quantity": 6,
            "average_price": 1500.0,
            "exchange": "NSE",
            "account": "MyAccount",
            "isin": "INE040A01034",
        }
        row = _stock_to_row(stock)
        self.assertEqual(row, ["HDFCBANK", "6", "1500", "NSE", "MyAccount", "INE040A01034", "zerodha"])

    def test_mf_to_row(self):
        mf = {
            "tradingsymbol": "INF123",
            "fund": "Test Fund",
            "quantity": 100.5,
            "average_price": 25.75,
            "account": "MyAcc",
        }
        row = _mf_to_row(mf)
        self.assertEqual(row, ["INF123", "Test Fund", "100.5", "25.75", "MyAcc", "zerodha"])

    def test_mf_to_row_uses_fund_fallback(self):
        mf = {"fund": "TestFund", "quantity": 10, "average_price": 20, "account": "A"}
        row = _mf_to_row(mf)
        self.assertEqual(row[0], "TestFund")
        self.assertEqual(row[1], "TestFund")  # fund_name from fund fallback

    def test_sip_to_row(self):
        sip = {
            "tradingsymbol": "INF456",
            "fund": "Test SIP Fund",
            "instalment_amount": 5000,
            "frequency": "MONTHLY",
            "instalments": 120,
            "completed_instalments": 24,
            "status": "ACTIVE",
            "next_instalment": "2025-04-01",
            "account": "MyAcc",
        }
        row = _sip_to_row(sip)
        self.assertEqual(len(row), 10)
        self.assertEqual(row[0], "INF456")
        self.assertEqual(row[1], "Test SIP Fund")
        self.assertEqual(row[2], "5000")
        self.assertEqual(row[-1], "zerodha")


class TestKeyFromRow(unittest.TestCase):
    def test_basic_key(self):
        row = ["INFY", "10", "1500", "NSE", "AcctA", "INE009A01021", "zerodha"]
        key = _key_from_row(row, 0, 4)
        self.assertEqual(key, ("INFY", "AcctA"))

    def test_strips_whitespace(self):
        row = ["  infy  ", "10", "1500", "NSE", "  AcctA  ", "INE009A01021", "zerodha"]
        key = _key_from_row(row, 0, 4)
        self.assertEqual(key, ("INFY", "AcctA"))

    def test_empty_row(self):
        key = _key_from_row([], 0, 4)
        self.assertEqual(key, ("", ""))


class TestValuesChanged(unittest.TestCase):
    def test_no_change(self):
        current = ["INFY", "10", "1500", "NSE", "Acc", "INE009A01021", "zerodha"]
        new = ["INFY", "10", "1500", "NSE", "Acc", "INE009A01021", "zerodha"]
        self.assertFalse(_values_changed(current, new))

    def test_quantity_changed(self):
        current = ["INFY", "10", "1500", "NSE", "Acc", "INE009A01021", "zerodha"]
        new = ["INFY", "5", "1500", "NSE", "Acc", "INE009A01021", "zerodha"]
        self.assertTrue(_values_changed(current, new))

    def test_price_changed(self):
        current = ["INFY", "10", "1500", "NSE", "Acc", "INE009A01021", "zerodha"]
        new = ["INFY", "10", "1600", "NSE", "Acc", "INE009A01021", "zerodha"]
        self.assertTrue(_values_changed(current, new))

    def test_shorter_current_row(self):
        current = ["INFY", "10"]
        new = ["INFY", "10", "1500", "NSE", "Acc", "INE009A01021", "zerodha"]
        self.assertTrue(_values_changed(current, new))


class TestSyncOneSheet(unittest.TestCase):
    """Test the core sync diff logic."""

    def _make_client(self, sheet_data):
        client = Mock()
        client.fetch_sheet_data_until_blank.return_value = sheet_data
        return client

    def test_fresh_sheet_appends_all(self):
        """Empty sheet → all broker items are appended."""
        client = self._make_client([["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"]])
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {"tradingsymbol": "INFY", "quantity": 10, "average_price": 1500, "exchange": "NSE", "account": "A"},
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["deleted"], 0)
        client.batch_append_rows.assert_called_once()

    def test_update_existing_holding(self):
        """Quantity change → existing zerodha row is updated."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["HDFCBANK", "6", "1400", "NSE", "MyAcc", "INE040A01034", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {"tradingsymbol": "HDFCBANK", "quantity": 2, "average_price": 1500, "exchange": "NSE", "account": "MyAcc"},
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["deleted"], 0)
        client.batch_update_rows.assert_called_once()
        # Verify the updated values
        update_args = client.batch_update_rows.call_args[0]
        row_num, values = update_args[2][0]
        self.assertEqual(row_num, 2)
        self.assertEqual(values[1], "2")  # new quantity
        self.assertEqual(values[2], "1500")  # new price

    def test_sold_holding_deleted(self):
        """Stock no longer in broker → zerodha row is deleted."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["RELIANCE", "10", "2500", "NSE", "MyAcc", "INE002A01018", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = []

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row, synced_accounts={"MyAcc"})

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["updated"], 0)
        client.batch_delete_rows.assert_called_once()

    def test_expired_account_rows_preserved(self):
        """Rows for accounts NOT in synced_accounts are not deleted."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["INFY", "10", "1500", "NSE", "Mine", "INE009A01021", "zerodha"],
                ["TCS", "5", "3500", "NSE", "Mom", "INE467B01029", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        # Only "Mine" was fetched (Mom's token expired)
        broker = [
            {
                "tradingsymbol": "INFY",
                "quantity": 10,
                "average_price": 1500,
                "exchange": "NSE",
                "account": "Mine",
                "isin": "INE009A01021",
            },
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row, synced_accounts={"Mine"})

        # Mom's TCS row should NOT be deleted
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["added"], 0)
        client.batch_delete_rows.assert_not_called()

    def test_synced_accounts_none_deletes_all(self):
        """When synced_accounts is None, all missing zerodha rows are deleted."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["RELIANCE", "10", "2500", "NSE", "Acc", "INE002A01018", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, [], _stock_to_row, synced_accounts=None)

        self.assertEqual(result["deleted"], 1)
        client.batch_delete_rows.assert_called_once()

    def test_manual_rows_untouched(self):
        """Manual entries are never modified by sync."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["TCS", "5", "3500", "NSE", "Manual", "INE467B01029", "manual"],
                ["INFY", "10", "1500", "NSE", "MyAcc", "INE009A01021", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        # Broker has INFY with updated qty but not TCS
        broker = [
            {"tradingsymbol": "INFY", "quantity": 15, "average_price": 1500, "exchange": "NSE", "account": "MyAcc"},
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        # Only INFY should be updated, TCS (manual) untouched
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(result["added"], 0)

    def test_mixed_add_update_delete(self):
        """Complex scenario: some holdings updated, some sold, some new."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["HDFCBANK", "6", "1400", "NSE", "Acc", "INE040A01034", "zerodha"],  # will update
                ["RELIANCE", "10", "2500", "NSE", "Acc", "INE002A01018", "zerodha"],  # will delete
                ["TCS", "5", "3500", "NSE", "Manual", "INE467B01029", "manual"],  # untouched
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {"tradingsymbol": "HDFCBANK", "quantity": 2, "average_price": 1500, "exchange": "NSE", "account": "Acc"},
            {"tradingsymbol": "WIPRO", "quantity": 20, "average_price": 400, "exchange": "NSE", "account": "Acc"},
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        self.assertEqual(result["updated"], 1)  # HDFCBANK
        self.assertEqual(result["deleted"], 1)  # RELIANCE
        self.assertEqual(result["added"], 1)  # WIPRO

    def test_no_changes_skips_api_calls(self):
        """Same data → no API calls."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"],
                ["INFY", "10", "1500", "NSE", "Acc", "INE009A01021", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {
                "tradingsymbol": "INFY",
                "quantity": 10,
                "average_price": 1500.0,
                "exchange": "NSE",
                "account": "Acc",
                "isin": "INE009A01021",
            },
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["deleted"], 0)
        client.batch_update_rows.assert_not_called()
        client.batch_delete_rows.assert_not_called()
        client.batch_append_rows.assert_not_called()

    def test_read_error_skips_sheet(self):
        """Sheet read failure → skip that sheet, don't crash."""
        client = Mock()
        client.fetch_sheet_data_until_blank.side_effect = Exception("API error")
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, [], _stock_to_row)

        self.assertEqual(result, {"updated": 0, "added": 0, "deleted": 0})

    def test_empty_symbol_skipped(self):
        """Broker entries with empty symbol are skipped."""
        client = self._make_client([["Symbol", "Qty", "Avg Price", "Exchange", "Account", "ISIN", "Source"]])
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {"tradingsymbol": "", "quantity": 10, "average_price": 1500, "exchange": "NSE", "account": "A"},
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        self.assertEqual(result["added"], 0)

    def test_old_sheet_without_source_column(self):
        """Pre-migration sheet without Source column → all rows treated as non-zerodha."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account"],
                ["INFY", "10", "1500", "NSE", "Acc"],  # No source column
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {"tradingsymbol": "INFY", "quantity": 10, "average_price": 1500, "exchange": "NSE", "account": "Acc"},
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        # INFY in sheet has no source → not zerodha → broker INFY is added as new
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["deleted"], 0)

    def test_old_sheet_without_isin_column_updates_instead_of_adding(self):
        """ISIN migration: legacy rows with old Source column should be updated, not duplicated."""
        client = self._make_client(
            [
                ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "Source"],
                ["INFY", "10", "1500", "NSE", "Acc", "zerodha"],
            ]
        )
        fields = ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"]
        broker = [
            {
                "tradingsymbol": "INFY",
                "quantity": 10,
                "average_price": 1500,
                "exchange": "NSE",
                "account": "Acc",
                "isin": "INE009A01021",
            },
        ]

        result = _sync_one_sheet(client, "sid", "Stocks", fields, broker, _stock_to_row)

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["deleted"], 0)
        client.batch_update_rows.assert_called_once()
        client.batch_append_rows.assert_not_called()


class TestSyncBrokerToSheets(unittest.TestCase):
    """Test the top-level sync orchestration."""

    @patch("app.broker_sync._do_sync")
    def test_calls_do_sync(self, mock_sync):
        sync_broker_to_sheets("user1", [{"s": 1}], [{"e": 1}], [{"m": 1}], [{"sip": 1}])
        mock_sync.assert_called_once_with("user1", [{"s": 1}], [{"e": 1}], [{"m": 1}], [{"sip": 1}], None)

    @patch("app.broker_sync._do_sync")
    def test_calls_do_sync_with_synced_accounts(self, mock_sync):
        accts = {"Mine", "Mom"}
        sync_broker_to_sheets("user1", [], [], [], [], synced_accounts=accts)
        mock_sync.assert_called_once_with("user1", [], [], [], [], accts)

    @patch("app.broker_sync._do_sync", side_effect=Exception("boom"))
    def test_exception_caught(self, mock_sync):
        # Should not raise
        sync_broker_to_sheets("user1", [], [], [], [])

    @patch("app.broker_sync._do_sync")
    def test_concurrent_sync_skipped(self, mock_sync):
        """Second sync for same user is skipped when first is running."""
        barrier = threading.Barrier(2, timeout=5)

        def slow_sync(*args):
            barrier.wait()
            import time

            time.sleep(0.1)

        mock_sync.side_effect = slow_sync

        t1 = threading.Thread(target=sync_broker_to_sheets, args=("user1", [], [], [], []))
        t1.start()
        barrier.wait()

        # Second call should skip (non-blocking acquire fails)
        sync_broker_to_sheets("user1", [], [], [], [])

        t1.join(timeout=5)
        # Only one actual sync call
        self.assertEqual(mock_sync.call_count, 1)

    @patch("app.broker_sync._do_sync")
    def test_start_broker_sync_thread(self, mock_sync):
        """Verify sync thread is started as daemon."""
        start_broker_sync_thread("user1", [{"s": 1}], [], [], [])
        import time

        time.sleep(0.2)
        mock_sync.assert_called_once()


class TestDoSync(unittest.TestCase):
    """Test _do_sync integration."""

    @patch("app.api.google_auth.persist_refreshed_credentials")
    @patch("app.broker_sync._sync_one_sheet")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    def test_syncs_all_sheet_types(
        self, mock_user, mock_creds_dict, mock_creds, mock_gsc, mock_sync_sheet, mock_persist
    ):
        mock_client = Mock()
        mock_gsc.return_value = mock_client
        mock_sync_sheet.return_value = {"updated": 0, "added": 0, "deleted": 0}

        _do_sync("user1", [{"stock": 1}], [{"etf": 1}], [{"mf": 1}], [{"sip": 1}])

        # Should sync 4 sheet types: stocks, etfs, mutual_funds, sips
        self.assertEqual(mock_sync_sheet.call_count, 4)

    @patch("app.api.google_auth.persist_refreshed_credentials")
    @patch("app.broker_sync._sync_one_sheet")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    def test_etfs_synced_to_etfs_sheet(
        self, mock_user, mock_creds_dict, mock_creds, mock_gsc, mock_sync_sheet, mock_persist
    ):
        """ETFs are synced to the ETFs sheet, not the Stocks sheet."""
        from app.api.user_sheets import SHEET_CONFIGS

        mock_client = Mock()
        mock_gsc.return_value = mock_client
        mock_sync_sheet.return_value = {"updated": 0, "added": 0, "deleted": 0}

        etfs = [{"tradingsymbol": "NIFTYBEES", "quantity": 10, "average_price": 200, "isin": "INF204KB14I2"}]
        _do_sync("user1", [], etfs, [], [])

        # Find the call that used the ETFs sheet
        etf_sheet_name = SHEET_CONFIGS["etfs"]["sheet_name"]
        stocks_sheet_name = SHEET_CONFIGS["stocks"]["sheet_name"]
        called_sheet_names = [call[0][2] for call in mock_sync_sheet.call_args_list]
        self.assertIn(etf_sheet_name, called_sheet_names)
        # ETFs should NOT be passed to the Stocks sheet call
        stocks_call = next(c for c in mock_sync_sheet.call_args_list if c[0][2] == stocks_sheet_name)
        self.assertEqual(stocks_call[0][4], [])  # empty stocks list

    @patch("app.fetchers.get_google_creds_dict", return_value=None)
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    def test_no_credentials_skips(self, mock_user, mock_creds_dict):
        # Should not raise
        _do_sync("user1", [], [], [], [])

    @patch("app.firebase_store.get_user", return_value=None)
    def test_no_user_skips(self, mock_user):
        # Should not raise
        _do_sync("user1", [], [], [], [])


class TestDeleteAccountFromSheets(unittest.TestCase):
    """Test explicit account deletion from sheets."""

    @patch("app.api.google_auth.persist_refreshed_credentials")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    def test_deletes_only_target_account_rows(self, mock_user, mock_creds_dict, mock_creds, mock_gsc, mock_persist):
        mock_client = Mock()
        mock_gsc.return_value = mock_client

        # Build sheet data per sheet type so column positions are correct.
        from app.api.user_sheets import SHEET_CONFIGS

        def make_sheet_data(sheet_type):
            cfg = SHEET_CONFIGS[sheet_type]
            headers = cfg["headers"]
            fields = cfg["fields"]
            account_idx = fields.index("account")
            source_idx = fields.index("source")

            def make_row(acct):
                row = [""] * len(headers)
                row[0] = "SYM"
                row[account_idx] = acct
                row[source_idx] = "zerodha"
                return row

            return [headers, make_row("Mine"), make_row("Mom")]

        # Return correct data per sheet name
        sheet_data_map = {
            SHEET_CONFIGS["stocks"]["sheet_name"]: make_sheet_data("stocks"),
            SHEET_CONFIGS["etfs"]["sheet_name"]: make_sheet_data("etfs"),
            SHEET_CONFIGS["mutual_funds"]["sheet_name"]: make_sheet_data("mutual_funds"),
            SHEET_CONFIGS["sips"]["sheet_name"]: make_sheet_data("sips"),
        }
        mock_client.fetch_sheet_data_until_blank.side_effect = lambda sid, name: sheet_data_map.get(name, [])

        delete_account_from_sheets("user1", "Mom")

        # Should delete 1 row (Mom) from each of the 4 sheet types
        self.assertEqual(mock_client.batch_delete_rows.call_count, 4)
        for call in mock_client.batch_delete_rows.call_args_list:
            rows = call[0][2]
            self.assertEqual(rows, [3])  # Row 3 is Mom's row

    @patch("app.firebase_store.get_user", return_value=None)
    def test_no_user_skips(self, mock_user):
        # Should not raise
        delete_account_from_sheets("user1", "Mom")

    @patch("app.api.google_auth.persist_refreshed_credentials")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    def test_delete_account_handles_legacy_source_column(
        self, mock_user, mock_creds_dict, mock_creds, mock_gsc, mock_persist
    ):
        """ISIN migration: legacy stocks rows with Source at old index are still deletable."""
        mock_client = Mock()
        mock_gsc.return_value = mock_client

        from app.api.user_sheets import SHEET_CONFIGS

        # Legacy stocks sheet: no ISIN column yet.
        legacy_stocks = [
            ["Symbol", "Qty", "Avg Price", "Exchange", "Account", "Source"],
            ["INFY", "10", "1500", "NSE", "Mine", "zerodha"],
            ["TCS", "5", "3500", "NSE", "Mom", "zerodha"],
        ]

        def make_sheet_data(sheet_type):
            cfg = SHEET_CONFIGS[sheet_type]
            headers = cfg["headers"]
            fields = cfg["fields"]
            account_idx = fields.index("account")
            source_idx = fields.index("source")

            def make_row(acct):
                row = [""] * len(headers)
                row[0] = "SYM"
                row[account_idx] = acct
                row[source_idx] = "zerodha"
                return row

            return [headers, make_row("Mine"), make_row("Mom")]

        sheet_data_map = {
            SHEET_CONFIGS["stocks"]["sheet_name"]: legacy_stocks,
            SHEET_CONFIGS["etfs"]["sheet_name"]: make_sheet_data("etfs"),
            SHEET_CONFIGS["mutual_funds"]["sheet_name"]: make_sheet_data("mutual_funds"),
            SHEET_CONFIGS["sips"]["sheet_name"]: make_sheet_data("sips"),
        }
        mock_client.fetch_sheet_data_until_blank.side_effect = lambda sid, name: sheet_data_map.get(name, [])

        delete_account_from_sheets("user1", "Mom")

        # Stocks + ETFs + MF + SIP should each delete Mom row.
        self.assertEqual(mock_client.batch_delete_rows.call_count, 4)

    @patch("app.fetchers.get_google_creds_dict", return_value=None)
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    def test_no_credentials_skips(self, mock_user, mock_creds_dict):
        # Should not raise
        delete_account_from_sheets("user1", "Mom")
