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
DEFAULT_AUTO_REFRESH_INTERVAL = 60  # seconds
DEFAULT_CALLBACK_HOST = "127.0.0.1"
DEFAULT_CALLBACK_PORT = 5000
DEFAULT_CALLBACK_PATH = "/callback"
DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8000

# File / directory paths
CONFIG_FILENAME = "config.json"
CONFIG_DIR_NAME = "config"  # directory that houses config.json and credentials

# HTTP Status codes
HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_CONFLICT = 409

# API client timeouts and rate-limiting (seconds)
NSE_REQUEST_TIMEOUT = 10
NSE_REQUEST_DELAY = 0.2  # delay between requests to avoid rate-limiting
GOOGLE_SHEETS_TIMEOUT = 20
IBJA_GOLD_PRICE_TIMEOUT = 20

# Server startup / UI timing (seconds)
SERVER_STARTUP_DELAY = 0.5
SSE_KEEPALIVE_INTERVAL = 30  # SSE client keepalive interval
TOKEN_WAIT_POLL_INTERVAL = 5  # interval for polling request token

# External service URLs
NSE_BASE_URL = "https://www.nseindia.com"
IBJA_BASE_URL = "https://ibjarates.com/"
BSE_API_BASE_URL = "https://api.bseindia.com"

# Market index cache
MARKET_INDEX_CACHE_TTL = 15  # seconds

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
