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
# TRADING PARAMETERS
# =====================================
# Core trading settings
TRADING_SYMBOL = "SOL-USDT-SWAP"  # Main trading pair (Solana perpetual)
REFERENCE_SYMBOL = "BTC-USDT-SWAP"  # Reference symbol (Bitcoin for correlation)
TRADING_MODE = "perp"  # 'spot' or 'perp'
MAX_DAILY_TRADES = 5  # Maximum trades per day
TRADE_INTERVAL_MINUTES = 60  # Minimum minutes between trades

# =====================================
# RISK MANAGEMENT
# =====================================
# Position sizing
MAX_RISK_PER_TRADE = 0.005  # 0.5% of account per trade
MAX_POSITIONS_OPEN = 1  # Only 1 position at a time
POSITION_SIZE_PCT = 0.02  # Use 2% of account per position

# Daily limits
MAX_DAILY_LOSS_PCT = 0.025  # 2.5% max daily loss
MAX_DAILY_DRAWDOWN = 0.03  # 3% max drawdown before shutdown

# Stop loss and take profit
ATR_STOP_MULTIPLIER = 2.0  # Stop loss = 2x ATR
TP1_RR_RATIO = 1.5  # First TP at 1.5:1 RR
TP2_RR_RATIO = 3.0  # Second TP at 3:1 RR
TRAILING_STOP_ACTIVATION = 1.2  # Activate trailing stop after 1.2:1 RR

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
# FILTER THRESHOLDS
# =====================================
# Market Regime Filter
ATR_MIN_PERCENTILE = 20  # ATR must be above 20th percentile
ATR_MAX_PERCENTILE = 80  # ATR must be below 80th percentile (avoid extreme volatility)
VOLATILITY_COMPRESSION_THRESHOLD = 0.7  # ATR ratio for compression detection
FUNDING_RATE_MAX = 0.0005  # Max funding rate (0.05%)
FUNDING_RATE_MIN = -0.0005  # Min funding rate
OI_CHANGE_MAX = 0.15  # Max 15% OI change in 24h

# Multi-Timeframe Filter
HTF_TREND_MIN_STRENGTH = 0.6  # HTF trend strength (0-1)
MTF_TREND_MIN_STRENGTH = 0.5  # MTF trend strength
LTF_TREND_MIN_STRENGTH = 0.4  # LTF trend strength
TIMEFRAME_ALIGNMENT_THRESHOLD = 0.7  # Alignment score threshold

# AI Rejection Filter
AI_CONFIDENCE_THRESHOLD = 70  # Minimum AI confidence score (0-100)
AI_MODEL_PATH = "model_learning/rejection_model.pkl"
AI_FEATURE_WINDOW = 50  # Candles to use for feature extraction

# Pattern Failure Detection
BULL_TRAP_THRESHOLD = 0.015  # 1.5% false breakout threshold
BEAR_TRAP_THRESHOLD = 0.015
LOW_LIQUIDITY_VOLUME_RATIO = 0.3  # Volume must be > 30% of avg
STOP_HUNT_WICK_RATIO = 3.0  # Wick-to-body ratio for stop hunt detection
FAKEOUT_REVERSION_PCT = 0.8  # Price reversion % to confirm fakeout

# BTC-SOL Correlation Filter
BTC_SOL_CORRELATION_ENABLED = True  # Enable BTC-SOL correlation check
BTC_SOL_MIN_CORRELATION = 0.7  # Minimum correlation score (0-1)
BTC_SOL_TREND_AGREEMENT_REQUIRED = True  # BTC and SOL must trend same direction
BTC_SOL_DIVERGENCE_MAX = 0.15  # Max 15% price divergence when trends differ

# =====================================
# STRATEGY SETTINGS
# =====================================
# Breakout Strategy
BREAKOUT_VOLUME_MULTIPLIER = 1.5  # Volume must be 1.5x average
BREAKOUT_ATR_COMPRESSION = 0.65  # ATR compression level
BREAKOUT_CONSOLIDATION_BARS = 20  # Min bars in consolidation

# Pullback Strategy
PULLBACK_FIBONACCI_LEVELS = [0.382, 0.5, 0.618]  # Fib levels for pullback
PULLBACK_MAX_RETRACEMENT = 0.618  # Max pullback depth
PULLBACK_TREND_STRENGTH_MIN = 0.6  # Min trend strength for pullback entry

# =====================================
# DATA FEED SETTINGS
# =====================================
# API rate limiting
API_RATE_LIMIT_MS = 100  # Milliseconds between API calls
MAX_RETRIES = 3  # Max retries for failed API calls
RETRY_DELAY_MS = 1000  # Delay between retries

# Caching
ENABLE_CACHE = True
CACHE_EXPIRY_SECONDS = 60  # Cache data for 60 seconds

# =====================================
# MODEL LEARNING SETTINGS
# =====================================
# Data collection for AI training
COLLECT_TRAINING_DATA = True
MIN_SAMPLES_FOR_TRAINING = 100  # Min samples before training model
RETRAIN_INTERVAL_DAYS = 7  # Retrain model every 7 days
FEATURE_ENGINEERING_ENABLED = True

# Feature categories
FEATURES_PRICE_ACTION = True  # Price patterns, candles
FEATURES_VOLUME = True  # Volume analysis
FEATURES_VOLATILITY = True  # ATR, Bollinger Bands
FEATURES_MOMENTUM = True  # RSI, MACD, momentum
FEATURES_MARKET_DATA = True  # Funding, OI, liquidations

# =====================================
# LOGGING & MONITORING
# =====================================
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "logs/trading.log"
LOG_TRADES_FILE = "logs/trades.log"
LOG_FILTERS_FILE = "logs/filters.log"

# Performance tracking
TRACK_METRICS = True
METRICS_FILE = "logs/metrics.json"

# =====================================
# SAFETY SETTINGS
# =====================================
# Emergency shutdown conditions
ENABLE_EMERGENCY_SHUTDOWN = True
EMERGENCY_VOLATILITY_MULTIPLIER = 5.0  # Shutdown if ATR > 5x average
EMERGENCY_DRAWDOWN_PCT = 0.05  # Shutdown if 5% drawdown
EMERGENCY_API_FAILURE_COUNT = 5  # Shutdown after 5 consecutive API failures

# Kill switch
ENABLE_KILL_SWITCH = True
KILL_SWITCH_FILE = "KILL_SWITCH.txt"  # Create this file to stop trading

# =====================================
# BACKTESTING SETTINGS (For Future Use)
# =====================================
BACKTEST_START_DATE = "2024-01-01"
BACKTEST_END_DATE = "2024-12-31"
BACKTEST_INITIAL_CAPITAL = 10000
BACKTEST_COMMISSION = 0.0006  # 0.06% taker fee

# =====================================
# TELEGRAM ALERTS (For Future Use)
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

    if MAX_RISK_PER_TRADE > 0.01:
        errors.append("MAX_RISK_PER_TRADE too high (>1%)")

    if MAX_DAILY_LOSS_PCT > 0.05:
        errors.append("MAX_DAILY_LOSS_PCT too high (>5%)")

    if MAX_POSITIONS_OPEN > 3:
        errors.append("MAX_POSITIONS_OPEN too high (>3)")

    return errors

# Validate on import
_validation_errors = validate_config()
if _validation_errors and not OKX_SIMULATED:
    print("⚠️  Configuration Warnings:")
    for error in _validation_errors:
        print(f"   - {error}")
