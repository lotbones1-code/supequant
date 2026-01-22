# 🚀 Quick Start Guide for Claude AI

**Repository:** `https://github.com/lotbones1-code/supequant.git`  
**Branch:** `main`  
**Status:** ✅ Latest live system committed and pushed

---

## ✅ VERIFICATION (Run First)

Before making any changes, verify you're on the correct system:

```bash
# Check these 3 things:
1. grep "USE_PRODUCTION_MANAGER = True" main.py
2. ls execution/production_manager.py
3. ls dashboard/app.py

# If all exist → You're on the correct system ✅
```

---

## 📋 KEY SYSTEM MARKERS

- **Main Entry:** `main.py` → `EliteQuantSystem` class
- **Production Manager:** `USE_PRODUCTION_MANAGER = True` (line 71)
- **Dashboard:** `dashboard/app.py` (port 8080)
- **7 Strategies:** All in `strategy/` directory
- **12+ Filters:** All in `filters/` directory
- **Analytics:** Phase 1.5 modules in `utils/`

---

## 🚨 DO NOT MODIFY

1. `execution/production_manager.py` - Working perfectly
2. `main.py` trade execution flow - Only add hooks
3. `risk/risk_manager.py` - Core risk logic
4. `data_feed/okx_client.py` - API client (except config)

---

## 📖 FULL DOCUMENTATION

- **System Details:** See `SYSTEM_IDENTIFICATION.md`
- **Features:** See `IMPLEMENTATION_ROADMAP.md`
- **Architecture:** See `README.md`

---

## 🔧 RECENT FIXES

- ✅ API timeout increased to 30 seconds (was 10s)
- ✅ System identification guide added
- ✅ All changes committed and pushed to GitHub

---

**For detailed system information, see `SYSTEM_IDENTIFICATION.md`**
