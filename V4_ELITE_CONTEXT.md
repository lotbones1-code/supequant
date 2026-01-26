# V4 Elite Wealth Engine - Technical Context

**Last Updated:** 2026-01-25
**Branch:** `elite-v4`
**Status:** Ready for live trading (small account optimized)

---

## QUICK START FOR NEXT CHAT

Tell the AI:
> "Read /Users/shamil/supequant/V4_ELITE_CONTEXT.md for full V4 system context, then continue working on the elite-v4 branch."

---

## CURRENT ACCOUNT STATUS

```
OKX API: Connected and working
Balance:
  - USDT: $23.50 (available for SOL trading)
  - XRP: 64.28 (~$120) - NOT being traded
  - SOL: 0.003 (~$0.33)
Total: ~$144

Trading Mode: LIVE TRADING ENABLED
Min Position: 0.1 SOL (~$12 notional, ~$2.45 margin at 5x)
```

---

## V4 SYSTEM ARCHITECTURE

### What's ENABLED (Working Well)

| Component | Config Key | Value | Purpose |
|-----------|------------|-------|---------|
| Strategy Boost | V4_STRATEGY_BOOST_ENABLED | True | 2.5x for breakout, 0.85x for MR, 0.3x for momentum |
| Score Sizing | V4_SCORE_SIZING_ENABLED | True | 75% size for score<=54, 115% for score>=60 |
| Early Exit | V4_EARLY_EXIT_ENABLED | True | Cut losers at 1.5% MAE in first 5 bars |
| Limit Orders | LIMIT_ORDER_ENTRY_ENABLED | True | 0.1% price improvement, 10s timeout |
| Funding Filter | FUNDING_RATE_FILTER_ENABLED | True | Skip extreme funding |

### What's DISABLED (Hurt Performance)

| Component | Why Disabled |
|-----------|--------------|
| V4_WINNER_PREDICTOR | ML model untrained, blocked trades at 8% probability |
| V4_DIRECTIONAL_BIAS | Shorts were actually profitable (28.6% WR, not 8%) |
| V4_KELLY_ENABLED | Hardcoded win rates were wrong, crushed returns |
| V4_REGIME_PREDICTION | Too conservative, reduced positions too much |
| V4_PYRAMID | 30/35/35 split hurt vs default 50/30/20 |
| V4_BREAKEVEN_AFTER_TP1 | Caused BE stop-outs |

---

## KEY CONFIG VALUES (config.py lines 793-870)

```python
# Master switch
V4_ENABLED = True

# Strategy Boost (WORKING)
V4_STRATEGY_BOOST_ENABLED = True
V4_BREAKOUT_BOOST = 2.5           # Breakout is best strategy
V4_MEAN_REVERSION_BOOST = 0.85    # Reduce MR slightly
V4_MOMENTUM_BOOST = 0.3           # Minimize momentum (negative PnL)

# Score Sizing (WORKING)
V4_SCORE_SIZING_ENABLED = True
V4_SCORE_LOW_MAX = 54             # score <= this: reduce size
V4_SCORE_HIGH_MIN = 60            # score >= this: boost
V4_SCORE_LOW_MULT = 0.75          # 75% size for low scores
V4_SCORE_HIGH_MULT = 1.15         # 115% size for high scores

# Early Exit (WORKING)
V4_EARLY_EXIT_ENABLED = True
V4_MAE_THRESHOLD_5BAR = 0.018     # 1.8% MAE = loser pattern
V4_MFE_THRESHOLD_8BAR = 0.002     # 0.2% MFE by bar 12 = no momentum

# Small Account (NEW)
MIN_POSITION_USDT = 3.0           # Minimum $3 margin
MIN_SOL_CONTRACT = 0.1            # OKX minimum contract size

# Realistic Backtest (NEW)
BACKTEST_COMMISSION = 0.0008      # 0.08% (taker fee)
BACKTEST_SLIPPAGE = 0.0005        # 0.05% slippage per trade
```

---

## V4 FILES

### New Files Created
- `backtesting/v4_early_exit.py` - MAE/MFE early exit logic
- `backtesting/v4_winner_predictor.py` - ML trade predictor (DISABLED)
- `backtesting/v4_directional_bias.py` - Long/short filter (DISABLED)
- `backtesting/v4_kelly_sizer.py` - Kelly position sizing (DISABLED)
- `backtesting/v4_regime_predictor.py` - Regime prediction (DISABLED)

### Modified Files
- `config.py` - V4 configuration section (lines 793-870)
- `backtesting/backtest_engine.py` - V4 integration, realistic slippage
- `risk/risk_manager.py` - Minimum position enforcement

---

## BACKTEST RESULTS

### Realistic Slippage (Oct-Dec 2025)
```
Return: 190%
Win Rate: 53.66%
Max Drawdown: 17.3%
Profit Factor: 3.40
Trades: 41
```

### Ideal (No Slippage) - For Reference Only
```
Return: 359%
Win Rate: 53.66%
Max Drawdown: 15.7%
Profit Factor: 4.48
```

### Live Trading Expectations
- Expect **50-70%** of backtest returns in live
- Realistic 3-month return: **100-130%**
- With $23.50 starting: **~$50-55** in 3 months

---

## EARLY EXIT THRESHOLDS (v4_early_exit.py)

Conservative thresholds to only catch clear losers:

```python
# MAE check (first 5 bars)
MAE_THRESHOLD_5BAR = 0.015  # 1.5% - losers avg 2.06%, winners 0.69%

# MFE check (bar 12)
MFE_THRESHOLD_12BAR = 0.002  # 0.2% - if no momentum, exit
MFE_CHECK_BAR = 12           # Check later than original bar 8

# MAE/MFE ratio check (after bar 10)
MAE_MFE_RATIO_THRESHOLD = 1.5  # MAE must be 1.5x MFE
MIN_MAE_FOR_RATIO_CHECK = 0.012  # 1.2% min MAE
MIN_BARS_FOR_RATIO_CHECK = 10    # Wait 10 bars before checking
```

---

## WHAT WORKS VS WHAT DOESN'T

### WORKS (Keep Enabled)
1. **Strategy Boost** - 2.5x breakout is the biggest edge
2. **Score Sizing** - Boost high quality, reduce marginal
3. **Early Exit** - Cuts losers before full stop (conservative)
4. **Limit Orders** - Saves 0.03% per trade in fees
5. **Funding Filter** - Avoids crowded trades

### DOESN'T WORK (Keep Disabled)
1. **Kelly Sizing** - Wrong win rate assumptions
2. **Directional Bias** - Shorts were profitable, not broken
3. **Winner Predictor** - Needs training data, blocks good trades
4. **Regime Prediction** - Too conservative for small accounts
5. **Pyramid/Breakeven** - Hurt returns vs simple 50/30/20 split

---

## HOW TO RUN

### Start Live Trading
```bash
cd /Users/shamil/supequant
source venv/bin/activate
python main.py
```

### Run Backtest
```bash
BACKTEST_MODE=true python run_backtest.py --start 2025-10-01 --end 2025-12-31 --name test
```

### Check Account
```bash
python -c "
from data_feed.okx_client import OKXClient
client = OKXClient()
print(client.get_account_balance())
"
```

---

## BRANCH STRUCTURE

```
main              - Production (don't touch)
elite-v2-aggressive - V3 working system (backup)
elite-v4          - V4 development (CURRENT)
```

**IMPORTANT:** V3 and V4 are separate. Don't merge V4 into main until proven profitable in live trading.

---

## NEXT STEPS TO IMPROVE

1. **Add More USDT** - Convert XRP to USDT for better sizing
2. **Paper Trade First** - Run for 1-2 weeks before real money
3. **Train Winner Predictor** - Collect live trade data, then enable ML
4. **Multi-Asset** - Add BTC-USDT-SWAP for more opportunities

---

## COMMITS ON elite-v4

```
01bce9e V4: Add realistic slippage + minimum position sizing
fa5a9fa Add backtest reports from optimization experiments
8670e90 Elite V2 Aggressive: 109.57% return
bc211d9 Final: Achieve 107.47% return
...
```

---

## CONTACT/NOTES

- OKX API Domain: us.okx.com
- Telegram: Configured and working
- System runs 24/7 with health monitoring
