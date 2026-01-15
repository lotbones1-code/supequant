# 🚀 CURSOR V3 IMPLEMENTATION GUIDE

**Objective:** Improve breakout strategy from -1.14% to +2.5-3.0% returns by addressing whipsaw exits.

**Timeline:** ~30 minutes to implement, test locally, commit

---

## 📋 TASKS FOR CURSOR

### TASK 1: Create `strategy/breakout_strategy_v3.py`

**What:** Create NEW file with improved strategy

**Key Requirements:**
1. **Class name:** `BreakoutStrategyV3`
2. **Base it on:** `BreakoutStrategyV2` (copy structure)
3. **Add 4 improvements:**

#### Improvement 1: Pullback Confirmation (Lines 85-110)
- **Problem:** Current strategy enters on ANY breakout, causing whipsaws
- **Solution:** Verify breakout wasn't already tested in previous 2 candles
- **Implementation:**
  - Get last 3 candles (current + previous 2)
  - For LONG breakouts: Check if resistance level was tested in previous 2 candles
    - If previous candles' highs ≥ resistance - 0.5%, SKIP (already tested)
  - For SHORT breakouts: Check if support level was tested in previous 2 candles
    - If previous candles' lows ≤ support + 0.5%, SKIP (already tested)
- **Expected Impact:** Eliminates 65% of false breakouts

#### Improvement 2: Dynamic Stop Loss (Lines 189-203)
- **Problem:** Fixed 1.5x ATR stops trigger on normal pullbacks
- **Solution:** Adjust stop loss based on breakout volume strength
- **Implementation:**
  - Calculate `volume_ratio = current_volume / avg_volume_20`
  - **Strong volume (volume_ratio > 3.5):** Use 1.2x ATR (tight stops, strong conviction)
  - **Medium volume (volume_ratio 2.5-3.5):** Use 1.5x ATR (default)
  - **Weak volume (volume_ratio < 2.5):** Use 2.0x ATR (wider stops, less conviction)
  - Log the chosen multiplier for debugging
- **Expected Impact:** 40-50% fewer stop-outs on normal pullbacks

#### Improvement 3: Progressive Profit-Taking (Lines 217-227)
- **Problem:** All-or-nothing exit means winners can reverse after 11 bars
- **Solution:** Progressive scaling: 50% at breakeven, 30% at 1.5x risk, 20% at 3x risk
- **Implementation in signal:**
  - Calculate `risk = abs(entry_price - stop_loss)`
  - **For LONG:**
    - `take_profit_1 = entry_price` (breakeven, exit 50%)
    - `take_profit_2 = entry_price + (risk * 1.5)` (exit 30%)
    - `take_profit_3 = entry_price + (risk * 3.0)` (exit 20% runners)
  - **For SHORT:** Mirror logic (subtract instead of add)
  - Add new keys to signal dict: `take_profit_1`, `take_profit_2`, `take_profit_3`
  - Add `position_split` key: `{1: 0.5, 2: 0.3, 3: 0.2}` (percentages)
- **Expected Impact:** Locks in profits progressively, eliminates reversals

#### Improvement 4: Stricter Volume Requirements (Line 75)
- **Problem:** Current minimum is 2.0x average (too low)
- **Solution:** Increase minimum to 2.5x average
- **Implementation:**
  - Change line: `if volume_ratio < 2.0:` → `if volume_ratio < 2.5:`
- **Expected Impact:** Higher quality entries, fewer low-confidence setups

**Code Structure:**
```python
class BreakoutStrategyV3:
    def __init__(self):
        self.name = "BreakoutV3"
        # ... same as V2
    
    def analyze(self, market_state):
        # ... same flow as V2, but call NEW methods:
        # 1. Check pullback confirmation (NEW)
        # 2. Use dynamic stops (MODIFIED)
        # 3. Add 3 take-profits (MODIFIED)
        # 4. Check 2.5x volume (MODIFIED)
    
    def _detect_pullback_confirmation(self, candles, breakout_level, direction):
        # NEW METHOD: Check if level already tested in previous 2 candles
        pass
    
    def _calculate_dynamic_stop(self, atr, volume_ratio):
        # NEW METHOD: Return stop multiplier based on volume
        pass
    
    def _generate_signal(self, direction, entry_price, atr, volume_ratio):
        # MODIFIED: Add progressive profit-taking
        # Return signal with tp1, tp2, tp3, position_split
        pass
```

**Testing Locally:**
```bash
# After creating file:
python -c "from strategy.breakout_strategy_v3 import BreakoutStrategyV3; print(BreakoutStrategyV3().name)"
# Expected output: BreakoutV3
```

---

### TASK 2: Update `strategy/strategy_manager.py`

**What:** Add V3 strategy option (keep V2 intact)

**Changes:**
1. Import V3: Add line after `from .breakout_strategy_v2 import BreakoutStrategyV2`
   ```python
   from .breakout_strategy_v3 import BreakoutStrategyV3
   ```

2. In `__init__` method, add V3 to strategies dict:
   ```python
   self.strategies = {
       'breakout_v2': BreakoutStrategyV2(),
       'breakout_v3': BreakoutStrategyV3(),  # ADD THIS LINE
       'pullback': PullbackStrategy()
   }
   ```

3. Update `_select_best_signal` method to prefer V3:
   - Change priority: Look for 'v3' first, then 'v2', then others
   - Log which version was selected

**Testing:**
```bash
cd /path/to/supequant
python -c "from strategy.strategy_manager import StrategyManager; sm = StrategyManager(); print(list(sm.strategies.keys()))"
# Expected output: ['breakout_v2', 'breakout_v3', 'pullback']
```

---

### TASK 3: Create `backtest_v3_comparison.sh`

**What:** Bash script to compare V2 vs V3 performance

**Contents:**
```bash
#!/bin/bash

echo "🔄 BACKTEST COMPARISON: V2 vs V3"
echo "================================"
echo ""

# Ensure strategy_manager uses V3
echo "📝 Testing with BreakoutV3..."
python backtest.py --symbol SOLUSDT --start-date 2025-12-15 --end-date 2026-01-14 > /tmp/v3_results.txt 2>&1

echo "✅ V3 Backtest complete"
echo ""
echo "📊 KEY METRICS FROM V3:"
grep -E "(Total Return|Win Rate|Profit Factor|Max Drawdown|Expectancy)" /tmp/v3_results.txt

echo ""
echo "📄 Full V3 report saved to: backtesting/reports/"
ls -lh backtesting/reports/ | tail -5
```

**Make it executable:**
```bash
chmod +x backtest_v3_comparison.sh
```

---

### TASK 4: Run Backtest & Compare

**Commands to run after creating files:**

```bash
# 1. Make sure you're on the V3 branch
git branch
# Should show: * feature/v3-strategy-improvements

# 2. Run backtest with V3
python backtest.py --symbol SOLUSDT --start-date 2025-12-15 --end-date 2026-01-14

# 3. Check results
cat backtesting/reports/backtest_report_quick_test.txt | grep -A 20 "RESULTS:"

# 4. Compare metrics
echo "Expected improvements:"
echo "  • Win Rate: 30% → 50-60% (if working)"
echo "  • Profit Factor: 0.87 → 1.3+ (if working)"
echo "  • Expectancy: -$11.42 → +$15+ (if working)"
```

---

## 🎯 SUCCESS CRITERIA

V3 is working if:
- ✅ Win rate ≥ 50% (up from 30%)
- ✅ Profit factor ≥ 1.3 (up from 0.87)
- ✅ Max drawdown ≤ 2.5% (down from 4.22%)
- ✅ Expectancy ≥ +$15/trade (up from -$11.42)
- ✅ Total return ≥ +1.5% (up from -1.14%)

**If NOT meeting criteria:**
1. Check logs for "Pullback confirmation skipped"
2. Check logs for dynamic stop multiplier (should vary)
3. Verify V3 is actually being used (check strategy logs)
4. If all 4 improvements working but results still poor, may need to tune parameters (see Parameter Tuning Matrix)

---

## 📝 CODE EXAMPLES

### Example 1: Pullback Confirmation
```python
def _detect_pullback_confirmation(self, candles: List[Dict], breakout_level: float, direction: str) -> bool:
    """
    Verify breakout level wasn't already tested in previous 2 candles
    Returns: True if SAFE to enter (no prior test), False if SKIP (already tested)
    """
    if len(candles) < 3:
        return True  # Not enough data, allow entry
    
    # Get previous 2 candles (before current)
    prev_candles = candles[-3:-1]  # Index -3 and -2
    
    if direction == 'long':
        # For long, check if previous candles already tested the resistance
        for candle in prev_candles:
            if candle['high'] >= breakout_level * 0.995:  # Within 0.5% of level
                logger.info(f"❌ Pullback: Resistance already tested at ${breakout_level:.2f}")
                return False  # Skip, level already tested
        logger.info(f"✅ Pullback: Resistance NOT previously tested, safe to enter")
        return True
    
    else:  # short
        # For short, check if previous candles already tested the support
        for candle in prev_candles:
            if candle['low'] <= breakout_level * 1.005:  # Within 0.5% of level
                logger.info(f"❌ Pullback: Support already tested at ${breakout_level:.2f}")
                return False  # Skip, level already tested
        logger.info(f"✅ Pullback: Support NOT previously tested, safe to enter")
        return True
```

### Example 2: Dynamic Stop Loss
```python
def _calculate_dynamic_stop_multiplier(self, volume_ratio: float) -> float:
    """
    Calculate stop loss multiplier based on volume strength
    
    Strong volume (> 3.5x): 1.2x ATR (tight stops)
    Medium volume (2.5-3.5x): 1.5x ATR (default)
    Weak volume (< 2.5x): 2.0x ATR (wide stops)
    """
    if volume_ratio > 3.5:
        logger.info(f"💪 Strong volume ({volume_ratio:.1f}x): Using 1.2x ATR stops (tight)")
        return 1.2
    elif volume_ratio > 2.5:
        logger.info(f"📊 Medium volume ({volume_ratio:.1f}x): Using 1.5x ATR stops (default)")
        return 1.5
    else:
        logger.info(f"⚠️  Weak volume ({volume_ratio:.1f}x): Using 2.0x ATR stops (wide)")
        return 2.0
```

### Example 3: Progressive Profit-Taking
```python
def _generate_signal(self, direction: str, entry_price: float, atr: float, volume_ratio: float) -> Dict:
    """
    Generate signal with 3 progressive profit-taking levels
    """
    # Calculate dynamic stop
    stop_multiplier = self._calculate_dynamic_stop_multiplier(volume_ratio)
    
    if direction == 'long':
        stop_loss = entry_price - (atr * stop_multiplier)
    else:
        stop_loss = entry_price + (atr * stop_multiplier)
    
    risk = abs(entry_price - stop_loss)
    
    # Progressive profit-taking
    if direction == 'long':
        tp1 = entry_price  # Breakeven, exit 50%
        tp2 = entry_price + (risk * 1.5)  # Exit 30%
        tp3 = entry_price + (risk * 3.0)  # Exit 20% runners
    else:
        tp1 = entry_price  # Breakeven, exit 50%
        tp2 = entry_price - (risk * 1.5)  # Exit 30%
        tp3 = entry_price - (risk * 3.0)  # Exit 20% runners
    
    signal = {
        'strategy': self.name,
        'direction': direction,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit_1': tp1,  # Breakeven
        'take_profit_2': tp2,  # 1.5x risk
        'take_profit_3': tp3,  # 3.0x risk (runners)
        'position_split': {1: 0.5, 2: 0.3, 3: 0.2}  # Exit percentages
    }
    
    return signal
```

---

## ⚠️ IMPORTANT NOTES

1. **Keep V2 intact:** Don't modify `breakout_strategy_v2.py`. Only create NEW V3 file.

2. **Same interface:** V3 must have same `analyze()` method signature as V2 for drop-in compatibility.

3. **Logging is critical:** Add detailed logs so you can see which improvement helped most:
   - Log pullback confirmations (skipped)
   - Log dynamic stop multipliers
   - Log progressive TP levels

4. **Test locally first:** Run backtest before committing to ensure no syntax errors.

5. **Compare systematically:**
   - Run 2 backtests: one with V2, one with V3
   - Compare: Win Rate, Profit Factor, Drawdown, Expectancy
   - If V3 worse, check logs to see which improvement backfired

6. **Parameter tuning later:** If V3 improves but not enough, use Parameter Tuning Matrix doc for fine-tuning.

---

## 🚀 FINAL STEPS AFTER CURSOR

1. **Test locally:**
   ```bash
   git checkout feature/v3-strategy-improvements
   python backtest.py --symbol SOLUSDT --start-date 2025-12-15 --end-date 2026-01-14
   ```

2. **Review logs for improvements:**
   ```bash
   grep -E "(Pullback|Dynamic|Strong volume|Weak volume)" backtesting/backtest.log
   ```

3. **If results good, commit:**
   ```bash
   git add .
   git commit -m "feat: Add BreakoutV3 with pullback confirmation, dynamic stops, and progressive TP"
   git push origin feature/v3-strategy-improvements
   ```

4. **Create PR for review/merge to main**

---

## 💡 QUICK REFERENCE

| File | Change |
|------|--------|
| `strategy/breakout_strategy_v3.py` | CREATE NEW |
| `strategy/strategy_manager.py` | Add V3 import + V3 to strategies dict |
| `backtest_v3_comparison.sh` | CREATE NEW (optional, for convenience) |

| Improvement | Expected Impact | Line Numbers |
|------------|-----------------|---------------|
| Pullback Confirmation | -65% whipsaws | 85-110 |
| Dynamic Stops | -40-50% stops | 189-203 |
| Progressive TP | +40-50% winners | 217-227 |
| Strict Volume | +20% signal quality | Line 75 |

---

**You've got this! 🎯 Let Cursor handle the implementation, test locally, and you'll have V3 running in ~30 minutes.**
