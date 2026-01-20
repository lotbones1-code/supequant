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
OKX_API_DOMAIN = os.getenv('OKX_API_DOMAIN', 'us.okx.com')  # US domain for American accounts

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

# Fallback for OKX US compliance (error 51155 blocks perpetuals)
SPOT_FALLBACK_ENABLED = True  # If perpetuals fail due to compliance, try spot
SPOT_SYMBOL = "SOL-USDT"  # Spot trading symbol for fallback
MAX_DAILY_TRADES = 10  # Increased from 5
TRADE_INTERVAL_MINUTES = 30  # Reduced from 60 - trade more often

# =====================================
# RISK MANAGEMENT
# =====================================
# Position sizing - OPTIMIZED FOR SMALL ACCOUNT GROWTH
MAX_RISK_PER_TRADE = 0.02  # 2% of account per trade (aggressive for growth)
MAX_POSITIONS_OPEN = 2  # Allow 2 positions (was 1)
POSITION_SIZE_PCT = 0.05  # Use 5% of account per position (aggressive for small accounts)

# Daily limits
MAX_DAILY_LOSS_PCT = 0.05  # 5% max daily loss (was 2.5%)
MAX_DAILY_DRAWDOWN = 0.06  # 6% max drawdown before shutdown (was 3%)

# Stop loss and take profit
ATR_STOP_MULTIPLIER = 1.5  # Stop loss = 1.5x ATR (tighter, was 2.0)
TP1_RR_RATIO = 1.5  # First TP at 1.5:1 RR
TP2_RR_RATIO = 2.5  # Second TP at 2.5:1 RR (was 3.0)
TRAILING_STOP_ACTIVATION = 1.0  # Activate trailing stop after 1:1 RR (was 1.2)

# =====================================
# AGGRESSIVE GROWTH MODE - OPTIMIZED FOR SMALL ACCOUNTS ($5 -> $1000+)
# =====================================
# Enable aggressive growth optimizations for small account growth
GROWTH_MODE_ENABLED = os.getenv('GROWTH_MODE_ENABLED', 'True').lower() == 'true'
GROWTH_BASE_RISK_PCT = 0.02  # Base risk (2% - aggressive for small accounts)
GROWTH_MAX_RISK_PCT = 0.10  # Max risk (10% - aggressive but controlled)
GROWTH_LEVERAGE = 5  # Leverage multiplier (5x for faster growth, max 10x)
GROWTH_COMPOUND_ENABLED = True  # Increase size as account grows - CRITICAL for small accounts
GROWTH_CONFIDENCE_MULTIPLIER = True  # Bigger positions on high confidence
GROWTH_AGGRESSIVE_TP = True  # Use aggressive TP targets (5R, 10R, 20R)

# Growth mode TP targets (if enabled) - AGGRESSIVE for small account growth
GROWTH_TP1_RR = 5.0  # First TP at 5:1 RR (very aggressive)
GROWTH_TP2_RR = 10.0  # Second TP at 10:1 RR
GROWTH_TP3_RR = 20.0  # Third TP at 20:1 RR (let winners run!)
GROWTH_TP_SPLIT = {1: 0.3, 2: 0.35, 3: 0.35}  # 30/35/35 position split (let winners run longer)

# Small account optimization
SMALL_ACCOUNT_THRESHOLD = 100.0  # Accounts under $100 use aggressive settings
SMALL_ACCOUNT_RISK_MULTIPLIER = 2.0  # 2x risk for small accounts
SMALL_ACCOUNT_COMPOUND_RATE = 1.5  # Compound 50% faster on wins

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

# Market Regime Enhanced Filter (Phase 2.1)
MARKET_REGIME_ENHANCED_ENABLED = True
REGIME_TRENDING_MIN_STRENGTH = 0.6   # trend_strength > this = trending market
REGIME_RANGING_MAX_STRENGTH = 0.35   # trend_strength < this = ranging market
REGIME_HIGH_VOL_PERCENTILE = 80      # ATR percentile > this = high volatility
REGIME_LOW_VOL_PERCENTILE = 25       # ATR percentile < this = low volatility (squeeze)

# Multi-Timeframe Filter - MUCH LIGHTER
HTF_TREND_MIN_STRENGTH = 0.3  # Was 0.6 - much lighter requirement
MTF_TREND_MIN_STRENGTH = 0.25  # Was 0.5
LTF_TREND_MIN_STRENGTH = 0.2  # Was 0.4
TIMEFRAME_ALIGNMENT_THRESHOLD = 0.4  # Was 0.7 - don't require perfect alignment

# AI Rejection Filter - MORE PERMISSIVE
AI_CONFIDENCE_THRESHOLD = 40  # Was 70 - allow more trades through
AI_MODEL_PATH = "model_learning/rejection_model.pkl"
AI_FEATURE_WINDOW = 50

# Quality Score Threshold - Adaptive learning system
SCORE_THRESHOLD = 50  # Base threshold - balanced quality vs frequency
SCORE_THRESHOLD_ADAPTIVE_ENABLED = True  # Enable adaptive threshold raising
SCORE_THRESHOLD_MIN_TRADES_FOR_ADAPTATION = 20  # Need 20+ trades before raising threshold
SCORE_THRESHOLD_ADAPTED_VALUE = 55  # Raise to 55 after enough winning trades

# Pattern Failure Detection - LESS STRICT
BULL_TRAP_THRESHOLD = 0.03  # Was 0.015 - more tolerance for fakeouts
BEAR_TRAP_THRESHOLD = 0.03
LOW_LIQUIDITY_VOLUME_RATIO = 0.15  # Was 0.3 - accept lower volume
STOP_HUNT_WICK_RATIO = 4.0  # Was 3.0 - less sensitive
FAKEOUT_REVERSION_PCT = 0.9  # RESTORED: Keep strict at 0.9 for high win rate (was 0.95 briefly)

# BTC-SOL Correlation Filter - MUCH LIGHTER
BTC_SOL_CORRELATION_ENABLED = True
BTC_SOL_MIN_CORRELATION = 0.4  # Was 0.7 - much looser
BTC_SOL_TREND_AGREEMENT_REQUIRED = False
BTC_SOL_DIVERGENCE_MAX = 0.25  # Was 0.15 - allow more divergence
BTC_SOL_STRONG_OPPOSITION_THRESHOLD = 0.85  # Was 0.7 - only reject on very strong opposition
BTC_VOL_EXTREME_PERCENTILE = 98  # Was 95 - only reject extreme BTC moves

# =====================================
# BTC Dump/Pump Protection (Phase 2.2 Elite)
# =====================================
BTC_DUMP_FILTER_ENABLED = True

# Severity thresholds (weighted across 15m/1H/4H timeframes)
# Weighted formula: (15m × 0.5) + (1H × 0.3) + (4H × 0.2)
BTC_SEVERE_DROP_PCT = 4.0     # 4%+ weighted drop = SEVERE (hard reject longs)
BTC_MODERATE_DROP_PCT = 2.5   # 2.5%+ = MODERATE (reject unless recovering)
BTC_MILD_DROP_PCT = 1.5       # 1.5%+ = MILD (allow but penalize score)

# Cascade threshold (capitulation detection)
# Consecutive red 15m candles = sustained selling pressure
BTC_CASCADE_REJECT_COUNT = 4  # 4+ consecutive red candles = reject longs

# =====================================
# Time-of-Day Filter (Phase 2.3 Elite)
# =====================================
TIME_OF_DAY_FILTER_ENABLED = True

# Weekend handling - crypto trades 24/7, allow trading but with score penalty
AVOID_WEEKENDS = False  # Allow weekend trading (other filters still apply)

# Dead zone (21:00-00:00 UTC) - between NY close and Asian open
AVOID_DEAD_ZONE = True  # Reject during dead zone

# Low liquidity hours (optional additional window)
AVOID_LOW_LIQUIDITY_HOURS = False  # Set True to add extra penalty 00:00-04:00
LOW_LIQUIDITY_START_UTC = 0   # 00:00 UTC
LOW_LIQUIDITY_END_UTC = 4     # 04:00 UTC

# =====================================
# Funding Rate Filter (Phase 2.4 Elite)
# =====================================
# Contrarian logic: trade AGAINST crowded positions
FUNDING_RATE_FILTER_ENABLED = True

# Thresholds (as decimals: 0.001 = 0.1%)
FUNDING_RATE_EXTREME_THRESHOLD = 0.001    # 0.1% = extreme crowding
FUNDING_RATE_MODERATE_THRESHOLD = 0.0005  # 0.05% = moderate crowding

# Score adjustments for contrarian signals
FUNDING_RATE_EXTREME_PENALTY = 20   # Penalty for trading WITH the crowd at extreme
FUNDING_RATE_EXTREME_BOOST = 15     # Boost for trading AGAINST the crowd at extreme
FUNDING_RATE_MODERATE_PENALTY = 10  # Penalty at moderate levels
FUNDING_RATE_MODERATE_BOOST = 7     # Boost at moderate levels

# =====================================
# Whale & Exchange Flow Tracking (Phase 3.1 Elite)
# =====================================
WHALE_TRACKING_ENABLED = True

# Helius API (free tier: 100k credits/day)
# Get your key at https://helius.xyz
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY', '')

# Thresholds
WHALE_TRANSFER_THRESHOLD = 10000   # Minimum SOL to track (10k SOL)
WHALE_FLOW_THRESHOLD = 50000       # Net flow threshold for signals (50k SOL)
WHALE_LOOKBACK_HOURS = 4           # Analysis window (hours)

# Score adjustments
WHALE_HIGH_FLOW_PENALTY = 20       # Penalty for trading against strong whale flow
WHALE_MED_FLOW_PENALTY = 10        # Penalty for moderate flow
WHALE_HIGH_FLOW_BOOST = 15         # Boost for trading with strong whale flow
WHALE_MED_FLOW_BOOST = 7           # Boost for moderate flow

# =====================================
# Liquidation Intelligence (Phase 3.3 Elite)
# =====================================
LIQUIDATION_FILTER_ENABLED = True

# Zone calculation settings
LIQ_LEVERAGE_LEVELS = [3, 5, 10, 20, 50, 100]  # Common leverage levels to calculate
LIQ_ZONE_PROXIMITY_PCT = 2.0   # Within 2% of zone = danger zone
LIQ_MAGNET_RANGE_PCT = 3.0     # Within 3% = magnet effect applies
LIQ_ZONE_RECALC_PCT = 1.0      # Recalculate zones when price moves 1%

# Score adjustments
LIQ_PROXIMITY_PENALTY = 15     # Near your-side liquidation zone (stop hunt risk)
LIQ_MAGNET_BOOST = 10          # Near opposite-side liquidation zone (squeeze/dump potential)
LIQ_CASCADE_PENALTY = 20       # Trading INTO an active liquidation cascade
LIQ_CASCADE_BOOST = 15         # Riding an active liquidation cascade
LIQ_EXHAUSTION_BOOST = 5       # Contrarian boost after cascade exhaustion

# API settings
LIQ_CACHE_SECONDS = 60         # Cache liquidation API calls for 60 seconds

# =====================================
# Open Interest Analysis (Phase 3.4 Elite - Boost Heavy)
# =====================================
OPEN_INTEREST_FILTER_ENABLED = True

# Divergence detection
OI_DIVERGENCE_THRESHOLD_PCT = 2.0    # 2% change = significant movement
OI_LOOKBACK_PERIODS = 12             # Compare vs 12 periods (~1 hour on 5m)

# Percentile thresholds (crowding detection)
OI_HIGH_PERCENTILE = 90              # Top 10% = crowded market
OI_LOW_PERCENTILE = 10               # Bottom 10% = uncrowded, room to run

# Score adjustments (BOOST-HEAVY - tilted toward helping signals pass)
OI_DIVERGENCE_BOOST = 12             # Boost for trading WITH divergence signal
OI_DIVERGENCE_PENALTY = 10           # Penalty for trading AGAINST divergence
OI_CONFIRMATION_BOOST = 8            # Boost for trend confirmation (price+OI aligned)
OI_EXTREME_PENALTY = 7               # Penalty at extreme OI levels (crowded)
OI_UNCROWDED_BOOST = 7               # Boost when market is uncrowded

# =====================================
# Phase 4.1: Mean Reversion Strategy (Elite)
# =====================================
# Only trades in RANGING markets - fades oversold/overbought extremes
MEAN_REVERSION_ENABLED = True  # Re-enabled with dynamic sizing

# Regime requirement (CRITICAL - don't fade strong trends!)
MR_REQUIRE_RANGING_REGIME = True       # Only trade when market is RANGING
MR_MAX_TREND_STRENGTH = 0.30           # TIGHTENED (was 0.50) - only trade in clear ranging markets

# RSI settings
MR_RSI_PERIOD = 14
MR_RSI_OVERSOLD = 30                   # Strict - only extreme oversold
MR_RSI_OVERBOUGHT = 70                 # Strict - only extreme overbought
MR_RSI_EXTREME_OVERSOLD = 20           # Extra strong long signal
MR_RSI_EXTREME_OVERBOUGHT = 80         # Extra strong short signal

# Bollinger Bands settings
MR_BB_PERIOD = 20
MR_BB_STD_DEV = 2.0

# Timeframes
MR_TIMEFRAME = "15m"                   # Primary signal timeframe
MR_CONFIRM_TIMEFRAME = "5m"            # Confirmation candle timeframe

# Entry confirmation
MR_REQUIRE_REVERSAL_CANDLE = False     # Optimized (was True) - faster entries
MR_REQUIRE_VOLUME_SPIKE = False        # Volume > average (disabled by default)
MR_VOLUME_MULTIPLIER = 1.2             # Volume must be 1.2x average if enabled

# Risk Management
MR_ATR_STOP_MULTIPLIER = 1.5           # Stop = beyond swing + ATR buffer
MR_RR_MINIMUM = 1.5                    # Minimum R:R to take trade
MR_TP1_RR_RATIO = 1.5                  # TP1 risk:reward (or use BB mid)
MR_TP2_RR_RATIO = 2.5                  # TP2 risk:reward (or use opposite BB)

# =====================================
# Phase 4.2: Funding Rate Arbitrage (Elite)
# =====================================
# Captures extreme funding imbalances - LOW RISK, collect funding payments
# Only triggers on VERY extreme funding where profit > fees
FUNDING_ARBITRAGE_ENABLED = True

# Threshold MUST exceed trading fees to profit
# Your fees: ~0.06% per trade = 0.12% round trip
# Threshold: 0.15% ensures profit after fees
FR_EXTREME_THRESHOLD = 0.0015          # 0.15% - only trade at EXTREME funding
FR_EMERGENCY_STOP_PCT = 0.025          # 2.5% hard stop (flash crash protection)

# Time-based exit (arb is time-based, not price-based)
FR_MIN_HOURS_TO_FUNDING = 1.5          # Need at least 1.5h until next funding to enter
FR_MAX_HOLD_HOURS = 9.0                # Auto-exit after 9h max (1 funding cycle + buffer)
FR_EXIT_BUFFER_MINUTES = 30            # Exit 30min after funding time passes

# Regime/safety requirements
FR_REQUIRE_LOW_VOLATILITY = True       # Only arb in low-vol markets (safer)
FR_MAX_ATR_PERCENTILE = 65             # Block if ATR > 65th percentile (too volatile)

# =====================================
# CONFIDENCE ENGINE V2 (Elite Position Sizing)
# =====================================
# Dynamic position sizing based on confidence bands
# Uses historical performance data to refine confidence scores
CONFIDENCE_ENGINE_V2_ENABLED = True

# Confidence bands and position size multipliers
# LOW (0-39):    Trade with reduced size (protect capital)
# MEDIUM (40-59): Trade with normal size
# HIGH (60-79):   Trade with increased size (high conviction)
# ELITE (80-100): Trade with maximum size (best setups only)
CONF_V2_LOW_MULTIPLIER = 0.5           # 0.5x position on weak signals
CONF_V2_MEDIUM_MULTIPLIER = 1.0        # 1.0x position on normal signals
CONF_V2_HIGH_MULTIPLIER = 1.3          # 1.3x position on strong signals
CONF_V2_ELITE_MULTIPLIER = 1.5         # 1.5x position on elite signals

# Band thresholds
CONF_V2_LOW_MAX = 39                   # 0-39 = LOW
CONF_V2_MEDIUM_MAX = 59                # 40-59 = MEDIUM
CONF_V2_HIGH_MAX = 79                  # 60-79 = HIGH
# 80-100 = ELITE

# Component weights for adjustment calculation
# Total max adjustment: +/- 32 points
CONF_V2_FILTER_WEIGHT = 10             # Max +/- 10 pts from filter effectiveness
CONF_V2_TIME_OF_DAY_WEIGHT = 8         # Max +/- 8 pts from hour performance
CONF_V2_CONFLUENCE_WEIGHT = 8          # Max +/- 8 pts from filter count
CONF_V2_MARKET_WEIGHT = 6              # Max +/- 6 pts from market conditions

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
# STRATEGY SETTINGS (Tuned for More Signals)
# =====================================
# Breakout Strategy - OPTIMIZED FOR ACTIVITY
BREAKOUT_VOLUME_MULTIPLIER = 1.0   # Reduced from 1.2 - volume spike still helps but not required
BREAKOUT_ATR_COMPRESSION = 1.5     # Raised from 1.25 - easier compression detection
BREAKOUT_CONSOLIDATION_BARS = 5    # Reduced from 8 - shorter consolidation OK
BREAKOUT_MIN_MOVE_ATR = 0.3        # Minimum breakout move in ATR units

# Pullback Strategy - OPTIMIZED FOR ACTIVITY
PULLBACK_FIBONACCI_LEVELS = [0.382, 0.5, 0.618, 0.786]  # Multiple entry zones
PULLBACK_MAX_RETRACEMENT = 0.786   # Deep pullbacks OK
PULLBACK_TREND_STRENGTH_MIN = 0.20  # Optimized (was 0.3) - catch weaker trends
PULLBACK_MIN_BOUNCE_CANDLES = 1    # Just need 1 bounce candle to confirm

# Momentum Strategy - NEW (Elite)
MOMENTUM_STRATEGY_ENABLED = True
MOMENTUM_RSI_PERIOD = 14
MOMENTUM_RSI_BULL_MIN = 50         # RSI > 50 for longs
MOMENTUM_RSI_BEAR_MAX = 50         # RSI < 50 for shorts
MOMENTUM_TREND_STRENGTH_MIN = 0.25 # Optimized (was 0.35) - catch earlier trends
MOMENTUM_VOLUME_CONFIRM = 1.0      # Optimized (was 1.1) - no volume filter
MOMENTUM_ATR_STOP_MULTIPLIER = 1.5 # Stop loss distance
MOMENTUM_TP1_RR = 1.5              # First target 1.5R
MOMENTUM_TP2_RR = 2.5              # Second target 2.5R

# Structure Strategy - NEW (Elite - S/R + Market Structure + Volume)
STRUCTURE_STRATEGY_ENABLED = False  # DISABLED - Backtest showed 21% win rate even with strict rules
STRUCTURE_TIMEFRAME = '15m'        # Primary analysis timeframe
STRUCTURE_MIN_CONFIDENCE = 0.70    # STRICT: Raised from 0.50 to reduce bad signals
STRUCTURE_ATR_STOP_MULT = 1.5      # ATR multiplier for stops
STRUCTURE_TP1_RR = 1.5             # First target R:R
STRUCTURE_TP2_RR = 2.5             # Second target R:R
STRUCTURE_LEVEL_TOLERANCE = 0.5    # % tolerance for S/R detection
STRUCTURE_MIN_TOUCHES = 2          # Min touches to confirm level

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
# CLAUDE AI SETTINGS
# =====================================
# DISABLED - Backtests showed +$4,076 WITHOUT Claude gating
# The filter system alone is sufficient for signal quality
CLAUDE_GATING_ENABLED = False  # os.getenv('CLAUDE_GATING_ENABLED', 'True').lower() == 'true'
CLAUDE_FAIL_OPEN = True  # Approve trades if Claude fails (recommended: True)
CLAUDE_TIMEOUT_SECONDS = 10.0  # Request timeout
CLAUDE_MIN_APPROVAL_RATE = 0.1  # Auto-disable if approval rate < 10%
CLAUDE_CIRCUIT_BREAKER_ENABLED = True  # Enable circuit breaker
CLAUDE_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # Failures before opening circuit
CLAUDE_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60  # Seconds before trying half-open
CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-20250514')

# =====================================
# CHATGPT AI SETTINGS
# =====================================
CHATGPT_ENABLED = os.getenv('CHATGPT_ENABLED', 'True').lower() == 'true'
CHATGPT_API_KEY = os.getenv('OPENAI_API_KEY', '')
CHATGPT_MODEL = os.getenv('CHATGPT_MODEL', 'gpt-4o')  # gpt-4o, gpt-4-turbo, gpt-4
CHATGPT_FAIL_OPEN = True  # Approve trades if ChatGPT fails
CHATGPT_TIMEOUT_SECONDS = 10.0  # Request timeout
CHATGPT_CIRCUIT_BREAKER_ENABLED = True
CHATGPT_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CHATGPT_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60

# =====================================
# HYBRID AI SETTINGS
# =====================================
HYBRID_AI_ENABLED = os.getenv('HYBRID_AI_ENABLED', 'True').lower() == 'true'
HYBRID_AI_MODE = os.getenv('HYBRID_AI_MODE', 'consensus')  # consensus, weighted, fallback
HYBRID_CLAUDE_WEIGHT = float(os.getenv('HYBRID_CLAUDE_WEIGHT', '0.5'))  # Weight for Claude (0-1)
HYBRID_CHATGPT_WEIGHT = float(os.getenv('HYBRID_CHATGPT_WEIGHT', '0.5'))  # Weight for ChatGPT (0-1)
HYBRID_REQUIRE_CONSENSUS = os.getenv('HYBRID_REQUIRE_CONSENSUS', 'True').lower() == 'true'  # Require agreement in consensus mode

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
EXTREME_VOLATILITY_PERCENTILE = 99  # ATR percentile threshold for emergency shutdown (was 95, too sensitive for crypto)

ENABLE_KILL_SWITCH = True
KILL_SWITCH_FILE = "KILL_SWITCH.txt"

# =====================================
# BACKTESTING SETTINGS
# =====================================
BACKTEST_START_DATE = "2025-12-01"
BACKTEST_END_DATE = "2025-12-15"
BACKTEST_INITIAL_CAPITAL = 10000
BACKTEST_COMMISSION = 0.0006

# =====================================
# ELITE BACKTEST IMPROVEMENTS (BACKTEST ONLY)
# =====================================
# These settings ONLY affect backtesting. Live system is unchanged.
# Set ELITE_BACKTEST_MODE = True to enable all improvements

ELITE_BACKTEST_MODE = True  # Master switch for elite improvements

# 1. STRICT REGIME FILTER - Skip MR when 1H trend is strong
ELITE_STRICT_REGIME = True         # Enable strict 1H trend check
ELITE_1H_TREND_MAX = 0.40          # Skip MR if 1H trend strength > this

# 2. ADAPTIVE POSITION SIZING - Trade smaller in uncertain regimes
ELITE_ADAPTIVE_SIZING = True       # Enable adaptive position sizing
ELITE_SIZE_FULL = 1.0              # Full size when regime is clear (confidence > 0.5)
ELITE_SIZE_HALF = 0.5              # Half size when uncertain (confidence 0.2-0.5)
ELITE_SIZE_SKIP = 0.0              # Skip when regime is bad (confidence < 0.2)

# 3. CONFIRMATION CANDLE - Wait for reversal confirmation before entry
ELITE_REQUIRE_CONFIRMATION = False # Disabled - too restrictive
ELITE_CONFIRMATION_BARS = 2        # Number of bars to confirm reversal

# 4. BREAKEVEN STOP - Move stop to entry after TP1 hit
ELITE_BREAKEVEN_AFTER_TP1 = False  # Disabled - causes premature exits
ELITE_BREAKEVEN_BUFFER = 0.001     # 0.1% buffer above/below entry

# FAIR AI BACKTESTING (AI evaluates without seeing future data)
BACKTEST_USE_FAIR_AI = False       # Disabled to test MTF alone
BACKTEST_AI_USE_CLAUDE = True      # Use Claude for evaluation
BACKTEST_AI_USE_OPENAI = False     # Use OpenAI for evaluation (set True for hybrid mode)

# AI Mode Options:
# - "VETO_ONLY": AI only blocks extreme risk trades (confidence < veto_threshold)
# - "STANDARD": AI approves/rejects based on its judgment  
# - "HYBRID": Uses both Claude AND OpenAI, requires consensus
BACKTEST_AI_MODE = "VETO_ONLY"     # Less conservative - only veto high risk
BACKTEST_AI_VETO_THRESHOLD = 0.30  # Only reject if AI confidence < 30%

# SMART MULTI-TIMEFRAME INTELLIGENCE (Backtest Only)
# Checks higher timeframes before allowing trades
# Now STRATEGY-AWARE: Different logic for Mean Reversion vs Trend Following
BACKTEST_USE_MTF = False           # Disabled - didn't improve results
BACKTEST_MTF_REQUIRE_1H = True     # Require 1H trend alignment (for trend following)
BACKTEST_MTF_REQUIRE_4H = False    # Require 4H trend alignment (stricter, for trend following)
BACKTEST_MTF_MIN_ALIGNMENT = 0.3   # Minimum alignment score (for trend following)
BACKTEST_MTF_MR_THRESHOLD = 0.5    # For Mean Reversion: only block if trend strength > this (lower = more aggressive)

# ============================================================================
# ML TRADE SCORING (BACKTESTING ONLY)
# ============================================================================
# Uses machine learning to score signals based on historical patterns
BACKTEST_USE_ML_SCORING = False    # Disabled - didn't improve results

# ============================================================================
# FEAR & GREED INDEX (BACKTESTING ONLY)
# ============================================================================
# Uses historical Fear & Greed data as contrarian signal
BACKTEST_USE_FEAR_GREED = False    # Disabled - hurt results (double-contrarian problem)
BACKTEST_FG_FEAR_THRESHOLD = 25    # Below this = Extreme Fear (favor longs)
BACKTEST_FG_GREED_THRESHOLD = 75   # Above this = Extreme Greed (favor shorts)
BACKTEST_FG_BLOCK_CONTRARIAN = True  # Block trades against extreme sentiment
BACKTEST_ML_MIN_SCORE = 0.35       # Minimum ML score to allow trade (0-1) - lowered from 0.4
BACKTEST_ML_ADAPTIVE = True        # Auto-adjust threshold based on performance

# Legacy regime settings (keeping for reference)
BACKTEST_REGIME_SWITCHING = False  # Old system - disabled
REGIME_WINDOW_SIZE = 48
REGIME_TREND_THRESHOLD = 0.20
BACKTEST_TREND_FOLLOWING = False   # Disabled - didn't improve results
BACKTEST_TF_MIN_SCORE = 35         # Lower quality threshold for TF (unused when disabled)

# ============================================================================
# BACKTEST TUNING OPTIONS (test one at a time!)
# ============================================================================
BACKTEST_SCORE_THRESHOLD = None    # Reset to baseline (None = use live value)
BACKTEST_TRADE_INTERVAL = 15       # TEST #2: Reduced cooldown (was 30 min)

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
# TELEGRAM NOTIFICATIONS
# =====================================
TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'False').lower() == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Notification Types
TELEGRAM_SEND_TRADE_ALERTS = True  # Send on entry/TP/SL
TELEGRAM_SEND_ERROR_ALERTS = True  # Send on system errors
TELEGRAM_SEND_PERIODIC_REPORTS = True  # Send performance reports
TELEGRAM_SEND_SENTIMENT_ALERTS = True  # Send market sentiment updates

# Periodic Report Settings
TELEGRAM_REPORT_INTERVAL_DAYS = 3  # Days between auto reports
TELEGRAM_SENTIMENT_INTERVAL_HOURS = 4  # Hours between sentiment updates

# =====================================
# TRADE JOURNAL SETTINGS
# =====================================
TRADE_JOURNAL_ENABLED = True  # Log all closed trades to disk
TRADE_JOURNAL_PATH = "runs"   # Base directory for trade logs (runs/YYYY-MM-DD/trades.jsonl)

# =====================================
# PERFORMANCE ANALYTICS SETTINGS
# =====================================
PERFORMANCE_ANALYTICS_ENABLED = True  # Enable performance analytics
ANALYTICS_OUTPUT_PATH = "runs/analytics"  # Where to save analytics reports
ANALYTICS_DEFAULT_LOOKBACK_DAYS = 30  # Default days to analyze

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
