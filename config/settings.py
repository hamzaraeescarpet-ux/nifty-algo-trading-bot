import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- ADAPTIVE SELF-LEARNING WEIGHTS ---
import json
ADAPTIVE_WEIGHTS_FILE = BASE_DIR / "config" / "adaptive_weights.json"

def load_adaptive_params():
    if ADAPTIVE_WEIGHTS_FILE.exists():
        try:
            with open(ADAPTIVE_WEIGHTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("parameters", {})
        except Exception:
            pass
    return {}

_adaptive = load_adaptive_params()

# --- TRADING MODE ---
# Mode: "PAPER" (virtual money simulation) or "LIVE" (Kotak Neo real orders)
TRADING_MODE = os.getenv("TRADING_MODE", "PAPER").upper()

# --- CAPITAL & RISK MANAGEMENT CONFIGURATION ---
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", 100000.0))  # ₹1,00,000 Starting Virtual Capital
RISK_PER_TRADE_PERCENT = float(os.getenv("RISK_PER_TRADE_PERCENT", 1.0))  # 1% risk per trade of total capital
MAX_DAILY_LOSS_PERCENT = float(os.getenv("MAX_DAILY_LOSS_PERCENT", 2.0))  # 2% Circuit Breaker (stops trading if hit)
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", 3))  # Max concurrent trades
MAX_DAILY_TRADES = int(_adaptive.get("max_daily_trades", 3))  # Self-learned daily trade limit (prevents overtrading)
RISK_REWARD_RATIO = float(_adaptive.get("risk_reward_ratio", os.getenv("RISK_REWARD_RATIO", 1.8)))  # Adaptive Target
BREAKEVEN_R_RATIO = float(_adaptive.get("breakeven_r_ratio", 0.6))  # Adaptive Breakeven Trigger

# --- STRATEGY PARAMETERS (Advanced Confluence with Trend Strength & Momentum) ---
TIMEFRAME = "5m"  # 5-minute candles for intraday
SUPERTREND_PERIOD = int(_adaptive.get("supertrend_period", 10))
SUPERTREND_MULTIPLIER = float(_adaptive.get("supertrend_multiplier", 3.0))
EMA_FAST = int(_adaptive.get("ema_fast", 20))
EMA_SLOW = int(_adaptive.get("ema_slow", 50))
RSI_PERIOD = 14
RSI_BUY_MIN = float(_adaptive.get("rsi_buy_min", 50.0))
RSI_BUY_MAX = float(_adaptive.get("rsi_buy_max", 70.0))
RSI_SELL_MIN = float(_adaptive.get("rsi_sell_min", 30.0))
RSI_SELL_MAX = float(_adaptive.get("rsi_sell_max", 50.0))
ADX_PERIOD = 14
ADX_MIN_THRESHOLD = float(_adaptive.get("adx_min_threshold", 20.0))  # Self-learned sideways filter
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = float(_adaptive.get("atr_sl_multiplier", 1.4))  # Tight, optimal volatility Stop Loss

# --- TIMEZONE & INTRADAY TIMINGS (IST) ---
from datetime import timezone, timedelta, datetime
IST = timezone(timedelta(hours=5, minutes=30))

def get_now_ist() -> datetime:
    """Returns current datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)

MARKET_OPEN_TIME = "09:15"
TRADING_START_TIME = "09:20"  # Small warm-up for initial candle
SQUARE_OFF_TIME = "15:10"     # Auto square-off all intraday positions before broker rush
MARKET_CLOSE_TIME = "15:30"

# --- DEFAULT WATCHLIST & INSTRUMENTS ---
TRADE_OPTIONS = True              # Enable Nifty 50 Options Trading (CE / PE)
INDEX_SYMBOL = "^NSEI"            # Nifty 50 Spot Index
OPTION_LOT_SIZE = 25              # Standard Nifty 50 Lot Size
ATM_STRIKE_STEP = 50              # Nifty strikes are every 50 points (e.g. 25000, 25050)
OPTION_DELTA = 0.5                # Delta for ATM options
MAX_OPTION_LOTS = 4               # Maximum lots allowed per trade

# Watchlist for Equity or Index
WATCHLIST = ["^NSEI"]

# --- GOOGLE SHEETS SETTINGS ---
GOOGLE_TOKEN_PATH = r"C:\Users\hamza\Downloads\python development\amro store\google_token.json"
GOOGLE_SHEET_NAME = "Nifty50_Algo_Trading_Journal"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1o37uPLPB9WrR97q3quvk8qFJm_JY5S5mJGgF4a-hhgE"

# --- WEB DASHBOARD SETTINGS ---
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 5000

# --- KOTAK NEO CREDENTIALS ---
KOTAK_CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY", "")
KOTAK_CONSUMER_SECRET = os.getenv("KOTAK_CONSUMER_SECRET", "")
KOTAK_MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER", "")
KOTAK_PASSWORD = os.getenv("KOTAK_PASSWORD", "")
KOTAK_MPIN = os.getenv("KOTAK_MPIN", "")
KOTAK_TOTP_KEY = os.getenv("KOTAK_TOTP_KEY", "")
KOTAK_ENVIRONMENT = os.getenv("KOTAK_ENVIRONMENT", "prod")
