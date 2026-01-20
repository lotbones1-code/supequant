"""
Hybrid AI Agent
Combines Claude and ChatGPT for consensus-based trading decisions
Uses both models to get better, more reliable recommendations
"""

import logging
from typing import Dict, Optional, List, Any
from datetime import datetime
import json

from .claude_agent import ClaudeAgent
from .chatgpt_agent import ChatGPTAgent

logger = logging.getLogger(__name__)


class HybridAIAgent:
    """
    Hybrid AI agent that combines Claude and ChatGPT for consensus
    
    Benefits:
    - Dual-model consensus reduces false positives/negatives
    - Fallback if one model fails
    - Different perspectives on same data
    - Better confidence scoring
    
    Modes:
    - CONSENSUS: Both models must agree (strictest)
    - MAJORITY: Use majority vote (if 3+ models)
    - WEIGHTED: Weighted average of confidence scores
    - FALLBACK: Use primary, fallback to secondary if primary fails
    """
    
    CONSENSUS_MODE = "consensus"
    MAJORITY_MODE = "majority"
    WEIGHTED_MODE = "weighted"
    FALLBACK_MODE = "fallback"
    
    def __init__(self, 
                 claude_api_key: Optional[str] = None,
                 chatgpt_api_key: Optional[str] = None,
                 claude_model: str = "claude-sonnet-4-20250514",
                 chatgpt_model: str = "gpt-4o",
                 mode: str = CONSENSUS_MODE,
                 claude_weight: float = 0.5,
                 chatgpt_weight: float = 0.5,
                 require_consensus: bool = True,
                 verbose: bool = False):
        """
        Initialize hybrid AI agent
        
        Args:
            claude_api_key: Anthropic API key
            chatgpt_api_key: OpenAI API key
            claude_model: Claude model to use
            chatgpt_model: ChatGPT model to use
            mode: Consensus mode (consensus/majority/weighted/fallback)
            claude_weight: Weight for Claude in weighted mode (0-1)
            chatgpt_weight: Weight for ChatGPT in weighted mode (0-1)
            require_consensus: If True, both must agree in consensus mode
            verbose: Enable verbose logging
        """
        self.mode = mode
        self.claude_weight = claude_weight
        self.chatgpt_weight = chatgpt_weight
        self.require_consensus = require_consensus
        self.verbose = verbose
        
        # Initialize agents
        self.claude_agent = None
        self.chatgpt_agent = None
        
        try:
            self.claude_agent = ClaudeAgent(
                api_key=claude_api_key,
                model=claude_model,
                verbose=verbose
            )
            logger.info("✅ Claude agent initialized")
        except Exception as e:
            logger.warning(f"⚠️  Claude agent init failed: {e}")
        
        try:
            self.chatgpt_agent = ChatGPTAgent(
                api_key=chatgpt_api_key,
                model=chatgpt_model,
                verbose=verbose
            )
            logger.info("✅ ChatGPT agent initialized")
        except Exception as e:
            logger.warning(f"⚠️  ChatGPT agent init failed: {e}")
        
        if not self.claude_agent and not self.chatgpt_agent:
            raise ValueError("At least one AI agent must be available")
        
        # Statistics
        self.stats = {
            'total_analyses': 0,
            'consensus_agreements': 0,
            'consensus_disagreements': 0,
            'claude_only': 0,
            'chatgpt_only': 0,
            'both_failed': 0
        }
        
        logger.info(f"✅ HybridAIAgent initialized (mode: {mode})")
    
    def analyze_setup(self, market_state: Dict, signal: Optional[Dict] = None,
                     filter_results: Optional[Dict] = None) -> Dict:
        """
        Analyze trading setup using both models
        
        Returns:
            Dict with combined analysis, recommendations, and consensus info
        """
        self.stats['total_analyses'] += 1
        
        claude_result = None
        chatgpt_result = None
        
        # Get Claude analysis
        if self.claude_agent:
            try:
                claude_result = self.claude_agent.analyze_setup(
                    market_state, signal, filter_results
                )
            except Exception as e:
                logger.warning(f"Claude analysis failed: {e}")
                claude_result = None
        
        # Get ChatGPT analysis
        if self.chatgpt_agent:
            try:
                chatgpt_result = self.chatgpt_agent.analyze_setup(
                    market_state, signal, filter_results
                )
            except Exception as e:
                logger.warning(f"ChatGPT analysis failed: {e}")
                chatgpt_result = None
        
        # Handle results based on mode
        if self.mode == self.FALLBACK_MODE:
            return self._handle_fallback(claude_result, chatgpt_result)
        elif self.mode == self.CONSENSUS_MODE:
            return self._handle_consensus(claude_result, chatgpt_result)
        elif self.mode == self.WEIGHTED_MODE:
            return self._handle_weighted(claude_result, chatgpt_result)
        else:
            return self._handle_majority(claude_result, chatgpt_result)
    
    def _handle_fallback(self, claude_result: Optional[Dict], 
                        chatgpt_result: Optional[Dict]) -> Dict:
        """Fallback mode: Use primary, fallback to secondary"""
        if claude_result:
            self.stats['claude_only'] += 1
            return {
                'recommendation': claude_result['recommendation'],
                'source': 'claude',
                'claude_analysis': claude_result,
                'chatgpt_analysis': chatgpt_result,
                'consensus': False,
                'timestamp': datetime.now().isoformat()
            }
        elif chatgpt_result:
            self.stats['chatgpt_only'] += 1
            return {
                'recommendation': chatgpt_result['recommendation'],
                'source': 'chatgpt',
                'claude_analysis': claude_result,
                'chatgpt_analysis': chatgpt_result,
                'consensus': False,
                'timestamp': datetime.now().isoformat()
            }
        else:
            self.stats['both_failed'] += 1
            return {
                'recommendation': "Both AI models unavailable - cannot analyze",
                'source': 'none',
                'claude_analysis': None,
                'chatgpt_analysis': None,
                'consensus': False,
                'error': 'Both models failed',
                'timestamp': datetime.now().isoformat()
            }
    
    def _handle_consensus(self, claude_result: Optional[Dict], 
                         chatgpt_result: Optional[Dict]) -> Dict:
        """Consensus mode: Both must agree (or use available if only one)"""
        if not claude_result and not chatgpt_result:
            self.stats['both_failed'] += 1
            return {
                'recommendation': "Both AI models unavailable",
                'source': 'none',
                'consensus': False,
                'error': 'Both models failed',
                'timestamp': datetime.now().isoformat()
            }
        
        if not claude_result:
            self.stats['chatgpt_only'] += 1
            return {
                'recommendation': chatgpt_result['recommendation'],
                'source': 'chatgpt',
                'claude_analysis': None,
                'chatgpt_analysis': chatgpt_result,
                'consensus': False,
                'timestamp': datetime.now().isoformat()
            }
        
        if not chatgpt_result:
            self.stats['claude_only'] += 1
            return {
                'recommendation': claude_result['recommendation'],
                'source': 'claude',
                'claude_analysis': claude_result,
                'chatgpt_analysis': None,
                'consensus': False,
                'timestamp': datetime.now().isoformat()
            }
        
        # Both available - check consensus
        claude_rec = self._extract_recommendation(claude_result['recommendation'])
        chatgpt_rec = self._extract_recommendation(chatgpt_result['recommendation'])
        
        consensus = claude_rec == chatgpt_rec
        
        if consensus:
            self.stats['consensus_agreements'] += 1
        else:
            self.stats['consensus_disagreements'] += 1
        
        # Combine recommendations
        combined_rec = self._combine_recommendations(
            claude_result['recommendation'],
            chatgpt_result['recommendation']
        )
        
        return {
            'recommendation': combined_rec,
            'source': 'hybrid',
            'claude_analysis': claude_result,
            'chatgpt_analysis': chatgpt_result,
            'claude_recommendation': claude_rec,
            'chatgpt_recommendation': chatgpt_rec,
            'consensus': consensus,
            'consensus_required': self.require_consensus,
            'timestamp': datetime.now().isoformat()
        }
    
    def _handle_weighted(self, claude_result: Optional[Dict], 
                         chatgpt_result: Optional[Dict]) -> Dict:
        """Weighted mode: Combine based on weights"""
        if not claude_result and not chatgpt_result:
            self.stats['both_failed'] += 1
            return {
                'recommendation': "Both AI models unavailable",
                'source': 'none',
                'consensus': False,
                'error': 'Both models failed',
                'timestamp': datetime.now().isoformat()
            }
        
        # Normalize weights if only one available
        total_weight = 0
        if claude_result:
            total_weight += self.claude_weight
        if chatgpt_result:
            total_weight += self.chatgpt_weight
        
        if total_weight == 0:
            return self._handle_fallback(claude_result, chatgpt_result)
        
        claude_weight_norm = (self.claude_weight / total_weight) if claude_result else 0
        chatgpt_weight_norm = (self.chatgpt_weight / total_weight) if chatgpt_result else 0
        
        # Extract confidence scores
        claude_conf = self._extract_confidence(claude_result['recommendation']) if claude_result else 0
        chatgpt_conf = self._extract_confidence(chatgpt_result['recommendation']) if chatgpt_result else 0
        
        # Weighted confidence
        weighted_conf = (claude_conf * claude_weight_norm + 
                        chatgpt_conf * chatgpt_weight_norm)
        
        # Combine recommendations
        combined_rec = self._combine_recommendations(
            claude_result['recommendation'] if claude_result else "",
            chatgpt_result['recommendation'] if chatgpt_result else ""
        )
        
        return {
            'recommendation': combined_rec,
            'source': 'hybrid_weighted',
            'claude_analysis': claude_result,
            'chatgpt_analysis': chatgpt_result,
            'weighted_confidence': weighted_conf,
            'claude_weight': claude_weight_norm,
            'chatgpt_weight': chatgpt_weight_norm,
            'consensus': False,
            'timestamp': datetime.now().isoformat()
        }
    
    def _handle_majority(self, claude_result: Optional[Dict], 
                         chatgpt_result: Optional[Dict]) -> Dict:
        """Majority mode: Use majority vote (for future expansion)"""
        # For now, same as consensus with 2 models
        return self._handle_consensus(claude_result, chatgpt_result)
    
    def _extract_recommendation(self, text: str) -> str:
        """Extract recommendation (LONG/SHORT/WAIT) from text"""
        text_upper = text.upper()
        if 'LONG' in text_upper and 'SHORT' not in text_upper:
            return 'LONG'
        elif 'SHORT' in text_upper:
            return 'SHORT'
        elif 'WAIT' in text_upper or 'NO TRADE' in text_upper or 'PASS' in text_upper:
            return 'WAIT'
        else:
            return 'UNKNOWN'
    
    def _extract_confidence(self, text: str) -> float:
        """Extract confidence score (1-10) from text"""
        import re
        # Look for "confidence: X" or "X/10" patterns
        patterns = [
            r'confidence[:\s]+(\d+)',
            r'(\d+)/10',
            r'(\d+) out of 10'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except:
                    pass
        
        # Default confidence based on recommendation
        rec = self._extract_recommendation(text)
        if rec == 'WAIT':
            return 3.0
        elif rec == 'UNKNOWN':
            return 5.0
        else:
            return 7.0
    
    def _combine_recommendations(self, claude_text: str, chatgpt_text: str) -> str:
        """Combine recommendations from both models"""
        if not claude_text and not chatgpt_text:
            return "Both models unavailable"
        
        if not claude_text:
            return f"ChatGPT Analysis:\n{chatgpt_text}"
        
        if not chatgpt_text:
            return f"Claude Analysis:\n{claude_text}"
        
        claude_rec = self._extract_recommendation(claude_text)
        chatgpt_rec = self._extract_recommendation(chatgpt_text)
        
        combined = f"""HYBRID AI ANALYSIS (Claude + ChatGPT)

Claude Recommendation: {claude_rec}
ChatGPT Recommendation: {chatgpt_rec}

Claude Analysis:
{claude_text}

ChatGPT Analysis:
{chatgpt_text}

Consensus: {'✅ AGREEMENT' if claude_rec == chatgpt_rec else '⚠️ DISAGREEMENT'}
"""
        return combined
    
    def debug_signals(self, market_state: Dict, strategy: str = "breakout", 
                     btc_market_state: Optional[Dict] = None) -> Dict:
        """Debug signals using both models"""
        results = {}
        
        if self.claude_agent:
            try:
                results['claude'] = self.claude_agent.debug_signals(
                    market_state, strategy, btc_market_state
                )
            except Exception as e:
                logger.warning(f"Claude debug failed: {e}")
        
        if self.chatgpt_agent:
            try:
                results['chatgpt'] = self.chatgpt_agent.debug_signals(
                    market_state, strategy, btc_market_state
                )
            except Exception as e:
                logger.warning(f"ChatGPT debug failed: {e}")
        
        return {
            'analyses': results,
            'timestamp': datetime.now().isoformat()
        }
    
    def explain_filter_rejection(self, filter_name: str, filter_result: Dict,
                                market_state: Dict) -> Dict:
        """Explain filter rejection using both models"""
        results = {}
        
        if self.claude_agent:
            try:
                results['claude'] = self.claude_agent.explain_filter_rejection(
                    filter_name, filter_result, market_state
                )
            except Exception as e:
                logger.warning(f"Claude explanation failed: {e}")
        
        if self.chatgpt_agent:
            try:
                results['chatgpt'] = self.chatgpt_agent.explain_filter_rejection(
                    filter_name, filter_result, market_state
                )
            except Exception as e:
                logger.warning(f"ChatGPT explanation failed: {e}")
        
        return {
            'explanations': results,
            'timestamp': datetime.now().isoformat()
        }
    
    def analyze_backtest_results(self, backtest_results: Dict) -> Dict:
        """Analyze backtest results using both models"""
        results = {}
        
        if self.claude_agent:
            try:
                results['claude'] = self.claude_agent.analyze_backtest_results(backtest_results)
            except Exception as e:
                logger.warning(f"Claude backtest analysis failed: {e}")
        
        if self.chatgpt_agent:
            try:
                results['chatgpt'] = self.chatgpt_agent.analyze_backtest_results(backtest_results)
            except Exception as e:
                logger.warning(f"ChatGPT backtest analysis failed: {e}")
        
        return {
            'analyses': results,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_stats(self) -> Dict:
        """Get hybrid agent statistics"""
        stats = self.stats.copy()
        
        if self.claude_agent:
            stats['claude_usage'] = self.claude_agent.get_token_usage()
            stats['claude_health'] = self.claude_agent.get_health_status()
        
        if self.chatgpt_agent:
            stats['chatgpt_usage'] = self.chatgpt_agent.get_token_usage()
            stats['chatgpt_health'] = self.chatgpt_agent.get_health_status()
        
        if stats['total_analyses'] > 0:
            stats['consensus_rate'] = (
                stats['consensus_agreements'] / 
                (stats['consensus_agreements'] + stats['consensus_disagreements'])
                if (stats['consensus_agreements'] + stats['consensus_disagreements']) > 0
                else 0
            )
        
        return stats
    
    def get_health_status(self) -> Dict:
        """Get health status of hybrid agent"""
        claude_healthy = self.claude_agent.get_health_status()['is_healthy'] if self.claude_agent else False
        chatgpt_healthy = self.chatgpt_agent.get_health_status()['is_healthy'] if self.chatgpt_agent else False
        
        return {
            'claude_available': self.claude_agent is not None,
            'chatgpt_available': self.chatgpt_agent is not None,
            'claude_healthy': claude_healthy,
            'chatgpt_healthy': chatgpt_healthy,
            'is_healthy': claude_healthy or chatgpt_healthy,  # At least one healthy
            'mode': self.mode,
            'stats': self.get_stats()
        }
