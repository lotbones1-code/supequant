"""
Strategy Advisor
Uses Claude to analyze and optimize trading strategies
"""

import os
import logging
from typing import Dict, Optional, List
from pathlib import Path

from .claude_agent import ClaudeAgent

logger = logging.getLogger(__name__)


class StrategyAdvisor:
    """
    Strategy advisor that uses Claude to:
    - Review strategy logic
    - Suggest optimal threshold values
    - Analyze missed opportunities
    - Recommend parameter changes
    """
    
    def __init__(self, claude_agent: Optional[ClaudeAgent] = None):
        """
        Initialize strategy advisor
        
        Args:
            claude_agent: Optional ClaudeAgent instance (creates new one if not provided)
        """
        self.agent = claude_agent or ClaudeAgent()
        self.project_root = Path(__file__).parent.parent
        
    def review_strategy_logic(self, strategy_name: str = "breakout") -> Dict:
        """
        Review strategy code and suggest improvements
        
        Args:
            strategy_name: 'breakout' or 'pullback'
            
        Returns:
            Dict with analysis and recommendations
        """
        strategy_file = self.project_root / "strategy" / f"{strategy_name}_strategy.py"
        
        if not strategy_file.exists():
            raise FileNotFoundError(f"Strategy file not found: {strategy_file}")
        
        # Read strategy code
        with open(strategy_file, 'r') as f:
            strategy_code = f.read()
        
        # Read config to understand current parameters
        config_file = self.project_root / "config.py"
        config_code = ""
        if config_file.exists():
            with open(config_file, 'r') as f:
                config_code = f.read()
        
        system_prompt = """You are an expert quantitative trading strategist reviewing strategy code.

Analyze the code for:
- Logic errors
- Threshold optimization opportunities
- Edge cases not handled
- Performance improvements

Provide specific, actionable recommendations with code examples."""
        
        prompt = f"""Review the {strategy_name} strategy code and suggest improvements.

Strategy Code:
```python
{strategy_code}
```

Configuration:
```python
{config_code[:2000]}  # First 2000 chars
```

Provide:
1. Code quality assessment
2. Logic issues (if any)
3. Threshold optimization suggestions
4. Edge cases to handle
5. Performance improvements
6. Specific code changes recommended"""
        
        response = self.agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt
        )
        
        return {
            'review': response['content'],
            'strategy': strategy_name,
            'usage': response['usage']
        }
    
    def suggest_thresholds(self, strategy_name: str, recent_price_action: Dict,
                          missed_opportunities: List[Dict]) -> Dict:
        """
        Suggest optimal threshold values based on recent price action
        
        Args:
            strategy_name: 'breakout' or 'pullback'
            recent_price_action: Dict with price data, ATR, volume, etc.
            missed_opportunities: List of dicts with opportunities that were close but didn't trigger
            
        Returns:
            Dict with threshold recommendations
        """
        system_prompt = """You are an expert at optimizing trading strategy thresholds.

Analyze price action and missed opportunities to suggest optimal threshold values.
Balance signal quality with frequency."""
        
        # Format missed opportunities
        missed_str = ""
        for i, opp in enumerate(missed_opportunities[:10], 1):  # Limit to 10
            missed_str += f"\n{i}. {opp.get('description', 'Unknown')}"
            missed_str += f"\n   Distance: {opp.get('distance_pct', 0):.3f}%"
            missed_str += f"\n   Price: ${opp.get('price', 0):.2f}"
        
        prompt = f"""Suggest optimal threshold values for the {strategy_name} strategy.

Recent Price Action:
- Current Price: ${recent_price_action.get('price', 0):.2f}
- ATR: {recent_price_action.get('atr', 0):.4f}
- ATR Percentile: {recent_price_action.get('atr_percentile', 50):.1f}
- Volume Ratio: {recent_price_action.get('volume_ratio', 1.0):.2f}x
- Consolidation Range: {recent_price_action.get('consolidation_range_pct', 0):.2%}

Missed Opportunities (price came close but didn't trigger):
{missed_str if missed_opportunities else "None recorded"}

Current Thresholds:
- Consolidation: < 5% range
- Volume: ≥ 0.8x average
- ATR Compression: < 1.5x average
- Breakout: 0.3% above/below

Provide:
1. Recommended threshold adjustments
2. Reasoning for each change
3. Expected impact (signal frequency, win rate)
4. Risk assessment"""
        
        response = self.agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt
        )
        
        return {
            'recommendations': response['content'],
            'strategy': strategy_name,
            'usage': response['usage']
        }
    
    def analyze_missed_opportunities(self, opportunities: List[Dict]) -> Dict:
        """
        Analyze missed opportunities and suggest how to catch them
        
        Args:
            opportunities: List of dicts with missed opportunity data
            
        Returns:
            Dict with analysis and recommendations
        """
        system_prompt = """You are an expert at analyzing why trading opportunities were missed.

Identify patterns in missed opportunities and suggest parameter adjustments to catch similar setups in the future."""
        
        # Group opportunities by type
        by_type = {}
        for opp in opportunities:
            opp_type = opp.get('type', 'unknown')
            if opp_type not in by_type:
                by_type[opp_type] = []
            by_type[opp_type].append(opp)
        
        # Format opportunities
        opp_summary = []
        for opp_type, opps in by_type.items():
            avg_distance = sum(o.get('distance_pct', 0) for o in opps) / len(opps) if opps else 0
            opp_summary.append(f"{opp_type}: {len(opps)} opportunities, avg distance: {avg_distance:.3f}%")
        
        prompt = f"""Analyze these missed trading opportunities.

Missed Opportunities Summary:
{chr(10).join(opp_summary)}

Total: {len(opportunities)} opportunities

Sample Opportunities:
{chr(10).join([f"- {o.get('description', 'Unknown')} (distance: {o.get('distance_pct', 0):.3f}%)" for o in opportunities[:5]])}

Provide:
1. Common patterns in missed opportunities
2. Which threshold is blocking most opportunities
3. Recommended parameter adjustments
4. Expected impact of changes
5. Risk of catching false signals"""
        
        response = self.agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt
        )
        
        return {
            'analysis': response['content'],
            'total_opportunities': len(opportunities),
            'usage': response['usage']
        }
    
    def recommend_parameter_changes(self, strategy_name: str, 
                                   current_performance: Dict,
                                   target_performance: Dict) -> Dict:
        """
        Recommend parameter changes to achieve target performance
        
        Args:
            strategy_name: 'breakout' or 'pullback'
            current_performance: Dict with current metrics (win rate, profit factor, etc.)
            target_performance: Dict with target metrics
            
        Returns:
            Dict with parameter change recommendations
        """
        system_prompt = """You are an expert at optimizing trading strategy parameters to achieve performance targets.

Provide specific parameter adjustments with expected impact on each metric."""
        
        prompt = f"""Recommend parameter changes for {strategy_name} strategy to achieve target performance.

Current Performance:
- Win Rate: {current_performance.get('win_rate', 0):.1f}%
- Profit Factor: {current_performance.get('profit_factor', 0):.2f}
- Signals/Week: {current_performance.get('signals_per_week', 0):.1f}
- Avg Return: {current_performance.get('avg_return', 0):.2f}%

Target Performance:
- Win Rate: {target_performance.get('win_rate', 0):.1f}%
- Profit Factor: {target_performance.get('profit_factor', 0):.2f}
- Signals/Week: {target_performance.get('signals_per_week', 0):.1f}
- Avg Return: {target_performance.get('avg_return', 0):.2f}%

Current Parameters:
- Consolidation: < 5% range
- Volume: ≥ 0.8x average
- ATR Compression: < 1.5x average
- Breakout: 0.3% above/below

Provide:
1. Specific parameter changes needed
2. Expected impact on each metric
3. Implementation steps
4. Risk assessment
5. Testing recommendations"""
        
        response = self.agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt
        )
        
        return {
            'recommendations': response['content'],
            'strategy': strategy_name,
            'usage': response['usage']
        }
