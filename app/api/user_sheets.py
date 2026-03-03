"""
Programmatic Google Sheets template for new users.

Creates a new spreadsheet in the authenticated user's Google Drive
with the exact sheet/column layout that ``PhysicalGoldService`` and
``FixedDepositsService`` expect.
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
    "Redeemed?",
    "Account",
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
                    "title": GOLD_SHEET_NAME,
                    "index": 0,
                    "gridProperties": {"frozenRowCount": 1},
                }
            },
            {
                "properties": {
                    "title": FD_SHEET_NAME,
                    "index": 1,
                    "gridProperties": {"frozenRowCount": 1},
                }
            },
        ],
    }

    resp = sheets_service.spreadsheets().create(
        body=body, fields="spreadsheetId"
    ).execute()
    spreadsheet_id = resp["spreadsheetId"]
    logger.info("Created new spreadsheet %s for user", spreadsheet_id)

    # Write header rows
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {
                    "range": f"{GOLD_SHEET_NAME}!A1",
                    "values": [GOLD_HEADERS],
                },
                {
                    "range": f"{FD_SHEET_NAME}!A1",
                    "values": [FD_HEADERS],
                },
            ],
        },
    ).execute()

    # Apply formatting: bold headers + auto-resize
    _format_headers(sheets_service, spreadsheet_id)

    logger.info("Populated headers for Gold and FixedDeposits sheets")
    return spreadsheet_id


def _format_headers(sheets_service, spreadsheet_id: str) -> None:
    """Apply bold + background colour to the header row in each sheet."""
    # Fetch sheet metadata so we can get internal sheet IDs
    meta = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties"
    ).execute()

    requests = []
    for sheet_props in meta.get("sheets", []):
        sheet_id = sheet_props["properties"]["sheetId"]
        col_count = (
            len(GOLD_HEADERS)
            if sheet_props["properties"]["title"] == GOLD_SHEET_NAME
            else len(FD_HEADERS)
        )
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
