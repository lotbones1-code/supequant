"""
AI Optimizer
Uses Claude to analyze code, optimize API calls, and improve success rate
Claude acts as an intelligent agent to make things better without breaking anything
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
from pathlib import Path

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logger = logging.getLogger(__name__)


class AIOptimizer:
    """
    Uses Claude to optimize the trading system:
    - Analyzes code for improvements
    - Optimizes API call patterns
    - Suggests parameter adjustments
    - Improves success rate through intelligent recommendations
    """
    
    def __init__(self, api_key: Optional[str] = None):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package required")
        
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-20250514"
        
        # Cache for API optimizations
        self.optimization_cache = {}
        self.success_rate_history = []
        self.api_call_patterns = []
        
        logger.info("✅ AI Optimizer initialized (Claude-powered)")
    
    def analyze_code_improvements(self, code_snippet: str, context: str = "") -> Dict:
        """
        Use Claude to analyze code and suggest improvements without breaking anything
        
        Args:
            code_snippet: Code to analyze
            context: Additional context about what the code does
            
        Returns:
            Dict with analysis and safe improvement suggestions
        """
        system_prompt = """You are an expert Python developer specializing in trading systems and API optimization.

Your task: Analyze code and suggest improvements that:
1. Increase efficiency and performance
2. Improve success rate
3. Optimize API calls
4. Do NOT break existing functionality
5. Are safe to implement

Be specific, actionable, and conservative. Only suggest changes that are clearly beneficial."""
        
        prompt = f"""Analyze this code and suggest improvements:

{code_snippet}

Context: {context if context else "Trading system code"}

Provide:
1. Performance optimizations
2. API call efficiency improvements
3. Success rate enhancements
4. Specific code changes (safe, non-breaking)
5. Expected impact of each change"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{'role': 'user', 'content': prompt}],
                system=system_prompt
            )
            
            analysis = response.content[0].text
            
            return {
                'analysis': analysis,
                'timestamp': datetime.now().isoformat(),
                'suggestions': self._extract_suggestions(analysis)
            }
        except Exception as e:
            logger.error(f"❌ Code analysis failed: {e}")
            return {
                'analysis': f"Analysis failed: {str(e)}",
                'timestamp': datetime.now().isoformat(),
                'suggestions': []
            }
    
    def optimize_api_calls(self, api_call_history: List[Dict]) -> Dict:
        """
        Analyze API call patterns and suggest optimizations
        
        Args:
            api_call_history: List of API call records with timing, success, etc.
            
        Returns:
            Optimization recommendations
        """
        if not api_call_history:
            return {'recommendations': [], 'efficiency_gain': 0}
        
        # Analyze patterns
        total_calls = len(api_call_history)
        successful_calls = sum(1 for call in api_call_history if call.get('success', False))
        avg_latency = sum(call.get('latency_ms', 0) for call in api_call_history) / total_calls
        
        # Use Claude to analyze and optimize
        system_prompt = """You are an API optimization expert. Analyze API call patterns and suggest:
1. Batching opportunities
2. Caching strategies
3. Rate limit optimizations
4. Parallelization opportunities
5. Request reduction techniques"""
        
        patterns_summary = self._summarize_api_patterns(api_call_history)
        
        prompt = f"""Analyze these API call patterns and suggest optimizations:

Total Calls: {total_calls}
Success Rate: {successful_calls/total_calls*100:.1f}%
Avg Latency: {avg_latency:.1f}ms

Patterns:
{patterns_summary}

Suggest specific optimizations to:
- Reduce API calls by 20%+
- Improve success rate
- Reduce latency
- Increase efficiency"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{'role': 'user', 'content': prompt}],
                system=system_prompt
            )
            
            recommendations = response.content[0].text
            
            return {
                'recommendations': recommendations,
                'current_stats': {
                    'total_calls': total_calls,
                    'success_rate': successful_calls / total_calls if total_calls > 0 else 0,
                    'avg_latency_ms': avg_latency
                },
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ API optimization analysis failed: {e}")
            return {'recommendations': [], 'error': str(e)}
    
    def improve_success_rate(self, trade_history: List[Dict], filter_results: List[Dict]) -> Dict:
        """
        Analyze trade history and filter results to improve success rate
        
        Uses Claude to identify patterns and suggest improvements
        """
        if not trade_history:
            return {'recommendations': [], 'expected_improvement': 0}
        
        # Calculate current success rate
        total_trades = len(trade_history)
        winning_trades = sum(1 for trade in trade_history if trade.get('pnl', 0) > 0)
        current_success_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Analyze patterns
        system_prompt = """You are a quantitative trading analyst. Analyze trade history to:
1. Identify what makes winning trades successful
2. Identify what makes losing trades fail
3. Suggest filter/strategy improvements
4. Recommend parameter adjustments
5. Predict expected success rate improvement"""
        
        trade_summary = self._summarize_trades(trade_history, filter_results)
        
        prompt = f"""Analyze this trading history to improve success rate:

Current Success Rate: {current_success_rate*100:.1f}%
Total Trades: {total_trades}
Winning Trades: {winning_trades}

Trade Patterns:
{trade_summary}

Provide:
1. Key factors in winning trades
2. Common patterns in losing trades
3. Specific filter/parameter improvements
4. Expected success rate improvement (realistic estimate)
5. Implementation steps"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{'role': 'user', 'content': prompt}],
                system=system_prompt
            )
            
            analysis = response.content[0].text
            
            return {
                'analysis': analysis,
                'current_success_rate': current_success_rate,
                'recommendations': self._extract_success_improvements(analysis),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Success rate analysis failed: {e}")
            return {
                'analysis': f"Analysis failed: {str(e)}",
                'current_success_rate': current_success_rate,
                'recommendations': []
            }
    
    def optimize_hybrid_ai_usage(self, claude_stats: Dict, chatgpt_stats: Dict, 
                                 consensus_rate: float) -> Dict:
        """
        Optimize when to use Claude vs ChatGPT vs Hybrid
        
        Uses Claude to intelligently decide the best strategy
        """
        system_prompt = """You are an AI optimization expert. Analyze API usage patterns and suggest:
1. When to use Claude only
2. When to use ChatGPT only  
3. When to use Hybrid (both)
4. Cost/benefit optimization
5. Success rate vs cost tradeoffs"""
        
        prompt = f"""Optimize hybrid AI usage:

Claude Stats:
- Requests: {claude_stats.get('total_requests', 0)}
- Success Rate: {claude_stats.get('success_rate', 0)*100:.1f}%
- Avg Latency: {claude_stats.get('avg_latency_ms', 0):.1f}ms

ChatGPT Stats:
- Requests: {chatgpt_stats.get('total_requests', 0)}
- Success Rate: {chatgpt_stats.get('success_rate', 0)*100:.1f}%
- Avg Latency: {chatgpt_stats.get('avg_latency_ms', 0):.1f}ms

Consensus Rate: {consensus_rate*100:.1f}%

Suggest:
1. Optimal hybrid mode (consensus/weighted/fallback)
2. When to skip ChatGPT (use Claude only)
3. When to skip Claude (use ChatGPT only)
4. Cost optimization strategies
5. Expected efficiency gain"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{'role': 'user', 'content': prompt}],
                system=system_prompt
            )
            
            recommendations = response.content[0].text
            
            return {
                'recommendations': recommendations,
                'optimal_mode': self._extract_optimal_mode(recommendations),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Hybrid optimization failed: {e}")
            return {'recommendations': [], 'error': str(e)}
    
    def _extract_suggestions(self, analysis: str) -> List[str]:
        """Extract actionable suggestions from Claude's analysis"""
        suggestions = []
        lines = analysis.split('\n')
        
        for line in lines:
            if any(marker in line.lower() for marker in ['- ', '• ', '1.', '2.', '3.']):
                suggestions.append(line.strip())
        
        return suggestions[:10]  # Top 10 suggestions
    
    def _summarize_api_patterns(self, history: List[Dict]) -> str:
        """Summarize API call patterns for Claude"""
        if not history:
            return "No API calls recorded"
        
        endpoints = {}
        for call in history:
            endpoint = call.get('endpoint', 'unknown')
            if endpoint not in endpoints:
                endpoints[endpoint] = {'count': 0, 'success': 0, 'latency': []}
            endpoints[endpoint]['count'] += 1
            if call.get('success', False):
                endpoints[endpoint]['success'] += 1
            if 'latency_ms' in call:
                endpoints[endpoint]['latency'].append(call['latency_ms'])
        
        summary = []
        for endpoint, stats in endpoints.items():
            success_rate = stats['success'] / stats['count'] * 100 if stats['count'] > 0 else 0
            avg_latency = sum(stats['latency']) / len(stats['latency']) if stats['latency'] else 0
            summary.append(f"{endpoint}: {stats['count']} calls, {success_rate:.1f}% success, {avg_latency:.1f}ms avg")
        
        return "\n".join(summary)
    
    def _summarize_trades(self, trades: List[Dict], filters: List[Dict]) -> str:
        """Summarize trade patterns for Claude"""
        if not trades:
            return "No trades recorded"
        
        winners = [t for t in trades if t.get('pnl', 0) > 0]
        losers = [t for t in trades if t.get('pnl', 0) <= 0]
        
        summary = [
            f"Winners: {len(winners)}",
            f"Losers: {len(losers)}",
            f"Avg Win: ${sum(t.get('pnl', 0) for t in winners) / len(winners) if winners else 0:.2f}",
            f"Avg Loss: ${sum(t.get('pnl', 0) for t in losers) / len(losers) if losers else 0:.2f}"
        ]
        
        # Add filter patterns
        if filters:
            filter_pass_rate = {}
            for f in filters:
                filter_name = f.get('filter_name', 'unknown')
                if filter_name not in filter_pass_rate:
                    filter_pass_rate[filter_name] = {'total': 0, 'passed': 0}
                filter_pass_rate[filter_name]['total'] += 1
                if f.get('passed', False):
                    filter_pass_rate[filter_name]['passed'] += 1
            
            summary.append("\nFilter Pass Rates:")
            for name, stats in filter_pass_rate.items():
                rate = stats['passed'] / stats['total'] * 100 if stats['total'] > 0 else 0
                summary.append(f"  {name}: {rate:.1f}%")
        
        return "\n".join(summary)
    
    def _extract_success_improvements(self, analysis: str) -> List[str]:
        """Extract success rate improvement suggestions"""
        improvements = []
        lines = analysis.split('\n')
        
        for line in lines:
            if any(keyword in line.lower() for keyword in ['improve', 'increase', 'suggest', 'recommend', 'adjust']):
                improvements.append(line.strip())
        
        return improvements[:5]  # Top 5 improvements
    
    def _extract_optimal_mode(self, recommendations: str) -> str:
        """Extract optimal hybrid mode from recommendations"""
        rec_lower = recommendations.lower()
        
        if 'consensus' in rec_lower and 'recommend' in rec_lower:
            return 'consensus'
        elif 'weighted' in rec_lower and 'recommend' in rec_lower:
            return 'weighted'
        elif 'fallback' in rec_lower and 'recommend' in rec_lower:
            return 'fallback'
        
        return 'consensus'  # Default
