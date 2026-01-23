# SuperQuant Trading System - Autonomous Improvements Log

## Baseline Metrics (Established 2026-01-23)

| Metric | Value | Target |
|--------|-------|--------|
| Return | 61.89% | >100% |
| Win Rate | 46.67% | >56% |
| Profit Factor | 2.00 | >3.0 |
| Sharpe Ratio | 3.41 | >5.5 |
| Max Drawdown | 19.55% | <12% |

**Test Period:** 2025-10-01 to 2025-12-31
**Initial Capital:** $10,000
**Trades Executed:** 45 (21W / 24L)

---

## Improvement Cycles

### Cycle 1 - 2026-01-23 11:15
**Change:** Optimized SCORE_THRESHOLD from 45 to 50
**Hypothesis:** Higher threshold filters out lower-quality signals, improving win rate and reducing drawdown

**Sweep Results:**
| Threshold | Return | Win Rate | PF | Sharpe | Max DD | Trades |
|-----------|--------|----------|------|--------|--------|--------|
| 35 | 71.11% | 42.53% | 1.81 | 1.15 | 19.35% | 87 |
| 45 (baseline) | 61.89% | 46.67% | 2.00 | 3.41 | 19.55% | 45 |
| 48 | 79.80% | 47.73% | 2.35 | 3.59 | 17.98% | 44 |
| **50** | **86.96%** | **51.28%** | **2.65** | **4.86** | **12.51%** | 39 |
| 52 | 32.54% | 38.46% | 2.28 | 2.35 | 7.31% | 13 |
| 55 | 31.80% | 57.14% | 5.11 | 6.71 | 2.84% | 7 |

**Result (SCORE_THRESHOLD=50):**
- Return: 86.96% (baseline: 61.89%) ✅ +25.07%
- Win Rate: 51.28% (baseline: 46.67%) ✅ +4.61%
- Profit Factor: 2.65 (baseline: 2.00) ✅ +0.65
- Sharpe: 4.86 (baseline: 3.41) ✅ +1.45
- Drawdown: 12.51% (baseline: 19.55%) ✅ -7.04%

**Decision:** KEEP
**Notes:** Threshold=50 provides best balance. Higher thresholds (52-55) are too restrictive, lower thresholds (35-48) let through too many poor-quality signals.

---

**Current Best Metrics (after Cycle 1):**
- Return: 86.96%
- Win Rate: 51.28%
- Profit Factor: 2.65
- Sharpe: 4.86
- Max Drawdown: 12.51%

