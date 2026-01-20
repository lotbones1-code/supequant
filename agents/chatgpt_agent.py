"""
ChatGPT AI Agent
OpenAI GPT-4/GPT-4o agent for trading analysis and decision-making
Complements Claude agent with dual-model consensus
"""

import os
import time
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import json
from enum import Enum

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("openai package not installed. Install with: pip install openai")

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class ChatGPTAgent:
    """
    ChatGPT/GPT-4 agent for trading bot analysis and debugging
    
    Capabilities:
    - Debug why signals aren't generating
    - Analyze market conditions and suggest trade direction
    - Explain filter rejections and recommend threshold adjustments
    - Analyze backtest results and suggest improvements
    - Provide consensus with Claude for better decisions
    
    Features:
    - Circuit breaker pattern to prevent cascading failures
    - Timeout protection
    - Fail-open behavior (returns safe defaults on errors)
    - Rate limiting
    - Token usage tracking
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o", 
                 verbose: bool = False, max_retries: int = 3, timeout_seconds: float = 10.0,
                 circuit_breaker_failure_threshold: int = 5,
                 circuit_breaker_recovery_timeout: int = 60):
        """
        Initialize ChatGPT agent
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: OpenAI model to use (gpt-4o, gpt-4-turbo, gpt-4, etc.)
            verbose: Enable verbose logging
            max_retries: Maximum retry attempts for API calls
            timeout_seconds: Request timeout in seconds
            circuit_breaker_failure_threshold: Failures before opening circuit
            circuit_breaker_recovery_timeout: Seconds before trying half-open
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package required. Install with: pip install openai")
        
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.model = model
        self.verbose = verbose
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        
        self.client = OpenAI(api_key=self.api_key, timeout=timeout_seconds)
        
        # Token usage tracking
        self.token_usage = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_requests': 0,
            'failed_requests': 0,
            'circuit_breaker_trips': 0
        }
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms between requests
        
        # Circuit breaker
        self.circuit_breaker_state = CircuitBreakerState.CLOSED
        self.circuit_breaker_failures = 0
        self.circuit_breaker_failure_threshold = circuit_breaker_failure_threshold
        self.circuit_breaker_recovery_timeout = circuit_breaker_recovery_timeout
        self.circuit_breaker_opened_at = None
        
        logger.info(f"✅ ChatGPTAgent initialized (model: {self.model}, timeout: {timeout_seconds}s)")
    
    def _rate_limit(self):
        """Enforce rate limiting"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows request"""
        if self.circuit_breaker_state == CircuitBreakerState.CLOSED:
            return True
        
        if self.circuit_breaker_state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if self.circuit_breaker_opened_at:
                elapsed = (datetime.now() - self.circuit_breaker_opened_at).total_seconds()
                if elapsed >= self.circuit_breaker_recovery_timeout:
                    logger.info("🔄 Circuit breaker: Moving to HALF_OPEN state")
                    self.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
                    return True
            return False
        
        # HALF_OPEN - allow one request to test
        return True
    
    def _record_success(self):
        """Record successful request"""
        if self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            logger.info("✅ Circuit breaker: Service recovered, moving to CLOSED")
            self.circuit_breaker_state = CircuitBreakerState.CLOSED
            self.circuit_breaker_failures = 0
            self.circuit_breaker_opened_at = None
        else:
            self.circuit_breaker_failures = 0
    
    def _record_failure(self):
        """Record failed request"""
        self.circuit_breaker_failures += 1
        self.token_usage['failed_requests'] += 1
        
        if self.circuit_breaker_failures >= self.circuit_breaker_failure_threshold:
            if self.circuit_breaker_state != CircuitBreakerState.OPEN:
                logger.warning(f"🚨 Circuit breaker: OPENING after {self.circuit_breaker_failures} failures")
                self.circuit_breaker_state = CircuitBreakerState.OPEN
                self.circuit_breaker_opened_at = datetime.now()
                self.token_usage['circuit_breaker_trips'] += 1
    
    def _call_chatgpt(self, messages: List[Dict], system: str = "", max_tokens: int = 4096, 
                     fail_open: bool = True) -> Dict:
        """
        Call ChatGPT API with retry logic, circuit breaker, and timeout protection
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system: System prompt (will be added as system message)
            max_tokens: Maximum tokens in response
            fail_open: If True, return safe default on failure instead of raising
            
        Returns:
            Response dict with 'content' and usage stats, or safe default if fail_open=True
        """
        # Check circuit breaker
        if not self._check_circuit_breaker():
            logger.warning("🚨 Circuit breaker OPEN - request blocked")
            if fail_open:
                return {
                    'content': "Circuit breaker is open - service temporarily unavailable",
                    'usage': {'input_tokens': 0, 'output_tokens': 0},
                    'circuit_breaker_blocked': True
                }
            raise Exception("Circuit breaker is OPEN")
        
        self._rate_limit()
        
        # Prepare messages with system prompt
        api_messages = []
        if system:
            api_messages.append({'role': 'system', 'content': system})
        api_messages.extend(messages)
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    max_tokens=max_tokens,
                    temperature=0.7  # Slightly creative for trading analysis
                )
                
                # Track token usage
                usage = response.usage
                self.token_usage['input_tokens'] += usage.prompt_tokens
                self.token_usage['output_tokens'] += usage.completion_tokens
                self.token_usage['total_requests'] += 1
                
                # Record success for circuit breaker
                self._record_success()
                
                if self.verbose:
                    logger.info(f"ChatGPT API: {usage.prompt_tokens} input, {usage.completion_tokens} output tokens")
                
                # Extract text content
                content = response.choices[0].message.content if response.choices else ""
                
                return {
                    'content': content,
                    'usage': {
                        'input_tokens': usage.prompt_tokens,
                        'output_tokens': usage.completion_tokens
                    },
                    'circuit_breaker_blocked': False
                }
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"ChatGPT API error (attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"ChatGPT API failed after {self.max_retries} attempts: {e}")
                    self._record_failure()
                    
                    if fail_open:
                        logger.warning("⚠️  ChatGPT API failed - returning safe default (fail-open)")
                        return {
                            'content': f"ChatGPT API unavailable: {str(e)[:100]}",
                            'usage': {'input_tokens': 0, 'output_tokens': 0},
                            'error': str(e),
                            'circuit_breaker_blocked': False
                        }
                    raise
        
        if fail_open:
            return {
                'content': "ChatGPT API request failed after all retries",
                'usage': {'input_tokens': 0, 'output_tokens': 0},
                'circuit_breaker_blocked': False
            }
        raise Exception("Failed to call ChatGPT API")
    
    def analyze_setup(self, market_state: Dict, signal: Optional[Dict] = None,
                     filter_results: Optional[Dict] = None) -> Dict:
        """
        Analyze a trading setup and provide recommendation
        
        Args:
            market_state: Current market state
            signal: Optional signal dict (if one was generated)
            filter_results: Optional filter results (if signal was rejected)
            
        Returns:
            Dict with trade recommendation and reasoning
        """
        system_prompt = """You are an expert crypto trader analyzing trading setups.

Provide clear, actionable trade recommendations with risk assessment.
Consider: market conditions, trend strength, volatility, volume, and risk/reward.
Be concise and specific with your recommendations."""
        
        context = self._build_market_context(market_state)
        
        if signal:
            signal_info = f"""
Signal Generated:
- Direction: {signal.get('direction', 'unknown')}
- Entry: ${signal.get('entry_price', 0):.2f}
- Stop Loss: ${signal.get('stop_loss', 0):.2f}
- Take Profit 1: ${signal.get('take_profit_1', 0):.2f}
- Strategy: {signal.get('strategy', 'unknown')}
"""
        else:
            signal_info = "No signal generated"
        
        if filter_results:
            filter_info = f"""
Filter Results:
- Passed: {filter_results.get('overall_pass', False)}
- Failed Filters: {', '.join(filter_results.get('failed_filters', []))}
"""
        else:
            filter_info = "No filter results available"
        
        prompt = f"""Analyze this trading setup and provide a recommendation.

Market State:
{context}

{signal_info}

{filter_info}

Provide:
1. Trade recommendation (LONG/SHORT/WAIT)
2. Confidence level (1-10)
3. Key factors supporting your recommendation
4. Risk assessment
5. Suggested position size (if trading)"""
        
        messages = [{'role': 'user', 'content': prompt}]
        
        response = self._call_chatgpt(messages, system=system_prompt)
        
        result = {
            'recommendation': response['content'],
            'timestamp': datetime.now().isoformat(),
            'usage': response['usage']
        }
        
        logger.info(f"📊 ChatGPT setup analysis complete ({response['usage']['input_tokens']} tokens)")
        return result
    
    def debug_signals(self, market_state: Dict, strategy: str = "breakout", 
                     btc_market_state: Optional[Dict] = None) -> Dict:
        """
        Debug why signals aren't generating
        
        Args:
            market_state: Current market state from MarketDataFeed
            strategy: Strategy name ('breakout' or 'pullback')
            btc_market_state: Optional BTC market state for correlation
            
        Returns:
            Dict with analysis and recommendations
        """
        system_prompt = """You are an expert quantitative trading analyst helping debug a crypto trading bot.

The bot trades SOL-USDT perpetual futures using breakout and pullback strategies. It has multiple filters that must all pass before a trade executes.

Your task: Analyze why signals aren't generating and provide specific, actionable recommendations.

Be concise, technical, and focus on specific threshold values that need adjustment."""
        
        context = self._build_market_context(market_state, btc_market_state)
        
        prompt = f"""Analyze why the {strategy} strategy is not generating signals.

Current Market State:
{context}

Strategy Requirements:
- Breakout: ATR compression (< 1.5x average), consolidation (< 5% range), volume (≥ 0.8x average), breakout (0.3% above/below)
- Pullback: Strong trend, Fibonacci retracement, trend resumption, volume confirmation

Provide:
1. Which conditions are failing
2. Current values vs required thresholds
3. Specific threshold adjustments needed
4. Reasoning for each recommendation"""
        
        messages = [{'role': 'user', 'content': prompt}]
        
        response = self._call_chatgpt(messages, system=system_prompt)
        
        result = {
            'analysis': response['content'],
            'timestamp': datetime.now().isoformat(),
            'strategy': strategy,
            'usage': response['usage']
        }
        
        logger.info(f"🔍 ChatGPT signal debug analysis complete ({response['usage']['input_tokens']} tokens)")
        return result
    
    def explain_filter_rejection(self, filter_name: str, filter_result: Dict,
                                market_state: Dict) -> Dict:
        """
        Explain why a filter rejected a signal and recommend threshold adjustments
        
        Args:
            filter_name: Name of the filter that rejected
            filter_result: Filter result dict with 'reason' and details
            market_state: Current market state
            
        Returns:
            Dict with explanation and recommendations
        """
        system_prompt = """You are an expert at tuning trading filters.

Explain why filters reject signals and provide specific threshold adjustments.
Focus on finding the balance between signal quality and frequency."""
        
        context = self._build_market_context(market_state)
        
        prompt = f"""The {filter_name} filter rejected a signal.

Filter Result:
{json.dumps(filter_result, indent=2)}

Market State:
{context}

Provide:
1. Why this filter rejected (explain the logic)
2. Current threshold value (if available)
3. Recommended threshold adjustment
4. Expected impact (more/fewer signals)
5. Risk of relaxing this filter"""
        
        messages = [{'role': 'user', 'content': prompt}]
        
        response = self._call_chatgpt(messages, system=system_prompt)
        
        result = {
            'explanation': response['content'],
            'filter_name': filter_name,
            'timestamp': datetime.now().isoformat(),
            'usage': response['usage']
        }
        
        logger.info(f"🔍 ChatGPT filter rejection explanation complete ({response['usage']['input_tokens']} tokens)")
        return result
    
    def analyze_backtest_results(self, backtest_results: Dict) -> Dict:
        """
        Analyze backtest results and suggest improvements
        
        Args:
            backtest_results: Backtest results dict from BacktestEngine
            
        Returns:
            Dict with analysis and improvement suggestions
        """
        system_prompt = """You are an expert quantitative analyst reviewing backtest results.

Identify weaknesses, suggest improvements, and provide specific parameter adjustments.
Focus on: win rate, profit factor, drawdown, and trade frequency."""
        
        results_summary = self._format_backtest_results(backtest_results)
        
        prompt = f"""Analyze these backtest results and suggest improvements.

Backtest Results:
{results_summary}

Provide:
1. Overall assessment (good/poor/needs work)
2. Key strengths
3. Key weaknesses
4. Specific parameter adjustments needed
5. Expected impact of changes
6. Risk considerations"""
        
        messages = [{'role': 'user', 'content': prompt}]
        
        response = self._call_chatgpt(messages, system=system_prompt)
        
        result = {
            'analysis': response['content'],
            'timestamp': datetime.now().isoformat(),
            'usage': response['usage']
        }
        
        logger.info(f"📈 ChatGPT backtest analysis complete ({response['usage']['input_tokens']} tokens)")
        return result
    
    def _build_market_context(self, market_state: Dict, 
                             btc_market_state: Optional[Dict] = None) -> str:
        """Build human-readable market context for ChatGPT"""
        context_parts = []
        
        # SOL market state
        if '15m' in market_state.get('timeframes', {}):
            tf_15m = market_state['timeframes']['15m']
            price = tf_15m.get('current_price', 0)
            candles = tf_15m.get('candles', [])
            
            context_parts.append(f"SOL Price: ${price:.2f}")
            
            if candles:
                recent = candles[-5:] if len(candles) >= 5 else candles
                highs = [c['high'] for c in recent]
                lows = [c['low'] for c in recent]
                context_parts.append(f"Recent Range: ${min(lows):.2f} - ${max(highs):.2f}")
            
            # ATR data
            atr_data = tf_15m.get('atr', {})
            if atr_data:
                atr = atr_data.get('atr', 0)
                atr_percentile = atr_data.get('atr_percentile', 50)
                context_parts.append(f"ATR: {atr:.4f} (percentile: {atr_percentile:.1f})")
            
            # Volume data
            volume_data = tf_15m.get('volume', {})
            if volume_data:
                volume_ratio = volume_data.get('volume_ratio', 1.0)
                context_parts.append(f"Volume Ratio: {volume_ratio:.2f}x average")
            
            # Trend data
            trend_data = tf_15m.get('trend', {})
            if trend_data:
                direction = trend_data.get('trend_direction', 'unknown')
                strength = trend_data.get('trend_strength', 0)
                context_parts.append(f"Trend: {direction} (strength: {strength:.2f})")
        
        # BTC market state
        if btc_market_state and '15m' in btc_market_state.get('timeframes', {}):
            btc_tf = btc_market_state['timeframes']['15m']
            btc_price = btc_tf.get('current_price', 0)
            context_parts.append(f"BTC Price: ${btc_price:.2f}")
        
        return "\n".join(context_parts) if context_parts else "No market data available"
    
    def _format_backtest_results(self, results: Dict) -> str:
        """Format backtest results for ChatGPT analysis"""
        summary = []
        
        # Trades
        trades = results.get('trades', {})
        if trades:
            summary.append(f"Total Trades: {trades.get('total_trades', 0)}")
            summary.append(f"Wins: {trades.get('wins', 0)} | Losses: {trades.get('losses', 0)}")
            summary.append(f"Win Rate: {trades.get('win_rate', 0):.1f}%")
        
        # Performance
        perf = results.get('performance', {})
        if perf:
            summary.append(f"Profit Factor: {perf.get('profit_factor', 0):.2f}")
            summary.append(f"Avg Win: ${perf.get('avg_win', 0):.2f}")
            summary.append(f"Avg Loss: ${perf.get('avg_loss', 0):.2f}")
        
        # Summary
        summary_data = results.get('summary', {})
        if summary_data:
            summary.append(f"Total PnL: ${summary_data.get('total_pnl', 0):.2f}")
            summary.append(f"Total Return: {summary_data.get('total_return_pct', 0):.2f}%")
            summary.append(f"Max Drawdown: {summary_data.get('max_drawdown_pct', 0):.2f}%")
        
        # Signals
        signals = results.get('signals', {})
        if signals:
            summary.append(f"Signals Generated: {signals.get('total_signals', 0)}")
            summary.append(f"Signals Rejected: {signals.get('signals_rejected', 0)}")
        
        return "\n".join(summary) if summary else "No results data available"
    
    def get_token_usage(self) -> Dict:
        """Get cumulative token usage statistics"""
        return {
            **self.token_usage,
            'total_tokens': self.token_usage['input_tokens'] + self.token_usage['output_tokens'],
            'circuit_breaker_state': self.circuit_breaker_state.value,
            'circuit_breaker_failures': self.circuit_breaker_failures
        }
    
    def reset_token_usage(self):
        """Reset token usage tracking"""
        self.token_usage = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_requests': 0,
            'failed_requests': 0,
            'circuit_breaker_trips': 0
        }
    
    def get_health_status(self) -> Dict:
        """Get health status of ChatGPT agent"""
        return {
            'available': OPENAI_AVAILABLE and self.api_key is not None,
            'circuit_breaker_state': self.circuit_breaker_state.value,
            'circuit_breaker_failures': self.circuit_breaker_failures,
            'total_requests': self.token_usage['total_requests'],
            'failed_requests': self.token_usage['failed_requests'],
            'success_rate': (
                (self.token_usage['total_requests'] - self.token_usage['failed_requests']) / 
                max(self.token_usage['total_requests'], 1)
            ),
            'is_healthy': (
                self.circuit_breaker_state == CircuitBreakerState.CLOSED and
                self.token_usage['failed_requests'] < self.token_usage['total_requests'] * 0.2
            )
        }
