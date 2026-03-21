"""
Unit tests for api/user_sheets.py — sheet templates, configs, and creation.
"""

import unittest
from unittest.mock import Mock, patch

from app.api.user_sheets import (
    ALL_SHEETS,
    ETFS_HEADERS,
    ETFS_SHEET_NAME,
    FD_HEADERS,
    FD_SHEET_NAME,
    GOLD_HEADERS,
    GOLD_SHEET_NAME,
    MF_HEADERS,
    MF_SHEET_NAME,
    SHEET_CONFIGS,
    SIPS_HEADERS,
    SIPS_SHEET_NAME,
    STOCKS_HEADERS,
    STOCKS_SHEET_NAME,
    _format_headers,
    create_portfolio_sheet,
)


class TestSheetConstants(unittest.TestCase):
    def test_gold_config(self):
        self.assertEqual(GOLD_SHEET_NAME, "Gold")
        self.assertEqual(len(GOLD_HEADERS), 6)

    def test_fd_config(self):
        self.assertEqual(FD_SHEET_NAME, "FixedDeposits")
        self.assertEqual(len(FD_HEADERS), 10)

    def test_stocks_config(self):
        self.assertEqual(STOCKS_SHEET_NAME, "Stocks")
        self.assertEqual(len(STOCKS_HEADERS), 7)

    def test_etfs_config(self):
        self.assertEqual(ETFS_SHEET_NAME, "ETFs")
        self.assertEqual(len(ETFS_HEADERS), 7)

    def test_mf_config(self):
        self.assertEqual(MF_SHEET_NAME, "MutualFunds")
        self.assertEqual(
            len(MF_HEADERS), 8
        )  # ISIN, Fund Name, Qty, Avg NAV, Account, Source, Latest NAV, NAV Updated Date
        self.assertEqual(MF_HEADERS[0], "ISIN")

    def test_sips_config(self):
        self.assertEqual(SIPS_SHEET_NAME, "SIPs")
        self.assertEqual(len(SIPS_HEADERS), 10)


class TestSheetConfigs(unittest.TestCase):
    def test_all_types_present(self):
        expected_types = {"stocks", "etfs", "mutual_funds", "sips", "physical_gold", "fixed_deposits"}
        self.assertEqual(set(SHEET_CONFIGS.keys()), expected_types)

    def test_each_config_has_required_keys(self):
        for stype, cfg in SHEET_CONFIGS.items():
            self.assertIn("sheet_name", cfg, f"{stype} missing sheet_name")
            self.assertIn("headers", cfg, f"{stype} missing headers")
            self.assertIn("fields", cfg, f"{stype} missing fields")

    def test_fields_count_matches_headers(self):
        for stype, cfg in SHEET_CONFIGS.items():
            self.assertEqual(len(cfg["fields"]), len(cfg["headers"]), f"{stype}: fields count != headers count")


class TestAllSheets(unittest.TestCase):
    def test_count(self):
        self.assertEqual(len(ALL_SHEETS), 6)

    def test_unique_indices(self):
        indices = [idx for _, _, idx in ALL_SHEETS]
        self.assertEqual(len(set(indices)), 6)


class TestCreatePortfolioSheet(unittest.TestCase):
    @patch("app.api.user_sheets._format_headers")
    @patch("app.api.user_sheets.google_build")
    def test_create_and_populate(self, mock_build, mock_format):
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Mock spreadsheets().create()
        mock_create = Mock()
        mock_create.execute.return_value = {"spreadsheetId": "new_sheet_id"}
        mock_service.spreadsheets.return_value.create.return_value = mock_create

        # Mock spreadsheets().values().batchUpdate()
        mock_batch = Mock()
        mock_batch.execute.return_value = {}
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value = mock_batch

        creds = Mock()
        result = create_portfolio_sheet(creds, title="Test Portfolio")

        self.assertEqual(result, "new_sheet_id")
        mock_build.assert_called_once_with("sheets", "v4", credentials=creds)
        mock_service.spreadsheets.return_value.create.assert_called_once()
        mock_format.assert_called_once()

    @patch("app.api.user_sheets._format_headers")
    @patch("app.api.user_sheets.google_build")
    def test_default_title(self, mock_build, mock_format):
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_create = Mock()
        mock_create.execute.return_value = {"spreadsheetId": "sid"}
        mock_service.spreadsheets.return_value.create.return_value = mock_create
        mock_batch = Mock()
        mock_batch.execute.return_value = {}
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value = mock_batch

        create_portfolio_sheet(Mock())
        # Verify create was called with default title "Metron"
        call_args = mock_service.spreadsheets.return_value.create.call_args
        body = call_args[1]["body"]
        self.assertEqual(body["properties"]["title"], "Metron")


class TestFormatHeaders(unittest.TestCase):
    def test_format_headers_applies_bold(self):
        mock_service = Mock()

        # Mock get (returns sheet properties)
        mock_meta = Mock()
        mock_meta.execute.return_value = {
            "sheets": [
                {"properties": {"title": "Gold", "sheetId": 0}},
                {"properties": {"title": "FixedDeposits", "sheetId": 1}},
            ]
        }
        mock_service.spreadsheets.return_value.get.return_value = mock_meta

        # Mock batchUpdate
        mock_batch = Mock()
        mock_batch.execute.return_value = {}
        mock_service.spreadsheets.return_value.batchUpdate.return_value = mock_batch

        _format_headers(mock_service, "sid")
        mock_service.spreadsheets.return_value.batchUpdate.assert_called_once()

    def test_format_headers_no_matching_sheets(self):
        mock_service = Mock()
        mock_meta = Mock()
        mock_meta.execute.return_value = {
            "sheets": [
                {"properties": {"title": "UnknownSheet", "sheetId": 99}},
            ]
        }
        mock_service.spreadsheets.return_value.get.return_value = mock_meta
        mock_batch = Mock()
        mock_batch.execute.return_value = {}
        mock_service.spreadsheets.return_value.batchUpdate.return_value = mock_batch
        # Should not call batchUpdate when no sheets match
        _format_headers(mock_service, "sid")
        mock_service.spreadsheets.return_value.batchUpdate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
