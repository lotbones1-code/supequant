# Getting Your Bot to Actually Trade

## The Problem
Your bot has been running for a week with **ZERO trades**. This is because:

1. **Strategy isn't generating signals** - OR
2. **Signals are being blocked by filters** - Most likely
3. **Bot is crashing** and you don't know why

---

## Solution: 3-Step Fix

### Step 1: Run Diagnostic (Find the Blocker)

```bash
# In your supequant folder:
python3 diagnose_no_trades.py
```

**What this does:**
- Runs for 10 cycles (5 minutes)
- Shows every signal generated
- Shows EXACTLY which filters reject it
- Gives you a report at the end

**Expected output:**
```
🔍 SIGNAL DETECTED: BREAKOUT - BUY
   Entry: $195.23
   Stop Loss: $190.45
   TP1: $201.34
   TP2: $210.15

❌ SIGNAL REJECTED BY FILTERS
   Failed filters: BTC-SOL Correlation, Macro Driver Filter, AI Confidence

📊 DIAGNOSTIC REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signals generated: 3
Signals rejected: 3
Rejection rate: 100%

🔍 Filter Failures:
   BTC-SOL Correlation: 3 times
   Macro Driver Filter: 2 times
   AI Confidence: 1 time
```

**What to do with the report:**
The filters blocking most trades are the ones to relax.

---

### Step 2: Understand Why (Check Market Conditions)

**Most common blockers:**

| Filter | Why It Blocks | How to Fix |
|--------|---------------|----------|
| **BTC-SOL Correlation** | SOL/BTC not moving together | Lower `BTC_SOL_MIN_CORRELATION` from 0.7 → 0.5 |
| **Macro Driver** | Market conditions unclear | Lower `MACRO_DRIVER_MIN_SCORE` from 40 → 30 |
| **AI Confidence** | Model hasn't seen this pattern | Lower `AI_CONFIDENCE_THRESHOLD` from 70 → 50 |
| **Trend Strength** | Trend not strong enough | Lower `HTF_TREND_MIN_STRENGTH` from 0.6 → 0.4 |
| **Pattern Failure** | Fakeout/trap detected | Lower `BULL_TRAP_THRESHOLD` from 0.015 → 0.025 |

---

### Step 3: Gradually Relax Filters (Test & Verify)

**IMPORTANT: Never make huge changes. Do this step by step.**

#### 3a. Edit config.py

```bash
# Open config.py
nano config.py
```

Find your main blocker from the diagnostic report and adjust ONE parameter at a time:

**Example: BTC-SOL Correlation is blocking all trades**

Find this line:
```python
BTC_SOL_MIN_CORRELATION = 0.7  # Minimum correlation score (0-1)
```

Change to:
```python
BTC_SOL_MIN_CORRELATION = 0.5  # Relaxed from 0.7
```

Save (Ctrl+O, Enter, Ctrl+X)

#### 3b. Test the change (Run diagnostic again)

```bash
python3 diagnose_no_trades.py
```

**Expected improvement:**
- Fewer rejections from that filter
- Might see some trades execute

If trades are NOW executing and profitable:
✅ **STOP HERE - Keep this setting**

If still no trades:
- Go back and relax NEXT main blocker
- Repeat Step 3a → 3b

---

## Step 4: Keep Bot Running 24/7

Once you have trades flowing, use the supervisor to keep it running:

```bash
python3 supervisor.py
```

**What this does:**
- Runs the main bot
- If bot crashes, automatically restarts it
- Logs everything to `logs/supervisor.log`
- Prevents bot from being down for hours unnoticed

**To stop the supervisor:**
```bash
Ctrl+C
```

---

## Backtest to Verify (IMPORTANT!)

Before going live with money, backtest to make sure trades are profitable:

```bash
python3 run_backtest.py
```

This simulates what would have happened in the past. If backtest shows:
- ✅ Positive returns = Strategy might work
- ❌ Negative returns = Strategy needs work

---

## Safe Filter Adjustment Cheat Sheet

**Use these values to gradually loosen filters:**

```python
# CONSERVATIVE (Current - too strict)
BTC_SOL_MIN_CORRELATION = 0.7
MACRO_DRIVER_MIN_SCORE = 40
AI_CONFIDENCE_THRESHOLD = 70
HTF_TREND_MIN_STRENGTH = 0.6

# MODERATE (First attempt - should get trades)
BTC_SOL_MIN_CORRELATION = 0.5
MACRO_DRIVER_MIN_SCORE = 30
AI_CONFIDENCE_THRESHOLD = 50
HTF_TREND_MIN_STRENGTH = 0.4

# AGGRESSIVE (Last resort - trades often but riskier)
BTC_SOL_MIN_CORRELATION = 0.3
MACRO_DRIVER_MIN_SCORE = 20
AI_CONFIDENCE_THRESHOLD = 30
HTF_TREND_MIN_STRENGTH = 0.2
```

**Remember:** Looser filters = more trades but more risk of losses.

---

## Troubleshooting

### "Still no trades after relaxing filters"

The **strategy itself** might not be generating signals. Check:

```bash
python3 diagnose_strategies.py
```

This shows if breakout/pullback strategies are even seeing setups.

### "Bot keeps crashing"

Run supervisor instead:
```bash
python3 supervisor.py
```

It will restart bot automatically. Check:
```bash
tail -f logs/supervisor.log
```

### "Backtest shows losses"

Your strategy parameters need tuning:
- Breakout threshold too low?
- Pullback entry too aggressive?
- Stop loss too tight?

Adjust in `config.py` and re-backtest.

---

## Timeline to Profitability

1. **Today**: Run diagnostic → identify blockers
2. **Today**: Relax filters gradually → get first trades
3. **Tomorrow**: Monitor dashboard → see real P&L
4. **This week**: Run backtest → verify strategy works
5. **When ready**: Switch to live mode with SMALL position sizes

---

## Files You Just Got

| File | Purpose |
|------|----------|
| `diagnose_no_trades.py` | Shows why signals are rejected |
| `supervisor.py` | Keeps bot running 24/7 |
| `diagnose_strategies.py` | Shows if strategies generate signals |

**These don't change your core strategy - they just help you see and fix the problem.**

---

## Remember

✅ Start VERY gradually
✅ One filter change at a time
✅ Test after each change
✅ Backtest before going live
✅ Start with TINY position sizes

🚀 Let's make this work!
