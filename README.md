# Metron

[![CI/CD](https://github.com/thecoducer/metron/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/thecoducer/metron/actions/workflows/ci-cd.yml)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-deployed-2196F3?logo=googlecloud&logoColor=white)](https://console.cloud.google.com/run/detail/asia-south1/metron/revisions?project=extreme-outpost-480113-c6)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A Flask-based dashboard for tracking your complete investment portfolio — stocks, mutual funds, SIPs, physical gold, and fixed deposits — with real-time broker sync and Google Sheets integration.

## Features

- **Broker account sync** — connect multiple broker accounts and fetch holdings automatically (currently supports [Zerodha Kite Connect](https://kite.trade/))
- **Real-time updates** via Server-Sent Events (SSE)
- **Auto-refresh** during market hours (9:00–16:30 IST) with optional 24/7 mode
- **Stocks & Mutual Funds** — holdings, P/L, day change, grouped by symbol across accounts
- **SIPs** tracking with monthly total and smart date formatting
- **Physical Gold** tracking via Google Sheets with live IBJA gold price P/L
- **Fixed Deposits** tracking via Google Sheets with compound interest calculations
- **Nifty 50** live prices page with NSE data
- **Interactive UI** — dark/light theme, privacy mode, compact number format (Lakhs/Crores), search, sort, pagination
- **Allocation percentages** across asset classes in summary cards

---

## Connecting a Broker Account

Metron syncs your holdings, mutual funds, and SIPs directly from your broker. Currently **Zerodha** (via Kite Connect) is supported — more brokers may be added in the future.

### Zerodha Kite Connect

#### 1. Register on the Developer Portal

1. Go to [Kite Connect Developer Portal](https://developers.kite.trade/) and sign in with your Zerodha credentials.
2. Click **Create new app** on the developer dashboard.
3. Fill in the app details:
   - **App name:** any name (e.g. "Metron")
   - **Redirect URL:** set based on how you'll use the app:
     - **Local:** `http://127.0.0.1:8000/api/callback`
     - **Web app:** `https://metron.web.app/api/callback`
   - **Postback URL:** Leave it as blank.
4. After creation, note your **API Key** and **API Secret** from the app details page.

#### 3. Connect Your Account in Metron

1. Sign in to Metron with your Google account.
2. Go to **Settings** → **Add Zerodha Account**.
3. Enter a label (e.g. "Personal"), your **API Key**, and **API Secret**.
4. Click **Save** — credentials are stored securely in Firebase.
5. Click **Login** next to the account — this opens Zerodha's OAuth page where you authorize access.
6. After authorization, you're redirected back and your portfolio data loads automatically.

> **Multiple accounts:** Repeat steps 2–5 for each Zerodha account. Each needs its own Kite Connect app with a separate API key and secret.

---

## Local Development Setup

### Prerequisites

- **Python 3.9+**
- A **Firebase** project (Firestore for data storage)
- A **Google Cloud** project (OAuth 2.0 for sign-in and Sheets access)
- A **broker developer account** ([setup instructions above](#connecting-a-broker-account)) — currently Zerodha Kite Connect

### 1. Clone the Repository

```bash
git clone https://github.com/thecoducer/metron.git
cd metron
```

### 2. Set Up Credential Files

All files go in the `config/` directory (all are git-ignored — never commit them):

| File | Purpose |
|------|---------|
| `config.json` | Server settings and feature flags |
| `firebase-credentials.json` | Firebase service account key |
| `google-oauth-credentials.json` | Google OAuth 2.0 client secrets |
| `flask-secret-key.txt` | Flask session signing secret |
| `zerodha-token-secret.txt` | Encryption key for cached Zerodha tokens |

---

#### Firebase Credentials

Firebase Firestore stores user profiles, connected broker accounts, OAuth tokens, and spreadsheet references.

1. Go to the [Firebase Console](https://console.firebase.google.com/) and create a project (or select existing).
2. Enable **Cloud Firestore** (Build → Firestore Database → Create database).
3. Go to **Project Settings** (gear icon) → **Service Accounts**.
4. Click **Generate new private key** — downloads a JSON file.
5. Save it as `config/firebase-credentials.json`.

---

#### Google OAuth Credentials

Google OAuth handles user sign-in and grants the app permission to create/read Google Sheets for physical gold and FD data.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) — use the same project linked to your Firebase project.
2. **Enable APIs:** Go to **APIs & Services** → **Library** and enable:
   - **Google Sheets API**
   - **Google Drive API**
3. **Configure consent screen:** Go to **APIs & Services** → **OAuth consent screen**.
   - Choose **External** user type.
   - Add scopes: `openid`, `userinfo.email`, `userinfo.profile`, `drive.file`.
   - Add your Google account as a **test user** (required while the app is in "Testing" mode).
4. **Create OAuth client:** Go to **APIs & Services** → **Credentials**.
   - Click **Create Credentials** → **OAuth client ID** → **Web application**.
   - Under **Authorized redirect URIs**, add: `http://127.0.0.1:8000/api/auth/google/callback`
   - Download the JSON and save as `config/google-oauth-credentials.json`.

---

#### Flask Secret Key

Signs Flask session cookies. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" > config/flask-secret-key.txt
```

Or set the `FLASK_SECRET_KEY` environment variable instead. If neither is set, a random key is used (sessions won't survive restarts).

---

#### Broker Token Secret

Encrypts cached broker access tokens at rest. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" > config/zerodha-token-secret.txt
```

Or set the `ZERODHA_TOKEN_SECRET` environment variable. If neither is set, a machine-specific key is derived (tokens won't be portable across machines).

---

### 3. Create `config/config.json`

```json
{
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
    "allow_browser_api_access": false
  }
}
```

| Key | Description | Default |
|-----|-------------|---------|
| `server.ui_host` | Host to bind the server | `127.0.0.1` |
| `server.ui_port` | Port number | `8000` |
| `timeouts.request_token_timeout_seconds` | Max wait for broker OAuth token | `180` |
| `timeouts.auto_refresh_interval_seconds` | Auto-refresh interval during market hours | `60` |
| `features.auto_refresh_outside_market_hours` | Auto-refresh outside 9:00–16:00 IST | `false` |
| `features.allow_browser_api_access` | Allow direct browser API access | `false` |

> **Redirect URLs must match your config.** Broker callback: `http://<host>:<port>/api/callback`. Google OAuth: `http://<host>:<port>/api/auth/google/callback`.

### 4. Start the Server

```bash
./start.sh
```

This script creates a virtual environment (`run_server/`), installs dependencies, validates config, and starts the server.

Open **http://127.0.0.1:8000/** in your browser.

---

## Security

- All credential files are git-ignored — never commit them
- Broker tokens encrypted at rest via `cryptography.fernet`
- Google OAuth 2.0 for user authentication
- Flask sessions signed with a secret key
- `drive.file` scope limits Google Drive access to files created by this app only

---

## Development

### Running Tests

```bash
./run_tests.sh
```

### Project Structure

```
├── main.py                         # Entry point
├── requirements.txt                # Dependencies
├── start.sh                        # Startup script (venv + deps + run)
├── run_tests.sh                    # Test runner
├── config/
│   ├── config.json                 # App config (git-ignored)
│   ├── firebase-credentials.json   # Firebase key (git-ignored)
│   ├── google-oauth-credentials.json # OAuth secrets (git-ignored)
│   ├── flask-secret-key.txt        # Session secret (git-ignored)
│   └── zerodha-token-secret.txt    # Token encryption key (git-ignored)
├── app/
│   ├── server.py                   # Flask app, SSE, background fetch
│   ├── routes.py                   # Route definitions
│   ├── services.py                 # Portfolio data aggregation
│   ├── fetchers.py                 # Data fetching orchestration
│   ├── config.py                   # Config loading & validation
│   ├── constants.py                # App-wide constants
│   ├── cache.py                    # In-memory cache with TTL
│   ├── utils.py                    # SessionManager, StateManager, helpers
│   ├── firebase_store.py           # Firestore persistence
│   ├── error_handler.py            # Exceptions & retry decorators
│   ├── logging_config.py           # Logger setup
│   ├── sse.py                      # Server-Sent Events manager
│   ├── middleware.py               # Request middleware
│   └── api/
│       ├── auth.py                 # Zerodha OAuth authentication
│       ├── google_auth.py          # Google OAuth 2.0 flow
│       ├── zerodha_client.py       # Multi-account Zerodha fetcher
│       ├── holdings.py             # Stock & MF holdings service
│       ├── sips.py                 # SIP data service
│       ├── market_data.py          # Market data (NSE, Yahoo Finance)
│       ├── google_sheets_client.py # Google Sheets integration
│       ├── ibja_gold_price.py      # IBJA gold price scraper
│       ├── physical_gold.py        # Physical gold P/L calculations
│       ├── fixed_deposits.py       # FD compound interest calculations
│       └── base_service.py         # Base class for data services
├── app/static/                     # CSS & JavaScript
├── app/templates/                  # HTML templates
└── tests/                          # Test suite
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Session expired** | Click **Login** next to the broker account to re-authorize |
| **Port already in use** | Change `ui_port` in `config/config.json` |
| **Config validation errors** | `start.sh` validates config on startup — check the error output |
| **Missing dependencies** | `start.sh` auto-installs from `requirements.txt` |
| **Gold prices not updating** | Fetched at 1 PM and 8 PM IST; click **Refresh** to force |

---

## License

MIT — For personal use.
