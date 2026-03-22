"""
Unit tests for api/google_sheets_client.py — GoogleSheetsClient and services.
"""

import unittest
from unittest.mock import Mock, patch

from app.error_handler import APIError, DataError, NetworkError


class TestGoogleSheetsClient(unittest.TestCase):
    """Test GoogleSheetsClient core methods."""

    def _make_client(self):
        from app.api.google_sheets_client import GoogleSheetsClient

        mock_creds = Mock()
        client = GoogleSheetsClient(user_credentials=mock_creds)
        return client

    def test_init_no_credentials_raises(self):
        from app.api.google_sheets_client import GoogleSheetsClient

        with self.assertRaises(ValueError):
            GoogleSheetsClient(user_credentials=None)

    @patch("app.api.google_sheets_client.build")
    @patch("app.api.google_sheets_client.AuthorizedHttp")
    @patch("app.api.google_sheets_client.httplib2.Http")
    def test_authenticate(self, mock_http, mock_auth_http, mock_build):
        client = self._make_client()
        mock_build.return_value = Mock()
        result = client.authenticate()
        self.assertTrue(result)
        self.assertTrue(client._is_authenticated)

    @patch("app.api.google_sheets_client.build")
    @patch("app.api.google_sheets_client.AuthorizedHttp")
    @patch("app.api.google_sheets_client.httplib2.Http")
    def test_authenticate_cached(self, mock_http, mock_auth_http, mock_build):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        result = client.authenticate()
        self.assertTrue(result)
        mock_build.assert_not_called()

    @patch("app.api.google_sheets_client.build")
    @patch("app.api.google_sheets_client.AuthorizedHttp")
    @patch("app.api.google_sheets_client.httplib2.Http")
    def test_authenticate_failure(self, mock_http, mock_auth_http, mock_build):
        client = self._make_client()
        mock_build.side_effect = Exception("auth fail")
        with self.assertRaises(Exception):
            client.authenticate()

    def test_fetch_sheet_data(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [["H1", "H2"], ["D1", "D2"]]
        }
        result = client.fetch_sheet_data("sid", "Sheet1!A:C")
        self.assertEqual(len(result), 2)

    def test_fetch_sheet_data_impl_http_error(self):
        from app.api.google_sheets_client import HttpError

        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()

        resp = Mock()
        resp.status = 500
        http_error = HttpError(resp, b"error")
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.side_effect = http_error

        with self.assertRaises(APIError):
            client._fetch_sheet_data_impl("sid", "Sheet1!A:C")

    def test_fetch_sheet_data_impl_http_error_4xx(self):
        from app.api.google_sheets_client import HttpError

        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()

        resp = Mock()
        resp.status = 404
        http_error = HttpError(resp, b"not found")
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.side_effect = http_error

        with self.assertRaises(APIError):
            client._fetch_sheet_data_impl("sid", "Sheet1!A:C")

    def test_fetch_sheet_data_impl_os_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        os_err = OSError("socket err")
        os_err.errno = 49
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.side_effect = os_err

        with self.assertRaises(NetworkError):
            client._fetch_sheet_data_impl("sid", "Sheet1!A:C")

    def test_fetch_sheet_data_impl_os_error_non_49(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        os_err = OSError("other")
        os_err.errno = 1
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.side_effect = os_err
        with self.assertRaises(NetworkError):
            client._fetch_sheet_data_impl("sid", "Sheet1!A:C")

    def test_fetch_sheet_data_impl_generic_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.side_effect = (
            RuntimeError("unexpected")
        )

        with self.assertRaises(RuntimeError):
            client._fetch_sheet_data_impl("sid", "Sheet1!A:C")

    def test_fetch_sheet_data_until_blank(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [
                ["H1", "H2"],
                ["A", "B"],
                ["C", "D"],
                ["", ""],  # blank row
                ["E", "F"],  # should be trimmed
            ]
        }
        result = client.fetch_sheet_data_until_blank("sid", "Sheet1")
        self.assertEqual(len(result), 3)  # header + 2 data rows

    def test_fetch_sheet_data_until_blank_no_data(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": []
        }
        result = client.fetch_sheet_data_until_blank("sid", "Sheet1")
        self.assertEqual(result, [])

    def test_batch_fetch_sheet_data(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value = {
            "valueRanges": [
                {"values": [["H"], ["A"]]},
                {"values": [["H2"], ["B"]]},
            ]
        }
        result = client.batch_fetch_sheet_data("sid", ["Sheet1!A:C", "Sheet2!A:C"])
        self.assertIn("Sheet1!A:C", result)
        self.assertIn("Sheet2!A:C", result)

    def test_batch_fetch_impl_http_error(self):
        from app.api.google_sheets_client import HttpError

        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        resp = Mock()
        resp.status = 503
        client.service.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.side_effect = (
            HttpError(resp, b"err")
        )
        with self.assertRaises(APIError):
            client._batch_fetch_impl("sid", ["Sheet1!A:C"])

    def test_batch_fetch_impl_os_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        os_err = OSError("err")
        os_err.errno = 49
        client.service.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.side_effect = os_err
        with self.assertRaises(NetworkError):
            client._batch_fetch_impl("sid", ["Sheet1!A:C"])

    def test_batch_fetch_impl_generic_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.side_effect = (
            RuntimeError("x")
        )
        with self.assertRaises(RuntimeError):
            client._batch_fetch_impl("sid", ["Sheet1!A:C"])

    def test_batch_fetch_sheet_data_until_blank(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value = {
            "valueRanges": [
                {"values": [["H"], ["A"], ["", ""]]},
                {"values": [["H2"], ["B"], ["C"]]},
            ]
        }
        result = client.batch_fetch_sheet_data_until_blank("sid", ["Sheet1", "Sheet2"])
        self.assertEqual(len(result["Sheet1"]), 2)  # trimmed
        self.assertEqual(len(result["Sheet2"]), 3)  # no blank

    def test_parse_number(self):
        from app.api.google_sheets_client import GoogleSheetsClient

        self.assertEqual(GoogleSheetsClient.parse_number(""), 0.0)
        self.assertEqual(GoogleSheetsClient.parse_number(None), 0.0)
        self.assertEqual(GoogleSheetsClient.parse_number(42), 42.0)
        self.assertEqual(GoogleSheetsClient.parse_number(42.5), 42.5)
        self.assertEqual(GoogleSheetsClient.parse_number("₹1,000"), 1000.0)
        self.assertEqual(GoogleSheetsClient.parse_number("invalid"), 0.0)

    def test_parse_yes_no(self):
        from app.api.google_sheets_client import GoogleSheetsClient

        self.assertTrue(GoogleSheetsClient.parse_yes_no("Yes"))
        self.assertTrue(GoogleSheetsClient.parse_yes_no("y"))
        self.assertTrue(GoogleSheetsClient.parse_yes_no("True"))
        self.assertTrue(GoogleSheetsClient.parse_yes_no("1"))
        self.assertFalse(GoogleSheetsClient.parse_yes_no("No"))
        self.assertFalse(GoogleSheetsClient.parse_yes_no(""))
        self.assertFalse(GoogleSheetsClient.parse_yes_no(None))
        self.assertFalse(GoogleSheetsClient.parse_yes_no(0))

    # ── CRUD methods ──

    def test_append_row(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.append.return_value.execute.return_value = {
            "updates": {"updatedRange": "Sheet!A8:F8"}
        }
        row_num = client.append_row("sid", "Sheet", ["A", "B", "C"])
        self.assertEqual(row_num, 8)

    def test_append_row_no_range(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.append.return_value.execute.return_value = {
            "updates": {}
        }
        row_num = client.append_row("sid", "Sheet", ["A"])
        self.assertEqual(row_num, -1)

    def test_append_row_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.append.return_value.execute.side_effect = (
            Exception("fail")
        )
        with self.assertRaises(Exception):
            client.append_row("sid", "Sheet", ["A"])

    def test_update_row(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {}
        client.update_row("sid", "Sheet", 5, ["A", "B"])
        client.service.spreadsheets.return_value.values.return_value.update.assert_called_once()

    def test_update_row_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.values.return_value.update.return_value.execute.side_effect = (
            Exception("fail")
        )
        with self.assertRaises(Exception):
            client.update_row("sid", "Sheet", 5, ["A"])

    def test_delete_row(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        # Mock _get_sheet_id
        mock_meta = Mock()
        mock_meta.execute.return_value = {"sheets": [{"properties": {"title": "Sheet", "sheetId": 42}}]}
        client.service.spreadsheets.return_value.get.return_value = mock_meta
        client.service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}

        client.delete_row("sid", "Sheet", 5)
        client.service.spreadsheets.return_value.batchUpdate.assert_called_once()

    def test_delete_row_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        mock_meta = Mock()
        mock_meta.execute.return_value = {"sheets": [{"properties": {"title": "Sheet", "sheetId": 42}}]}
        client.service.spreadsheets.return_value.get.return_value = mock_meta
        client.service.spreadsheets.return_value.batchUpdate.return_value.execute.side_effect = Exception("fail")
        with self.assertRaises(Exception):
            client.delete_row("sid", "Sheet", 5)

    def test_get_sheet_id(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        mock_meta = Mock()
        mock_meta.execute.return_value = {
            "sheets": [
                {"properties": {"title": "Gold", "sheetId": 0}},
                {"properties": {"title": "FD", "sheetId": 1}},
            ]
        }
        client.service.spreadsheets.return_value.get.return_value = mock_meta
        self.assertEqual(client._get_sheet_id("sid", "FD"), 1)

    def test_get_sheet_id_not_found(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        mock_meta = Mock()
        mock_meta.execute.return_value = {"sheets": [{"properties": {"title": "Gold", "sheetId": 0}}]}
        client.service.spreadsheets.return_value.get.return_value = mock_meta
        with self.assertRaises(ValueError):
            client._get_sheet_id("sid", "Missing")

    def test_ensure_sheet_tab_exists(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        mock_meta = Mock()
        mock_meta.execute.return_value = {"sheets": [{"properties": {"title": "Stocks"}}]}
        client.service.spreadsheets.return_value.get.return_value = mock_meta
        client.ensure_sheet_tab("sid", "Stocks", ["H1"])
        # Should not call addSheet if tab exists
        client.service.spreadsheets.return_value.batchUpdate.assert_not_called()

    def test_ensure_sheet_tab_creates(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        mock_meta = Mock()
        mock_meta.execute.return_value = {"sheets": [{"properties": {"title": "Other"}}]}
        client.service.spreadsheets.return_value.get.return_value = mock_meta
        client.service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}
        client.service.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {}

        client.ensure_sheet_tab("sid", "NewTab", ["H1", "H2"])
        client.service.spreadsheets.return_value.batchUpdate.assert_called_once()

    def test_ensure_sheet_tab_error(self):
        client = self._make_client()
        client._is_authenticated = True
        client.service = Mock()
        client.service.spreadsheets.return_value.get.return_value.execute.side_effect = Exception("fail")
        with self.assertRaises(Exception):
            client.ensure_sheet_tab("sid", "X", ["H"])


class TestGoogleSheetsService(unittest.TestCase):
    def _make_service(self):
        from app.api.google_sheets_client import GoogleSheetsService

        mock_client = Mock()
        svc = GoogleSheetsService(mock_client)
        return svc, mock_client

    def test_safe_get_in_range(self):
        from app.api.google_sheets_client import GoogleSheetsService

        self.assertEqual(GoogleSheetsService._safe_get(["a", "b", "c"], 1), "b")

    def test_safe_get_out_of_range(self):
        from app.api.google_sheets_client import GoogleSheetsService

        self.assertEqual(GoogleSheetsService._safe_get(["a"], 5, "default"), "default")

    def test_safe_get_with_parser(self):
        from app.api.google_sheets_client import GoogleSheetsService

        result = GoogleSheetsService._safe_get(["42"], 0, 0, float)
        self.assertEqual(result, 42.0)

    def test_fetch_and_parse_empty(self):
        svc, mock_client = self._make_service()
        mock_client.fetch_sheet_data.return_value = []
        result = svc._fetch_and_parse("sid", "Sheet!A:C")
        self.assertEqual(result, [])

    def test_fetch_and_parse_header_only(self):
        svc, mock_client = self._make_service()
        mock_client.fetch_sheet_data.return_value = [["H1", "H2"]]
        result = svc._fetch_and_parse("sid", "Sheet!A:C")
        self.assertEqual(result, [])

    def test_fetch_and_parse_skip_empty_rows(self):
        svc, mock_client = self._make_service()
        mock_client.fetch_sheet_data.return_value = [
            ["H1"],
            ["data"],
            [],
        ]
        svc._parse_row = Mock(return_value={"parsed": True})
        result = svc._fetch_and_parse("sid", "Sheet!A:B")
        self.assertEqual(len(result), 1)

    def test_fetch_and_parse_row_error_skipped(self):
        svc, mock_client = self._make_service()
        mock_client.fetch_sheet_data.return_value = [
            ["H"],
            ["row1"],
            ["row2"],
        ]
        svc._parse_row = Mock(side_effect=[{"ok": True}, Exception("parse fail")])
        result = svc._fetch_and_parse("sid", "Sheet!A:B")
        self.assertEqual(len(result), 1)

    def test_parse_rows_empty(self):
        svc, _ = self._make_service()
        self.assertEqual(svc._parse_rows([]), [])

    def test_parse_rows_trims_blank(self):
        svc, _ = self._make_service()
        svc._parse_row = Mock(return_value={"parsed": True})
        result = svc._parse_rows([["H"], ["A"], ["", ""], ["B"]])
        self.assertEqual(len(result), 1)

    def test_parse_batch_data(self):
        svc, _ = self._make_service()
        svc._parse_row = Mock(return_value={"p": True})
        result = svc._parse_batch_data([["H"], ["A"], ["B"]])
        self.assertEqual(len(result), 2)


class TestPhysicalGoldService(unittest.TestCase):
    def test_fetch_holdings(self):
        from app.api.google_sheets_client import PhysicalGoldService

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Date", "Type", "Outlet", "Purity", "Weight", "Rate"],
            ["2024-01-01", "Bar", "Tanishq", "999", "10", "5000"],
        ]
        svc = PhysicalGoldService(mock_client)
        result = svc.fetch_holdings("sid", "Gold!A:F")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "Bar")
        self.assertEqual(result[0]["weight_gms"], 10.0)

    def test_fetch_holdings_empty(self):
        from app.api.google_sheets_client import PhysicalGoldService

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = []
        svc = PhysicalGoldService(mock_client)
        result = svc.fetch_holdings("sid")
        self.assertEqual(result, [])

    def test_parse_row(self):
        from app.api.google_sheets_client import PhysicalGoldService

        svc = PhysicalGoldService(Mock())
        row = ["2024-01-01", "Coin", "Shop", "916", "5", "4500"]
        result = svc._parse_row(row, 2)
        self.assertEqual(result["date"], "2024-01-01")
        self.assertEqual(result["purity"], "916")
        self.assertEqual(result["row_number"], 2)


class TestFixedDepositsService(unittest.TestCase):
    def test_fetch_deposits(self):
        from app.api.google_sheets_client import FixedDepositsService

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Date", "Reinvested", "Bank", "Year", "Month", "Day", "Amount", "Reinv Amt", "Rate", "Account"],
            ["2024-01-01", "", "SBI", "1", "0", "0", "100000", "0", "7.5", "Savings"],
        ]
        svc = FixedDepositsService(mock_client)
        result = svc.fetch_deposits("sid", "FixedDeposits!A:K")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["bank_name"], "SBI")

    def test_parse_row_missing_bank_raises(self):
        from app.api.google_sheets_client import FixedDepositsService

        svc = FixedDepositsService(Mock())
        row = ["2024-01-01", "", "", "1", "0", "0", "100000", "0", "7.5", ""]
        with self.assertRaises(DataError):
            svc._parse_row(row, 2)

    def test_parse_row_zero_rate_raises(self):
        from app.api.google_sheets_client import FixedDepositsService

        svc = FixedDepositsService(Mock())
        row = ["2024-01-01", "", "Bank", "1", "0", "0", "100000", "0", "0", ""]
        with self.assertRaises(DataError):
            svc._parse_row(row, 2)


class TestGoogleSheetsClientEdges(unittest.TestCase):
    """Cover remaining uncovered lines in google_sheets_client.py."""

    def _make_authed_client(self):
        from app.api.google_sheets_client import GoogleSheetsClient

        client = GoogleSheetsClient(user_credentials=Mock())
        client._is_authenticated = True
        client.service = Mock()
        return client

    def test_init_no_credentials(self):
        """Line 39: raise ValueError when credentials are empty."""
        from app.api.google_sheets_client import GoogleSheetsClient

        with self.assertRaises(ValueError):
            GoogleSheetsClient(user_credentials="")

    def test_fetch_sheet_data_error_logged_and_raised(self):
        """Lines 79-81: fetch_sheet_data catches, logs, and re-raises."""
        client = self._make_authed_client()
        # pyrefly: ignore [missing-attribute]
        client.service.spreadsheets().values().get().execute.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            client.fetch_sheet_data("sid", "Sheet1!A:Z", max_retries=0)

    def test_batch_fetch_error_logged_and_raised(self):
        """Lines 130-132: batch_fetch_sheet_data catches, logs, and re-raises."""
        client = self._make_authed_client()
        # pyrefly: ignore [missing-attribute]
        client.service.spreadsheets().values().batchGet().execute.side_effect = RuntimeError("batch boom")
        with self.assertRaises(RuntimeError):
            client.batch_fetch_sheet_data("sid", ["Sheet1!A:Z"], max_retries=0)

    def test_batch_until_blank_short_data(self):
        """Lines 180-181: sheet with < 2 rows returns raw data as-is."""
        client = self._make_authed_client()
        # batch_fetch_sheet_data returns raw batch keyed by range
        with patch.object(
            client,
            "batch_fetch_sheet_data",
            return_value={
                "ShortSheet!A1:Z200": [["Header"]],
                "EmptySheet!A1:Z200": [],
            },
        ):
            result = client.batch_fetch_sheet_data_until_blank("sid", ["ShortSheet", "EmptySheet"])
        self.assertEqual(result["ShortSheet"], [["Header"]])
        self.assertEqual(result["EmptySheet"], [])

    def test_parse_number_unusual_type(self):
        """Line 203: parse_number with non-str/int/float type returns 0.0."""
        from app.api.google_sheets_client import GoogleSheetsClient

        self.assertEqual(GoogleSheetsClient.parse_number([1, 2, 3]), 0.0)
        self.assertEqual(GoogleSheetsClient.parse_number({"a": 1}), 0.0)

    def test_init_google_libs_unavailable(self):
        """Line 39: raise ImportError when GOOGLE_SHEETS_AVAILABLE is False."""
        from app.api import google_sheets_client as gsc

        with patch.object(gsc, "GOOGLE_SHEETS_AVAILABLE", False):
            with self.assertRaises(ImportError):
                gsc.GoogleSheetsClient(user_credentials=Mock())

    def test_parse_rows_parse_exception_caught(self):
        """Lines 413-414: _parse_rows catches per-row parse exceptions."""
        from app.api.google_sheets_client import GoogleSheetsService

        svc = GoogleSheetsService(Mock())
        svc.entity_name = "test"
        call_count = [0]

        def _parse_row(row, idx):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("bad row")
            return {"val": row[0]}

        svc._parse_row = _parse_row
        raw = [["Header"], ["bad"], ["good"]]
        result = svc._parse_rows(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["val"], "good")


if __name__ == "__main__":
    unittest.main()
