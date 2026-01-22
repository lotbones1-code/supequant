# 🎯 System Identification Guide for Claude

**Purpose:** This document helps Claude AI identify and work with the correct live trading system.

---

## ✅ CURRENT LIVE SYSTEM IDENTIFIERS

### **Repository Information**
- **GitHub URL:** `https://github.com/lotbones1-code/supequant.git`
- **Branch:** `main`
- **Last Verified:** 2026-01-21

### **Key System Markers (How to Identify This System)**

#### 1. **Main Entry Point**
- **File:** `main.py`
- **Class:** `EliteQuantSystem`
- **Key Flag:** `USE_PRODUCTION_MANAGER = True` (line 71)
- **Production Manager:** Uses `ProductionOrderManager` from `execution/production_manager.py`

#### 2. **Dashboard Integration**
- **File:** `dashboard/app.py`
- **Port:** 8080 (configurable in `config.py`)
- **Status:** Fully integrated with Phase 1.5 analytics endpoints
- **Auto-start:** Starts automatically with `main.py` if `DASHBOARD_ENABLED = True`

#### 3. **Active Strategies (7 Total)**
All registered in `strategy/strategy_manager.py`:
1. ✅ Breakout Strategy (`breakout_strategy.py`)
2. ✅ Pullback Strategy (`pullback_strategy.py`)
3. ✅ Mean Reversion Strategy (`mean_reversion.py`)
4. ✅ Funding Arbitrage Strategy (`funding_arbitrage.py`)
5. ✅ Momentum Strategy (`momentum_strategy.py`)
6. ✅ Structure Strategy (`structure_strategy.py`) - **NEW**
7. ✅ Research/Checklist Strategy (`research_filters/checklist_filter.py`)

#### 4. **Active Filters (12+ Quality Filters)**
All registered in `filters/filter_manager.py`:
- ✅ Time of Day Filter
- ✅ BTC/SOL Correlation Filter (Enhanced)
- ✅ Market Regime Filter
- ✅ Funding Rate Filter
- ✅ Whale Filter (On-chain tracking)
- ✅ Liquidation Filter
- ✅ Open Interest Filter
- ✅ Sentiment Filter (Fear & Greed Index)
- ✅ Confidence Engine V2 (Dynamic position sizing)
- ✅ And more...

#### 5. **Key Configuration Flags**
Check `config.py` for these active features:
```python
USE_PRODUCTION_MANAGER = True  # In main.py
DASHBOARD_ENABLED = True
TRADE_JOURNAL_ENABLED = True
CONFIDENCE_ENGINE_V2_ENABLED = True
STRUCTURE_STRATEGY_ENABLED = True
API_TIMEOUT_SECONDS = 30  # Fixed timeout issue
```

#### 6. **Execution System**
- **File:** `execution/production_manager.py`
- **Status:** ✅ DO NOT MODIFY (working perfectly)
- **Features:**
  - Virtual TP/SL monitoring
  - Position tracking
  - Time-based exits for funding arbitrage
  - Background monitoring thread

#### 7. **Analytics & Monitoring (Phase 1.5)**
All modules in `utils/`:
- ✅ `system_monitor.py` - System health tracking
- ✅ `filter_scorer.py` - Filter effectiveness
- ✅ `risk_dashboard.py` - Risk exposure
- ✅ `trade_quality.py` - Trade quality analysis
- ✅ All integrated with dashboard API endpoints

---

## 🔍 HOW TO VERIFY YOU'RE ON THE CORRECT SYSTEM

### **Quick Verification Commands:**

```bash
# 1. Check main.py has ProductionOrderManager
grep -n "USE_PRODUCTION_MANAGER = True" main.py
# Should show: 71:USE_PRODUCTION_MANAGER = True

# 2. Check dashboard exists and is configured
grep -n "DASHBOARD_ENABLED = True" config.py
# Should show: 23:DASHBOARD_ENABLED = True

# 3. Check ProductionOrderManager exists
ls -la execution/production_manager.py
# Should exist

# 4. Check Structure Strategy exists (latest addition)
ls -la strategy/structure_strategy.py
# Should exist

# 5. Check API timeout is fixed
grep -n "API_TIMEOUT_SECONDS" config.py
# Should show: 459:API_TIMEOUT_SECONDS = 30
```

### **File Structure Checklist:**
```
supequant/
├── main.py                          ✅ Main entry (EliteQuantSystem)
├── config.py                        ✅ Configuration
├── dashboard/
│   ├── app.py                       ✅ Flask dashboard
│   └── templates/index.html         ✅ Dashboard UI
├── execution/
│   └── production_manager.py       ✅ Production order manager (DO NOT MODIFY)
├── strategy/
│   ├── strategy_manager.py          ✅ Strategy coordinator
│   ├── structure_strategy.py        ✅ Structure strategy (NEW)
│   └── [6 other strategies]         ✅ All active
├── filters/
│   └── filter_manager.py            ✅ Filter coordinator
├── utils/
│   ├── system_monitor.py            ✅ Phase 1.5 analytics
│   ├── filter_scorer.py             ✅ Phase 1.5 analytics
│   ├── risk_dashboard.py           ✅ Phase 1.5 analytics
│   └── trade_quality.py             ✅ Phase 1.5 analytics
└── IMPLEMENTATION_ROADMAP.md        ✅ Feature documentation
```

---

## 🚨 CRITICAL FILES - DO NOT MODIFY

These files are working perfectly and should NOT be changed:
1. **`execution/production_manager.py`** - Core execution logic
2. **`main.py` trade execution flow** - Only add hooks, never change core logic
3. **`risk/risk_manager.py`** - Core risk logic
4. **`data_feed/okx_client.py`** - API client (except timeout config)

---

## 📋 INTEGRATION PATTERN FOR NEW FEATURES

When adding new features, follow this pattern:

```
New Feature → New File → Register in Manager → Add Config Flag → Test
```

### Example:
1. Create new filter: `filters/my_new_filter.py`
2. Register in: `filters/filter_manager.py` → `quality_filters` dict
3. Add config: `config.py` → `MY_NEW_FILTER_ENABLED = True`
4. Export: `filters/__init__.py` → Add to `__all__`

---

## 🔗 GITHUB REPOSITORY

**Repository:** `https://github.com/lotbones1-code/supequant.git`
**Branch:** `main`
**Status:** ✅ All latest changes committed and pushed

### To Clone/Update:
```bash
# Clone the repository
git clone https://github.com/lotbones1-code/supequant.git
cd supequant

# Pull latest changes
git pull origin main

# Verify you're on the correct system
grep "USE_PRODUCTION_MANAGER = True" main.py
```

---

## 📊 DASHBOARD ACCESS

- **URL:** `http://localhost:8080`
- **Auto-start:** Starts with `main.py` if `DASHBOARD_ENABLED = True`
- **Endpoints:**
  - `/api/status` - Bot status
  - `/api/live` - Live OKX data
  - `/api/positions` - Open positions
  - `/api/trade-history` - Recent trades
  - `/api/system-health` - System health
  - `/api/filter-scores` - Filter effectiveness
  - `/api/risk-exposure` - Risk metrics
  - `/api/trade-quality` - Trade quality analysis

---

## ✅ SYSTEM STATUS CHECKLIST

Before making changes, verify:
- [ ] `USE_PRODUCTION_MANAGER = True` in `main.py`
- [ ] `execution/production_manager.py` exists
- [ ] `dashboard/app.py` exists
- [ ] `strategy/structure_strategy.py` exists (confirms latest version)
- [ ] `config.py` has `API_TIMEOUT_SECONDS = 30` (timeout fix applied)
- [ ] Git status shows clean working tree
- [ ] Repository is `https://github.com/lotbones1-code/supequant.git`

---

## 🎯 FOR CLAUDE AI

**When starting a new session, tell Claude:**

> "I'm working on the Elite Quant Trading System. Please verify you're on the correct system by checking:
> 1. `main.py` has `USE_PRODUCTION_MANAGER = True`
> 2. `execution/production_manager.py` exists
> 3. `dashboard/app.py` exists
> 4. Repository is `https://github.com/lotbones1-code/supequant.git`
> 
> If these match, we're on the correct live system. Reference `SYSTEM_IDENTIFICATION.md` for full details."

---

**Last Updated:** 2026-01-21
**System Version:** 1.6 (Latest Live System)
