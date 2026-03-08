"""
Programmatic Google Sheets template for new users.

Creates a new spreadsheet in the authenticated user's Google Drive
with the exact sheet/column layout that ``PhysicalGoldService`` and
``FixedDepositsService`` expect, plus entry tabs for stocks,
mutual funds, SIPs, and ETFs.
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as google_build

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

# ── Manual-entry sheet templates ─────────────────────────────

STOCKS_SHEET_NAME = "Stocks"
STOCKS_HEADERS = [
    "Symbol",
    "Qty",
    "Avg Price",
    "Exchange",
    "Account",
]

ETFS_SHEET_NAME = "ETFs"
ETFS_HEADERS = [
    "Symbol",
    "Qty",
    "Avg Price",
    "Exchange",
    "Account",
]

MF_SHEET_NAME = "MutualFunds"
MF_HEADERS = [
    "Fund",
    "Qty",
    "Avg NAV",
    "Account",
]

SIPS_SHEET_NAME = "SIPs"
SIPS_HEADERS = [
    "Fund",
    "Amount",
    "Frequency",
    "Installments",
    "Completed",
    "Status",
    "Next Due",
    "Account",
]

PF_SHEET_NAME = "ProvidentFund"
PF_HEADERS = [
    "Company",
    "Start Date",
    "End Date",
    "Monthly Contribution",
    "Interest Rate (%)",
    "Opening Balance",
    "Contribution",
]

# Unified registry used by the CRUD API (sheet_type → config)
SHEET_CONFIGS = {
    "stocks": {
        "sheet_name": STOCKS_SHEET_NAME,
        "headers": STOCKS_HEADERS,
        "fields": ["symbol", "qty", "avg_price", "exchange", "account"],
    },
    "etfs": {
        "sheet_name": ETFS_SHEET_NAME,
        "headers": ETFS_HEADERS,
        "fields": ["symbol", "qty", "avg_price", "exchange", "account"],
    },
    "mutual_funds": {
        "sheet_name": MF_SHEET_NAME,
        "headers": MF_HEADERS,
        "fields": ["fund", "qty", "avg_nav", "account"],
    },
    "sips": {
        "sheet_name": SIPS_SHEET_NAME,
        "headers": SIPS_HEADERS,
        "fields": ["fund", "amount", "frequency", "installments",
                    "completed", "status", "next_due", "account"],
    },
    "physical_gold": {
        "sheet_name": GOLD_SHEET_NAME,
        "headers": GOLD_HEADERS,
        "fields": ["date", "type", "retail_outlet", "purity",
                    "weight_gms", "bought_ibja_rate_per_gm"],
    },
    "fixed_deposits": {
        "sheet_name": FD_SHEET_NAME,
        "headers": FD_HEADERS,
        "fields": ["original_investment_date", "reinvested_date",
                    "bank_name", "deposit_year", "deposit_month",
                    "deposit_day", "original_amount", "reinvested_amount",
                    "interest_rate", "account"],
    },
    "provident_fund": {
        "sheet_name": PF_SHEET_NAME,
        "headers": PF_HEADERS,
        "fields": ["company_name", "start_date", "end_date",
                    "monthly_contribution", "interest_rate",
                    "opening_balance", "actual_contribution"],
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
    (PF_SHEET_NAME, PF_HEADERS, 6),
]


def create_portfolio_sheet(credentials: Credentials,
                           title: str = "Metron") -> str:
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

    resp = sheets_service.spreadsheets().create(
        body=body, fields="spreadsheetId"
    ).execute()
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

    # Apply formatting: bold headers + auto-resize
    _format_headers(sheets_service, spreadsheet_id)

    logger.info("Populated headers for all %d sheets", len(ALL_SHEETS))
    return spreadsheet_id


def _format_headers(sheets_service, spreadsheet_id: str) -> None:
    """Apply bold + background colour to the header row in each sheet."""
    meta = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties"
    ).execute()

    # Build a lookup from sheet name → header count
    header_counts = {name: len(headers) for name, headers, _idx in ALL_SHEETS}

    requests = []
    for sheet_props in meta.get("sheets", []):
        title = sheet_props["properties"]["title"]
        sheet_id = sheet_props["properties"]["sheetId"]
        col_count = header_counts.get(title)
        if col_count is None:
            continue
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {
                            "red": 0.9,
                            "green": 0.93,
                            "blue": 0.98,
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })

    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()
