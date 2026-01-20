"""
Enhanced Autonomous Trading System
Uses Hybrid AI (Claude + ChatGPT) for better trade analysis and decisions
"""

import logging
from typing import Dict, Optional
from datetime import datetime

from .claude_autonomous_system import AutonomousTradeSystem
from .hybrid_ai_agent import HybridAIAgent

logger = logging.getLogger(__name__)


class EnhancedAutonomousTradeSystem(AutonomousTradeSystem):
    """
    Enhanced version that uses Hybrid AI (Claude + ChatGPT) for better analysis
    
    Benefits:
    - Dual-model consensus reduces false positives/negatives
    - Better trade analysis with two perspectives
    - More reliable pattern learning
    - Fallback if one model fails
    """
    
    def __init__(self, 
                 claude_api_key: Optional[str] = None,
                 chatgpt_api_key: Optional[str] = None,
                 use_hybrid: bool = True,
                 hybrid_mode: str = "consensus",
                 timeout_seconds: float = 10.0,
                 fail_open: bool = True,
                 min_approval_rate: float = 0.1):
        """
        Initialize enhanced autonomous system
        
        Args:
            claude_api_key: Anthropic API key
            chatgpt_api_key: OpenAI API key
            use_hybrid: If True, use hybrid AI (default: True)
            hybrid_mode: Hybrid mode (consensus/weighted/fallback)
            timeout_seconds: Request timeout
            fail_open: Approve trades if AI fails
            min_approval_rate: Minimum approval rate before auto-disable
        """
        # Initialize base system
        super().__init__(
            api_key=claude_api_key,
            timeout_seconds=timeout_seconds,
            fail_open=fail_open,
            min_approval_rate=min_approval_rate
        )
        
        self.use_hybrid = use_hybrid
        self.hybrid_agent = None
        self.require_consensus = True  # Require both models to agree by default
        
        if use_hybrid:
            try:
                # Try efficient hybrid agent first (with optimizations)
                try:
                    from .efficient_hybrid_agent import EfficientHybridAgent
                    self.hybrid_agent = EfficientHybridAgent(
                        claude_api_key=claude_api_key,
                        chatgpt_api_key=chatgpt_api_key,
                        mode=hybrid_mode,
                        verbose=True
                    )
                    logger.info(f"✅ Efficient Hybrid AI enabled (mode: {hybrid_mode}) - Optimized with Claude-powered improvements")
                except ImportError:
                    # Fallback to standard hybrid agent
                    from .hybrid_ai_agent import HybridAIAgent
                    self.hybrid_agent = HybridAIAgent(
                        claude_api_key=claude_api_key,
                        chatgpt_api_key=chatgpt_api_key,
                        mode=hybrid_mode,
                        verbose=True
                    )
                    logger.info(f"✅ Hybrid AI enabled (mode: {hybrid_mode}) - Using Claude + ChatGPT for trade decisions")
            except Exception as e:
                logger.warning(f"⚠️  Hybrid AI init failed: {e}, falling back to Claude only")
                self.use_hybrid = False
    
    def approve_trade(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """
        Approve/reject a trade using Hybrid AI (Claude + ChatGPT) for better decisions
        
        This overrides the base class method to use hybrid analysis
        """
        if self.use_hybrid and self.hybrid_agent:
            try:
                # Build market state for hybrid analysis
                market_state = {
                    'timeframes': {
                        '15m': {
                            'current_price': market_context.get('price', trade.get('entry_price', 0)) if market_context else trade.get('entry_price', 0),
                            'trend': {'trend_direction': market_context.get('trend', 'unknown') if market_context else 'unknown'},
                            'volume': {'volume_ratio': market_context.get('volume_ratio', 1) if market_context else 1}
                        }
                    } if market_context else {}
                }
                
                # Get hybrid AI analysis
                hybrid_result = self.hybrid_agent.analyze_setup(
                    market_state=market_state,
                    signal={
                        'direction': trade.get('direction', 'unknown'),
                        'entry_price': trade.get('entry_price', 0),
                        'stop_loss': trade.get('stop_loss', 0),
                        'take_profit_1': trade.get('take_profit_1', 0),
                        'strategy': trade.get('strategy', 'unknown')
                    }
                )
                
                # Extract recommendations
                claude_rec = hybrid_result.get('claude_recommendation', 'UNKNOWN')
                chatgpt_rec = hybrid_result.get('chatgpt_recommendation', 'UNKNOWN')
                consensus = hybrid_result.get('consensus', False)
                
                # Determine approval: both must agree on LONG/SHORT (not WAIT)
                approved = (
                    claude_rec in ['LONG', 'SHORT'] and 
                    chatgpt_rec in ['LONG', 'SHORT'] and
                    claude_rec == chatgpt_rec  # Must agree on direction
                )
                
                # If no consensus but one model says trade, use fallback logic
                if not approved and not self.require_consensus:
                    approved = (
                        claude_rec in ['LONG', 'SHORT'] or 
                        chatgpt_rec in ['LONG', 'SHORT']
                    )
                
                reasoning = []
                if consensus:
                    reasoning.append(f"✅ Hybrid AI Consensus: Both models agree ({claude_rec})")
                else:
                    reasoning.append(f"⚠️ Hybrid AI: Claude={claude_rec}, ChatGPT={chatgpt_rec}")
                
                decision = {
                    'trade_id': trade.get('trade_id'),
                    'timestamp': datetime.now().isoformat(),
                    'approved': approved,
                    'confidence': 0.9 if consensus else 0.7,
                    'reasoning': reasoning,
                    'hybrid_analysis': hybrid_result.get('recommendation', '')[:200],
                    'consensus': consensus,
                    'claude_recommendation': claude_rec,
                    'chatgpt_recommendation': chatgpt_rec
                }
                
                if approved:
                    logger.info(f"✅ HYBRID AI APPROVED: {trade.get('trade_id')} (Claude={claude_rec}, ChatGPT={chatgpt_rec}, Consensus={consensus})")
                else:
                    logger.warning(f"🚫 HYBRID AI REJECTED: {trade.get('trade_id')} - Claude={claude_rec}, ChatGPT={chatgpt_rec}")
                
                return decision
                
            except Exception as e:
                logger.warning(f"⚠️  Hybrid AI approval failed: {e}, falling back to Claude-only")
                # Fall through to base class method
        
        # Fallback to base Claude-only approval
        return super().approve_trade(trade, market_context)
    
    def analyze_losing_trade_with_hybrid(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """
        Analyze losing trade using hybrid AI for better insights
        
        Returns:
            Enhanced analysis with consensus from both models
        """
        if not self.use_hybrid or not self.hybrid_agent:
            # Fallback to base Claude analysis
            return self.analyzer.analyze_losing_trade(trade, market_context)
        
        try:
            # Use hybrid agent to analyze the setup
            # Build market state from context
            market_state = {
                'timeframes': {
                    '15m': market_context or {}
                }
            } if market_context else {}
            
            # Get hybrid analysis
            hybrid_result = self.hybrid_agent.analyze_setup(
                market_state=market_state,
                signal={
                    'direction': trade.get('direction', 'unknown'),
                    'entry_price': trade.get('entry_price', 0),
                    'stop_loss': trade.get('stop_loss', 0),
                    'strategy': trade.get('strategy', 'unknown')
                }
            )
            
            # Combine with Claude's specific loss analysis
            claude_analysis = self.analyzer.analyze_losing_trade(trade, market_context)
            
            # Merge analyses
            enhanced_analysis = {
                'trade_id': trade.get('trade_id'),
                'loss_amount': trade.get('loss_amount', 0),
                'claude_analysis': claude_analysis.get('analysis', ''),
                'hybrid_analysis': hybrid_result.get('recommendation', ''),
                'consensus': hybrid_result.get('consensus', False),
                'claude_recommendation': hybrid_result.get('claude_recommendation', 'UNKNOWN'),
                'chatgpt_recommendation': hybrid_result.get('chatgpt_recommendation', 'UNKNOWN'),
                'timestamp': datetime.now().isoformat(),
                'tokens_used': (
                    claude_analysis.get('tokens_used', 0) +
                    hybrid_result.get('usage', {}).get('input_tokens', 0) +
                    hybrid_result.get('usage', {}).get('output_tokens', 0)
                )
            }
            
            # Create combined analysis text
            combined_text = f"""HYBRID AI ANALYSIS (Claude + ChatGPT)

Claude Analysis:
{claude_analysis.get('analysis', 'Analysis unavailable')}

Hybrid AI Consensus:
{hybrid_result.get('recommendation', 'Analysis unavailable')}

Consensus Status: {'✅ AGREEMENT' if hybrid_result.get('consensus', False) else '⚠️ DISAGREEMENT'}
Claude Recommendation: {hybrid_result.get('claude_recommendation', 'UNKNOWN')}
ChatGPT Recommendation: {hybrid_result.get('chatgpt_recommendation', 'UNKNOWN')}
"""
            
            enhanced_analysis['analysis'] = combined_text
            
            logger.info(f"✅ Hybrid analysis complete (consensus: {hybrid_result.get('consensus', False)})")
            return enhanced_analysis
            
        except Exception as e:
            logger.error(f"❌ Hybrid analysis failed: {e}, falling back to Claude")
            return self.analyzer.analyze_losing_trade(trade, market_context)
    
    def process_completed_trade(self, trade: Dict, market_context: Optional[Dict] = None) -> Dict:
        """Process completed trade with enhanced hybrid analysis"""
        trade_id = trade.get('trade_id')
        pnl = trade.get('pnl', 0)
        
        # Record outcome
        self.gatekeeper.record_trade_outcome(trade_id, pnl)
        
        result = {
            'trade_id': trade_id,
            'action': 'analyzed',
            'is_loss': pnl < 0,
            'is_win': pnl > 0,
            'timestamp': datetime.now().isoformat(),
            'used_hybrid': self.use_hybrid
        }
        
        # Track winning trades
        if result['is_win']:
            logger.info(f"✅ Recording winning trade {trade_id}...")
            self.winning_learner.add_winning_pattern(trade, market_context)
            result['pnl'] = trade.get('pnl', 0)
        
        # Analyze losing trades with hybrid AI
        if result['is_loss']:
            try:
                logger.info(f"🔍 Analyzing losing trade {trade_id} with {'Hybrid AI' if self.use_hybrid else 'Claude'}...")
                
                # Use hybrid analysis if available
                if self.use_hybrid:
                    analysis = self.analyze_losing_trade_with_hybrid(trade, market_context)
                else:
                    analysis = self.analyzer.analyze_losing_trade(trade, market_context)
                
                result['analysis'] = analysis.get('analysis', 'Analysis unavailable')
                result['consensus'] = analysis.get('consensus', False)
                
                # Extract rejection rule
                if 'Analysis unavailable' not in result['analysis']:
                    rule = self.analyzer.extract_rejection_rule(
                        analysis.get('claude_analysis', analysis.get('analysis', '')),
                        trade
                    )
                    
                    if rule:
                        self.learner.add_rule(rule)
                        result['rule_added'] = rule['rule_name']
                        result['rule_confidence'] = rule.get('confidence', 0.5)
                    else:
                        result['rule_added'] = None
                else:
                    result['rule_added'] = None
                    
            except Exception as e:
                logger.error(f"❌ Error analyzing losing trade: {e}")
                result['analysis'] = f"Error: {str(e)[:200]}"
                result['rule_added'] = None
        
        self.performance_log.append(result)
        return result
    
    def get_system_status(self) -> Dict:
        """Get enhanced system status with hybrid AI stats"""
        base_status = super().get_system_status()
        
        if self.use_hybrid and self.hybrid_agent:
            hybrid_stats = self.hybrid_agent.get_stats()
            hybrid_health = self.hybrid_agent.get_health_status()
            
            base_status['hybrid_ai'] = {
                'enabled': True,
                'mode': self.hybrid_agent.mode,
                'stats': hybrid_stats,
                'health': hybrid_health,
                'consensus_rate': hybrid_stats.get('consensus_rate', 0)
            }
        else:
            base_status['hybrid_ai'] = {
                'enabled': False
            }
        
        return base_status
    
    def generate_daily_report(self) -> str:
        """Generate enhanced daily report with hybrid AI stats"""
        base_report = super().generate_daily_report()
        
        if self.use_hybrid and self.hybrid_agent:
            hybrid_stats = self.hybrid_agent.get_stats()
            hybrid_health = self.hybrid_agent.get_health_status()
            
            hybrid_section = f"""
🤖 HYBRID AI STATUS:
  • Mode: {self.hybrid_agent.mode}
  • Consensus Rate: {hybrid_stats.get('consensus_rate', 0)*100:.1f}%
  • Total Analyses: {hybrid_stats.get('total_analyses', 0)}
  • Agreements: {hybrid_stats.get('consensus_agreements', 0)}
  • Disagreements: {hybrid_stats.get('consensus_disagreements', 0)}
  • Claude Health: {'✅' if hybrid_health.get('claude_healthy', False) else '❌'}
  • ChatGPT Health: {'✅' if hybrid_health.get('chatgpt_healthy', False) else '❌'}
"""
            # Insert hybrid section before token usage
            base_report = base_report.replace("💡 TOKEN USAGE:", hybrid_section + "\n💡 TOKEN USAGE:")
        
        return base_report
