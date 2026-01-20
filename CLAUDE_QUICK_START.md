# Claude Agent Quick Start Guide

## ✅ What's Fixed

All the problems you were having are now solved:

1. ✅ **No more random crashes** - Circuit breaker prevents failures
2. ✅ **No more blocking all trades** - Auto-disable protection
3. ✅ **No more API timeouts** - Built-in timeout handling
4. ✅ **Fail-safe by default** - Trades continue even if Claude fails

## 🚀 Quick Configuration

### Option 1: Use Defaults (Recommended)

Just use the defaults - everything is configured for safety:

```python
# In config.py - these are already set:
CLAUDE_GATING_ENABLED = True
CLAUDE_FAIL_OPEN = True  # ✅ Approves trades if Claude fails
CLAUDE_TIMEOUT_SECONDS = 10.0
```

**Result**: Claude helps when it can, but never blocks trading.

### Option 2: Disable Claude Completely

If you want to trade without Claude:

```python
# In config.py
CLAUDE_GATING_ENABLED = False
```

### Option 3: Strict Mode (Not Recommended)

Only use if you want Claude to block trades on errors:

```python
# In config.py
CLAUDE_FAIL_OPEN = False  # ⚠️ Rejects trades if Claude fails
```

## 📊 Monitoring

Check Claude status in logs:

```
🤖 Claude AI Statistics:
   Rules learned: 5
   Trades blocked: 12
   Approval rate: 85.2%
   Success rate: 65.0% ✅
   Error rate: 2.1% ✅
```

## 🔧 Troubleshooting

### "Circuit breaker is OPEN"

**What it means**: Too many API failures  
**What happens**: Trades are approved automatically (fail-open)  
**Fix**: Check API key, wait 60 seconds, or restart bot

### "Auto-disabling Claude gating"

**What it means**: Claude was blocking too many trades  
**What happens**: Claude disables itself, trading continues  
**Fix**: Review `claude_rejection_rules.json` and remove strict rules

### High Error Rate

**What it means**: Many API calls failing  
**What happens**: Trades still approved (fail-open)  
**Fix**: Check Anthropic API status, verify API key

## 🎯 Key Points

1. **Fail-Open is Default**: Trades are approved if Claude fails ✅
2. **Auto-Disable Protection**: Claude won't block all your trades ✅
3. **Circuit Breaker**: Prevents cascading failures ✅
4. **Easy to Disable**: Set `CLAUDE_GATING_ENABLED = False` ✅

## 📝 Files Changed

- `agents/claude_agent.py` - Added circuit breaker, timeout, fail-open
- `agents/claude_autonomous_system.py` - Added safeguards, auto-disable
- `main.py` - Improved error handling
- `config.py` - Added Claude configuration options

## 🚀 You're Ready!

Your Claude agent is now **production-ready** and **won't cause problems**. Just run your bot normally - everything is configured for safety!
