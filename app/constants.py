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

# HTTP Status codes
HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_CONFLICT = 409

# API client timeouts and rate-limiting (seconds)
NSE_REQUEST_TIMEOUT = 10
GOOGLE_SHEETS_TIMEOUT = 20
IBJA_GOLD_PRICE_TIMEOUT = 20

# Yahoo Finance batch quote settings
YF_BATCH_MAX_WORKERS = 2  # max concurrent Yahoo Finance requests (tuned for 512 MB)
YF_MAX_RETRIES = 3  # retry attempts per symbol on transient failures
YF_RETRY_BASE_DELAY = 1.0  # exponential backoff base (1s, 2s, 4s)

# Server startup / UI timing (seconds)
SERVER_STARTUP_DELAY = 0.5

# Portfolio table row limit (displayed per table on the dashboard)
# Only a developer should change this value from the backend.
PORTFOLIO_TABLE_ROW_LIMIT = 10

# PIN / Authentication
PIN_CHECK_SENTINEL = "METRON_PIN_OK"
PIN_TTL = 30 * 60  # 30 minutes — in-memory PIN expiry
PIN_LOCKOUT_TIERS = [
    (3, 15 * 60),  # 3 failures → 15 minutes
    (6, 60 * 60),  # 6 failures → 1 hour
    (9, 4 * 60 * 60),  # 9 failures → 4 hours
]
PIN_RATE_LIMITER_MAX_ENTRIES = 1000

# Per-user in-memory store sizing (LRU caps)
SESSION_MANAGER_MAX_USERS = 1000
STATE_MANAGER_MAX_USERS = 1000

# Cache sizing and TTLs
MAX_PORTFOLIO_CACHE_USERS = 200
MAX_SHEETS_CACHE_USERS = 200
MAX_LTP_CACHE_SYMBOLS = 1000
NEGATIVE_LTP_CACHE_TTL = 300  # 5 minutes

# Middleware / Request origin validation
APP_REQUEST_HEADER = "X-Requested-With"
APP_REQUEST_HEADER_VALUE = "MetronApp"
PROGRAMMATIC_FETCH_MODES = frozenset({"cors", "same-origin", "no-cors"})

# Background data fetching
LTP_CACHE_WARMUP_INTERVAL = 2  # seconds between warmup polls
LTP_CACHE_WARMUP_ATTEMPTS = 6  # max polls (~12 s total)
USER_FETCH_LOCKS_MAX = 500
MARKET_DATA_MIN_INTERVAL = 60  # seconds — skip re-fetch if data is fresher

# Broker → Sheets sync
BROKER_SYNC_LOCKS_MAX = 500

# External service URLs
NSE_BASE_URL = "https://www.nseindia.com"
IBJA_BASE_URL = "https://ibjarates.com/"
YF_BASE_URL = "https://query1.finance.yahoo.com"

# Mutual fund market data (mfapi.in)
MF_API_URL = "https://api.mfapi.in/mf/latest"
MF_HOLDINGS_URL_TEMPLATE = "https://staticassets.zerodha.com/coin/scheme-portfolio/{isin}.json"
MF_API_TIMEOUT = 90  # seconds — the response is large (~4 MB)
MF_API_MAX_RETRIES = 3  # retry attempts on transient failures
MF_API_RETRY_DELAY = 5  # base delay in seconds (exponential backoff: 5s, 10s)
MARKET_DATA_CRON_HOUR_IST = 2  # daily refresh at 2 AM IST

# External service purities (gold)
IBJA_GOLD_PURITIES = ["999", "995", "916", "750", "585"]

# Nifty 50 configuration
NIFTY50_FALLBACK_SYMBOLS = [
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJFINANCE",
    "BAJAJFINSV",
    "BEL",
    "BHARTIARTL",
    "BRITANNIA",
    "CIPLA",
    "COALINDIA",
    "DIVISLAB",
    "DRREDDY",
    "EICHERMOT",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HEROMOTOCO",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "ITC",
    "INDUSINDBK",
    "INFY",
    "JSWSTEEL",
    "KOTAKBANK",
    "LT",
    "LTIM",
    "M&M",
    "MARUTI",
    "NESTLEIND",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SBIN",
    "SUNPHARMA",
    "TCS",
    "TATACONSUM",
    "TATASTEEL",
    "TECHM",
    "TITAN",
    "ULTRACEMCO",
    "WIPRO",
    "BPCL",
    "SHRIRAMFIN",
]
