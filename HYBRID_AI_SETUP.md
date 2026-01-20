# Hybrid AI Setup Guide

## Overview

The trading system now supports **Hybrid AI** that combines Claude and ChatGPT for better trading decisions. This dual-model approach provides:

- ✅ **Consensus-based decisions** - Both models must agree (reduces false positives/negatives)
- ✅ **Better analysis** - Two perspectives on the same data
- ✅ **Fallback protection** - If one model fails, the other can still operate
- ✅ **Improved pattern learning** - Better insights from losing trades

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `anthropic` (for Claude)
- `openai` (for ChatGPT)

### 2. Set Environment Variables

Add to your `.env` file:

```bash
# Claude API Key (required)
ANTHROPIC_API_KEY=your_claude_api_key_here

# ChatGPT API Key (required for hybrid mode)
OPENAI_API_KEY=your_openai_api_key_here

# Optional: Configure hybrid mode
HYBRID_AI_ENABLED=True
HYBRID_AI_MODE=consensus  # consensus, weighted, or fallback
CHATGPT_MODEL=gpt-4o  # gpt-4o, gpt-4-turbo, or gpt-4
```

### 3. Configuration Options

In `config.py`, you can configure:

```python
# Hybrid AI Settings
HYBRID_AI_ENABLED = True  # Enable hybrid mode
HYBRID_AI_MODE = 'consensus'  # consensus, weighted, fallback
HYBRID_CLAUDE_WEIGHT = 0.5  # Weight for Claude (0-1)
HYBRID_CHATGPT_WEIGHT = 0.5  # Weight for ChatGPT (0-1)
HYBRID_REQUIRE_CONSENSUS = True  # Require agreement in consensus mode

# ChatGPT Settings
CHATGPT_ENABLED = True
CHATGPT_MODEL = 'gpt-4o'  # Best model: gpt-4o
CHATGPT_FAIL_OPEN = True  # Approve trades if ChatGPT fails
```

## Modes

### Consensus Mode (Recommended)
Both models must agree on the recommendation. Most reliable but may reject more trades.

```python
HYBRID_AI_MODE=consensus
```

### Weighted Mode
Combines recommendations based on weights. More flexible.

```python
HYBRID_AI_MODE=weighted
HYBRID_CLAUDE_WEIGHT=0.6  # Trust Claude more
HYBRID_CHATGPT_WEIGHT=0.4
```

### Fallback Mode
Uses Claude as primary, falls back to ChatGPT if Claude fails.

```python
HYBRID_AI_MODE=fallback
```

## Usage

The system automatically uses hybrid AI if:
1. `HYBRID_AI_ENABLED=True` in config
2. Both API keys are set
3. Both agents initialize successfully

If hybrid fails, it automatically falls back to Claude-only mode.

## Benefits

### 1. Better Trade Analysis
- Dual-model analysis provides more comprehensive insights
- Consensus reduces false positives
- Different perspectives catch edge cases

### 2. Improved Pattern Learning
- Both models analyze losing trades
- Better rejection rules learned
- More accurate pattern recognition

### 3. Reliability
- Fallback if one model fails
- Circuit breaker protection
- Fail-open behavior (approves trades if AI fails)

## Monitoring

Check hybrid AI status in logs:

```
✅ Hybrid AI (Claude + ChatGPT) initialized (mode: consensus, fail_open=True, timeout=10.0s)
```

View statistics:

```python
from agents import HybridAIAgent

# Get stats
stats = hybrid_agent.get_stats()
print(f"Consensus Rate: {stats['consensus_rate']*100:.1f}%")
print(f"Agreements: {stats['consensus_agreements']}")
print(f"Disagreements: {stats['consensus_disagreements']}")
```

## Troubleshooting

### Issue: Hybrid AI not initializing

**Solution:**
1. Check both API keys are set: `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`
2. Verify API keys are valid
3. Check logs for specific error messages
4. System will fallback to Claude-only if hybrid fails

### Issue: Too many trades rejected

**Solution:**
1. Try `fallback` mode instead of `consensus`
2. Adjust `HYBRID_REQUIRE_CONSENSUS=False`
3. Check individual model recommendations in logs

### Issue: High API costs

**Solution:**
1. Use `fallback` mode (only calls ChatGPT when needed)
2. Adjust `CHATGPT_MODEL` to cheaper model (gpt-4-turbo)
3. Monitor token usage in logs

## Example Output

```
🔍 Analyzing losing trade TRADE_001 with Hybrid AI...
✅ Hybrid analysis complete (consensus: True)

HYBRID AI ANALYSIS (Claude + ChatGPT)

Claude Analysis:
The trade failed due to low volume confirmation...

ChatGPT Analysis:
The setup lacked sufficient trend strength...

Consensus Status: ✅ AGREEMENT
Claude Recommendation: WAIT
ChatGPT Recommendation: WAIT
```

## Advanced Usage

### Direct Hybrid Agent Usage

```python
from agents import HybridAIAgent

# Initialize
hybrid = HybridAIAgent(
    claude_api_key="...",
    chatgpt_api_key="...",
    mode="consensus"
)

# Analyze setup
result = hybrid.analyze_setup(
    market_state=market_data,
    signal=trade_signal
)

# Check consensus
if result['consensus']:
    print("Both models agree!")
```

### Using Individual Agents

```python
from agents import ClaudeAgent, ChatGPTAgent

# Claude only
claude = ClaudeAgent()

# ChatGPT only
chatgpt = ChatGPTAgent(model="gpt-4o")

# Use independently
claude_result = claude.analyze_setup(market_state)
chatgpt_result = chatgpt.analyze_setup(market_state)
```

## Performance

- **Consensus Mode**: ~2x API calls (both models), highest accuracy
- **Weighted Mode**: ~2x API calls, balanced decisions
- **Fallback Mode**: ~1-2x API calls (ChatGPT only when needed), cost-efficient

## Best Practices

1. **Start with Consensus Mode** - Best accuracy
2. **Monitor Consensus Rate** - Should be >70% for good alignment
3. **Use GPT-4o** - Best ChatGPT model for trading analysis
4. **Enable Fail-Open** - Prevents blocking all trades if AI fails
5. **Monitor Token Usage** - Track costs in logs

## Support

For issues or questions:
1. Check logs for error messages
2. Verify API keys and configuration
3. System automatically falls back to Claude-only if hybrid fails
