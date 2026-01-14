# Context Pack: Supequant Trading System

## Project Overview

**Supequant** is a professional-grade automated cryptocurrency trading system for OKX exchange. It uses a multi-layer filtering system to trade only high-probability setups, prioritizing quality over quantity (target: 3-5 trades/day max). The system trades SOL-USDT perpetuals with BTC as a correlation reference.

**Current Goal (This Week)**: Fix zero-trade issue by relaxing overly strict strategy conditions and filters. Strategy was generating 0 signals due to tight thresholds (3% consolidation, 1.2x volume, strict ATR compression). Recent changes relaxed these to 5% consolidation, 0.8x volume, and ATR < 1.5x average.

## Current Status

**✅ What Works:**
- Data feed from OKX API (`data_feed/okx_client.py`, `data_feed/market_data.py`)
- Historical data loading with caching (`backtesting/historical_data_loader.py`)
- Backtest engine (`backtesting/backtest_engine.py`)
- Multi-layer filter system (7 blocking filters + 2 research filters)
- Risk management (`risk/risk_manager.py`)
- Order execution (`execution/order_manager.py`, `execution/position_tracker.py`)
- Dashboard (`dashboard/app.py`)

**❌ What's Broken:**
- Strategy generating 0 signals (recently relaxed but not yet validated)
- Breakout detection threshold may still be too strict (currently 0.3% after recent fix)
- Filter pass rate unknown (needs testing with relaxed thresholds)

**❓ Unknowns:**
- Actual signal generation rate with new relaxed thresholds
- Filter rejection rates with current market conditions
- Backtest performance on recent data

## How to Run

### Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.template .env
# Edit .env with OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE
# Set OKX_SIMULATED=True for paper trading

# 3. Review config.py (trading params, risk limits, filter thresholds)
```

### Run Live Trading
```bash
python main.py                    # Start main trading loop
python supervisor.py             # Run with auto-restart on crash
```

### Run Backtests
```bash
python run_backtest.py --start 2025-12-01 --end 2026-01-13 --name test --timeframe 15m
python run_backtest.py --quick   # Quick 30-day test
```

### Diagnostics
```bash
python diagnose_no_trades.py      # Find why no trades (30 days analysis)
python debug_strategy.py         # Debug strategy conditions (7 days)
python tune_filters.py           # Analyze filter thresholds
python force_test_trade.py --paper  # Force one test trade
```

### Dashboard
```bash
# Dashboard runs automatically with main.py
# Access at http://localhost:8080
```

## Environment Setup

### Required Environment Variables (`.env`)
```
OKX_API_KEY=your_api_key
OKX_SECRET_KEY=your_secret_key
OKX_PASSPHRASE=your_passphrase
OKX_SIMULATED=True              # Start in demo mode (recommended)
DASHBOARD_SECRET_KEY=supequant-dashboard-2026
```

### Key Config Files
- `config.py` - All trading parameters, risk limits, filter thresholds
- `.env` - API credentials (DO NOT COMMIT)
- `config_strategy_relaxed.yaml` - Relaxed strategy settings reference

### Dependencies (`requirements.txt`)
- `python-okx>=0.2.1` - OKX API client
- `pandas>=2.0.0`, `numpy>=1.24.0` - Data analysis
- `scikit-learn>=1.3.0` - ML models
- `flask>=3.0.0` - Dashboard
- `python-dotenv>=1.0.0` - Environment variables

## Repository Map

```
supequant/
├── main.py                      # Main entry point (live trading loop)
├── config.py                    # Global configuration (risk, filters, strategy params)
├── requirements.txt             # Python dependencies
│
├── data_feed/                   # Market data acquisition
│   ├── okx_client.py           # OKX API wrapper (auth, rate limits, retries)
│   ├── market_data.py          # Multi-timeframe data aggregation
│   └── indicators.py           # Technical indicators (ATR, RSI, EMA, etc.)
│
├── backtesting/                # Backtesting system
│   ├── historical_data_loader.py  # Fetch/cache historical OHLCV from OKX
│   ├── backtest_engine.py        # Core simulation engine
│   ├── performance_metrics.py     # 25+ trading metrics (Sharpe, Sortino, etc.)
│   └── report_generator.py        # Text/CSV/JSON reports
│
├── filters/                     # Trade filtering (ALL must pass)
│   ├── filter_manager.py       # Orchestrates all filters
│   ├── market_regime.py        # ATR volatility, funding rate, OI stability
│   ├── multi_timeframe.py      # HTF/MTF/LTF trend alignment
│   ├── ai_rejection.py         # ML confidence scoring (rule-based fallback)
│   ├── pattern_failure.py      # Bull/bear trap, stop hunt, fakeout detection
│   ├── btc_sol_correlation.py  # BTC-SOL correlation check
│   └── macro_driver.py         # Macro environment analysis
│
├── strategy/                    # Trading strategies
│   ├── breakout_strategy.py    # Breakouts from consolidation (ATR compression + volume)
│   ├── pullback_strategy.py    # Pullbacks in trends (Fibonacci levels)
│   └── strategy_manager.py     # Strategy orchestration
│
├── execution/                   # Order execution
│   ├── order_manager.py        # Order placement, retries, error handling
│   └── position_tracker.py     # Position tracking, PnL calculation
│
├── risk/                       # Risk management
│   └── risk_manager.py         # Position sizing, daily limits, kill switches
│
├── model_learning/             # AI model training
│   ├── data_collector.py       # Collect trade predictions/outcomes
│   └── model_trainer.py        # Train rejection model
│
├── dashboard/                  # Web dashboard
│   ├── app.py                  # Flask app (trades, positions, PnL)
│   └── templates/index.html    # Dashboard UI
│
├── research_filters/          # Research/advisory filters (non-blocking)
│   ├── sol_playbook.py
│   ├── checklist_filter.py
│   └── driver_weighting.py
│
├── utils/                      # Utilities
│   └── logger.py               # Logging setup
│
├── runs/                       # Event logs (paper trading)
│   └── YYYY-MM-DD/events.jsonl
│
├── backtesting/cache/         # Cached historical data
├── backtesting/reports/       # Backtest reports
└── logs/                      # Application logs
```

## Key Modules & Responsibilities

### Data Layer (`data_feed/`)
- **OKXClient** (`okx_client.py`): Handles API auth, rate limiting, retries, error handling. Supports simulated mode.
- **MarketDataFeed** (`market_data.py`): Aggregates multi-timeframe data, calculates indicators, provides unified interface.
- **TechnicalIndicators** (`indicators.py`): ATR, RSI, EMA, Bollinger Bands, volatility metrics.

### Strategy Layer (`strategy/`)
- **BreakoutStrategy** (`breakout_strategy.py`): Trades breakouts from consolidation. Requires: ATR compression (< 1.5x average), consolidation (< 5% range), volume confirmation (≥ 0.8x average), breakout detection (0.3% above/below). **RECENTLY RELAXED** from 3% consolidation, 1.2x volume, strict ATR.
- **PullbackStrategy** (`pullback_strategy.py`): Trades pullbacks in trends using Fibonacci levels.
- **StrategyManager**: Orchestrates strategies, aggregates signals.

### Filter Layer (`filters/`)
- **FilterManager** (`filter_manager.py`): Runs all filters sequentially. ALL must pass.
- **MarketRegimeFilter**: ATR percentile (10-95), funding rate (< 0.001), OI stability.
- **MultiTimeframeFilter**: HTF/MTF/LTF trend alignment (strength thresholds: 0.3/0.25/0.2).
- **AIRejectionFilter**: ML confidence scoring (threshold: 40), rule-based fallback.
- **PatternFailureFilter**: Bull/bear trap (threshold: 0.03), stop hunt, fakeout detection.
- **BTCSOLCorrelationFilter**: Correlation check (min: 0.4), trend agreement.
- **MacroDriverFilter**: Macro environment score (min: 25).

### Risk Layer (`risk/`)
- **RiskManager** (`risk_manager.py`): Position sizing (1% risk per trade), daily loss limits (5%), max positions (2), kill switch checks.

### Execution Layer (`execution/`)
- **OrderManager** (`order_manager.py`): Places orders via OKX API, handles retries, error recovery.
- **PositionTracker** (`position_tracker.py`): Tracks open positions, calculates PnL, monitors exits.

### Backtesting (`backtesting/`)
- **HistoricalDataLoader**: Fetches/caches historical data from OKX, handles pagination, symbol conversion (SWAP → spot format for API).
- **BacktestEngine**: Simulates trading on historical data, applies strategies/filters, tracks trades, calculates PnL. **NO LOOKAHEAD** - processes candles sequentially.
- **PerformanceMetrics**: Calculates 25+ metrics (Sharpe, Sortino, max drawdown, win rate, profit factor, etc.).
- **ReportGenerator**: Generates text/CSV/JSON reports.

## Data Sources & Timeframes

### Exchange
- **OKX** (https://www.okx.com) - Perpetual futures
- **Primary Symbol**: `SOL-USDT-SWAP` (Solana perpetual)
- **Reference Symbol**: `BTC-USDT-SWAP` (Bitcoin for correlation)

### Timeframes
- **1m, 5m, 15m, 1H, 4H** (primary: 15m for signals)
- **Lookback**: 1m=300, 5m=300, 15m=200, 1H=100, 4H=100 candles

### Data Format
- OHLCV candles with timestamps (milliseconds)
- Cached in `backtesting/cache/` as JSON files
- Symbol conversion: `SOL-USDT-SWAP` → `SOL-USDT` for API calls

## Strategy Description

### Breakout Strategy (`strategy/breakout_strategy.py`)
**High-Level Rules:**
1. Volatility compression: ATR < 1.5x 20-period average (or percentile < 60)
2. Consolidation: Price range < 5% over last 15 candles, max 2 breaks
3. Breakout: Close > resistance * 1.003 (long) or < support * 0.997 (short) - **0.3% threshold**
4. Volume: Current volume ≥ 0.8x 20-period average

**Inputs:** Market state with 15m candles, ATR data, volume data
**Outputs:** Signal dict with direction, entry_price, stop_loss, take_profit_1, take_profit_2

**Recent Changes (Jan 2026):**
- Consolidation: 3% → 5% range
- Volume: 1.2x → 0.8x average
- ATR compression: percentile < 40 → ATR < 1.5x average
- Breakout threshold: 0.1% → 0.3%

### Pullback Strategy (`strategy/pullback_strategy.py`)
**High-Level Rules:**
1. Strong trend on HTF (1H)
2. Pullback to Fibonacci levels (0.382, 0.5, 0.618)
3. Trend resumption signal
4. Volume confirmation

## Risk Rules

### Position Sizing (`config.py`)
- **Risk per trade**: 1% of account (`MAX_RISK_PER_TRADE = 0.01`)
- **Position size**: 3% of account (`POSITION_SIZE_PCT = 0.03`)
- **Max positions**: 2 open simultaneously (`MAX_POSITIONS_OPEN = 2`)

### Daily Limits
- **Max daily loss**: 5% (`MAX_DAILY_LOSS_PCT = 0.05`)
- **Max drawdown**: 6% (`MAX_DAILY_DRAWDOWN = 0.06`)
- **Max trades/day**: 10 (`MAX_DAILY_TRADES = 10`)
- **Trade interval**: 30 minutes minimum (`TRADE_INTERVAL_MINUTES = 30`)

### Stop Loss & Take Profit
- **Stop loss**: 1.5x ATR below/above entry (`ATR_STOP_MULTIPLIER = 1.5`)
- **Take profit 1**: 2.0x risk (`TP1_RR_RATIO = 2.0`)
- **Take profit 2**: 3.0x risk (`TP2_RR_RATIO = 3.0`)

### Kill Switches
- **File-based**: Create `KILL_SWITCH.txt` to stop trading immediately
- **Daily loss**: Auto-stop at 5% daily loss
- **Drawdown**: Auto-stop at 6% drawdown

## Execution Details

### Exchange Adapter (`data_feed/okx_client.py`)
- **API**: OKX REST API v5
- **Auth**: HMAC-SHA256 signature with API key/secret/passphrase
- **Rate limits**: 20 requests/second (enforced with delays)
- **Retries**: 3 attempts with exponential backoff
- **Simulated mode**: `OKX_SIMULATED=True` (no real orders, local simulation)

### Order Types
- **Market orders** for entry (immediate execution)
- **Stop-loss orders** for exits
- **Take-profit orders** (TP1, TP2)

### Error Handling
- Network errors: Retry with backoff
- API errors: Log and skip trade
- Position reconciliation: `execution/position_reconciler.py` (if exists)

## Testing & Evaluation

### Backtest Execution (`run_backtest.py`)
```bash
python run_backtest.py --start YYYY-MM-DD --end YYYY-MM-DD --name test_name --timeframe 15m
```

### Metrics Tracked (`backtesting/performance_metrics.py`)
- Returns: Total return, annualized return
- Risk-adjusted: Sharpe ratio, Sortino ratio, Calmar ratio
- Drawdown: Max drawdown, average drawdown, recovery time
- Trade stats: Win rate, profit factor, average win/loss, largest win/loss
- Advanced: Kelly Criterion, MFE/MAE, expectancy

### Assumptions
- **Slippage**: ASSUMED 0.1% (not explicitly modeled in current code)
- **Fees**: ASSUMED 0.05% per trade (maker/taker, not explicitly modeled)
- **Lookahead**: **NONE** - backtest processes candles sequentially, no future data
- **Data quality**: Validates gaps, missing candles, out-of-order data

### Validation
- **Walk-forward testing**: Train on period A, test on period B
- **Out-of-sample**: Test on unseen data
- **Stress testing**: Different market conditions (bull/bear/volatile)

## Known Issues

1. **Zero signals generated** (`strategy/breakout_strategy.py`)
   - **Status**: Recently relaxed thresholds (5% consolidation, 0.8x volume, ATR < 1.5x, 0.3% breakout)
   - **File**: `strategy/breakout_strategy.py` lines 93-112, 140-143, 184, 196, 214-216
   - **Fix**: Applied Jan 2026, needs validation

2. **Symbol format conversion** (`backtesting/historical_data_loader.py`)
   - **Status**: Fixed - converts `SOL-USDT-SWAP` → `SOL-USDT` for API calls
   - **File**: `backtesting/historical_data_loader.py` line ~120

3. **Data filtering too strict** (`backtesting/historical_data_loader.py`)
   - **Status**: Fixed - added `skip_date_filter` for fallback data
   - **File**: `backtesting/historical_data_loader.py` `_fetch_candles()` method

4. **OKX API authentication** (`data_feed/okx_client.py`)
   - **Status**: Fixed - tries unauthenticated first, falls back to authenticated for pagination
   - **File**: `data_feed/okx_client.py` `get_history_candles()` method

5. **Infinite loop in backtest** (`backtesting/backtest_engine.py`)
   - **Status**: Fixed - removed `processed_timestamps` check (was preventing signal reprocessing)
   - **File**: `backtesting/backtest_engine.py` line ~92

## Next 5 Tasks (Ordered)

1. **Validate relaxed strategy thresholds** - Run `diagnose_no_trades.py` on 30+ days to confirm signals are generated
2. **Test breakout detection at 0.3%** - Verify 0.3% threshold catches breakouts (currently price gets within 0.16-0.23%)
3. **Run full backtest** - `python run_backtest.py --start 2025-12-01 --end 2026-01-13 --name relaxed_validation`
4. **Analyze filter rejection rates** - Use `tune_filters.py` to identify if filters are still too strict
5. **Paper trade test** - Run `force_test_trade.py --paper` to verify execution pipeline works

## "Do Not Break" Constraints

### Hard Rules
1. **NO LOOKAHEAD** - Backtest must process candles sequentially, never use future data (`backtesting/backtest_engine.py`)
2. **NO DELETING AUTH** - Never remove API authentication logic (`data_feed/okx_client.py`)
3. **ALL FILTERS MUST PASS** - Trade only executes if ALL filters pass (`filters/filter_manager.py` line 63-77)
4. **RISK LIMITS ENFORCED** - Never bypass risk management (`risk/risk_manager.py`)
5. **SIMULATED MODE DEFAULT** - Always default to `OKX_SIMULATED=True` for safety (`config.py` line 17)

### Data Integrity
- **Symbol format**: Always convert futures format (`-SWAP`) to spot format for API calls
- **Timestamp ordering**: Candles must be processed in chronological order
- **Cache validation**: Check cache expiry before using cached data

### Code Structure
- **Filter order matters**: Filters run in specific order (cheap checks first) - don't reorder
- **Strategy independence**: Strategies should not depend on each other
- **Error handling**: All API calls must have try/except with logging

---

**Last Updated**: 2026-01-13
**Version**: 1.0 (Post-relaxation)
**Status**: Strategy thresholds relaxed, awaiting validation
