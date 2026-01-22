# Verified V1 Configuration (87.89% Return)

**DO NOT MODIFY THIS FILE** - This documents the exact configuration that achieved the verified results.

---

## Verified Results

| Metric | Value |
|--------|-------|
| **Total Return** | **87.89%** |
| Total P&L | $8,251.83 |
| Final Capital | $18,789.20 |
| Initial Capital | $10,000.00 |
| Period | Oct 15, 2025 → Jan 20, 2026 (86 days) |
| Total Trades | 43 |
| Wins | 23 |
| Losses | 20 |
| Win Rate | 53.49% |
| Max Drawdown | 13.64% |
| Profit Factor | 2.78 |
| Sharpe Ratio | 4.88 |

**Report:** `backtesting/reports/backtest_report_verify_v1_prediction.txt`

---

## Exact V1 Configuration Settings

Copy these EXACTLY to replicate the 87.89% backtest:

```python
# =============================================================================
# V1 PREDICTION SYSTEM SETTINGS (VERIFIED 87.89% RETURN)
# =============================================================================

# Core V1 Settings
BACKTEST_PREDICTION_GUIDED = True
BACKTEST_PREDICTION_HORIZONS = [30, 90, 365]  # Days ahead (1m, 3m, 1y)

# Direction Filter
BACKTEST_PRED_DIRECTION_FILTER = True
BACKTEST_PRED_BLOCK_ON_CONFLICT = False
BACKTEST_PRED_CONFLICT_SIZE_REDUCTION = 0.5

# Confidence Sizing
BACKTEST_PRED_CONFIDENCE_SIZING = True
BACKTEST_PRED_MIN_CONFIDENCE = 0.3
BACKTEST_PRED_MAX_MULTIPLIER = 1.8
BACKTEST_PRED_MIN_MULTIPLIER = 0.5

# Market Timing
BACKTEST_PRED_MARKET_TIMING = True
BACKTEST_PRED_MIN_CONF_TO_TRADE = 0.35

# Trend Bias
BACKTEST_PRED_TREND_BIAS = True
BACKTEST_PRED_TREND_THRESHOLD = 0.05
BACKTEST_PRED_BIAS_BOOST = 1.3
BACKTEST_PRED_ANTI_BIAS = 0.7

# V2 System (DISABLED for V1)
BACKTEST_ELITE_PREDICTION_V2 = False
```

---

## How to Replicate

1. Ensure all settings above are in `config.py`
2. Run backtest with exact period:
   ```bash
   python run_backtest.py --start 2025-10-15 --end 2026-01-20 --name verify_v1
   ```
3. Expected result: ~87-88% return, 43 trades

---

## What NOT to Change

1. **BACKTEST_PRED_MARKET_TIMING** - Keep TRUE
2. **BACKTEST_PRED_MIN_CONF_TO_TRADE** - Keep 0.35
3. **BACKTEST_ELITE_PREDICTION_V2** - Keep FALSE
4. **Period** - Oct 15, 2025 to Jan 20, 2026

---

## Live System

The live system (`main.py`) uses these same V1 settings for production trading.

**Live System Status:** ✅ Configured and verified
