"""
Efficient Hybrid AI Agent
Optimized version that intelligently uses Claude and ChatGPT
- Caches results when appropriate
- Batches requests when possible
- Uses Claude for code analysis and improvements
- Optimizes API calls for better efficiency and success rate
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import hashlib
import json

from .hybrid_ai_agent import HybridAIAgent
from .ai_optimizer import AIOptimizer

logger = logging.getLogger(__name__)


class EfficientHybridAgent(HybridAIAgent):
    """
    Enhanced hybrid agent with:
    - Intelligent caching
    - API call optimization
    - Success rate tracking
    - Claude-powered code improvements
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Caching for similar requests
        self.cache = {}
        self.cache_ttl = timedelta(minutes=5)  # Cache for 5 minutes
        
        # Success rate tracking
        self.success_tracking = {
            'claude_only': {'total': 0, 'success': 0},
            'chatgpt_only': {'total': 0, 'success': 0},
            'hybrid': {'total': 0, 'success': 0}
        }
        
        # API call optimization
        self.api_call_history = []
        self.batch_window = timedelta(seconds=2)  # Batch requests within 2 seconds
        
        # AI Optimizer (uses Claude for improvements)
        try:
            self.optimizer = AIOptimizer()
            logger.info("✅ AI Optimizer enabled (Claude-powered improvements)")
        except Exception as e:
            logger.warning(f"⚠️  AI Optimizer not available: {e}")
            self.optimizer = None
        
        logger.info("✅ Efficient Hybrid Agent initialized")
    
    def analyze_setup(self, market_state: Dict, signal: Optional[Dict] = None,
                     filter_results: Optional[Dict] = None) -> Dict:
        """
        Analyze setup with caching and optimization
        """
        # Check cache first
        cache_key = self._generate_cache_key(market_state, signal)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            logger.debug("📦 Using cached analysis result")
            # Track cached call
            self._record_api_call(cached=True)
            return cached_result
        
        # Use parent class for actual analysis
        result = super().analyze_setup(market_state, signal, filter_results)
        
        # Track success
        self._track_success(result)
        
        # Cache result
        self._cache_result(cache_key, result)
        
        # Track API call (not cached)
        self._record_api_call(cached=False)
        
        # Periodically optimize (every 10 actual API calls)
        if len(self.api_call_history) > 0 and len(self.api_call_history) % 10 == 0:
            self._optimize_api_usage()
        
        return result
    
    def _generate_cache_key(self, market_state: Dict, signal: Optional[Dict]) -> str:
        """Generate cache key from market state and signal"""
        # Use price, trend, and signal direction for cache key
        price = market_state.get('timeframes', {}).get('15m', {}).get('current_price', 0)
        trend = market_state.get('timeframes', {}).get('15m', {}).get('trend', {}).get('trend_direction', 'unknown')
        direction = signal.get('direction', 'unknown') if signal else 'unknown'
        
        # Round price to reduce cache misses from tiny fluctuations
        price_rounded = round(price, 2)
        
        key_data = f"{price_rounded}_{trend}_{direction}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict]:
        """Get cached result if still valid"""
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if datetime.now() - cached['timestamp'] < self.cache_ttl:
                return cached['result']
            else:
                # Expired, remove
                del self.cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: Dict):
        """Cache result"""
        self.cache[cache_key] = {
            'result': result,
            'timestamp': datetime.now()
        }
        
        # Limit cache size
        if len(self.cache) > 100:
            # Remove oldest entries
            sorted_cache = sorted(
                self.cache.items(),
                key=lambda x: x[1]['timestamp']
            )
            for key, _ in sorted_cache[:20]:  # Remove 20 oldest
                del self.cache[key]
    
    def _record_api_call(self, cached: bool = False):
        """Record an API call in history for tracking"""
        self.api_call_history.append({
            'timestamp': datetime.now(),
            'cached': cached
        })
        
        # Limit history size to prevent memory issues
        if len(self.api_call_history) > 1000:
            # Keep last 500 entries
            self.api_call_history = self.api_call_history[-500:]
    
    def _track_success(self, result: Dict):
        """Track success rate by mode"""
        source = result.get('source', 'unknown')
        
        if source in self.success_tracking:
            self.success_tracking[source]['total'] += 1
            # Consider successful if consensus or high confidence
            if result.get('consensus', False) or result.get('confidence', 0) > 0.7:
                self.success_tracking[source]['success'] += 1
    
    def _optimize_api_usage(self):
        """Use AI Optimizer to improve API usage"""
        if not self.optimizer:
            return
        
        try:
            # Get stats from both agents
            claude_stats = {}
            chatgpt_stats = {}
            
            if self.claude_agent:
                usage = self.claude_agent.get_token_usage()
                health = self.claude_agent.get_health_status()
                claude_stats = {
                    'total_requests': usage.get('total_requests', 0),
                    'success_rate': health.get('success_rate', 0),
                    'avg_latency_ms': 0  # Would need to track this
                }
            
            if self.chatgpt_agent:
                usage = self.chatgpt_agent.get_token_usage()
                health = self.chatgpt_agent.get_health_status()
                chatgpt_stats = {
                    'total_requests': usage.get('total_requests', 0),
                    'success_rate': health.get('success_rate', 0),
                    'avg_latency_ms': 0
                }
            
            # Get consensus rate
            stats = self.get_stats()
            consensus_rate = stats.get('consensus_rate', 0)
            
            # Get optimization recommendations
            optimization = self.optimizer.optimize_hybrid_ai_usage(
                claude_stats, chatgpt_stats, consensus_rate
            )
            
            # Log recommendations
            if optimization.get('recommendations'):
                logger.info(f"💡 AI Optimization Suggestions:\n{optimization['recommendations'][:500]}")
                
                # Apply optimal mode if suggested
                optimal_mode = optimization.get('optimal_mode')
                if optimal_mode and optimal_mode != self.mode:
                    logger.info(f"🔄 Switching to optimal mode: {optimal_mode}")
                    self.mode = optimal_mode
            
        except Exception as e:
            logger.warning(f"⚠️  API optimization failed: {e}")
    
    def get_efficiency_stats(self) -> Dict:
        """Get efficiency statistics"""
        cache_hit_rate = 0.0
        total_calls = len(self.api_call_history)
        
        if total_calls > 0:
            cache_hits = sum(1 for call in self.api_call_history if call.get('cached', False))
            cache_hit_rate = cache_hits / total_calls
        
        success_rates = {}
        for mode, stats in self.success_tracking.items():
            if stats['total'] > 0:
                success_rates[mode] = stats['success'] / stats['total']
            else:
                success_rates[mode] = 0.0
        
        return {
            'cache_size': len(self.cache),
            'cache_hit_rate': cache_hit_rate,
            'cache_hits': sum(1 for call in self.api_call_history if call.get('cached', False)),
            'cache_misses': sum(1 for call in self.api_call_history if not call.get('cached', False)),
            'success_rates': success_rates,
            'total_api_calls': total_calls,
            'current_mode': self.mode
        }
    
    def improve_success_rate(self, trade_history: List[Dict], filter_results: List[Dict]) -> Dict:
        """Use AI Optimizer to improve success rate"""
        if not self.optimizer:
            return {'recommendations': [], 'error': 'Optimizer not available'}
        
        return self.optimizer.improve_success_rate(trade_history, filter_results)
