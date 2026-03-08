"""
Constants used throughout the Metron application.

This module is the single source of truth for all default values,
timeouts, paths, and tunables used across the application.
"""

# Status states
STATE_UPDATING = "updating"
STATE_UPDATED = "updated"
STATE_ERROR = "error"

# Market Hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 0
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
WEEKEND_SATURDAY = 5

# Gold Price Fetch Schedule (IST)
GOLD_PRICE_FETCH_HOURS = [13, 20]  # 1pm and 8pm IST

# Default server configuration values
DEFAULT_REQUEST_TOKEN_TIMEOUT = 180  # seconds
DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8000

# File / directory paths
CONFIG_DIR_NAME = "config"  # directory that houses credentials

# HTTP Status codes
HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_CONFLICT = 409

# API client timeouts and rate-limiting (seconds)
NSE_REQUEST_TIMEOUT = 10
NSE_REQUEST_DELAY = 0.2  # delay between requests to avoid rate-limiting
GOOGLE_SHEETS_TIMEOUT = 20
IBJA_GOLD_PRICE_TIMEOUT = 20

# Yahoo Finance batch quote settings
YF_BATCH_MAX_WORKERS = 10   # max concurrent Yahoo Finance requests
YF_MAX_RETRIES = 3           # retry attempts per symbol on transient failures
YF_RETRY_BASE_DELAY = 1.0   # exponential backoff base (1s, 2s, 4s)

# Server startup / UI timing (seconds)
SERVER_STARTUP_DELAY = 0.5
TOKEN_WAIT_POLL_INTERVAL = 5  # interval for polling request token

# Portfolio table row limit (displayed per table on the dashboard)
# Only a developer should change this value from the backend.
PORTFOLIO_TABLE_ROW_LIMIT = 10

# External service URLs
NSE_BASE_URL = "https://www.nseindia.com"
IBJA_BASE_URL = "https://ibjarates.com/"
BSE_API_BASE_URL = "https://api.bseindia.com"

# External service purities (gold)
IBJA_GOLD_PURITIES = ['999', '995', '916', '750', '585']

# Per-user Google OAuth scopes (drive.file covers sheet create + read/write
# for files created by this app only — no access to user's other sheets)
GOOGLE_USER_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",
]

# EPF (Employee Provident Fund) historical interest rates.
# Keyed by financial-year start year (e.g. 2024 = FY 2024-25, Apr 2024 – Mar 2025).
# Source: EPFO official annual gazette notifications.
EPF_HISTORICAL_RATES = {
    2010: 9.50,
    2011: 8.25,
    2012: 8.50,
    2013: 8.75,
    2014: 8.75,
    2015: 8.80,
    2016: 8.65,
    2017: 8.55,
    2018: 8.65,
    2019: 8.50,
    2020: 8.50,
    2021: 8.10,
    2022: 8.15,
    2023: 8.25,
    2024: 8.25,
    2025: 8.25,
}
EPF_DEFAULT_RATE = 8.50  # fallback for financial years not in the table

# Nifty 50 configuration
NIFTY50_FALLBACK_SYMBOLS = [
    "ADANIPORTS", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BHARTIARTL", "BPCL", "BRITANNIA", "CIPLA",
    "COALINDIA", "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM",
    "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC",
    "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE",
    "SBILIFE", "SBIN", "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM",
    "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN",
    "ULTRACEMCO", "WIPRO", "APOLLOHOSP", "ADANIENT", "LTIM"
]
