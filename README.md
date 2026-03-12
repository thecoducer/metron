<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/thecoducer/metron/main/app/static/images/metron-logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/thecoducer/metron/main/app/static/images/metron-logo-light.svg">
  <img alt="Metron" src="https://raw.githubusercontent.com/thecoducer/metron/main/app/static/images/metron-logo-light.svg" width="280">
</picture>

### *Measure what matters.*

**An open-source investment dashboard for Indian investors.**<br>
Track stocks, mutual funds, SIPs, physical gold, and fixed deposits — all in one place.

[![CI/CD](https://github.com/thecoducer/metron/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/thecoducer/metron/actions/workflows/ci-cd.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.3-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=D7FF64)](https://docs.astral.sh/ruff/)
[![Deploy on Render](https://img.shields.io/badge/deploy-Render-46E3B7?logo=render&logoColor=white)](https://render.com)

</div>

---

## Features

| Category | What you get |
|---|---|
| **Broker Sync** | Connect multiple Zerodha accounts via [Kite Connect](https://kite.trade/). Holdings, mutual funds, and SIPs are fetched automatically. |
| **Stocks & Mutual Funds** | Holdings with P/L, day change, and LTP — grouped by symbol across accounts. Sortable columns, search, and pagination. |
| **SIPs** | Active SIP list with monthly/annual outflow summary and frequency breakdown (weekly, monthly, quarterly). |
| **Physical Gold** | Track gold holdings via Google Sheets with live P/L calculated from [IBJA](https://ibjarates.com/) spot prices. |
| **Fixed Deposits** | FDs with compound interest calculations, maturity tracking, and ₹5L DICGC insurance limit warnings. |
| **Nifty 50** | Live constituent prices with NSE data on a dedicated page. |
| **Market Indices** | NIFTY 50, SENSEX, and other key indices with mini sparkline charts on the dashboard. |
| **Manual Entries** | Add, edit, and delete stocks, ETFs, mutual funds, SIPs, gold, and FDs directly from the UI — stored in your Google Sheet. |
| **Asset Allocation** | Visual allocation bar across all asset classes with clickable segments to jump to each section. |
| **Multi-Account** | Merge holdings from multiple broker accounts. Same symbol across accounts is grouped automatically. |
| **Dark & Light Theme** | Toggle from the user menu. Preference persists across sessions. |
| **Privacy Mode** | Blur sensitive financial data with one click. |
| **Compact Formatting** | Numbers displayed in Lakhs/Crores (₹) throughout. |
| **Mobile-Ready** | Fully responsive design with 5 breakpoints — works on phones, tablets, and desktops. Horizontal-scroll tables on small screens. |
| **Guided Tour** | Interactive onboarding walkthrough for new users. |
| **Google Drive as DB** | All investment data lives in a Google Sheet auto-created in your Drive — you own and control the data. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12 · Flask · Gunicorn |
| **Frontend** | Vanilla JS (no framework) · CSS with responsive breakpoints |
| **Data Sources** | Zerodha KiteConnect · Google Sheets API · NSE · Yahoo Finance · IBJA |
| **Auth** | Google OAuth 2.0 · PIN-based broker credential decryption |
| **Storage** | Firebase Firestore (user profiles, encrypted credentials) · Google Sheets (financial data) |
| **Encryption** | Fernet symmetric encryption for broker tokens and API keys at rest |
| **Deployment** | Docker · Render.com · GitHub Actions CI/CD |

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
     - **Web app:** `https://metron.onrender.com/api/callback`
   - **Postback URL:** Leave it as blank.
4. After creation, note your **API Key** and **API Secret** from the app details page.

#### 2. Connect Your Account in Metron

1. Sign in to Metron with your Google account.
2. Go to **Settings** → **Add Zerodha Account**.
3. Enter a label (e.g. "Personal"), your **API Key**, and **API Secret**.
4. Click **Save** — credentials are stored securely in Firebase.
5. Click **Login** next to the account — this opens Zerodha's OAuth page where you authorize access.
6. After authorization, you're redirected back and your portfolio data loads automatically.

> **Multiple accounts:** Repeat steps 2–5 for each Zerodha account. Each needs its own Kite Connect app with a separate API key and secret.

---

## Local Development Setup

Follow these steps carefully to get Metron running on your local machine.

### Prerequisites

- **Python 3.9+** (3.12 recommended)
- **pip** and **venv** (usually bundled with Python)
- A **Firebase** project with Firestore enabled
- A **Google Cloud** project with OAuth 2.0 configured
- A **Zerodha developer account** with a Kite Connect app ([setup instructions above](#connecting-a-broker-account))

### Step 1 — Clone the Repository

```bash
git clone https://github.com/thecoducer/metron.git
cd metron
```

### Step 2 — Set Up Firebase

Firebase Firestore stores user profiles, connected broker accounts, encrypted OAuth tokens, and spreadsheet references.

1. Go to the [Firebase Console](https://console.firebase.google.com/) and create a new project (or select an existing one).
2. Enable **Cloud Firestore**:
   - Navigate to **Build** → **Firestore Database** → **Create database**.
   - Choose your preferred region and start in **production mode**.
3. Generate a service account key:
   - Go to **Project Settings** (gear icon) → **Service Accounts**.
   - Click **Generate new private key** — this downloads a JSON file.
4. Save the downloaded file as:
   ```
   config/firebase-credentials.json
   ```

### Step 3 — Set Up Google OAuth

Google OAuth handles user sign-in and grants the app permission to create/read Google Sheets for your financial data.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) — use the **same project** linked to your Firebase project.
2. **Enable required APIs:**
   - Go to **APIs & Services** → **Library**.
   - Search for and enable:
     - **Google Sheets API**
     - **Google Drive API**
3. **Configure the OAuth consent screen:**
   - Go to **APIs & Services** → **OAuth consent screen**.
   - Choose **External** user type.
   - Add scopes: `openid`, `userinfo.email`, `userinfo.profile`, `drive.file`.
   - Add your Google account email as a **test user** (required while the app is in "Testing" mode).
4. **Create OAuth client credentials:**
   - Go to **APIs & Services** → **Credentials**.
   - Click **Create Credentials** → **OAuth client ID** → **Web application**.
   - Under **Authorized redirect URIs**, add:
     ```
     http://127.0.0.1:8000/api/auth/google/callback
     ```
   - Download the JSON file and save it as:
     ```
     config/google-oauth-credentials.json
     ```

### Step 4 — Generate Secrets

These secrets are used for session signing and encrypting broker tokens. All secret files go in the `config/` directory.

**Flask Secret Key** — signs session cookies:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" > config/flask-secret-key.txt
```

**Broker Token Secret** — encrypts cached broker access tokens at rest:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" > config/zerodha-token-secret.txt
```

> Alternatively, set `FLASK_SECRET_KEY` and `ZERODHA_TOKEN_SECRET` as environment variables instead of files.

### Step 5 — Create a `.env` File (Optional)

All settings have sensible defaults. Create a `.env` file in the **project root** only if you need to override them:

```bash
# Server
METRON_UI_HOST=127.0.0.1
METRON_UI_PORT=8000

# Timeouts (seconds)
METRON_REQUEST_TOKEN_TIMEOUT=180

# Features
METRON_ALLOW_BROWSER_API_ACCESS=false
```

| Variable | Description | Default |
|---|---|---|
| `METRON_UI_HOST` | Host to bind the server | `127.0.0.1` |
| `METRON_UI_PORT` | Port number | `8000` |
| `METRON_REQUEST_TOKEN_TIMEOUT` | Max wait for broker OAuth token (seconds) | `180` |
| `METRON_ALLOW_BROWSER_API_ACCESS` | Allow direct browser API access (for development) | `false` |

> **Redirect URLs must match your config.** Ensure the host and port in your broker app's redirect URL and Google OAuth redirect URI match `METRON_UI_HOST` and `METRON_UI_PORT`.
>
> - Broker callback: `http://<host>:<port>/api/callback`
> - Google OAuth: `http://<host>:<port>/api/auth/google/callback`

### Step 6 — Start the Server

```bash
./start.sh
```

This script automatically:
1. Creates a Python virtual environment (`run_server/`)
2. Installs all dependencies from `requirements.txt`
3. Loads `.env` (if present)
4. Starts the development server

Open **http://127.0.0.1:8000/** in your browser.

### Summary of Config Files

| File | Location | Purpose |
|---|---|---|
| `.env` | Project root | Server settings and feature flags |
| `firebase-credentials.json` | `config/` | Firebase service account key |
| `google-oauth-credentials.json` | `config/` | Google OAuth 2.0 client secrets |
| `flask-secret-key.txt` | `config/` | Flask session signing secret |
| `zerodha-token-secret.txt` | `config/` | Encryption key for cached broker tokens |

> All files in `config/` are git-ignored — **never commit them**.

---

## Security

| Measure | Details |
|---|---|
| **Credential isolation** | Financial data lives in your Google Sheet; credentials are in Firebase — separated by design |
| **Encryption at rest** | Broker API keys and tokens encrypted with Fernet (AES-128-CBC) using a server secret + your personal PIN |
| **OAuth 2.0** | Google sign-in with minimal scopes; `drive.file` limits access to app-created files only |
| **Session signing** | Flask sessions signed with a secret key |
| **Git-ignored secrets** | All credential files excluded from version control |

---

## Development

### Running Tests

```bash
./run_tests.sh
```

### Project Structure

```
metron/
├── main.py                          # Entry point (development server)
├── wsgi.py                          # WSGI entry point (production)
├── gunicorn.conf.py                 # Gunicorn config (production)
├── Dockerfile                       # Container build
├── render.yaml                      # Render.com deployment blueprint
├── requirements.txt                 # Runtime dependencies
├── requirements-prod.txt            # Production-only dependencies
├── requirements-dev.txt             # Dev/test dependencies
├── pyproject.toml                   # Ruff linter & formatter config
├── start.sh                         # Local startup script
├── run_tests.sh                     # Test runner
│
├── config/                          # Secrets & credentials (git-ignored)
│   ├── firebase-credentials.json
│   ├── google-oauth-credentials.json
│   ├── flask-secret-key.txt
│   └── zerodha-token-secret.txt
│
├── app/
│   ├── server.py                    # Flask app factory
│   ├── routes.py                    # Route definitions & API endpoints
│   ├── services.py                  # Portfolio data aggregation
│   ├── fetchers.py                  # Data fetching orchestration
│   ├── config.py                    # Config loading from env vars
│   ├── constants.py                 # App-wide constants & defaults
│   ├── cache.py                     # In-memory cache with TTL
│   ├── utils.py                     # SessionManager, StateManager, helpers
│   ├── firebase_store.py            # Firestore persistence layer
│   ├── error_handler.py             # Exceptions & retry decorators
│   ├── logging_config.py            # Logger setup
│   ├── middleware.py                # Request middleware
│   │
│   ├── api/
│   │   ├── auth.py                  # Zerodha OAuth authentication
│   │   ├── google_auth.py           # Google OAuth 2.0 flow
│   │   ├── zerodha_client.py        # Multi-account Zerodha fetcher
│   │   ├── holdings.py              # Stock & MF holdings service
│   │   ├── sips.py                  # SIP data service
│   │   ├── market_data.py           # Market data (NSE, Yahoo Finance)
│   │   ├── google_sheets_client.py  # Google Sheets integration
│   │   ├── ibja_gold_price.py       # IBJA gold price scraper
│   │   ├── physical_gold.py         # Physical gold P/L calculations
│   │   ├── fixed_deposits.py        # FD compound interest calculations
│   │   ├── user_sheets.py           # Sheet tab configs (headers, fields)
│   │   └── base_service.py          # Base class for data services
│   │
│   ├── static/                      # CSS, JavaScript, images
│   └── templates/                   # Jinja2 HTML templates
│
└── tests/                           # Test suite
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **Session expired** | Click **Login** next to the broker account to re-authorize |
| **Port already in use** | Change `METRON_UI_PORT` in `.env` or kill the process using the port |
| **Config validation errors** | Check `.env` syntax — `KEY=VALUE`, no spaces around `=` |
| **Missing dependencies** | `start.sh` auto-installs from `requirements.txt` on every run |
| **Gold prices not updating** | IBJA prices are fetched at 1 PM and 8 PM IST; click **Refresh** to force |
| **Google OAuth errors** | Ensure your email is added as a test user in the OAuth consent screen |
| **Redirect URI mismatch** | Verify that redirect URIs in broker app and Google OAuth match your `METRON_UI_HOST` and `METRON_UI_PORT` |

---

## License

MIT — For personal use.
