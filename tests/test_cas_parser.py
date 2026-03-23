"""Tests for CAS PDF parser (app/api/cas_parser.py)."""

from unittest.mock import MagicMock, patch

import pytest

from app.api.cas_parser import (
    CASParseResult,
    CASScheme,
    CASTransaction,
    _safe_float,
    parse_cas_pdf,
    serialise_parse_result,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_cas_data():
    """Build a mock casparser output structure."""
    mock = MagicMock()
    mock.model_dump.return_value = {
        "statement_period": {"from_": "01-Jan-2022", "to": "20-Mar-2026"},
        "file_type": "CAMS",
        "investor_info": {
            "name": "TEST USER",
            "email": "test@example.com",
            "address": "123 Street",
            "mobile": "9999999999",
        },
        "folios": [
            {
                "folio": "12345 / 67",
                "amc": "Test Mutual Fund",
                "PAN": "ABCDE1234F",
                "schemes": [
                    {
                        "scheme": "Test Fund - Direct Plan - Growth",
                        "isin": "INF123K01AB4",
                        "amfi": "100001",
                        "rta": "CAMS",
                        "type": "EQUITY",
                        "open": "0.000",
                        "close": "50.123",
                        "close_calculated": "50.123",
                        "valuation": {
                            "date": "2026-03-19",
                            "nav": "100.50",
                            "cost": "5000.00",
                            "value": "5035.36",
                        },
                        "transactions": [
                            {
                                "date": "2025-01-15",
                                "description": "Purchase Online",
                                "amount": "4999.75",
                                "units": "49.750",
                                "nav": "100.50",
                                "balance": "49.750",
                                "type": "PURCHASE",
                                "dividend_rate": None,
                            },
                            {
                                "date": "2025-01-15",
                                "description": "*** Stamp Duty ***",
                                "amount": "0.25",
                                "units": None,
                                "nav": None,
                                "balance": None,
                                "type": "STAMP_DUTY_TAX",
                                "dividend_rate": None,
                            },
                            {
                                "date": "2025-06-01",
                                "description": "Purchase Online",
                                "amount": "999.95",
                                "units": "0.373",
                                "nav": "102.00",
                                "balance": "50.123",
                                "type": "PURCHASE",
                                "dividend_rate": None,
                            },
                        ],
                    },
                    {
                        "scheme": "No ISIN Fund",
                        "isin": "",
                        "amfi": "",
                        "rta": "CAMS",
                        "type": "DEBT",
                        "close": "0",
                        "valuation": {"date": "", "nav": "0", "cost": "0", "value": "0"},
                        "transactions": [],
                    },
                ],
            },
        ],
    }
    return mock


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_none_returns_zero(self):
        assert _safe_float(None) == 0.0

    def test_string_number(self):
        assert _safe_float("123.45") == 123.45

    def test_int(self):
        assert _safe_float(42) == 42.0

    def test_invalid_string(self):
        assert _safe_float("abc") == 0.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0


# ---------------------------------------------------------------------------
# parse_cas_pdf
# ---------------------------------------------------------------------------


class TestParseCasPdf:
    @patch("app.api.cas_parser.casparser")
    def test_basic_parsing(self, mock_casparser):
        mock_casparser.read_cas_pdf.return_value = _make_mock_cas_data()

        result = parse_cas_pdf(b"fake-pdf-bytes", "password123")

        assert isinstance(result, CASParseResult)
        assert result.investor_name == "TEST USER"
        assert result.investor_email == "test@example.com"
        assert result.statement_from == "01-Jan-2022"
        assert result.statement_to == "20-Mar-2026"
        assert result.file_type == "CAMS"

    @patch("app.api.cas_parser.casparser")
    def test_schemes_extracted(self, mock_casparser):
        mock_casparser.read_cas_pdf.return_value = _make_mock_cas_data()
        result = parse_cas_pdf(b"fake", "pass")

        # Only 1 scheme extracted (the one with no ISIN is skipped)
        assert len(result.schemes) == 1
        scheme = result.schemes[0]
        assert scheme.isin == "INF123K01AB4"
        assert scheme.scheme_name == "Test Fund - Direct Plan - Growth"
        assert scheme.amc == "Test Mutual Fund"
        assert scheme.folio == "12345 / 67"
        assert scheme.units == 50.123
        assert scheme.cost == 5000.0
        assert scheme.current_value == 5035.36

    @patch("app.api.cas_parser.casparser")
    def test_stamp_duty_filtered(self, mock_casparser):
        mock_casparser.read_cas_pdf.return_value = _make_mock_cas_data()
        result = parse_cas_pdf(b"fake", "pass")

        # Stamp duty should be filtered out (3 raw → 2 kept)
        txns = result.schemes[0].transactions
        assert len(txns) == 2
        assert all(t.type != "STAMP_DUTY_TAX" for t in txns)

    @patch("app.api.cas_parser.casparser")
    def test_transactions_parsed(self, mock_casparser):
        mock_casparser.read_cas_pdf.return_value = _make_mock_cas_data()
        result = parse_cas_pdf(b"fake", "pass")

        txn = result.schemes[0].transactions[0]
        assert isinstance(txn, CASTransaction)
        assert txn.date == "2025-01-15"
        assert txn.amount == 4999.75
        assert txn.units == 49.75
        assert txn.nav == 100.50
        assert txn.type == "PURCHASE"

    @patch("app.api.cas_parser.casparser")
    def test_wrong_password_raises(self, mock_casparser):
        mock_casparser.read_cas_pdf.side_effect = Exception("incorrect password for file")

        with pytest.raises(ValueError, match="Incorrect password"):
            parse_cas_pdf(b"fake", "wrong")

    @patch("app.api.cas_parser.casparser")
    def test_invalid_pdf_raises(self, mock_casparser):
        mock_casparser.read_cas_pdf.side_effect = Exception("Not a valid PDF")

        with pytest.raises(ValueError, match="Failed to parse"):
            parse_cas_pdf(b"not-a-pdf", "pass")


# ---------------------------------------------------------------------------
# serialise_parse_result
# ---------------------------------------------------------------------------


class TestSerialiseParseResult:
    def test_serialisation(self):
        result = CASParseResult(
            investor_name="Test",
            investor_email="test@test.com",
            statement_from="01-Jan-2022",
            statement_to="20-Mar-2026",
            file_type="CAMS",
            schemes=[
                CASScheme(
                    scheme_name="Fund A",
                    isin="INF123",
                    amfi="100",
                    rta="CAMS",
                    scheme_type="EQUITY",
                    folio="123",
                    amc="AMC A",
                    units=10.0,
                    cost=1000.0,
                    current_value=1100.0,
                    nav=110.0,
                    nav_date="2026-03-19",
                    transactions=[
                        CASTransaction(
                            date="2025-01-01",
                            description="Purchase",
                            amount=1000.0,
                            units=10.0,
                            nav=100.0,
                            balance=10.0,
                            type="PURCHASE",
                        )
                    ],
                )
            ],
        )

        data = serialise_parse_result(result)
        assert data["investor_name"] == "Test"
        assert len(data["schemes"]) == 1
        assert data["schemes"][0]["isin"] == "INF123"
        assert data["schemes"][0]["transaction_count"] == 1
        assert len(data["schemes"][0]["transactions"]) == 1
        assert data["schemes"][0]["transactions"][0]["type"] == "PURCHASE"

    def test_empty_schemes(self):
        result = CASParseResult(
            investor_name="",
            investor_email="",
            statement_from="",
            statement_to="",
            file_type="",
            schemes=[],
        )
        data = serialise_parse_result(result)
        assert data["schemes"] == []
