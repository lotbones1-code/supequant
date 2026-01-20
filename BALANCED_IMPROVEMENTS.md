# Balanced Strategy Improvements

## Problem Analysis

**Current State:**
- Filters TOO strict → Only 1 signal in 30 days
- That 1 trade lost money (hit stop)
- MFE: 0.96% but stop hit at 0.56% → Stop too tight!

**Root Cause:**
- Overcorrected from "too many bad trades" to "too few trades"
- Need BALANCE: Quality + Quantity

## Changes Applied

### 1. Volume Filter (BALANCED)
- **Before:** 3.0x + highest volume only
- **After:** 2.5x + top 3 volumes
- **Why:** Allows more opportunities while maintaining quality

### 2. RSI Filter (BALANCED)
- **Before:** RSI >= 55 (longs), <= 45 (shorts) - TOO strict
- **After:** RSI >= 52 (longs), <= 48 (shorts)
- **Why:** Balanced momentum requirement

### 3. Trend Filter (BALANCED)
- **Before:** Require 0.3% EMA difference - TOO strict
- **After:** Require EMA alignment but allow 0.15% diff
- **Why:** More opportunities while maintaining trend direction

### 4. Stop Loss (BALANCED)
- **Before:** 1.2x/1.5x/2.0x ATR - Too tight (MFE 0.96% vs stop 0.56%)
- **After:** 1.3x/1.6x/2.2x ATR - Slightly wider
- **Why:** Prevent premature stop-outs while maintaining risk control

## Expected Results

- **More signals:** 3-5 trades (vs 1)
- **Better win rate:** 40-50%+ (vs 0%)
- **Profit factor:** >1.5 (vs 0.0)
- **Fewer premature stops:** Wider stops allow trades to breathe

## Test Command

```bash
python run_backtest.py --quick
```

## Next Steps

If still losing:
1. Analyze winning vs losing trades
2. Check entry timing (are we chasing?)
3. Consider multi-timeframe confirmation
4. Use Claude agent: `python fix_strategy.py` (if API key set)
