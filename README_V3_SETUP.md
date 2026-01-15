# 🚀 QUICK START: V3 WITH CURSOR

## What's Ready For You

✅ **Branch created:** `feature/v3-strategy-improvements`
✅ **Implementation guide:** `CURSOR_IMPLEMENTATION.md` (detailed, 12KB)
✅ **Quick prompt:** `CURSOR_PROMPT.txt` (copy-paste into Cursor)
✅ **Code examples:** Both files include copy-paste code snippets

---

## 🚀 SETUP IN 3 STEPS

### Step 1: Checkout the Branch
```bash
git checkout feature/v3-strategy-improvements
```

### Step 2: Open in Cursor
```bash
cursor .
```

### Step 3: Open CURSOR_PROMPT.txt and Copy Content
1. In Cursor file tree, click `CURSOR_PROMPT.txt`
2. Select ALL (Cmd+A)
3. Copy (Cmd+C)
4. Open Cursor AI chat (Cmd+K)
5. Paste the prompt (Cmd+V)
6. Hit Enter

Cursor will now implement V3 automatically.

---

## 📊 What Cursor Will Do

**File 1: `strategy/breakout_strategy_v3.py`** (NEW)
- Create new strategy class inheriting V2 logic
- Add 4 improvements:
  1. ✅ Pullback confirmation (skip already-tested levels)
  2. ✅ Dynamic stops (adjust based on volume)
  3. ✅ Progressive profit-taking (3 TP levels instead of 2)
  4. ✅ Stricter volume (2.5x minimum)

**File 2: `strategy/strategy_manager.py`** (UPDATE)
- Import V3 strategy
- Add V3 to strategies dict
- Make V3 preferred choice

**File 3: `backtest_v3_comparison.sh`** (NEW, optional)
- Bash script for easy backtest running

---

## ⚡ After Cursor Finishes

### Test It Works
```bash
# Verify V3 imports correctly
python -c "from strategy.breakout_strategy_v3 import BreakoutStrategyV3; print('✅ V3 imported')"
```

### Run Backtest
```bash
python backtest.py --symbol SOLUSDT --start-date 2025-12-15 --end-date 2026-01-14
```

### Check Results
```bash
# Show summary
grep -A 20 "BACKTEST SUMMARY" backtesting/reports/backtest_report_quick_test.txt

# Expected improvements:
# Win Rate: 30% → 50%+
# Profit Factor: 0.87 → 1.3+
# Max Drawdown: 4.22% → 2.5% or less
# Total Return: -1.14% → +1.5%+
```

### Verify Improvements Working
```bash
# Check logs for each improvement
grep -i "pullback\|dynamic\|strong volume\|strict" backtesting/backtest.log
```

### If Results Look Good, Commit
```bash
git add -A
git commit -m "feat: Add BreakoutV3 with pullback confirmation, dynamic stops, progressive TP, strict volume"
git push origin feature/v3-strategy-improvements
```

---

## 💡 Key Metrics to Watch

| Metric | Current | Target | If V3 Working |
|--------|---------|--------|---------------|
| **Win Rate** | 30% | 50%+ | Yes if ≥ 50% |
| **Profit Factor** | 0.87 | 1.3+ | Yes if ≥ 1.3 |
| **Max Drawdown** | 4.22% | 2.5% | Yes if ≤ 2.5% |
| **Expectancy** | -$11.42 | +$15+ | Yes if ≥ +$15 |
| **Total Return** | -1.14% | +1.5%+ | Yes if ≥ +1.5% |

**Success = At least 4 of 5 metrics improved**

---

## 💀 Troubleshooting

### "ImportError: No module named strategy.breakout_strategy_v3"
- File wasn't created correctly
- Run: `ls strategy/breakout_strategy_v3.py` to verify it exists
- If not, re-run Cursor prompt

### Backtest runs but no improvement
- Check logs: `grep -i pullback backtesting/backtest.log`
- Should see "Pullback confirmation" messages
- If not logging, the improvement isn't being called
- Check strategy_manager.py to ensure V3 is selected (not V2)

### Performance got worse
- This shouldn't happen with current parameters
- Check logs for which improvement is causing issues
- Most likely: dynamic stops too aggressive
- Solution: Fine-tune parameters (see CURSOR_IMPLEMENTATION.md for details)

### Unsure if V3 is running
- Add manual check in backtest.py:
  ```python
  signal = strategy.analyze(market_state)
  if signal:
      print(f"Strategy used: {signal.get('strategy')}")
  ```
- Should print "Strategy used: BreakoutV3"

---

## 📚 Documentation Files

You have 3 docs:

1. **CURSOR_PROMPT.txt** (THIS ONE)
   - Copy-paste into Cursor
   - Quick, direct instructions
   - ~4KB

2. **CURSOR_IMPLEMENTATION.md** (DETAILED)
   - Complete reference guide
   - All code examples
   - Parameter tuning matrix
   - Troubleshooting checklist
   - ~12KB

3. **This file: README_V3_SETUP.md**
   - Quick start checklist
   - Post-Cursor steps
   - Key metrics to watch
   - Basic troubleshooting

---

## 🚀 READY?

1. ✅ Branch ready: `feature/v3-strategy-improvements`
2. ✅ Cursor prompt ready: `CURSOR_PROMPT.txt`
3. ✅ Detailed guide ready: `CURSOR_IMPLEMENTATION.md`

**Next:** Open Cursor, paste CURSOR_PROMPT.txt, watch it build your V3 strategy!

---

**Estimated time:**
- Cursor implementation: 10-15 minutes
- Testing: 5-10 minutes
- Total: ~20 minutes to working V3

**Expected outcome:**
- Win rate ↑ from 30% → 50-60%
- Profit factor ↑ from 0.87 → 1.3+
- Total return ↑ from -1.14% → +2-3%

Let's go! 🚀
