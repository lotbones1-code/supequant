"""
Global Configuration for Elite Quant Trading System
All settings centralized here for easy tuning
"""

import os
from dotenv import load_dotenv

load_dotenv()

# =====================================
# API CREDENTIALS
# =====================================
OKX_API_KEY = os.getenv('OKX_API_KEY', '')
OKX_SECRET_KEY = os.getenv('OKX_SECRET_KEY', '')
OKX_PASSPHRASE = os.getenv('OKX_PASSPHRASE', '')
OKX_SIMULATED = os.getenv('OKX_SIMULATED', 'True').lower() == 'true'  # Start in demo mode

# =====================================
# DASHBOARD SETTINGS
# =====================================
DASHBOARD_ENABLED = True
DASHBOARD_HOST = '0.0.0.0'
DASHBOARD_PORT = 8080
DASHBOARD_SECRET_KEY = os.getenv('DASHBOARD_SECRET_KEY', 'supequant-dashboard-2026')

# =====================================
# TRADING PARAMETERS
# =====================================
# Core trading settings
TRADING_SYMBOL = "SOL-USDT-SWAP"  # Main trading pair (Solana perpetual)
REFERENCE_SYMBOL = "BTC-USDT-SWAP"  # Reference symbol (Bitcoin for correlation)
TRADING_MODE = "perp"  # 'spot' or 'perp'
MAX_DAILY_TRADES = 10  # Increased from 5
TRADE_INTERVAL_MINUTES = 30  # Reduced from 60 - trade more often

# =====================================
# RISK MANAGEMENT
# =====================================
# Position sizing
MAX_RISK_PER_TRADE = 0.01  # 1% of account per trade (was 0.5%)
MAX_POSITIONS_OPEN = 2  # Allow 2 positions (was 1)
POSITION_SIZE_PCT = 0.03  # Use 3% of account per position (was 2%)

# Daily limits
MAX_DAILY_LOSS_PCT = 0.05  # 5% max daily loss (was 2.5%)
MAX_DAILY_DRAWDOWN = 0.06  # 6% max drawdown before shutdown (was 3%)

# Stop loss and take profit
ATR_STOP_MULTIPLIER = 1.5  # Stop loss = 1.5x ATR (tighter, was 2.0)
TP1_RR_RATIO = 1.5  # First TP at 1.5:1 RR
TP2_RR_RATIO = 2.5  # Second TP at 2.5:1 RR (was 3.0)
TRAILING_STOP_ACTIVATION = 1.0  # Activate trailing stop after 1:1 RR (was 1.2)

# =====================================
# TIMEFRAME SETTINGS
# =====================================
# Multi-timeframe analysis
HTF_TIMEFRAME = "4H"  # Higher timeframe for trend (OKX uses capital H)
MTF_TIMEFRAME = "15m"  # Medium timeframe for conviction
LTF_TIMEFRAME = "5m"  # Lower timeframe for entry trigger
MICRO_TIMEFRAME = "1m"  # Micro timeframe for precise entry

# Data lookback periods (in candles)
HTF_LOOKBACK = 100
MTF_LOOKBACK = 200
LTF_LOOKBACK = 300

# =====================================
# FILTER THRESHOLDS - LOOSENED FOR MORE TRADES
# =====================================
# Market Regime Filter - MORE PERMISSIVE
ATR_MIN_PERCENTILE = 10  # Was 20 - accept calmer markets
ATR_MAX_PERCENTILE = 95  # Was 80 - accept higher volatility
VOLATILITY_COMPRESSION_THRESHOLD = 0.5  # Was 0.7 - easier to detect compression
FUNDING_RATE_MAX = 0.001  # Was 0.0005 - more permissive (0.1%)
FUNDING_RATE_MIN = -0.001
OI_CHANGE_MAX = 0.25  # Was 0.15 - allow more OI change

# Multi-Timeframe Filter - MUCH LIGHTER
HTF_TREND_MIN_STRENGTH = 0.3  # Was 0.6 - much lighter requirement
MTF_TREND_MIN_STRENGTH = 0.25  # Was 0.5
LTF_TREND_MIN_STRENGTH = 0.2  # Was 0.4
TIMEFRAME_ALIGNMENT_THRESHOLD = 0.4  # Was 0.7 - don't require perfect alignment

# AI Rejection Filter - MORE PERMISSIVE
AI_CONFIDENCE_THRESHOLD = 40  # Was 70 - allow more trades through
AI_MODEL_PATH = "model_learning/rejection_model.pkl"
AI_FEATURE_WINDOW = 50

# Pattern Failure Detection - LESS STRICT
BULL_TRAP_THRESHOLD = 0.03  # Was 0.015 - more tolerance for fakeouts
BEAR_TRAP_THRESHOLD = 0.03
LOW_LIQUIDITY_VOLUME_RATIO = 0.15  # Was 0.3 - accept lower volume
STOP_HUNT_WICK_RATIO = 4.0  # Was 3.0 - less sensitive
FAKEOUT_REVERSION_PCT = 0.9  # Was 0.8 - need stronger confirmation

# BTC-SOL Correlation Filter - MUCH LIGHTER
BTC_SOL_CORRELATION_ENABLED = True
BTC_SOL_MIN_CORRELATION = 0.4  # Was 0.7 - much looser
BTC_SOL_TREND_AGREEMENT_REQUIRED = False
BTC_SOL_DIVERGENCE_MAX = 0.25  # Was 0.15 - allow more divergence
BTC_SOL_STRONG_OPPOSITION_THRESHOLD = 0.85  # Was 0.7 - only reject on very strong opposition
BTC_VOL_EXTREME_PERCENTILE = 98  # Was 95 - only reject extreme BTC moves

# Macro Driver Filter - LIGHTER
MACRO_DRIVER_ENABLED = True
MACRO_DRIVER_BLOCK_ON_CRISIS = True  # Still block during real crisis
MACRO_DRIVER_MIN_SCORE = 25  # Was 40 - lower bar
MACRO_DRIVER_TIER1_WEIGHT = 0.40
MACRO_DRIVER_TIER2_WEIGHT = 0.30
MACRO_DRIVER_TIER3_WEIGHT = 0.20
MACRO_DRIVER_TIER4_WEIGHT = 0.10

# Trading Checklist Filter - MORE PERMISSIVE
CHECKLIST_ENABLED = True
CHECKLIST_BLOCK_THRESHOLD = 35  # Was 60 - much lower bar
CHECKLIST_REDUCE_THRESHOLD = 55  # Was 80 - reduce size less often
CHECKLIST_MACRO_WEIGHT = 0.25
CHECKLIST_SENTIMENT_WEIGHT = 0.20
CHECKLIST_STRUCTURE_WEIGHT = 0.25
CHECKLIST_AI_WEIGHT = 0.15
CHECKLIST_FLOWS_WEIGHT = 0.10
CHECKLIST_SOCIAL_WEIGHT = 0.05

# =====================================
# STRATEGY SETTINGS
# =====================================
# Breakout Strategy - EASIER TO TRIGGER
BREAKOUT_VOLUME_MULTIPLIER = 1.2  # Was 1.5 - less volume required
BREAKOUT_ATR_COMPRESSION = 0.75  # Was 0.65 - easier to detect
BREAKOUT_CONSOLIDATION_BARS = 15  # Was 20 - shorter consolidation OK

# Pullback Strategy - MORE PERMISSIVE
PULLBACK_FIBONACCI_LEVELS = [0.382, 0.5, 0.618, 0.786]  # Added 0.786
PULLBACK_MAX_RETRACEMENT = 0.786  # Was 0.618 - allow deeper pullbacks
PULLBACK_TREND_STRENGTH_MIN = 0.4  # Was 0.6 - lighter trend requirement

# =====================================
# DATA FEED SETTINGS
# =====================================
# API rate limiting
API_RATE_LIMIT_MS = 100
MAX_RETRIES = 3
RETRY_DELAY_MS = 1000

# Caching
ENABLE_CACHE = True
CACHE_EXPIRY_SECONDS = 60

# =====================================
# MODEL LEARNING SETTINGS
# =====================================
COLLECT_TRAINING_DATA = True
MIN_SAMPLES_FOR_TRAINING = 100
RETRAIN_INTERVAL_DAYS = 7
FEATURE_ENGINEERING_ENABLED = True

FEATURES_PRICE_ACTION = True
FEATURES_VOLUME = True
FEATURES_VOLATILITY = True
FEATURES_MOMENTUM = True
FEATURES_MARKET_DATA = True

# =====================================
# LOGGING & MONITORING
# =====================================
LOG_LEVEL = "INFO"  # Changed from DEBUG to reduce noise
LOG_FILE = "logs/trading.log"
LOG_TRADES_FILE = "logs/trades.log"
LOG_FILTERS_FILE = "logs/filters.log"

TRACK_METRICS = True
METRICS_FILE = "logs/metrics.json"

# =====================================
# SAFETY SETTINGS
# =====================================
ENABLE_EMERGENCY_SHUTDOWN = True
EMERGENCY_VOLATILITY_MULTIPLIER = 6.0  # Was 5.0 - less sensitive
EMERGENCY_DRAWDOWN_PCT = 0.08  # Was 0.05 - more headroom
EMERGENCY_API_FAILURE_COUNT = 10  # Was 5 - more tolerance

ENABLE_KILL_SWITCH = True
KILL_SWITCH_FILE = "KILL_SWITCH.txt"

# =====================================
# BACKTESTING SETTINGS
# =====================================
BACKTEST_START_DATE = "2024-01-01"
BACKTEST_END_DATE = "2024-12-31"
BACKTEST_INITIAL_CAPITAL = 10000
BACKTEST_COMMISSION = 0.0006

BACKTEST_MODE = os.getenv('BACKTEST_MODE', 'False').lower() == 'true'

# BACKTEST MODE - Even looser for testing
if BACKTEST_MODE:
    ATR_MIN_PERCENTILE = 5
    ATR_MAX_PERCENTILE = 98
    FUNDING_RATE_MAX = 0.002
    FUNDING_RATE_MIN = -0.002
    OI_CHANGE_MAX = 0.35
    HTF_TREND_MIN_STRENGTH = 0.2
    MTF_TREND_MIN_STRENGTH = 0.15
    LTF_TREND_MIN_STRENGTH = 0.1
    TIMEFRAME_ALIGNMENT_THRESHOLD = 0.3
    AI_CONFIDENCE_THRESHOLD = 30
    BULL_TRAP_THRESHOLD = 0.04
    BEAR_TRAP_THRESHOLD = 0.04
    LOW_LIQUIDITY_VOLUME_RATIO = 0.1
    STOP_HUNT_WICK_RATIO = 5.0
    BTC_SOL_MIN_CORRELATION = 0.3
    BTC_SOL_DIVERGENCE_MAX = 0.35
    BTC_SOL_STRONG_OPPOSITION_THRESHOLD = 0.9
    MACRO_DRIVER_MIN_SCORE = 15
    CHECKLIST_BLOCK_THRESHOLD = 25
    CHECKLIST_REDUCE_THRESHOLD = 45

# =====================================
# TELEGRAM ALERTS
# =====================================
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# =====================================
# VALIDATION
# =====================================
def validate_config():
    """Validate critical configuration settings"""
    errors = []

    if not OKX_API_KEY or not OKX_SECRET_KEY or not OKX_PASSPHRASE:
        errors.append("Missing OKX API credentials in .env file")

    if MAX_RISK_PER_TRADE > 0.02:
        errors.append("MAX_RISK_PER_TRADE too high (>2%)")

    if MAX_DAILY_LOSS_PCT > 0.10:
        errors.append("MAX_DAILY_LOSS_PCT too high (>10%)")

    if MAX_POSITIONS_OPEN > 5:
        errors.append("MAX_POSITIONS_OPEN too high (>5)")

    return errors

_validation_errors = validate_config()
if _validation_errors and not OKX_SIMULATED:
    print("⚠️  Configuration Warnings:")
    for error in _validation_errors:
        print(f"   - {error}")
