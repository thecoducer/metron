"""
Programmatic Google Sheets template for new users.

Creates a new spreadsheet in the authenticated user's Google Drive
with the exact sheet/column layout that ``PhysicalGoldService`` and
``FixedDepositsService`` expect, plus entry tabs for stocks,
mutual funds, SIPs, and ETFs.
"""

from typing import TypedDict

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as google_build


class SheetConfig(TypedDict):
    """Configuration for a Google Sheets tab."""

    sheet_name: str
    headers: list[str]
    fields: list[str]


from ..logging_config import logger

# ---------------------------------------------------------------------------
# Template definitions — headers must match the column order that the
# existing parsers in google_sheets_client.py read.
# ---------------------------------------------------------------------------

GOLD_SHEET_NAME = "Gold"
GOLD_HEADERS = [
    "Date",
    "Type",
    "Retail Outlet",
    "Purity",
    "Weight in gms",
    "IBJA PM rate per 1 gm",
]

FD_SHEET_NAME = "FixedDeposits"
FD_HEADERS = [
    "Deposited On",
    "Reinvested On",
    "Bank",
    "Year",
    "Month",
    "Day",
    "Amount",
    "Reinvested Amt",
    "Rate",
    "Account",
]

# ── Transaction history sheet (CAS-sourced) ─────────────────

TRANSACTIONS_SHEET_NAME = "Transactions"
TRANSACTIONS_HEADERS = [
    "ISIN",
    "Fund Name",
    "Date",
    "Type",
    "Amount",
    "Units",
    "NAV",
    "Balance",
    "Account",
]

# ── Manual-entry sheet templates ─────────────────────────────

STOCKS_SHEET_NAME = "Stocks"
STOCKS_HEADERS = [
    "Symbol",
    "Qty",
    "Avg Price",
    "Exchange",
    "Account",
    "ISIN",
    "Source",
]

ETFS_SHEET_NAME = "ETFs"
ETFS_HEADERS = [
    "Symbol",
    "Qty",
    "Avg Price",
    "Exchange",
    "Account",
    "ISIN",
    "Source",
]

MF_SHEET_NAME = "MutualFunds"
MF_HEADERS = [
    "ISIN",  # was "Fund" — stores ISIN / trading symbol
    "Fund Name",
    "Qty",
    "Avg NAV",
    "Account",
    "Source",
    "Latest NAV",
    "NAV Updated Date",
]

SIPS_SHEET_NAME = "SIPs"
SIPS_HEADERS = [
    "Fund",
    "Fund Name",
    "Amount",
    "Frequency",
    "Installments",
    "Completed",
    "Status",
    "Next Due",
    "Account",
    "Source",
]

# Fields that hold date values and must be stored as MM/DD/YYYY in sheets.
DATE_FIELDS: frozenset[str] = frozenset(
    {"date", "original_investment_date", "reinvested_date", "nav_updated_date", "next_due"}
)

# Unified registry used by the CRUD API (sheet_type → config)
SHEET_CONFIGS: dict[str, SheetConfig] = {
    "stocks": {
        "sheet_name": STOCKS_SHEET_NAME,
        "headers": STOCKS_HEADERS,
        "fields": ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"],
    },
    "etfs": {
        "sheet_name": ETFS_SHEET_NAME,
        "headers": ETFS_HEADERS,
        "fields": ["symbol", "qty", "avg_price", "exchange", "account", "isin", "source"],
    },
    "mutual_funds": {
        "sheet_name": MF_SHEET_NAME,
        "headers": MF_HEADERS,
        "fields": ["isin", "fund_name", "qty", "avg_nav", "account", "source", "latest_nav", "nav_updated_date"],
    },
    "sips": {
        "sheet_name": SIPS_SHEET_NAME,
        "headers": SIPS_HEADERS,
        "fields": [
            "fund",
            "fund_name",
            "amount",
            "frequency",
            "installments",
            "completed",
            "status",
            "next_due",
            "account",
            "source",
        ],
    },
    "physical_gold": {
        "sheet_name": GOLD_SHEET_NAME,
        "headers": GOLD_HEADERS,
        "fields": ["date", "type", "retail_outlet", "purity", "weight_gms", "bought_ibja_rate_per_gm"],
    },
    "fixed_deposits": {
        "sheet_name": FD_SHEET_NAME,
        "headers": FD_HEADERS,
        "fields": [
            "original_investment_date",
            "reinvested_date",
            "bank_name",
            "deposit_year",
            "deposit_month",
            "deposit_day",
            "original_amount",
            "reinvested_amount",
            "interest_rate",
            "account",
        ],
    },
    "transactions": {
        "sheet_name": TRANSACTIONS_SHEET_NAME,
        "headers": TRANSACTIONS_HEADERS,
        "fields": [
            "isin",
            "fund_name",
            "date",
            "type",
            "amount",
            "units",
            "nav",
            "balance",
            "account",
        ],
    },
}

# All sheet tabs to create for a new user
ALL_SHEETS = [
    (GOLD_SHEET_NAME, GOLD_HEADERS, 0),
    (FD_SHEET_NAME, FD_HEADERS, 1),
    (STOCKS_SHEET_NAME, STOCKS_HEADERS, 2),
    (ETFS_SHEET_NAME, ETFS_HEADERS, 3),
    (MF_SHEET_NAME, MF_HEADERS, 4),
    (SIPS_SHEET_NAME, SIPS_HEADERS, 5),
    (TRANSACTIONS_SHEET_NAME, TRANSACTIONS_HEADERS, 6),
]


def create_portfolio_sheet(credentials: Credentials, title: str = "Metron") -> str:
    """Create a brand‑new spreadsheet in the user's Drive and populate headers.

    Args:
        credentials: The user's Google OAuth credentials.
        title: Title of the new spreadsheet.

    Returns:
        The ``spreadsheetId`` of the newly created file.
    """
    sheets_service = google_build("sheets", "v4", credentials=credentials)

    body = {
        "properties": {"title": title},
        "sheets": [
            {
                "properties": {
                    "title": name,
                    "index": idx,
                    "gridProperties": {"frozenRowCount": 1},
                }
            }
            for name, _headers, idx in ALL_SHEETS
        ],
    }

    resp = sheets_service.spreadsheets().create(body=body, fields="spreadsheetId").execute()
    spreadsheet_id = resp["spreadsheetId"]
    logger.info("Created new spreadsheet %s for user", spreadsheet_id)

    # Write header rows for all sheets
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {
                    "range": f"{name}!A1",
                    "values": [headers],
                }
                for name, headers, _idx in ALL_SHEETS
            ],
        },
    ).execute()

    logger.info("Populated headers for all %d sheets", len(ALL_SHEETS))
    return spreadsheet_id
