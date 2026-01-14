"""\nClaude Autonomous Trading System
AI-powered trade analysis, loss prevention, and continuous optimization

Architecture:
1. Trade Monitor - watches every trade result
2. Loss Analyzer - Claude analyzes losing trades
3. Pattern Learner - builds rejection rules from losses
4. Trade Gatekeeper - blocks bad setups before execution
5. Performance Tracker - tracks AI recommendations vs actual results
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("anthropic package not installed")

logger = logging.getLogger(__name__)


class TradeAnalyzer:
    """Analyzes individual trades to identify why they won/lost"""
    
    def __init__(self, api_key: Optional[str] = None):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package required")
        
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-20250514"
        self.token_usage = {'input': 0, 'output': 0, 'requests': 0}
    
    def analyze_losing_trade(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """Analyze why a trade lost money"""
        system_prompt = """You are an expert crypto trading analyst specializing in loss prevention.

Analyze this losing trade and identify:
1. What went wrong with the setup?
2. Which filter should have blocked this?
3. What pattern indicates this type of bad setup?
4. How to recognize and avoid this in future?

Be specific and actionable. Provide exact conditions to filter on."""
        
        trade_data = self._format_trade_for_analysis(trade, market_context)
        
        prompt = f"""A trade lost money. Analyze:

{trade_data}

Provide:
1. Root cause of loss (3-4 sentences)
2. Which setup condition was violated?
3. Pattern signature (how to identify similar bad setups)
4. Exact filter rule to prevent this (technical description)
5. Confidence level (1-10)"""
        
        messages = [{'role': 'user', 'content': prompt}]
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=messages,
            system=system_prompt
        )
        
        self.token_usage['input'] += response.usage.input_tokens
        self.token_usage['output'] += response.usage.output_tokens
        self.token_usage['requests'] += 1
        
        analysis = response.content[0].text
        
        return {
            'trade_id': trade.get('trade_id'),
            'loss_amount': trade.get('loss_amount', 0),
            'analysis': analysis,
            'timestamp': datetime.now().isoformat(),
            'tokens_used': response.usage.input_tokens + response.usage.output_tokens
        }
    
    def extract_rejection_rule(self, analysis: str, trade: Dict) -> Optional[Dict]:
        """Extract a concrete rejection rule from analysis"""
        system_prompt = """Extract a specific rejection rule from the analysis.
        
Return JSON with:
- rule_name: Short name
- condition: Python-like condition to check
- parameters: Dict of values used
- confidence: 0-1

If no clear rule, return null."""
        
        prompt = f"""Trade data:
{json.dumps(trade, indent=2)}

Analysis:
{analysis}

Extract a concrete rejection rule as JSON."""
        
        messages = [{'role': 'user', 'content': prompt}]
        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=messages,
            system=system_prompt
        )
        
        self.token_usage['input'] += response.usage.input_tokens
        self.token_usage['output'] += response.usage.output_tokens
        
        try:
            # Extract JSON from response
            text = response.content[0].text
            if 'null' in text.lower():
                return None
            
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                rule_json = json.loads(text[start:end])
                return rule_json
        except:
            pass
        
        return None
    
    def _format_trade_for_analysis(self, trade: Dict, market_context: Optional[Dict] = None) -> str:
        """Format trade data for Claude analysis"""
        parts = []
        
        parts.append(f"Trade ID: {trade.get('trade_id')}")
        parts.append(f"Direction: {trade.get('direction', 'unknown').upper()}")
        parts.append(f"Entry Price: ${trade.get('entry_price', 0):.2f}")
        parts.append(f"Exit Price: ${trade.get('exit_price', 0):.2f}")
        parts.append(f"Stop Loss: ${trade.get('stop_loss', 0):.2f}")
        parts.append(f"Loss Amount: ${trade.get('loss_amount', 0):.2f}")
        parts.append(f"Loss %: {trade.get('loss_pct', 0):.2f}%")
        parts.append(f"Duration: {trade.get('duration_minutes', 0)} minutes")
        parts.append(f"Strategy: {trade.get('strategy', 'unknown')}")
        
        if market_context:
            parts.append(f"\nMarket at Entry:")
            parts.append(f"  Price: ${market_context.get('price', 0):.2f}")
            parts.append(f"  Trend: {market_context.get('trend', 'unknown')}")
            parts.append(f"  Volatility: {market_context.get('volatility', 'unknown')}")
            parts.append(f"  Volume: {market_context.get('volume_ratio', 1):.2f}x avg")
        
        # Add filter results if available
        if 'filter_results' in trade:
            parts.append(f"\nFilters That Passed:")
            for f in trade['filter_results'].get('passed', []):
                parts.append(f"  ✓ {f}")
        
        return "\n".join(parts)


class PatternLearner:
    """Learns rejection patterns from losing trades"""
    
    def __init__(self, rules_file: str = "claude_rejection_rules.json"):
        self.rules_file = rules_file
        self.rules: List[Dict] = self._load_rules()
        self.rule_stats = self._load_stats()
    
    def add_rule(self, rule: Dict) -> None:
        """Add a rejection rule from trade analysis"""
        if not rule or 'rule_name' not in rule:
            return
        
        # Check if rule already exists
        existing = next((r for r in self.rules if r['rule_name'] == rule['rule_name']), None)
        
        if existing:
            # Update stats
            existing['hits'] = existing.get('hits', 0) + 1
            existing['last_triggered'] = datetime.now().isoformat()
        else:
            # New rule
            rule['created_at'] = datetime.now().isoformat()
            rule['hits'] = 1
            rule['last_triggered'] = datetime.now().isoformat()
            rule['accuracy'] = rule.get('confidence', 0.5)
            self.rules.append(rule)
        
        self._save_rules()
        logger.info(f"✓ Added rejection rule: {rule.get('rule_name')}")
    
    def check_trade(self, trade: Dict) -> Tuple[bool, List[str]]:
        """Check if trade matches any rejection rules
        
        Returns: (should_block, list of matching rules)
        """
        blocked_by = []
        
        for rule in self.rules:
            if self._rule_matches(rule, trade):
                blocked_by.append(rule['rule_name'])
        
        # Block if high-confidence rules match
        should_block = any(
            next((r for r in self.rules if r['rule_name'] == name), {}).get('confidence', 0) >= 0.7
            for name in blocked_by
        )
        
        return should_block, blocked_by
    
    def get_rule_effectiveness(self) -> Dict:
        """Get stats on rule effectiveness"""
        total_blocks = sum(r.get('hits', 0) for r in self.rules)
        prevented_losses = sum(r.get('prevented_loss', 0) for r in self.rules)
        
        return {
            'total_rules': len(self.rules),
            'total_blocks': total_blocks,
            'estimated_prevented_loss': prevented_losses,
            'top_rules': sorted(
                self.rules,
                key=lambda r: r.get('hits', 0),
                reverse=True
            )[:5]
        }
    
    def _rule_matches(self, rule: Dict, trade: Dict) -> bool:
        """Check if trade matches rule condition"""
        try:
            condition = rule.get('condition', '')
            params = rule.get('parameters', {})
            
            # Simple condition matching (can be extended)
            if 'stop_loss_margin' in condition:
                sl_margin = abs(trade.get('entry_price', 0) - trade.get('stop_loss', 0))
                if sl_margin < params.get('min_margin', 0):
                    return True
            
            if 'volatility' in condition:
                if trade.get('volatility', 10) < params.get('min_volatility', 10):
                    return True
            
            if 'duration' in condition:
                if trade.get('duration_minutes', 999) < params.get('min_duration', 0):
                    return True
        except:
            pass
        
        return False
    
    def _load_rules(self) -> List[Dict]:
        """Load rules from file"""
        if not Path(self.rules_file).exists():
            return []
        
        try:
            with open(self.rules_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def _save_rules(self) -> None:
        """Save rules to file"""
        with open(self.rules_file, 'w') as f:
            json.dump(self.rules, f, indent=2, default=str)
    
    def _load_stats(self) -> Dict:
        """Load rule statistics"""
        stats_file = self.rules_file.replace('.json', '_stats.json')
        if not Path(stats_file).exists():
            return {}
        
        try:
            with open(stats_file, 'r') as f:
                return json.load(f)
        except:
            return {}


class TradeGatekeeper:
    """Approves or blocks trades before execution"""
    
    def __init__(self, analyzer: TradeAnalyzer, learner: PatternLearner):
        self.analyzer = analyzer
        self.learner = learner
        self.decisions_log = []
        self.approval_stats = {
            'total_reviewed': 0,
            'approved': 0,
            'rejected': 0,
            'prevented_loss_estimate': 0
        }
    
    def review_trade(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """Review and approve/reject a trade"""
        self.approval_stats['total_reviewed'] += 1
        
        decision = {
            'trade_id': trade.get('trade_id'),
            'timestamp': datetime.now().isoformat(),
            'rules_checked': [],
            'approved': True,
            'confidence': 1.0,
            'reasoning': []
        }
        
        # Check against learned rejection patterns
        should_block, matching_rules = self.learner.check_trade(trade)
        
        if should_block:
            decision['approved'] = False
            decision['confidence'] = 0.0
            decision['rules_checked'] = matching_rules
            decision['reasoning'].append(f"Blocked by rules: {', '.join(matching_rules)}")
            self.approval_stats['rejected'] += 1
            # Estimate prevented loss
            decision['estimated_prevented_loss'] = trade.get('risk_amount', 0)
            self.approval_stats['prevented_loss_estimate'] += decision['estimated_prevented_loss']
        else:
            self.approval_stats['approved'] += 1
            decision['reasoning'].append("No rejection rules triggered")
        
        # Log decision
        self.decisions_log.append(decision)
        self._save_decision_log()
        
        return decision
    
    def get_approval_rate(self) -> Dict:
        """Get approval statistics"""
        total = self.approval_stats['total_reviewed']
        if total == 0:
            return {'rate': 0, 'stats': self.approval_stats}
        
        return {
            'approval_rate': self.approval_stats['approved'] / total,
            'rejection_rate': self.approval_stats['rejected'] / total,
            'estimated_prevented_loss': self.approval_stats['prevented_loss_estimate'],
            'stats': self.approval_stats
        }
    
    def _save_decision_log(self) -> None:
        """Save decisions to log file"""
        log_file = 'claude_gatekeeper_decisions.jsonl'
        with open(log_file, 'a') as f:
            for decision in self.decisions_log[-1:]:
                f.write(json.dumps(decision) + '\n')


class AutonomousTradeSystem:
    """Main orchestrator - coordinates analysis, learning, and gating"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.analyzer = TradeAnalyzer(api_key)
        self.learner = PatternLearner()
        self.gatekeeper = TradeGatekeeper(self.analyzer, self.learner)
        self.performance_log = []
    
    def process_completed_trade(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """Process a completed trade: analyze if lost, extract rules, learn patterns"""
        result = {
            'trade_id': trade.get('trade_id'),
            'action': 'analyzed',
            'is_loss': trade.get('pnl', 0) < 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Only analyze losing trades
        if result['is_loss']:
            logger.info(f"🔍 Analyzing losing trade {trade.get('trade_id')}...")
            
            # Get Claude's analysis
            analysis = self.analyzer.analyze_losing_trade(trade, market_context)
            result['analysis'] = analysis['analysis']
            
            # Extract rejection rule
            rule = self.analyzer.extract_rejection_rule(analysis['analysis'], trade)
            
            if rule:
                self.learner.add_rule(rule)
                result['rule_added'] = rule['rule_name']
                result['rule_confidence'] = rule.get('confidence', 0.5)
            else:
                result['rule_added'] = None
        else:
            result['pnl'] = trade.get('pnl', 0)
        
        self.performance_log.append(result)
        return result
    
    def approve_trade(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """Approve/reject a trade before execution"""
        decision = self.gatekeeper.review_trade(trade, market_context)
        
        if decision['approved']:
            logger.info(f"✅ APPROVED: {trade.get('trade_id')}")
        else:
            logger.warning(f"🚫 REJECTED: {trade.get('trade_id')} - {decision['reasoning']}")
        
        return decision
    
    def get_system_status(self) -> Dict:
        """Get overall system performance"""
        rule_stats = self.learner.get_rule_effectiveness()
        approval_stats = self.gatekeeper.get_approval_rate()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'learned_rules': rule_stats['total_rules'],
            'total_blocks': rule_stats['total_blocks'],
            'estimated_prevented_loss': rule_stats['estimated_prevented_loss'],
            'approval_stats': approval_stats,
            'token_usage': self.analyzer.token_usage,
            'top_rejection_rules': [
                {'name': r['rule_name'], 'hits': r.get('hits', 0), 'confidence': r.get('confidence', 0)}
                for r in rule_stats['top_rules']
            ]
        }
    
    def generate_daily_report(self) -> str:
        """Generate daily optimization report"""
        status = self.get_system_status()
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║          CLAUDE AUTONOMOUS SYSTEM - DAILY REPORT          ║
╚════════════════════════════════════════════════════════════╝

📊 SYSTEM STATUS:
  • Rules Learned: {status['learned_rules']}
  • Total Blocks: {status['total_blocks']}
  • Estimated Loss Prevention: ${status['estimated_prevented_loss']:.2f}

🎯 TRADE GATING:
  • Approval Rate: {status['approval_stats']['approval_rate']*100:.1f}%
  • Rejection Rate: {status['approval_stats']['rejection_rate']*100:.1f}%
  • Total Reviewed: {status['approval_stats']['stats']['total_reviewed']}

🔥 TOP REJECTION RULES:
"""
        for rule in status['top_rejection_rules']:
            report += f"  • {rule['name']}: {rule['hits']} blocks (confidence: {rule['confidence']*100:.0f}%)\n"
        
        report += f"""
💡 TOKEN USAGE:
  • Input Tokens: {status['token_usage']['input']}
  • Output Tokens: {status['token_usage']['output']}
  • Requests: {status['token_usage']['requests']}
"""
        return report


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    system = AutonomousTradeSystem()
    
    # Simulate analyzing a losing trade
    example_trade = {
        'trade_id': 'TRADE_001',
        'direction': 'long',
        'entry_price': 150.25,
        'exit_price': 149.50,
        'stop_loss': 149.00,
        'loss_amount': 0.75,
        'loss_pct': 0.5,
        'duration_minutes': 15,
        'strategy': 'breakout',
        'pnl': -7.50,
        'volatility': 8,
        'volume_ratio': 0.7
    }
    
    # Process the trade
    result = system.process_completed_trade(example_trade)
    print(json.dumps(result, indent=2))
    
    # Get system status
    print(system.generate_daily_report())
