# CLAUDE.md - Elite Quant Trading System

## ⚠️ MANDATORY: Check Live Status First

**IMMEDIATELY run this when starting ANY conversation or task:**

```bash
./status.sh
```

Do this BEFORE responding to the user's first message. This is non-negotiable for a live trading system.

This shows: bot running status, current cycle, drawdown %, pause status, and live position with PnL.

---

## CRITICAL WARNING

This is a **LIVE TRADING SYSTEM** on Hyperliquid mainnet with real money. The current configuration is the result of extensive backtesting and debugging. **DO NOT OPTIMIZE OR "IMPROVE" ANYTHING** without explicit user permission.

## Quick Reference

| Setting | Value | Notes |
|---------|-------|-------|
| Exchange | Hyperliquid | NOT OKX |
| Symbol | SOL-USDT-SWAP | Perpetual futures |
| Mode | perp | NOT spot |
| Leverage | 5x | Growth mode |
| Min Contract | 0.01 SOL | Dynamic from szDecimals=2 |
| Win Rate | 36% | Intentional - 3:1 R:R |
| Backtest Return | +340% | 6 months |

## Architecture

```
main.py                    # Main loop, V4 early exit integration
├── config.py              # All configuration (PROTECTED)
├── data_feed/
│   ├── hyperliquid_client.py  # Exchange API (PROTECTED)
│   └── market_data.py     # Price data fetching
├── execution/
│   └── production_manager.py  # Order execution (PROTECTED)
├── risk/
│   └── risk_manager.py    # Position sizing (PROTECTED)
├── strategy/
│   └── strategy_manager.py    # Signal generation
├── filters/
│   └── filter_manager.py  # Trade quality scoring
└── utils/
    ├── telegram_bot.py    # User notifications (PROTECTED)
    ├── context_builder.py # ChatGPT context (PROTECTED)
    └── system_health.py   # Health monitoring (PROTECTED)
```

## NEVER MODIFY

These settings must remain exactly as configured:

```python
# config.py - LOCKED VALUES
TRADING_SYMBOL = "SOL-USDT-SWAP"
TRADING_MODE = "perp"
SPOT_FALLBACK_ENABLED = False

# V4 Elite - ENABLED
V4_ENABLED = True
V4_STRATEGY_BOOST_ENABLED = True
V4_SCORE_SIZING_ENABLED = True
V4_EARLY_EXIT_ENABLED = True

# Adaptive Thresholds - DISABLED (backtest: +$106 better OFF)
ADAPTIVE_THRESHOLD_ENABLED = False
SCORE_THRESHOLD_ADAPTIVE_ENABLED = False
```

## NEVER ENABLE

These features hurt returns in backtests:

- `V4_KELLY_ENABLED` - Wrong win rate assumptions
- `V4_REGIME_PREDICTION_ENABLED` - Too conservative
- `V4_PYRAMID_ENABLED` - Hurt returns
- `V4_BREAKEVEN_AFTER_TP1` - Caused premature stop-outs
- `V4_WINNER_PREDICTOR_ENABLED` - Untrained ML model
- `V4_DIRECTIONAL_BIAS_ENABLED` - Wrong assumptions
- `ADAPTIVE_THRESHOLD_ENABLED` - Lost $106 vs fixed
- `SCORE_THRESHOLD_ADAPTIVE_ENABLED` - Inconsistent results

## Dynamic Config Values

`MIN_SOL_CONTRACT` is updated at runtime by `hyperliquid_client.py`:

```python
# CORRECT - use config module reference (dynamic)
import config
size = round(size / config.MIN_SOL_CONTRACT) * config.MIN_SOL_CONTRACT

# WRONG - static import (stale value)
from config import MIN_SOL_CONTRACT  # DON'T DO THIS
```

## Telegram Bot Context Fixes

The following were fixed to prevent false alerts when a position is open:

1. **system_health.py**: Checks Hyperliquid for open positions before showing "stale" alerts
2. **context_builder.py**: Shows "SYSTEM IS ACTIVELY TRADING" when position is open
3. **telegram_bot.py**: Hourly updates include live exchange data and unrealized PnL

## Running the System

```bash
# Start
nohup /Users/shamil/supequant/.venv/bin/python /Users/shamil/supequant/main.py > /Users/shamil/supequant/logs/nohup.out 2>&1 &

# Check logs
tail -f /Users/shamil/supequant/logs/nohup.out

# Dashboard
http://localhost:8080
```

## Safe Modifications

You MAY modify without permission:
- Dashboard UI (`dashboard/`)
- Documentation files
- Test files
- New monitoring/logging (read-only)
- Telegram commands that don't affect trading

## Before ANY Trading Logic Changes

1. **STOP** and ask user for permission
2. Explain what you want to change
3. Show the exact diff
4. Wait for explicit approval

## Why This Matters

Previous AI "improvements" caused:
- Spot trading mode -> Error 51008, all trades failed
- Kelly sizing -> Crushed returns
- Changed V4 boosts -> Destroyed edge
- Adaptive thresholds -> Lost $106

The 36% win rate with 3:1 reward-to-risk is intentional and profitable. Don't try to "fix" it.
