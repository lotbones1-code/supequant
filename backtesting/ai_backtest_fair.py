"""
Fair AI Backtesting System

This module allows backtesting with AI (Claude/ChatGPT) assistance
while preventing the AI from "cheating" by using future knowledge.

Key principles:
1. AI only sees data UP TO the current candle (no future data)
2. Dates are anonymized (AI doesn't know it's looking at historical data)
3. AI makes decisions based purely on technical patterns
4. Results are compared against non-AI baseline

Modes:
- VETO_ONLY: AI only blocks extreme risk trades (confidence < 30%)
- STANDARD: AI approves/rejects based on its judgment
- HYBRID: Uses both Claude AND OpenAI, requires consensus
"""

import logging
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
import config

logger = logging.getLogger(__name__)

# Try to import AI clients
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not available")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai package not available")


class FairAIBacktester:
    """
    Backtests trading signals with AI assistance, ensuring no future data leakage.
    
    The AI sees:
    - Recent candles (anonymized timestamps)
    - Technical indicators
    - The proposed trade setup
    - Optional: Recent news/sentiment context
    
    The AI does NOT see:
    - Actual dates (prevents knowing historical outcomes)
    - Future candles
    - Any hint that this is a backtest
    """
    
    def __init__(self, use_claude: bool = True, use_openai: bool = False, 
                 mode: str = "VETO_ONLY", veto_threshold: float = 0.30):
        """
        Initialize the fair AI backtester.
        
        Args:
            use_claude: Use Claude for evaluation
            use_openai: Use OpenAI for evaluation
            mode: "VETO_ONLY" (only block extreme risk), "STANDARD" (normal), "HYBRID" (both AIs)
            veto_threshold: In VETO_ONLY mode, only reject if confidence < this (default 30%)
        """
        self.use_claude = use_claude and ANTHROPIC_AVAILABLE
        self.use_openai = use_openai and OPENAI_AVAILABLE
        self.mode = mode
        self.veto_threshold = veto_threshold
        
        # Initialize clients
        self.claude_client = None
        self.openai_client = None
        
        if self.use_claude:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                self.claude_client = anthropic.Anthropic(api_key=api_key)
                logger.info("✅ FairAIBacktester: Claude client initialized")
            else:
                self.use_claude = False
                logger.warning("⚠️ ANTHROPIC_API_KEY not set")
        
        if self.use_openai:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.openai_client = openai.OpenAI(api_key=api_key)
                logger.info("✅ FairAIBacktester: OpenAI client initialized")
            else:
                self.use_openai = False
                logger.warning("⚠️ OPENAI_API_KEY not set")
        
        # Stats
        self.stats = {
            'signals_evaluated': 0,
            'ai_approved': 0,
            'ai_rejected': 0,
            'ai_vetoed': 0,  # Specifically for VETO_ONLY mode
            'ai_errors': 0,
            'claude_calls': 0,
            'openai_calls': 0,
            'hybrid_agreements': 0,
            'hybrid_disagreements': 0
        }
        
        logger.info(f"📊 FairAI Mode: {mode} (veto threshold: {veto_threshold:.0%})")
    
    def evaluate_signal(
        self,
        candles: List[Dict],
        signal: Dict,
        indicators: Dict,
        news_context: Optional[str] = None
    ) -> Tuple[bool, float, str]:
        """
        Ask AI to evaluate a trading signal WITHOUT revealing future data.
        
        Args:
            candles: Historical candles UP TO current bar (anonymized)
            signal: Proposed trade (direction, entry, stop, target)
            indicators: Current indicator values (RSI, BB, trend, etc.)
            news_context: Optional recent news/sentiment (anonymized)
        
        Returns:
            (approved: bool, confidence: float, reasoning: str)
        """
        self.stats['signals_evaluated'] += 1
        
        # Anonymize the data (remove actual timestamps)
        anonymized_candles = self._anonymize_candles(candles[-50:])  # Last 50 candles
        
        # Build prompt that doesn't reveal this is a backtest
        prompt = self._build_evaluation_prompt(anonymized_candles, signal, indicators, news_context)
        
        # Get AI opinion based on mode
        if self.mode == "HYBRID" and self.use_claude and self.use_openai:
            return self._hybrid_evaluation(prompt)
        elif self.use_claude:
            approved, confidence, reasoning = self._ask_claude(prompt)
        elif self.use_openai:
            approved, confidence, reasoning = self._ask_openai(prompt)
        else:
            logger.warning("No AI client available, approving by default")
            return True, 0.5, "No AI available"
        
        # Apply VETO_ONLY mode logic
        if self.mode == "VETO_ONLY":
            if not approved and confidence < self.veto_threshold:
                # Only veto if AI is confident this is a BAD trade
                self.stats['ai_vetoed'] += 1
                return False, confidence, f"[VETOED] {reasoning}"
            else:
                # Approve even if AI said reject, unless confidence is very low
                if not approved:
                    reasoning = f"[AI cautious but allowed] {reasoning}"
                return True, confidence, reasoning
        
        return approved, confidence, reasoning
    
    def _hybrid_evaluation(self, prompt: str) -> Tuple[bool, float, str]:
        """Get opinions from both AIs and combine them."""
        claude_approved, claude_conf, claude_reason = self._ask_claude(prompt)
        openai_approved, openai_conf, openai_reason = self._ask_openai(prompt)
        
        # Track agreement
        if claude_approved == openai_approved:
            self.stats['hybrid_agreements'] += 1
        else:
            self.stats['hybrid_disagreements'] += 1
        
        # Combine: require both to approve, or average confidence > 50%
        avg_confidence = (claude_conf + openai_conf) / 2
        
        if claude_approved and openai_approved:
            return True, avg_confidence, f"[Both agree] Claude: {claude_reason} | GPT: {openai_reason}"
        elif not claude_approved and not openai_approved:
            return False, avg_confidence, f"[Both reject] Claude: {claude_reason} | GPT: {openai_reason}"
        else:
            # Disagreement - approve only if average confidence is high
            if avg_confidence >= 0.5:
                return True, avg_confidence, f"[Split decision, approved] Claude: {claude_reason} | GPT: {openai_reason}"
            else:
                return False, avg_confidence, f"[Split decision, rejected] Claude: {claude_reason} | GPT: {openai_reason}"
    
    def _anonymize_candles(self, candles: List[Dict]) -> List[Dict]:
        """
        Remove timestamps and use relative bar numbers instead.
        This prevents AI from knowing what date/time it is.
        """
        anonymized = []
        for i, candle in enumerate(candles):
            anonymized.append({
                'bar': i - len(candles) + 1,  # -49, -48, ..., -1, 0 (current)
                'open': round(candle['open'], 2),
                'high': round(candle['high'], 2),
                'low': round(candle['low'], 2),
                'close': round(candle['close'], 2),
                'volume': int(candle.get('volume', 0))
            })
        return anonymized
    
    def _build_evaluation_prompt(
        self,
        candles: List[Dict],
        signal: Dict,
        indicators: Dict,
        news_context: Optional[str] = None
    ) -> str:
        """Build a prompt that asks for trade evaluation without revealing backtest context."""
        
        current_price = candles[-1]['close']
        direction = signal.get('direction', 'long')
        entry = signal.get('entry_price', current_price)
        stop = signal.get('stop_price', 0)
        target = signal.get('target_price', 0)
        
        # Calculate R:R safely
        stop_dist = abs(entry - stop) if stop > 0 else 1
        target_dist = abs(target - entry) if target > 0 else stop_dist * 2
        rr_ratio = target_dist / stop_dist if stop_dist > 0 else 2.0
        
        # Format recent candles as a simple table
        recent_candles = candles[-10:]  # Last 10 bars
        candle_table = "Bar | Open | High | Low | Close | Volume\n"
        candle_table += "----|------|------|-----|-------|-------\n"
        for c in recent_candles:
            candle_table += f"{c['bar']:3d} | {c['open']:.2f} | {c['high']:.2f} | {c['low']:.2f} | {c['close']:.2f} | {c['volume']:,}\n"
        
        # News/sentiment section if provided
        news_section = ""
        if news_context:
            news_section = f"""
## Recent Market Context
{news_context}
"""
        
        prompt = f"""You are an experienced crypto trader evaluating a mean reversion setup.
This strategy BUYS oversold dips and SELLS overbought rallies - it works best in RANGING markets.

Your job: Identify ONLY the highest-risk setups that should be VETOED.
Be permissive - most mean reversion setups in ranging markets work. Only flag:
1. Clear trending markets (strong momentum against the trade)
2. Obvious traps/fakeouts (abnormal wicks, volume patterns)
3. Major support/resistance being broken

## Current Market Data (15-minute candles)
{candle_table}
{news_section}
## Technical Indicators
- RSI(14): {indicators.get('rsi', 'N/A')}
- Trend Direction: {indicators.get('trend_direction', 'N/A')}
- Trend Strength: {indicators.get('trend_strength', 'N/A')}
- Bollinger Band Position: {indicators.get('bb_position', 'N/A')}

## Proposed Trade
- Strategy: Mean Reversion (fade extreme RSI)
- Direction: {direction.upper()}
- Entry: ${entry:.2f}
- Stop Loss: ${stop:.2f}
- Target: ${target:.2f}
- Risk/Reward: {rr_ratio:.1f}:1

## Your Assessment
Rate this setup 0-100:
- 0-30: HIGH RISK - Clear traps, strong trend against, or breakdown/breakout
- 31-60: MODERATE - Some concerns but tradeable
- 61-100: GOOD SETUP - Classic mean reversion opportunity

ONLY recommend REJECT for scores 0-30 (clear danger signs).
Scores 31+ should be APPROVED - the strategy filters handle normal risk.

Respond in this exact format:
CONFIDENCE: [0-100]
DECISION: [APPROVE/REJECT]
REASONING: [2-3 sentences explaining your decision]
"""
        return prompt
    
    def _ask_claude(self, prompt: str) -> Tuple[bool, float, str]:
        """Query Claude for trade evaluation."""
        try:
            self.stats['claude_calls'] += 1
            
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            text = response.content[0].text
            return self._parse_response(text)
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            self.stats['ai_errors'] += 1
            return True, 0.5, f"API error: {str(e)[:50]}"
    
    def _ask_openai(self, prompt: str) -> Tuple[bool, float, str]:
        """Query OpenAI for trade evaluation."""
        try:
            self.stats['openai_calls'] += 1
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            text = response.choices[0].message.content
            return self._parse_response(text)
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            self.stats['ai_errors'] += 1
            return True, 0.5, f"API error: {str(e)[:50]}"
    
    def _parse_response(self, text: str) -> Tuple[bool, float, str]:
        """Parse AI response to extract decision."""
        try:
            lines = text.strip().split('\n')
            
            confidence = 50
            approved = True
            reasoning = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith('CONFIDENCE:'):
                    try:
                        confidence = int(line.split(':')[1].strip().split()[0])
                    except:
                        pass
                elif line.startswith('DECISION:'):
                    decision = line.split(':')[1].strip().upper()
                    approved = 'APPROVE' in decision
                elif line.startswith('REASONING:'):
                    reasoning = line.split(':', 1)[1].strip()
            
            if approved:
                self.stats['ai_approved'] += 1
            else:
                self.stats['ai_rejected'] += 1
            
            return approved, confidence / 100.0, reasoning
            
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            return True, 0.5, "Parse error"
    
    def get_stats(self) -> Dict:
        """Get AI evaluation statistics."""
        total = self.stats['ai_approved'] + self.stats['ai_rejected']
        return {
            **self.stats,
            'approval_rate': self.stats['ai_approved'] / total if total > 0 else 0,
            'veto_rate': self.stats['ai_vetoed'] / self.stats['signals_evaluated'] if self.stats['signals_evaluated'] > 0 else 0,
            'error_rate': self.stats['ai_errors'] / self.stats['signals_evaluated'] if self.stats['signals_evaluated'] > 0 else 0
        }


# Convenience function for backtest integration
def create_fair_ai_evaluator(
    use_claude: bool = True, 
    use_openai: bool = False,
    mode: str = None,
    veto_threshold: float = None
) -> Optional[FairAIBacktester]:
    """
    Create a fair AI evaluator for backtest integration.
    
    Args:
        use_claude: Use Claude (default True)
        use_openai: Use OpenAI (default False, set True for hybrid)
        mode: "VETO_ONLY", "STANDARD", or "HYBRID" (default from config)
        veto_threshold: For VETO_ONLY mode (default from config)
    """
    try:
        # Get defaults from config
        if mode is None:
            mode = getattr(config, 'BACKTEST_AI_MODE', 'VETO_ONLY')
        if veto_threshold is None:
            veto_threshold = getattr(config, 'BACKTEST_AI_VETO_THRESHOLD', 0.30)
        
        evaluator = FairAIBacktester(
            use_claude=use_claude, 
            use_openai=use_openai,
            mode=mode,
            veto_threshold=veto_threshold
        )
        
        if evaluator.use_claude or evaluator.use_openai:
            return evaluator
        else:
            logger.warning("No AI client available for fair backtest")
            return None
    except Exception as e:
        logger.error(f"Failed to create AI evaluator: {e}")
        return None
