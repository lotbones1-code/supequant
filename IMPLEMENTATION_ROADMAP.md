# Elite Quant System - Complete Implementation Roadmap

**Version:** 1.6  
**Last Updated:** 2026-01-19  
**Purpose:** Detailed implementation guide for all enhancement features

---

## ✅ COMPLETION STATUS

| Phase | Status | Notes |
|-------|--------|-------|
| **Phase 1: Visibility & Monitoring** | ✅ COMPLETE | All 4 items done |
| **Phase 1.5: Analytics & Monitoring** | ✅ COMPLETE | 4 modules + dashboard integration |
| **Phase 2: Smarter Filtering** | ✅ COMPLETE | 2.1, 2.2, 2.3, 2.4 all done |
| **Phase 3: On-Chain Intelligence** | ✅ COMPLETE | 3.1-3.4 all done |
| **Phase 4: Multi-Strategy** | ✅ COMPLETE | 4.1, 4.2, 4.3, 4.4 done |
| **Sentiment Integration** | ✅ COMPLETE | Real Fear & Greed API |
| **Market Structure Intelligence** | ✅ COMPLETE | S/R + Structure + Volume Profile |
| **Bonus: Confidence V2** | ✅ WIRED IN | Elite position sizing active |

---

## 🎯 CURRENT SYSTEM OVERVIEW

### **Active Strategies (7 Total):**
1. ✅ **Breakout Strategy** - Consolidation breakouts with volume
2. ✅ **Pullback Strategy** - Trend continuation on pullbacks
3. ✅ **Mean Reversion Strategy** - Ranging market reversals (Phase 4.1)
4. ✅ **Funding Arbitrage Strategy** - Extreme funding rate capture (Phase 4.2)
5. ✅ **Momentum Strategy** - Trend-following momentum (Phase 4.3)
6. ✅ **Structure Strategy** - S/R + Market Structure + Volume Profile (Phase 4.4) **NEW**
7. ✅ **Research/Checklist Strategy** - Multi-factor scoring

### **Active Filters (12+ Quality Filters):**
- ✅ Time of Day Filter (Phase 2.3)
- ✅ BTC/SOL Correlation Filter (Enhanced)
- ✅ Market Regime Filter (Trending/Ranging/Volatile)
- ✅ Funding Rate Filter (Phase 3.4)
- ✅ Whale Filter (Phase 3.1 - On-chain tracking)
- ✅ Liquidation Filter (Phase 3.3)
- ✅ Open Interest Filter (Phase 3.4)
- ✅ Sentiment Filter (Fear & Greed Index - Phase 4.3c)
- ✅ Confidence Engine V2 (Dynamic position sizing)
- ✅ And more...

### **Data Sources:**
- ✅ OKX Exchange API (market data, funding, liquidations)
- ✅ Helius API (Solana on-chain data)
- ✅ Alternative.me API (Fear & Greed Index)

### **Recent Additions (Latest Session):**
- ✅ **Market Structure Intelligence** - Professional-grade S/R detection, structure analysis, volume profile
- ✅ **Structure Strategy** - 7th strategy that trades based on market structure
- ✅ All integrated seamlessly with existing system

---

## 🚨 CRITICAL RULES - READ FIRST

### **DO NOT TOUCH:**
1. **`execution/production_manager.py`** - Working perfectly, DO NOT MODIFY
2. **`main.py` trade execution flow** - Only add hooks, never change core logic
3. **`risk/risk_manager.py`** - Core risk logic is sacred
4. **`data_feed/okx_client.py`** - API client is stable

### **SAFE TO MODIFY:**
1. **`config.py`** - Add new config flags (always with defaults)
2. **`filters/`** - Add new filter files, register in `filter_manager.py`
3. **`strategy/`** - Add new strategy files, register in `strategy_manager.py`
4. **`utils/`** - Add helper utilities

### **INTEGRATION PATTERN:**
```
New Feature → New File → Register in Manager → Add Config Flag → Test
```

---

## 📐 CURRENT ARCHITECTURE

### **Trading Pipeline Flow:**
```
main.py (EliteQuantSystem.run())
    ↓
1. Market Data Fetch (MarketDataFeed.get_market_state())
    ↓
2. Strategy Generation (StrategyManager.generate_signals())
    ↓
3. Filter Check (FilterManager.check_all())
    ├─ Critical Filters (binary pass/fail)
    └─ Quality Filters (scoring 0-100)
    ↓
4. AI Approval (Claude/ChatGPT - optional)
    ↓
5. Risk Check (RiskManager.check_can_trade())
    ↓
6. Trade Execution (ProductionOrderManager.execute_trade())
    ├─ Pre-trade cleanup
    ├─ Entry order
    ├─ TP placement (limit or virtual)
    └─ Background monitoring
```

### **Key Files:**
- **`main.py`** - Main orchestration loop
- **`filters/filter_manager.py`** - Filter registration and execution
- **`strategy/strategy_manager.py`** - Strategy registration and execution
- **`config.py`** - All configuration flags
- **`execution/production_manager.py`** - Trade execution (DO NOT MODIFY)

---

## 📋 PHASE 1: VISIBILITY & MONITORING ✅ COMPLETE

### **1.1: Telegram/Discord Alerts** ✅ DONE

**File Created:** `utils/telegram_notifier.py`

**Purpose:** Get real-time notifications when trades execute, TPs hit, SL triggers, or errors occur.

**Logic:**
- Create notification service that sends messages to Telegram/Discord
- Hook into existing events (trade execution, TP/SL hits, errors)
- Format messages with key info (symbol, direction, price, PnL)

**New Files:**
- `utils/notifications.py` - Notification service class

**Modify:**
- `config.py`:
  ```python
  # Telegram/Discord Notifications
  TELEGRAM_ENABLED = False
  TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
  TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
  DISCORD_ENABLED = False
  DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
  ```

- `main.py`:
  - Import: `from utils.notifications import NotificationService`
  - In `__init__`: `self.notifier = NotificationService()` if enabled
  - In `_execute_trade_production()`: Add `self.notifier.send_trade_alert(...)`
  - In `_update_positions()`: Add alerts for TP/SL hits

- `execution/production_manager.py`:
  - Add optional `notifier` parameter to `__init__`
  - Call `notifier.send_*()` methods at key events (entry, TP1, TP2, SL, close)

**Dependencies:**
- `requests` (for webhooks) - likely already installed

**Integration Points:**
- Hook into `main.py._execute_trade_production()` after trade executes
- Hook into `production_manager._check_position()` when TP/SL triggers
- Hook into error handlers in `main.py`

**DO NOT TOUCH:**
- Core execution logic
- Order placement logic

**Example Code Structure:**
```python
# utils/notifications.py
class NotificationService:
    def __init__(self):
        self.telegram_enabled = config.TELEGRAM_ENABLED
        self.discord_enabled = config.DISCORD_ENABLED
        # ... initialize clients
    
    def send_trade_alert(self, position, event_type):
        # Format message, send to enabled channels
        pass
```

---

### **1.2: Trade Journal** ✅ DONE

**File Created:** `utils/trade_journal.py`

**Purpose:** Auto-log every trade with full details for analysis and learning.

**Logic:**
- After each trade closes, log to JSON/CSV file
- Include: entry/exit prices, size, PnL, strategy, filters passed, time, duration
- Store in `runs/YYYY-MM-DD/trades.jsonl` (one JSON per line)

**New Files:**
- `utils/trade_journal.py` - Trade logging service

**Modify:**
- `config.py`:
  ```python
  TRADE_JOURNAL_ENABLED = True
  TRADE_JOURNAL_PATH = "runs"
  ```

- `execution/production_manager.py`:
  - Add optional `trade_journal` parameter
  - Call `trade_journal.log_trade(...)` when position closes

- `main.py`:
  - Import and initialize `TradeJournal` if enabled
  - Pass to `ProductionOrderManager` if using production manager

**Dependencies:**
- None (uses standard library `json`, `os`)

**Integration Points:**
- Hook into `production_manager._close_position()` after position closes
- Also log in `main.py._execute_trade_production()` for legacy path

**DO NOT TOUCH:**
- Position tracking logic
- Execution logic

**Example Code Structure:**
```python
# utils/trade_journal.py
class TradeJournal:
    def log_trade(self, position_data):
        # Write to runs/YYYY-MM-DD/trades.jsonl
        pass
```

---

### **1.3: Performance Analytics** ✅ DONE

**File Created:** `utils/performance_analytics.py`

**Purpose:** Track win rate, average PnL, best/worst trades, weekly summaries.

**Logic:**
- Read trade journal files
- Calculate metrics: win rate, avg win/loss, profit factor, max drawdown
- Generate weekly/monthly reports
- Store in `runs/analytics/` directory

**New Files:**
- `utils/performance_analytics.py` - Analytics calculator

**Modify:**
- `config.py`:
  ```python
  PERFORMANCE_ANALYTICS_ENABLED = True
  ANALYTICS_UPDATE_INTERVAL_HOURS = 24
  ```

- `main.py`:
  - Add scheduled task (thread) to run analytics daily
  - Or run on-demand via CLI argument

**Dependencies:**
- `pandas` (optional, for easier analysis) or pure Python

**Integration Points:**
- Reads from `TradeJournal` output files
- Can be run independently or scheduled

**DO NOT TOUCH:**
- Trade execution
- Trade logging

---

### **1.4: Dashboard Upgrades** ✅ DONE

**Files Updated:** `dashboard/app.py`, `dashboard/templates/index.html`

**Purpose:** Show live position status, virtual order monitoring, real-time PnL, trade history chart.

**Logic:**
- Enhance existing dashboard (`dashboard/app.py`)
- Add endpoints for:
  - Live position status (from `ProductionOrderManager`)
  - Virtual order status (TP/SL monitoring)
  - Real-time PnL updates
  - Trade history chart (from trade journal)

**Modify:**
- `dashboard/app.py`:
  - Add new routes for position/virtual order status
  - Add endpoint to fetch trade history
  - Update frontend templates

- `dashboard/templates/index.html`:
  - Add position monitoring section
  - Add virtual order status display
  - Add PnL chart (using Chart.js or similar)

**Dependencies:**
- Existing dashboard dependencies

**Integration Points:**
- Reads from `ProductionOrderManager` for live positions
- Reads from `TradeJournal` for history
- Uses existing dashboard update functions

**DO NOT TOUCH:**
- Core trading logic
- Execution manager

---

## 📋 PHASE 1.5: ANALYTICS & MONITORING ✅ COMPLETE

*Added during implementation - not in original roadmap*

### **1.5.1: System Health Monitor** ✅ DONE

**File Created:** `utils/system_monitor.py`

**Purpose:** Track API connectivity, resource usage, uptime, error rates.

**Features:**
- OKX API status checking
- CPU/Memory/Disk monitoring via psutil
- Uptime tracking
- Error rate calculation
- Health status reports

---

### **1.5.2: Filter Effectiveness Scorer** ✅ DONE

**File Created:** `utils/filter_scorer.py`

**Purpose:** Analyze which filters help/hurt trade performance.

**Features:**
- Per-filter precision tracking
- Contribution scoring (vs baseline)
- Identifies ineffective filters
- Requires `filters_passed` in trade journal (added)

---

### **1.5.3: Risk Exposure Dashboard** ✅ DONE

**File Created:** `utils/risk_dashboard.py`

**Purpose:** Real-time risk exposure and metrics.

**Features:**
- Current position risk calculation
- Drawdown tracking with peak equity
- Value at Risk (VaR) estimates (needs 10+ trades)
- Kelly Criterion recommendations (needs 20+ trades)
- Session statistics

---

### **1.5.4: Trade Quality Inspector** ✅ DONE

**File Created:** `utils/trade_quality.py`

**Purpose:** Analyze trade patterns and quality.

**Features:**
- Hourly performance analysis
- Trade duration analysis
- Close reason breakdown (TP1/TP2/SL)
- Strategy comparison

---

### **1.5.5: Dashboard API Integration** ✅ DONE

**Files Updated:** `dashboard/app.py`, `dashboard/templates/index.html`

**New Endpoints:**
- `/api/system-health`
- `/api/filter-scores`
- `/api/risk-exposure`
- `/api/trade-quality`
- `/api/analytics-summary`

**New UI:** Collapsible "System Analytics" section with 4 panels

---

### **BONUS: Confidence Engine V2** ✅ WIRED IN

**File Created:** `utils/confidence_v2.py`

**Purpose:** Enhanced confidence scoring using historical performance data for elite position sizing.

**Features:**
- Filter effectiveness scoring (uses historical precision data)
- Time-of-day performance scoring (uses hourly win rates)
- Confluence scoring (number of filters passed)
- Market condition scoring (trend + volatility analysis)
- Dynamic position size multipliers based on confidence bands

**Confidence Bands (Elite Position Sizing):**
| Band | Score Range | Position Multiplier |
|------|-------------|---------------------|
| LOW | 0-39 | 0.5x (protect capital) |
| MEDIUM | 40-59 | 1.0x (normal size) |
| HIGH | 60-79 | 1.3x (high conviction) |
| ELITE | 80-100 | 1.5x (best setups) |

**Integration Points:**
- `filters/filter_manager.py`: Wired into check_all() after base scoring
- `config.py`: Added CONFIDENCE_ENGINE_V2_ENABLED and all multiplier settings

**Status:** ✅ FULLY INTEGRATED - Active in live trading

---

## 📋 PHASE 2: SMARTER FILTERING 🟡 IN PROGRESS

### **2.1: Market Regime Detection (Enhanced)** ✅ DONE

**File Created:** `filters/market_regime_enhanced.py`

**Purpose:** Detect if market is trending, ranging, or highly volatile - adapt strategy accordingly.

**Logic:**
- Analyze price action to classify regime:
  - **Trending:** Strong directional movement, higher highs/lower lows
  - **Ranging:** Sideways movement, support/resistance bouncing
  - **High Volatility:** Large price swings, wide ATR
  - **Low Volatility:** Compressed price action, low ATR
- Adjust filter strictness based on regime

**New Files:**
- `filters/market_regime_enhanced.py` - Enhanced regime detection

**Modify:**
- `filters/filter_manager.py`:
  - Add to `quality_filters` dict: `'market_regime_enhanced': MarketRegimeEnhancedFilter()`

- `filters/__init__.py`:
  - Add import: `from .market_regime_enhanced import MarketRegimeEnhancedFilter`
  - Add to `__all__`

- `config.py`:
  ```python
  MARKET_REGIME_ENHANCED_ENABLED = True
  REGIME_TRENDING_MIN_STRENGTH = 0.6  # 0-1 scale
  REGIME_RANGING_MAX_STRENGTH = 0.4
  REGIME_HIGH_VOL_THRESHOLD = 1.5  # ATR multiplier
  ```

**Dependencies:**
- None (uses existing market data)

**Integration Points:**
- Called in `FilterManager.check_all()` as quality filter
- Uses `market_state` dict from `MarketDataFeed`

**DO NOT TOUCH:**
- Existing `MarketRegimeFilter` (keep both, or enhance existing one)
- Strategy generation
- Execution

**Example Code Structure:**
```python
# filters/market_regime_enhanced.py
class MarketRegimeEnhancedFilter:
    def check(self, market_state, signal_direction):
        # Analyze price action, classify regime
        # Return (passed: bool, score: float, reason: str)
        pass
```

---

### **2.2: BTC Correlation Filter (Enhanced)** ✅ DONE

**File Enhanced:** `filters/btc_sol_correlation.py`

**Purpose:** Don't trade SOL when BTC is dumping hard (drags everything down).

**Logic:**
- Check BTC price change over last 1h and 4h
- If BTC down >3% in 1h OR >5% in 4h → reject trade
- Log reason: "BTC correlation filter: BTC down X%"

**Modify:**
- `filters/btc_sol_correlation.py`:
  - Enhance existing filter with hard BTC dump check
  - Add config thresholds

- `config.py`:
  ```python
  BTC_DUMP_FILTER_ENABLED = True
  BTC_DROP_THRESHOLD_1H = 3.0  # % drop to trigger
  BTC_DROP_THRESHOLD_4H = 5.0  # % drop to trigger
  ```

**Dependencies:**
- None (uses existing BTC market data)

**Integration Points:**
- Already integrated in `FilterManager`
- Uses `btc_market_state` passed to `check_all()`

**DO NOT TOUCH:**
- Core filter logic (just enhance)
- Market data fetching

---

### **2.3: Time-of-Day Filter** ✅ DONE

**File Created:** `filters/time_of_day.py`

**Purpose:** Avoid trading during low-liquidity hours (weekends, late night).

**Logic:**
- Check current UTC time
- Reject trades during:
  - Weekend (Saturday 00:00 - Sunday 23:59 UTC)
  - Low liquidity hours (e.g., 00:00-04:00 UTC)
- Configurable time windows

**New Files:**
- `filters/time_of_day.py` - Time-based filter

**Modify:**
- `filters/filter_manager.py`:
  - Add to `quality_filters`: `'time_of_day': TimeOfDayFilter()`

- `filters/__init__.py`:
  - Add import and export

- `config.py`:
  ```python
  TIME_OF_DAY_FILTER_ENABLED = True
  AVOID_WEEKENDS = True
  AVOID_LOW_LIQUIDITY_HOURS = True
  LOW_LIQUIDITY_START_UTC = 0  # 00:00 UTC
  LOW_LIQUIDITY_END_UTC = 4    # 04:00 UTC
  ```

**Dependencies:**
- None (uses `datetime`)

**Integration Points:**
- Called in `FilterManager.check_all()`
- No market data needed, just current time

---

### **2.4: Funding Rate Filter** ✅ DONE

**File Created:** `filters/funding_rate.py`

**Purpose:** Use funding rate as sentiment signal - extreme funding = contrarian opportunity.

**Logic:**
- Fetch funding rate for SOL-USDT-SWAP
- If funding extremely positive (>0.1%) → bullish sentiment, good for longs
- If funding extremely negative (<-0.1%) → bearish sentiment, good for shorts
- Reject if funding opposes signal direction too strongly

**New Files:**
- `filters/funding_rate.py` - Funding rate filter

**Modify:**
- `filters/filter_manager.py`:
  - Add to `quality_filters`: `'funding_rate': FundingRateFilter()`

- `filters/__init__.py`:
  - Add import and export

- `config.py`:
  ```python
  FUNDING_RATE_FILTER_ENABLED = True
  FUNDING_RATE_THRESHOLD = 0.001  # 0.1% threshold
  FUNDING_RATE_OPPOSING_MAX = 0.002  # Reject if funding opposes by >0.2%
  ```

**Dependencies:**
- Uses existing `MarketDataFeed.get_funding_rate()` (already implemented)

**Integration Points:**
- Called in `FilterManager.check_all()`
- Uses `market_state.get('funding_rate')` from market data

**DO NOT TOUCH:**
- Market data fetching
- Funding rate calculation

---

## 📋 PHASE 3: ON-CHAIN INTELLIGENCE ✅ COMPLETE

### **3.1: Whale Wallet Tracking** ✅ DONE

**Files Created:** 
- `data_feed/onchain_tracker.py` - Helius API integration, exchange flow tracking
- `filters/whale_filter.py` - Whale movement filter

**Note:** This implementation includes exchange flow analysis (originally Phase 3.2) - the `OnchainTracker` class tracks both whale movements AND exchange flows (deposits/withdrawals) in one unified system.

**Purpose:** Monitor large SOL holders - their moves often precede price action.

**Logic:**
- Track top 100 SOL wallets (via Solana RPC or API)
- Monitor for large transfers (>10k SOL)
- Alert when whales accumulate/distribute
- Use as filter: don't trade against whale accumulation

**New Files:**
- `data_feed/onchain_tracker.py` - On-chain data fetcher
- `filters/whale_tracker.py` - Whale movement filter

**Modify:**
- `config.py`:
  ```python
  WHALE_TRACKING_ENABLED = True
  WHALE_THRESHOLD_SOL = 10000  # Wallets with >10k SOL
  WHALE_TRANSFER_THRESHOLD = 10000  # Large transfer size
  SOLANA_RPC_URL = os.getenv('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')
  ```

- `filters/filter_manager.py`:
  - Add to `quality_filters`: `'whale_tracker': WhaleTrackerFilter()`

**Dependencies:**
- `solana-py` or direct RPC calls
- Or use API service like Helius, QuickNode

**Integration Points:**
- Background thread to fetch whale data periodically
- Filter checks whale status before allowing trade

**DO NOT TOUCH:**
- Trading execution
- Market data (add new data source, don't modify existing)

---

### **3.2: Exchange Flow Analysis** ✅ MERGED INTO 3.1

**Status:** Merged into Phase 3.1 implementation.

**Why:** The `OnchainTracker` class in `data_feed/onchain_tracker.py` already handles exchange flow analysis as part of whale tracking. It:
- Tracks transfers TO exchanges (bearish - preparing to sell)
- Tracks transfers FROM exchanges (bullish - accumulating)
- Calculates net flow over time windows
- Uses the same Helius API and exchange wallet database

**Implementation:** See Phase 3.1 files - exchange flow is part of `OnchainTracker.analyze_flow()` method.

---

### **3.3: Liquidation Intelligence** ✅ DONE

**Files Created:**
- `data_feed/liquidation_tracker.py` - Elite liquidation zone calculator + OKX API integration
- `filters/liquidation_filter.py` - Liquidation-based filter with cascade detection

**Purpose:** Know where liquidations cluster - price often bounces off these levels. Elite implementation calculates zones from leverage math and tracks real liquidation events.

**Logic:**
- Calculate liquidation zones for common leverage levels (3x, 5x, 10x, 20x, 50x, 100x)
- Fetch recent liquidation events from OKX API
- Detect liquidation cascades (snowball effect)
- Detect exhaustion signals (reversal opportunities)
- Proximity risk: penalty when near your-side liquidation zones
- Magnet effect: boost when large opposite-side zones nearby

**Features:**
- Direction-aware scoring (LONG vs SHORT)
- Combines with funding rate for crowding detection
- Never hard rejects - uses score adjustments only

**Config Added:**
- `LIQUIDATION_FILTER_ENABLED = True`
- `LIQ_LEVERAGE_LEVELS = [3, 5, 10, 20, 50, 100]`
- `LIQ_ZONE_PROXIMITY_PCT = 2.0`
- `LIQ_MAGNET_RANGE_PCT = 3.0`
- Score adjustments: proximity penalty (-15), magnet boost (+10), cascade detection

**Integration:**
- Registered in `filter_manager.py` as `'liquidation': LiquidationFilter()`
- Uses existing market_state data, adds OKX liquidation API calls

---

### **3.4: Open Interest Analysis** ✅ DONE

**Files Created:**
- `filters/open_interest.py` - Elite OI divergence filter (Boost-Heavy settings)

**Purpose:** Gauge market positioning - detect OI divergences and crowding. Elite implementation with boost-heavy settings to help signals pass threshold.

**Logic:**
- Builds internal OI history (tracks OI over time for percentile calculation)
- Detects 4 divergence types:
  - **Bullish confirmation**: Price↑ + OI↑ (new longs entering)
  - **Bearish divergence**: Price↑ + OI↓ (shorts covering, weak rally)
  - **Bullish divergence**: Price↓ + OI↓ (longs capitulating, reversal setup)
  - **Bearish confirmation**: Price↓ + OI↑ (new shorts entering)
- Calculates OI percentile (crowded vs uncrowded markets)
- Combines with funding rate for double crowding confirmation

**Features:**
- Boost-heavy settings (tilted toward helping signals pass)
- Divergence boost: +12, Confirmation boost: +8, Uncrowded boost: +7
- Divergence penalty: -10, Crowded penalty: -7
- Never hard rejects - uses score adjustments only

**Config Added:**
- `OPEN_INTEREST_FILTER_ENABLED = True`
- `OI_DIVERGENCE_THRESHOLD_PCT = 2.0`
- `OI_LOOKBACK_PERIODS = 12`
- `OI_HIGH_PERCENTILE = 90`, `OI_LOW_PERCENTILE = 10`
- All boost-heavy score adjustment values configured

**Integration:**
- Registered in `filter_manager.py` as `'open_interest': OpenInterestFilter()`
- Uses existing `market_state.get('open_interest')` data
- Builds own history from current OI snapshots (warms up over time)

---

## 📋 PHASE 4: MULTI-STRATEGY ENGINE 🟡 IN PROGRESS

### **4.1: Mean Reversion Strategy** ✅ DONE

**Files Created:**
- `strategy/mean_reversion.py` - Elite regime-aware mean reversion strategy

**Purpose:** Trade oversold/overbought bounces ONLY in RANGING markets. Elite implementation with regime detection to avoid fading strong trends.

**Logic (Elite Version):**
- **Regime Check**: Only trades when trend_strength < 0.45 (ranging market)
- RSI at extreme (≤30 for long, ≥70 for short)
- Price touching Bollinger Band (lower for long, upper for short)
- Reversal candle confirmation (bullish/bearish body)
- Dynamic targets: TP1 = BB midline, TP2 = opposite band
- R:R validation before taking trade (minimum 1.5)

**Features:**
- Uses existing `calculate_rsi()` and `calculate_bollinger_bands()` from `indicators.py`
- Blocks signals in trending markets (regime-aware)
- Smart signal selection in StrategyManager (prefers MR in ranging, breakout in trending)
- Tracks `signals_blocked_trending` for analytics

**Config Added:**
- `MEAN_REVERSION_ENABLED = True`
- `MR_REQUIRE_RANGING_REGIME = True`
- `MR_MAX_TREND_STRENGTH = 0.45`
- `MR_RSI_OVERSOLD = 30`, `MR_RSI_OVERBOUGHT = 70`
- `MR_BB_PERIOD = 20`, `MR_BB_STD_DEV = 2.0`
- `MR_REQUIRE_REVERSAL_CANDLE = True`
- `MR_RR_MINIMUM = 1.5`

**Integration:**
- Registered in `strategy_manager.py` when `MEAN_REVERSION_ENABLED = True`
- Exported from `strategy/__init__.py`
- `_select_best_signal()` updated for regime-aware signal selection

---

### **4.2: Funding Rate Arbitrage** ✅ DONE

**Files Created:**
- `strategy/funding_arbitrage.py` - Elite time-based funding arbitrage strategy

**Purpose:** Capture EXTREME funding rate imbalances where funding > fees. LOW-RISK, LOW-FREQUENCY strategy that only triggers on rare extremes.

**Logic (Elite Version):**
- Only triggers when funding rate > 0.15% (ensures profit after 0.12% fees)
- Extreme positive funding (>0.15%) = SHORT to collect from longs
- Extreme negative funding (<-0.15%) = LONG to collect from shorts
- TIME-BASED exit (not price targets) - auto-close after funding collected
- Low volatility requirement (ATR < 65th percentile)
- Minimum 1.5h time buffer before next funding
- Emergency stop loss (2.5%) for flash crash protection

**Features:**
- Coordinates with existing FundingRateFilter
- No TP orders (arb is time-based, not price-based)
- ProductionOrderManager updated with `_check_arb_time_exit()` and `_execute_arb_exit()`
- ManagedPosition has new fields: `exit_after_funding`, `max_hold_hours`, `expected_funding_time`
- Lowest priority in signal selection (only if no better opportunity)

**Config Added:**
- `FUNDING_ARBITRAGE_ENABLED = True`
- `FR_EXTREME_THRESHOLD = 0.0015` (0.15% - must exceed fees)
- `FR_EMERGENCY_STOP_PCT = 0.025` (2.5% hard stop)
- `FR_MIN_HOURS_TO_FUNDING = 1.5`
- `FR_MAX_HOLD_HOURS = 9.0`
- `FR_EXIT_BUFFER_MINUTES = 30`
- `FR_REQUIRE_LOW_VOLATILITY = True`
- `FR_MAX_ATR_PERCENTILE = 65`

**Integration:**
- Registered in `strategy_manager.py` when `FUNDING_ARBITRAGE_ENABLED = True`
- Exported from `strategy/__init__.py`
- `_select_best_signal()` gives arb LOWEST priority (only if nothing else available)
- `production_manager.py` handles time-based exit for arb positions

---

### **4.3: Elite Momentum Strategy** ✅ DONE

**File Created:** `strategy/momentum_strategy.py`

**Purpose:** Ride established trends by catching momentum in motion. Different from breakout (doesn't need consolidation), different from mean reversion (follows trend, doesn't fade).

**Entry Conditions:**
- Trend established (trend_strength > 0.35)
- RSI confirms direction (>50 for long, <50 for short)
- Price aligned with EMAs (20 > 50 for bull, 20 < 50 for bear)
- Volume above average (1.1x minimum)
- NOT overbought/oversold (RSI between 25-75)

**Targets:**
- TP1: 1.5R (quick partial profit)
- TP2: 2.5R (let winner run with trend)

**Config Added:**
```python
MOMENTUM_STRATEGY_ENABLED = True
MOMENTUM_TREND_STRENGTH_MIN = 0.35
MOMENTUM_RSI_BULL_MIN = 50
MOMENTUM_RSI_BEAR_MAX = 50
MOMENTUM_VOLUME_CONFIRM = 1.1
MOMENTUM_TP1_RR = 1.5
MOMENTUM_TP2_RR = 2.5
```

**Integration:** Registered in `strategy_manager.py`, exported from `strategy/__init__.py`

---

### **4.3b: Strategy Parameter Tuning** ✅ DONE

**Purpose:** Loosened strategy parameters to catch more signals without sacrificing quality.

**Changes Made:**
| Parameter | Old | New | Effect |
|-----------|-----|-----|--------|
| `BREAKOUT_VOLUME_MULTIPLIER` | 1.2 | 1.0 | Less volume required |
| `BREAKOUT_CONSOLIDATION_BARS` | 8 | 5 | Shorter consolidation OK |
| `PULLBACK_TREND_STRENGTH_MIN` | 0.4 | 0.3 | Weaker trends OK |
| `MR_MAX_TREND_STRENGTH` | 0.45 | 0.50 | More ranging allowed |

---

### **4.3c: Real Sentiment Integration** ✅ DONE

**File Created:** `data_feed/sentiment_tracker.py`

**Purpose:** Real Fear & Greed Index data from Alternative.me API (free).

**Features:**
- Fetches real crypto sentiment (0-100 scale)
- Caches results (1 hour) to avoid API spam
- Contrarian logic: Extreme Fear + Long = Boost, Extreme Greed + Short = Boost
- Integrated into `checklist_filter.py` for score adjustments

**Sentiment Score Adjustments:**
| Sentiment | Score | Effect on Signals |
|-----------|-------|-------------------|
| Extreme Fear (0-24) | +20 | Buy when fearful |
| Fear (25-44) | +10 | Favorable for longs |
| Neutral (45-55) | 0 | No adjustment |
| Greed (56-74) | -5 | Cautious |
| Extreme Greed (75-100) | -15 | Caution on longs |

**Integration:** Used in `research_filters/checklist_filter.py`, exported from `data_feed/__init__.py`

---

### **4.4: Elite Market Structure Intelligence** ✅ DONE

**Files Created:**
- `data_feed/market_structure.py` - Core analysis module
- `strategy/structure_strategy.py` - Strategy using the analysis

**Purpose:** Institutional-grade market analysis that sees the market like a professional trader.

**Components:**

**1. Support/Resistance Detection**
- Automatic identification of key price levels
- Swing high/low analysis
- Price clustering for level confirmation
- Round number (psychological) levels
- Level strength based on number of touches

**2. Market Structure Analysis**
- Higher highs / Higher lows detection (bullish)
- Lower highs / Lower lows detection (bearish)
- Structure break detection (trend reversals)
- Ranging market identification

**3. Volume Profile**
- High volume nodes as dynamic S/R
- Identifies where liquidity sits
- Price bins with volume accumulation

**Signal Types Generated:**
| Type | Trigger | Direction |
|------|---------|-----------|
| Structure Break | Trend reversal detected | With the break |
| Support Bounce | Price at support in uptrend | Long |
| Resistance Rejection | Price at resistance in downtrend | Short |
| Momentum Continuation | Strong move + bias alignment | With momentum |
| Range Bias | Ranging market with directional bias | With bias |

**Config:**
```python
STRUCTURE_STRATEGY_ENABLED = True
STRUCTURE_TIMEFRAME = '15m'
STRUCTURE_MIN_CONFIDENCE = 0.50
STRUCTURE_ATR_STOP_MULT = 1.5
STRUCTURE_TP1_RR = 1.5
STRUCTURE_TP2_RR = 2.5
```

**Integration:** Registered in `strategy_manager.py`, exported from `strategy/__init__.py`

**Status:** ✅ FULLY INTEGRATED - 7th strategy active

---

### **4.5: Strategy Allocator** (Future)

**Purpose:** Distribute capital across multiple strategies based on performance.

**Logic:**
- Track performance of each strategy
- Allocate more capital to winning strategies
- Reduce allocation to losing strategies
- Rebalance weekly

**New Files:**
- `strategy/strategy_allocator.py` - Capital allocation manager

**Modify:**
- `strategy/strategy_manager.py`:
  - Add `StrategyAllocator` instance
  - Use allocator to determine position size per strategy

- `config.py`:
  ```python
  STRATEGY_ALLOCATION_ENABLED = True
  ALLOCATION_REBALANCE_DAYS = 7
  MIN_STRATEGY_ALLOCATION = 0.1  # 10% minimum per strategy
  MAX_STRATEGY_ALLOCATION = 0.5  # 50% maximum per strategy
  ```

**Dependencies:**
- Uses `TradeJournal` data for performance tracking
- Uses existing volume and price data

**Integration Points:**
- Called in `main.py` before trade execution
- Adjusts `position_size` based on strategy performance

**DO NOT TOUCH:**
- Individual strategy logic
- Risk manager (works alongside it)

---

## 📋 PHASE 5: MACHINE LEARNING

### **5.1: Trade Outcome Learning**

**Purpose:** Learn which setups actually win vs lose from historical trades.

**Logic:**
- After each trade closes, extract features:
  - Market conditions (volatility, trend, volume)
  - Signal characteristics (strategy, filters passed, score)
  - Entry/exit details
- Train ML model to predict win probability
- Use model to filter low-probability trades

**New Files:**
- `model_learning/trade_outcome_learner.py` - ML model trainer

**Modify:**
- `model_learning/model_trainer.py`:
  - Enhance existing trainer or create new one

- `filters/filter_manager.py`:
  - Add ML filter: `'ml_outcome': MLOutcomeFilter()`

- `config.py`:
  ```python
  ML_OUTCOME_ENABLED = True
  ML_MIN_WIN_PROBABILITY = 0.55  # Require 55%+ win probability
  ML_MODEL_RETRAIN_DAYS = 30
  ```

**Dependencies:**
- `scikit-learn` or `xgboost`
- Uses `TradeJournal` data

**Integration Points:**
- Filter called in `FilterManager.check_all()`
- Model retrained periodically from trade history

**DO NOT TOUCH:**
- Trade execution
- Existing model learning (enhance, don't replace)

---

### **5.2: Pattern Recognition**

**Purpose:** ML to spot profitable price patterns automatically.

**Logic:**
- Extract price patterns (candlestick sequences, chart patterns)
- Label patterns as winners/losers from history
- Train CNN or LSTM to recognize patterns
- Use model to score new signals

**New Files:**
- `model_learning/pattern_recognizer.py` - Pattern ML model

**Modify:**
- `config.py`:
  ```python
  ML_PATTERN_ENABLED = True
  PATTERN_LOOKBACK_CANDLES = 50
  ```

**Dependencies:**
- `tensorflow` or `pytorch` (for deep learning)
- Or `scikit-learn` for simpler pattern matching

**Integration Points:**
- Called in `FilterManager` or `StrategyManager`
- Uses historical price data

---

### **5.3: Optimal Timing Model**

**Purpose:** Learn best entry/exit times from historical performance.

**Logic:**
- Analyze trade outcomes by:
  - Hour of day
  - Day of week
  - Time since last trade
  - Market session (Asian/European/US)
- Train model to predict optimal timing
- Filter trades that occur at historically bad times

**New Files:**
- `model_learning/timing_model.py` - Timing predictor

**Modify:**
- `filters/filter_manager.py`:
  - Add timing filter

- `config.py`:
  ```python
  ML_TIMING_ENABLED = True
  TIMING_MIN_PROBABILITY = 0.52  # Require 52%+ win rate for this time
  ```

**Dependencies:**
- `scikit-learn` or simple statistical analysis

**Integration Points:**
- Filter in `FilterManager`
- Uses `TradeJournal` data

---

### **5.4: Filter Auto-Tuning**

**Purpose:** ML adjusts filter thresholds based on what actually works.

**Logic:**
- Track which filter thresholds lead to wins
- Use optimization algorithm (genetic algorithm, Bayesian optimization)
- Periodically retune filter thresholds
- Log changes for review

**New Files:**
- `model_learning/filter_tuner.py` - Filter optimizer

**Modify:**
- `config.py`:
  ```python
  FILTER_AUTO_TUNE_ENABLED = False  # Start disabled, enable after review
  FILTER_TUNE_INTERVAL_DAYS = 30
  FILTER_TUNE_MIN_TRADES = 50  # Need 50+ trades before tuning
  ```

**Dependencies:**
- `scipy.optimize` or `optuna`

**Integration Points:**
- Runs as background task
- Updates `config.py` or separate tuning config file

**⚠️ WARNING:** This is advanced - test thoroughly before enabling. Could break things if tuned incorrectly.

---

## 📋 PHASE 6: SENTIMENT INTEGRATION

### **6.1: Fear & Greed Index**

**Purpose:** Use crypto Fear & Greed Index as contrarian signal.

**Logic:**
- Fetch Fear & Greed Index (0-100 scale)
- Extreme fear (<20) = potential buy opportunity
- Extreme greed (>80) = potential sell opportunity
- Use as filter or signal enhancer

**New Files:**
- `data_feed/sentiment.py` - Sentiment data fetcher
- `filters/fear_greed.py` - Fear & Greed filter

**Modify:**
- `config.py`:
  ```python
  FEAR_GREED_ENABLED = True
  FEAR_GREED_API_URL = "https://api.alternative.me/fng/"
  FEAR_THRESHOLD = 20
  GREED_THRESHOLD = 80
  ```

**Dependencies:**
- `requests` (for API call)

**Integration Points:**
- Background data fetch (update every hour)
- Filter in `FilterManager`

---

### **6.2: Twitter/X Sentiment**

**Purpose:** Gauge crypto social mood from Twitter/X.

**Logic:**
- Monitor crypto Twitter for SOL-related mentions
- Analyze sentiment (positive/negative/neutral)
- Track sentiment trends
- Use extreme sentiment as contrarian signal

**New Files:**
- `data_feed/twitter_sentiment.py` - Twitter sentiment analyzer

**Modify:**
- `config.py`:
  ```python
  TWITTER_SENTIMENT_ENABLED = True
  TWITTER_API_KEY = os.getenv('TWITTER_API_KEY', '')
  TWITTER_SEARCH_TERMS = ['SOL', 'Solana', '$SOL']
  SENTIMENT_UPDATE_INTERVAL_MINUTES = 15
  ```

**Dependencies:**
- Twitter API v2 (requires API key)
- `tweepy` or direct API calls
- Sentiment analysis: `textblob` or `vaderSentiment`

**Integration Points:**
- Background data collection
- Filter or signal enhancer

---

### **6.3: News Impact Detection**

**Purpose:** Detect major news events that could cause volatility.

**Logic:**
- Monitor crypto news feeds (CoinDesk, The Block, etc.)
- Detect major announcements (partnerships, upgrades, hacks)
- Pause trading during high-impact news
- Resume after volatility settles

**New Files:**
- `data_feed/news_monitor.py` - News event detector

**Modify:**
- `config.py`:
  ```python
  NEWS_MONITOR_ENABLED = True
  NEWS_PAUSE_DURATION_MINUTES = 30  # Pause trading after major news
  ```

**Dependencies:**
- News API or RSS feeds
- `feedparser` for RSS

**Integration Points:**
- Filter in `FilterManager` (rejects trades during news events)
- Or pause main loop in `main.py`

---

## 📋 PHASE 7: ADVANCED RISK MANAGEMENT

### **7.1: Kelly Criterion Sizing**

**Purpose:** Mathematically optimal position size based on win rate and risk/reward.

**Logic:**
- Calculate Kelly %: `f = (p * (b + 1) - 1) / b`
  - `p` = win probability (from history)
  - `b` = average win / average loss
- Use fractional Kelly (e.g., 0.25x Kelly) for safety
- Adjust position size based on Kelly calculation

**New Files:**
- `risk/kelly_criterion.py` - Kelly calculator

**Modify:**
- `risk/risk_manager.py`:
  - Add optional Kelly sizing method
  - Use if `KELLY_CRITERION_ENABLED = True`

- `config.py`:
  ```python
  KELLY_CRITERION_ENABLED = False  # Start disabled, test first
  KELLY_FRACTION = 0.25  # Use 25% of full Kelly (safer)
  KELLY_MIN_WIN_RATE = 0.50  # Need 50%+ win rate to use Kelly
  ```

**Dependencies:**
- None (pure math)

**Integration Points:**
- Called in `RiskManager.calculate_position_size()`
- Overrides or adjusts default position sizing

**⚠️ WARNING:** Kelly can suggest very large positions. Always use fractional Kelly and test thoroughly.

**DO NOT TOUCH:**
- Core risk limits (max risk per trade still applies)
- Position tracking

---

### **7.2: Drawdown Circuit Breaker**

**Purpose:** Stop trading if account drawdown exceeds threshold.

**Logic:**
- Track account equity over time
- Calculate current drawdown from peak
- If drawdown > threshold → pause trading
- Resume after manual review or time delay

**New Files:**
- `risk/drawdown_monitor.py` - Drawdown tracker

**Modify:**
- `config.py`:
  ```python
  DRAWDOWN_CIRCUIT_BREAKER_ENABLED = True
  DRAWDOWN_THRESHOLD_PCT = 10.0  # Stop at 10% drawdown
  DRAWDOWN_RESUME_AFTER_HOURS = 24  # Manual resume required
  ```

- `main.py`:
  - Check drawdown before each trade cycle
  - Pause loop if threshold exceeded

**Dependencies:**
- Uses account balance from `OKXClient`

**Integration Points:**
- Called in `main.py.run()` before trade cycle
- Also in `RiskManager.check_can_trade()`

**DO NOT TOUCH:**
- Trade execution (just prevents new trades)

---

### **7.3: Dynamic Position Sizing**

**Purpose:** Adjust position size by confidence level and volatility.

**Logic:**
- Higher confidence signals → larger size (up to max)
- Higher volatility → smaller size (reduce risk)
- Winning streak → slightly increase
- Losing streak → reduce

**New Files:**
- `risk/dynamic_sizing.py` - Dynamic size calculator

**Modify:**
- `risk/risk_manager.py`:
  - Add dynamic sizing method
  - Use signal confidence score

- `config.py`:
  ```python
  DYNAMIC_SIZING_ENABLED = True
  DYNAMIC_SIZE_BASE_MULTIPLIER = 1.0  # Base size
  DYNAMIC_SIZE_CONFIDENCE_MULTIPLIER = 0.5  # +0.5x per confidence point
  DYNAMIC_SIZE_VOLATILITY_DIVISOR = 1.5  # Divide by volatility multiplier
  ```

**Dependencies:**
- Uses existing volatility (ATR) data

**Integration Points:**
- Called in `RiskManager.calculate_position_size()`
- Uses signal confidence from `FilterManager`

**DO NOT TOUCH:**
- Max risk limits (still enforced)

---

### **7.4: Daily Loss Limit**

**Purpose:** Hard stop after X losses or X% loss in a single day.

**Logic:**
- Track trades and PnL for current day
- If loss count > threshold OR loss % > threshold → stop trading
- Reset at midnight UTC

**Modify:**
- `risk/risk_manager.py`:
  - Add daily loss tracking
  - Check in `check_can_trade()`

- `config.py`:
  ```python
  DAILY_LOSS_LIMIT_ENABLED = True
  DAILY_MAX_LOSSES = 3  # Stop after 3 losses
  DAILY_MAX_LOSS_PCT = 5.0  # Or 5% loss
  ```

**Dependencies:**
- Uses `TradeJournal` or internal tracking

**Integration Points:**
- Called in `RiskManager.check_can_trade()`
- Tracks in `RiskManager` state

---

## 📋 PHASE 8: EXECUTION OPTIMIZATION

### **8.1: Slippage Tracking**

**Purpose:** Log and analyze execution quality (slippage vs expected price).

**Logic:**
- Record expected price (market price at signal time)
- Record actual fill price
- Calculate slippage: `(actual - expected) / expected`
- Log to trade journal
- Generate slippage reports

**Modify:**
- `execution/production_manager.py`:
  - Record expected price before order
  - Record actual fill price from order response
  - Calculate and log slippage

- `utils/trade_journal.py`:
  - Add slippage field to trade log

**Dependencies:**
- None (uses existing order data)

**Integration Points:**
- In `production_manager.execute_trade()` when entry fills
- Logged to `TradeJournal`

**DO NOT TOUCH:**
- Order placement logic (just add tracking)

---

### **8.2: TWAP Orders**

**Purpose:** Split large orders over time to reduce market impact.

**Logic:**
- If position size > threshold, split into multiple orders
- Execute orders over time window (e.g., 5 minutes)
- Distribute evenly or use volume-weighted timing

**New Files:**
- `execution/twap_executor.py` - TWAP order executor

**Modify:**
- `config.py`:
  ```python
  TWAP_ENABLED = True
  TWAP_SIZE_THRESHOLD = 1000  # USDT - use TWAP for orders >$1000
  TWAP_DURATION_MINUTES = 5
  TWAP_NUM_SLICES = 5  # Split into 5 orders
  ```

- `execution/production_manager.py`:
  - Check if TWAP needed before placing order
  - Use `TWAPExecutor` if size > threshold

**Dependencies:**
- None (uses existing order placement)

**Integration Points:**
- Called in `production_manager.execute_trade()` before entry
- Replaces single order with TWAP sequence

**⚠️ WARNING:** TWAP can result in partial fills. Ensure position tracking handles this.

**DO NOT TOUCH:**
- Core order placement (TWAP calls it multiple times)

---

### **8.3: Smart Timing**

**Purpose:** Avoid high-spread periods (low liquidity times).

**Logic:**
- Track historical spread data
- Identify high-spread periods (e.g., weekends, late night)
- Delay orders during high spread
- Execute when spread narrows

**New Files:**
- `execution/smart_timing.py` - Spread-aware order timing

**Modify:**
- `config.py`:
  ```python
  SMART_TIMING_ENABLED = True
  MAX_SPREAD_BPS = 10  # 0.1% max spread before delaying
  SMART_TIMING_MAX_DELAY_MINUTES = 30
  ```

- `execution/production_manager.py`:
  - Check spread before order
  - Delay if spread too high

**Dependencies:**
- Uses existing market data (bid/ask spread)

**Integration Points:**
- Called in `production_manager.execute_trade()` before order
- Uses `OKXClient` to get current spread

**DO NOT TOUCH:**
- Order placement (just adds delay logic)

---

## 🧪 TESTING APPROACH

### **For Each Feature:**

1. **Unit Tests:**
   - Test new module in isolation
   - Mock dependencies
   - Verify logic correctness

2. **Integration Tests:**
   - Test with real market data (but no real trades)
   - Verify it doesn't break existing flow
   - Check config flags work

3. **Dry Run:**
   - Enable feature with `OKX_SIMULATED=True`
   - Run for 24-48 hours
   - Monitor logs for errors

4. **Gradual Rollout:**
   - Start with feature disabled
   - Enable in monitoring mode (log but don't affect trades)
   - Enable with conservative settings
   - Gradually tune

### **Safety Checklist:**
- [ ] Feature has config flag to enable/disable
- [ ] Feature fails gracefully (try/except, fallback)
- [ ] Feature doesn't modify existing working code
- [ ] Feature logs its actions
- [ ] Feature tested in simulated mode first

---

## 📝 IMPLEMENTATION ORDER RECOMMENDATION

**Start with Phase 1** (Visibility) - Zero risk, immediate value:
1. Trade Journal (1.2) - Foundation for everything else
2. Performance Analytics (1.3) - Understand current performance
3. Telegram Alerts (1.1) - Know what's happening
4. Dashboard Upgrades (1.4) - Visual monitoring

**Then Phase 2** (Filtering) - Low risk, better signals:
- All filters are additive and can be toggled

**Then Phase 3-8** - As needed, based on performance

---

## 🔗 KEY INTEGRATION POINTS SUMMARY

| Integration Point | File | Method | Purpose |
|------------------|------|--------|---------|
| **Add Filter** | `filters/filter_manager.py` | `quality_filters` dict | Register new filter |
| **Add Strategy** | `strategy/strategy_manager.py` | `strategies` list | Register new strategy |
| **Add Config** | `config.py` | New variables | Add feature flags |
| **Trade Execution Hook** | `main.py` | `_execute_trade_production()` | Add post-trade logic |
| **Position Update Hook** | `main.py` | `_update_positions()` | Add monitoring logic |
| **Risk Calculation** | `risk/risk_manager.py` | `calculate_position_size()` | Modify sizing |
| **Data Collection** | `data_feed/` | New files | Add data sources |

---

## ✅ FINAL CHECKLIST BEFORE IMPLEMENTING ANY FEATURE

- [ ] Read this entire document
- [ ] Understand current architecture
- [ ] Identify integration points
- [ ] Plan new files (don't modify existing unnecessarily)
- [ ] Add config flags (always with safe defaults)
- [ ] Write code with error handling
- [ ] Test in simulated mode
- [ ] Document what you changed
- [ ] Verify it doesn't break existing features

---

**END OF DOCUMENT**

*This roadmap is a living document. Update it as features are implemented or requirements change.*
