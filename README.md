# Metron

[![Tests](https://github.com/thecoducer/investment-portfolio-tracker/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/thecoducer/investment-portfolio-tracker/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A Flask-based dashboard for tracking your complete investment portfolio — stocks, mutual funds, SIPs, physical gold, and fixed deposits — with real-time updates from Zerodha and Google Sheets.

## Features

- **Multi-account Zerodha support** with encrypted session caching
- **Real-time updates** via Server-Sent Events (SSE)
- **Auto-refresh** during market hours (9:00–16:30 IST) with optional 24/7 mode
- **Stocks & Mutual Funds** — holdings, P/L, day change, grouped by symbol across accounts
- **SIPs** tracking with monthly total and smart date formatting
- **Physical Gold** tracking via Google Sheets with live IBJA price P/L

*Summary view enhancements:* the gold summary card now shows “(ETFs + Physical)” to clarify the components and includes a small CSS‑styled toggle icon (no emojis) that switches between ETF and physical gold P/L, invested and current values.
- **Fixed Deposits** tracking via Google Sheets with compound interest calculations
- **FD Summary** grouped by bank and account with high-value highlighting
- **Nifty 50** live prices page with NSE data
- **Interactive UI** — dark/light theme, privacy mode, compact number format (Lakhs/Crores), search, sort, pagination
- **Allocation percentages** across asset classes in summary cards

## Prerequisites

1. **Python 3.9+**
2. **Zerodha KiteConnect API credentials** — see [Zerodha Setup](#zerodha-kiteconnect-setup) below
3. **(Optional) Google Sheets API** — for physical gold and/or fixed deposits tracking. See [Google Sheets Setup](#google-sheets-setup-optional)

## Quick Start

```bash
# 1. Clone and configure
cp config/config.json.example config/config.json
# Edit config/config.json with your Zerodha API credentials (see setup guide below)

# 2. Run
./start.sh

# 3. Open dashboard
# http://127.0.0.1:8000/
```

The `start.sh` script automatically creates a virtual environment, installs dependencies, validates your config, and starts the server.

---

## Zerodha KiteConnect Setup

### 1. Create a Kite Connect App

1. Go to [Kite Connect Developer Console](https://developers.kite.trade/)
2. Sign in with your Zerodha credentials
3. Click **Create new app** (or use an existing one)
4. Fill in the app details:
   - **App Name**: Any name (e.g., `Metron`)
   - **Redirect URL**: `http://127.0.0.1:5000/callback`
   - **Postback URL**: Leave blank
   - **Description**: Optional
5. Click **Create**

### 2. Get Your API Credentials

After creating the app, you'll see:
- **API Key** — a string like `abcdef1234567890`
- **API Secret** — click "Show API secret" to reveal it

### 3. Configure `config.json`

```bash
cp config/config.json.example config/config.json
```

Edit `config/config.json` with your credentials:

```json
{
  "accounts": [
    {
      "name": "MyAccount",
      "api_key": "your_api_key_here",
      "api_secret": "your_api_secret_here"
    }
  ]
}
```

For **multiple Zerodha accounts**, add more entries to the `accounts` array. Each account needs its own Kite Connect app with its own API key and secret.

### 4. Authentication Flow

1. Run `./start.sh` — the dashboard opens in your browser
2. Click **Refresh** (or **Login** if session is expired)
3. A Zerodha login page opens — enter your credentials and complete 2FA
4. The tab auto-closes and data starts loading
5. Subsequent refreshes are automatic (no login needed until the session expires)

> **Note:** Sessions are encrypted and cached locally. You only need to log in again when the Kite session expires (typically daily).

---

## Configuration

Full `config/config.json` reference:

```json
{
  "accounts": [
    {
      "name": "Account1",
      "api_key": "your_kite_api_key_here",
      "api_secret": "your_kite_api_secret_here"
    }
  ],
  "server": {
    "ui_host": "127.0.0.1",
    "ui_port": 8000
  },
  "timeouts": {
    "request_token_timeout_seconds": 180,
    "auto_refresh_interval_seconds": 60
  },
  "features": {
    "auto_refresh_outside_market_hours": false,
    "fetch_physical_gold_from_google_sheets": {
      "enabled": false,
      "credentials_file": "path/to/service-account-credentials.json",
      "spreadsheet_id": "your_google_sheets_spreadsheet_id",
      "range_name": "Gold!A:K"
    },
    "fetch_fixed_deposits_from_google_sheets": {
      "enabled": false,
      "credentials_file": "path/to/service-account-credentials.json",
      "spreadsheet_id": "your_google_sheets_spreadsheet_id",
      "range_name": "FixedDeposits!A:J"
    }
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `ui_host` / `ui_port` | `127.0.0.1:8000` | Dashboard web server and OAuth callback |
| `ui_host` / `ui_port` | `127.0.0.1:8000` | Dashboard web server |
| `request_token_timeout_seconds` | `180` | How long to wait for OAuth login |
| `auto_refresh_interval_seconds` | `60` | Seconds between auto-refreshes |
| `auto_refresh_outside_market_hours` | `false` | Set `true` to refresh 24/7 |

> **Important:** Your Google and Zerodha app redirect URLs must exactly match `http://127.0.0.1:8000/callback`.

---

## Google Sheets Setup (Optional)

Physical Gold and Fixed Deposits tracking both use Google Sheets as the data source. They share the same Google Cloud setup but can use different spreadsheets.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Google Sheets API**:
   - Navigate to **APIs & Services** → **Library**
   - Search for **Google Sheets API** → Click **Enable**

### Step 2: Create a Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Enter a name (e.g., `metron`) → Click **Create and Continue**
4. Skip optional permissions → Click **Done**

### Step 3: Download the Credentials Key

1. Click on the service account you just created
2. Go to the **Keys** tab
3. Click **Add Key** → **Create new key** → Choose **JSON** → Click **Create**
4. Save the downloaded file to your project's config directory (e.g., `config/google-credentials.json`)

### Step 4: Share Your Spreadsheet

1. Open your Google Sheet
2. Click **Share**
3. Add the service account email (found in the JSON file as `client_email`, looks like `metron@project-name.iam.gserviceaccount.com`)
4. Set permission to **Viewer** (read-only is sufficient)
5. Copy the **Spreadsheet ID** from the URL: `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit`

### Step 5: Install Dependencies

These are included in `requirements.txt` and installed automatically by `start.sh`. If installing manually:

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

---

## Physical Gold Sheet Template

Create a sheet (e.g., named `Gold`) with the following structure. The first row is the header; data starts from row 2.

| Column | Header | Description | Example |
|--------|--------|-------------|---------|
| A | Date | Purchase date | `2024-01-15` |
| B | Type | Item type | `Coin`, `Bar`, `Jewellery` |
| C | Retail Outlet | Store/dealer name | `Tanishq`, `Malabar Gold` |
| D | Purity | Gold purity | `999`, `916`, `750` |
| E | Weight in gms | Weight in grams | `10.5` |
| F | IBJA PM rate per 1 gm | IBJA rate at time of purchase | `6543.21` |

**Example data:**

```
| Date       | Type | Retail Outlet | Purity | Weight in gms | IBJA PM rate per 1 gm |
|------------|------|---------------|--------|---------------|-----------------------|
| 2024-01-15 | Coin | Tanishq       | 999    | 10.000        | 6543.21               |
| 2024-03-20 | Bar  | Malabar Gold  | 999    | 8.000         | 6812.50               |
| 2024-06-10 | Coin | Joyalukkas    | 916    | 5.000         | 6012.00               |
```

**Enable in `config/config.json`:**

```json
"fetch_physical_gold_from_google_sheets": {
  "enabled": true,
  "credentials_file": "google-credentials.json",
  "spreadsheet_id": "your_spreadsheet_id",
  "range_name": "Gold!A:F"
}
```

**How P/L is calculated:**
- Latest IBJA gold prices are fetched from [ibjarates.com](https://ibjarates.com/)
- **999 purity**: Uses the latest IBJA 999 fine gold PM rate
- **916 purity**: Uses the latest IBJA 916 gold PM rate
- **Other purities**: Matched to the closest available IBJA rate
- Prices are refreshed on first load and during scheduled hours

**Notes:**
- Empty rows are skipped automatically
- Numbers can include `₹` symbols and commas — they are parsed automatically
- The `range_name` should cover all your data columns (A through F minimum)

---

## Fixed Deposits Sheet Template

Create a sheet (e.g., named `FixedDeposits`) with the following structure. The first row is the header; data starts from row 2.

| Column | Header | Description | Example |
|--------|--------|-------------|---------|
| A | Deposited On | Original deposit date | `January 15, 2024` |
| B | Reinvested On | Reinvestment date (if rolled over) | `January 15, 2025` |
| C | Bank | Bank or institution name | `SBI`, `HDFC Bank` |
| D | Year | Deposit tenure — years | `1` |
| E | Month | Deposit tenure — months | `6` |
| F | Day | Deposit tenure — days | `0` |
| G | Amount | Original deposit amount | `100000` |
| H | Reinvested Amount | Amount after reinvestment (if any) | `107000` |
| I | Interest Rate | Annual interest rate (%) | `7.25` |
| J | Redeemed? | Whether the FD has been redeemed | `Yes` or `No` |
| K | Account | Account holder name | `John` |

**Example data:**

```
| Deposited On      | Reinvested On     | Bank      | Year | Month | Day | Amount  | Reinvested Amt | Rate | Redeemed? | Account |
|-------------------|-------------------|-----------|------|-------|-----|---------|----------------|------|-----------|---------|
| January 15, 2024  |                   | SBI       | 1    | 0     | 0   | 100000  |                | 7.10 | No        | John    |
| March 20, 2023    | March 20, 2024    | HDFC Bank | 1    | 6     | 0   | 200000  | 214500         | 7.25 | No        | John    |
| June 1, 2023      |                   | ICICI     | 2    | 0     | 0   | 50000   |                | 6.90 | Yes       | Jane    |
```

**Enable in `config/config.json`:**

```json
"fetch_fixed_deposits_from_google_sheets": {
  "enabled": true,
  "credentials_file": "google-credentials.json",
  "spreadsheet_id": "your_spreadsheet_id",
  "range_name": "FixedDeposits!A:K"
}
```

**How it works:**
- Current value is calculated using **compound interest** (quarterly compounding) based on the deposit amount, interest rate, and elapsed time
- **Redeemed FDs** (marked `Yes` in column J) are excluded from calculations
- **Reinvested FDs** use the reinvested amount and date for current value calculation
- **Maturity date** is auto-calculated from the deposit date + tenure (Year/Month/Day)
- The **FD Summary** table groups deposits by bank and account, highlighting accounts with total current value >= 5 Lakhs

**Notes:**
- Both Physical Gold and Fixed Deposits can share the same `credentials_file` and even the same `spreadsheet_id` (just use different sheet tabs and `range_name` values)
- Empty rows are skipped automatically
- Numbers can include `₹` symbols and commas

---

## Security

- Never commit `config/config.json` or your Google credentials JSON file
- Both are listed in `.gitignore`
- Session tokens are encrypted using machine-specific keys (via `cryptography.fernet`)
- OAuth flow for secure Zerodha authentication
- Google Sheets service account has read-only access

---

## Development

### Running Tests

```bash
./run_tests.sh
```

### Project Structure

```
├── main.py                        # Entry point
├── requirements.txt               # Python dependencies
├── pytest.ini                     # Pytest configuration
├── config/
│   ├── config.json.example        # Configuration template
│   ├── config.json                # Your local config (git-ignored)
│   └── google-credentials.json    # Google service account key (git-ignored)
├── start.sh                       # Startup script (venv + deps + run)
├── run_tests.sh                   # Test runner
├── app/                           # Main application package
│   ├── server.py                  # Flask app, SSE, background fetch orchestration
│   ├── routes.py                  # Flask route definitions
│   ├── services.py                # Portfolio data aggregation services
│   ├── fetchers.py                # Data fetching orchestration
│   ├── config.py                  # Configuration loading & validation
│   ├── constants.py               # App-wide constants
│   ├── cache.py                   # In-memory cache with TTL
│   ├── utils.py                   # SessionManager, StateManager, helpers
│   ├── error_handler.py           # Custom exceptions, retry/error decorators
│   ├── logging_config.py          # Logger setup
│   ├── sse.py                     # Server-Sent Events manager
│   ├── api/
│   │   ├── auth.py                # Zerodha OAuth authentication
│   │   ├── zerodha_client.py      # Multi-account data fetcher
│   │   ├── holdings.py            # Stock & MF holdings service
│   │   ├── sips.py                # SIP service
│   │   ├── market_data.py          # Market data client (NSE, Yahoo Finance)
│   │   ├── google_sheets_client.py # Google Sheets client
│   │   ├── ibja_gold_price.py     # IBJA gold price scraper
│   │   ├── physical_gold.py       # Gold P/L enrichment
│   │   ├── fixed_deposits.py      # FD compound interest calculations
│   │   └── base_service.py        # Base class for data services
│   ├── static/
│   │   ├── css/styles.css         # Stylesheet
│   │   └── js/
│   │       ├── app.js             # Main app controller
│   │       ├── data-manager.js    # API data fetcher
│   │       ├── table-renderer.js  # Table rendering (stocks, MF, SIPs, gold, FDs)
│   │       ├── summary-manager.js # Summary card updates
│   │       ├── sort-manager.js    # Sort logic for all tables
│   │       ├── pagination.js      # Reusable pagination component
│   │       ├── sse-manager.js     # SSE connection manager
│   │       ├── theme-manager.js   # Dark/light theme
│   │       ├── visibility-manager.js # Privacy mode
│   │       ├── nifty50.js         # Nifty 50 page controller
│   │       └── utils.js           # Formatter & Calculator utilities
│   └── templates/
│       ├── portfolio.html         # Main portfolio dashboard
│       ├── nifty50.html           # Nifty 50 page
│       ├── callback_success.html  # OAuth success page
│       └── callback_error.html    # OAuth error page
├── tests/                         # Test suite
└── docs/                          # Documentation
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Session expired / Login button shown** | Click **Login** — completes Zerodha OAuth in a new tab |
| **Port already in use** | Change `ui_port` in `config/config.json` |
| **Google Sheets not loading** | Check that the sheet is shared with the service account email |
| **Gold prices not updating** | Prices are fetched on first load and at scheduled hours; click **Refresh** to force |
| **Config validation errors** | Run `./start.sh` — it validates `config/config.json` before starting |
| **Missing dependencies** | `start.sh` auto-installs from `requirements.txt`; for Google Sheets, ensure the libraries are in `requirements.txt` |

---

## License

MIT — For personal use.
