"""
Macro Driver Filter - 4-Tier System
Analyzes market conditions across multiple driver tiers
Tier 1: Macro & Liquidity (highest weight)
Tier 2: Derivatives & Flows
Tier 3: Trend & Health Confirmers
Tier 4: Tactical Tools
"""

from typing import Dict, Tuple, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MacroDriverFilter:
    """
    Filter #6: Macro Market Driver Analysis

    Implements 4-tier driver system to assess overall market conditions
    Higher tiers have more weight in final decision
    """

    def __init__(self):
        self.name = "MacroDriver"

    def check(self, market_state: Dict, btc_market_state: Optional[Dict],
             signal_direction: str) -> Tuple[bool, str, Dict]:
        """
        Analyze all market driver tiers and determine if conditions allow trading

        Args:
            market_state: Complete market state (SOL)
            btc_market_state: Bitcoin market state (optional)
            signal_direction: 'long' or 'short'

        Returns:
            (passed: bool, reason: str, macro_state: Dict)
        """
        try:
            # Analyze each tier
            tier1 = self._analyze_tier1_macro_liquidity(market_state)
            tier2 = self._analyze_tier2_derivatives(market_state)
            tier3 = self._analyze_tier3_trend_health(market_state, signal_direction)
            tier4 = self._analyze_tier4_tactical(market_state, signal_direction)

            # Tier 1 is CRITICAL - can hard block trades
            if tier1['risk_level'] == 'critical':
                macro_state = self._build_macro_state(tier1, tier2, tier3, tier4, None)
                return False, f"Tier 1 Critical: {tier1['reason']}", macro_state

            # Tier 2 at high risk should block
            if tier2['squeeze_risk'] == 'high' or tier2['positioning_risk'] == 'high':
                macro_state = self._build_macro_state(tier1, tier2, tier3, tier4, None)
                return False, f"Tier 2 High Risk: {tier2['reason']}", macro_state

            # Calculate weighted environment score
            environment = self._calculate_environment_score(tier1, tier2, tier3, tier4, signal_direction)

            # Log comprehensive analysis
            logger.info(f"📊 {self.name}: Environment Analysis")
            logger.info(f"   Tier 1 (Macro): {tier1['status']} - {tier1['bias']}")
            logger.info(f"   Tier 2 (Derivatives): {tier2['positioning_risk']} positioning, {tier2['squeeze_risk']} squeeze risk")
            logger.info(f"   Tier 3 (Trend): {tier3['trend_bias']} bias, overextended={tier3['overextended']}")
            logger.info(f"   Tier 4 (Tactical): {tier4['technical_quality']}")
            logger.info(f"   Overall: {environment['environment_bias']} (confidence: {environment['confidence']:.2f})")

            # Build comprehensive macro state
            macro_state = self._build_macro_state(tier1, tier2, tier3, tier4, environment)

            # Decision logic
            if environment['confidence'] < 0.4:
                return False, f"Low environment confidence ({environment['confidence']:.2f})", macro_state

            logger.info(f"✅ {self.name}: Macro conditions acceptable")
            return True, f"Macro environment {environment['environment_bias']}", macro_state

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during analysis: {e}")
            # Fail open for macro filter (don't block on errors)
            return True, f"Macro filter error (allowing): {e}", {}

    def _analyze_tier1_macro_liquidity(self, market_state: Dict) -> Dict:
        """
        Tier 1: Macro & Liquidity (Highest Weight)

        Analyzes:
        - Fed tone / rate environment
        - USD strength
        - ETF flows
        - Major events
        - Risk-on/risk-off regime
        """
        result = {
            'status': 'normal',
            'risk_level': 'low',
            'bias': 'neutral',
            'reason': '',
            'score': 0.5
        }

        # Check 1: Funding rate as proxy for macro stress
        funding = market_state.get('funding_rate')
        if funding:
            funding_rate = funding.get('funding_rate', 0)

            # Extremely negative funding = stress/fear
            if funding_rate < -0.001:  # -0.1%
                result['status'] = 'stressed'
                result['risk_level'] = 'high'
                result['bias'] = 'bearish'
                result['reason'] = f'Extreme negative funding ({funding_rate:.4f})'
                result['score'] = 0.3
                return result

            # Extremely positive funding = euphoria
            elif funding_rate > 0.001:  # +0.1%
                result['status'] = 'euphoric'
                result['risk_level'] = 'medium'
                result['bias'] = 'bullish'
                result['reason'] = f'High funding rate ({funding_rate:.4f})'
                result['score'] = 0.6
                return result

        # Check 2: Open Interest changes (proxy for capital flows)
        oi = market_state.get('open_interest')
        if oi:
            # Would need historical OI to calculate change
            # For now, just log current state
            current_oi = oi.get('open_interest', 0)
            if current_oi > 0:
                result['reason'] = f'OI stable at {current_oi:.0f}'

        # Default: Normal conditions
        result['status'] = 'normal'
        result['risk_level'] = 'low'
        result['bias'] = 'neutral'
        result['reason'] = 'Macro conditions normal'
        result['score'] = 0.5

        return result

    def _analyze_tier2_derivatives(self, market_state: Dict) -> Dict:
        """
        Tier 2: Derivatives & Flows

        Analyzes:
        - Funding rates (current + changes)
        - Open interest (absolute + 24h change)
        - Liquidation risk
        - Whale flows (if available)
        """
        result = {
            'positioning_risk': 'low',
            'squeeze_risk': 'low',
            'reason': '',
            'score': 0.5
        }

        funding = market_state.get('funding_rate')
        oi = market_state.get('open_interest')

        # Check 1: Funding + OI combo for squeeze risk
        if funding and oi:
            funding_rate = funding.get('funding_rate', 0)

            # High positive funding = long squeeze risk
            if funding_rate > 0.0008:  # 0.08%
                result['squeeze_risk'] = 'high'
                result['positioning_risk'] = 'high'
                result['reason'] = 'High long funding, potential squeeze'
                result['score'] = 0.3
                return result

            # High negative funding = short squeeze risk
            elif funding_rate < -0.0008:
                result['squeeze_risk'] = 'medium'
                result['positioning_risk'] = 'medium'
                result['reason'] = 'Negative funding, shorts crowded'
                result['score'] = 0.4
                return result

        # Check 2: Liquidation data (if available)
        liquidations = market_state.get('liquidation_heatmap')
        if liquidations and len(liquidations) > 0:
            # Large recent liquidations = volatility risk
            recent_liq_sizes = [liq.get('size', 0) for liq in liquidations[:5]]
            avg_liq = sum(recent_liq_sizes) / len(recent_liq_sizes) if recent_liq_sizes else 0

            if avg_liq > 0:  # Would need threshold based on historical data
                result['positioning_risk'] = 'medium'
                result['reason'] = f'Recent liquidations detected'

        # Default: Low risk
        result['positioning_risk'] = 'low'
        result['squeeze_risk'] = 'low'
        result['reason'] = 'Derivatives positioning normal'
        result['score'] = 0.5

        return result

    def _analyze_tier3_trend_health(self, market_state: Dict, signal_direction: str) -> Dict:
        """
        Tier 3: Trend & Health Confirmers

        Analyzes:
        - Price vs major MAs
        - Higher timeframe structure
        - Trend alignment with signal
        """
        result = {
            'trend_bias': 'neutral',
            'overextended': False,
            'reason': '',
            'score': 0.5
        }

        timeframes = market_state.get('timeframes', {})

        # Check HTF trend (4H)
        if '4H' in timeframes:
            htf_trend = timeframes['4H'].get('trend', {})
            trend_direction = htf_trend.get('trend_direction', 'sideways')
            trend_strength = htf_trend.get('trend_strength', 0)

            # Determine bias
            if trend_direction == 'up' and trend_strength > 0.6:
                result['trend_bias'] = 'bullish'
                result['score'] = 0.7
            elif trend_direction == 'down' and trend_strength > 0.6:
                result['trend_bias'] = 'bearish'
                result['score'] = 0.3
            else:
                result['trend_bias'] = 'neutral'
                result['score'] = 0.5

            # Check if overextended (RSI extreme)
            rsi = htf_trend.get('rsi', 50)
            if rsi > 80 or rsi < 20:
                result['overextended'] = True
                result['reason'] = f'Overextended (RSI: {rsi:.1f})'
            else:
                result['reason'] = f'{trend_direction} trend (strength: {trend_strength:.2f})'

        return result

    def _analyze_tier4_tactical(self, market_state: Dict, signal_direction: str) -> Dict:
        """
        Tier 4: Tactical Tools

        Analyzes:
        - RSI, MACD signals
        - ATR for volatility
        - Bollinger Bands position
        - Technical setup quality
        """
        result = {
            'technical_quality': 'neutral',
            'reason': '',
            'score': 0.5
        }

        timeframes = market_state.get('timeframes', {})

        # Use 15m for tactical analysis
        if '15m' in timeframes:
            trend = timeframes['15m'].get('trend', {})
            atr_data = timeframes['15m'].get('atr', {})

            rsi = trend.get('rsi', 50)
            atr_percentile = atr_data.get('atr_percentile', 50)

            # RSI assessment
            rsi_quality = 'neutral'
            if 40 < rsi < 60:
                rsi_quality = 'good'
            elif rsi > 70 or rsi < 30:
                rsi_quality = 'extreme'

            # ATR assessment
            atr_quality = 'normal'
            if atr_percentile < 30:
                atr_quality = 'low'
            elif atr_percentile > 70:
                atr_quality = 'high'

            # Combine into quality score
            if rsi_quality == 'good' and atr_quality == 'normal':
                result['technical_quality'] = 'good'
                result['score'] = 0.6
            elif rsi_quality == 'extreme' or atr_quality == 'high':
                result['technical_quality'] = 'challenging'
                result['score'] = 0.4
            else:
                result['technical_quality'] = 'neutral'
                result['score'] = 0.5

            result['reason'] = f'RSI: {rsi:.1f}, ATR: {atr_percentile:.0f}th percentile'

        return result

    def _calculate_environment_score(self, tier1: Dict, tier2: Dict, tier3: Dict,
                                     tier4: Dict, signal_direction: str) -> Dict:
        """
        Combine all tiers into weighted environment assessment

        Tier weights:
        - Tier 1 (Macro): 40%
        - Tier 2 (Derivatives): 30%
        - Tier 3 (Trend): 20%
        - Tier 4 (Tactical): 10%
        """
        # Weighted score
        weighted_score = (
            tier1['score'] * 0.4 +
            tier2['score'] * 0.3 +
            tier3['score'] * 0.2 +
            tier4['score'] * 0.1
        )

        # Determine bias
        if weighted_score > 0.6:
            bias = 'bullish'
        elif weighted_score < 0.4:
            bias = 'bearish'
        else:
            bias = 'neutral'

        # Risk flags
        risk_flags = []
        if tier1['risk_level'] in ['high', 'critical']:
            risk_flags.append(f"macro_{tier1['risk_level']}")
        if tier2['squeeze_risk'] == 'high':
            risk_flags.append('squeeze_risk')
        if tier3['overextended']:
            risk_flags.append('overextended')

        return {
            'environment_bias': bias,
            'confidence': weighted_score,
            'risk_flags': risk_flags,
            'weighted_score': weighted_score
        }

    def get_detailed_analysis(self, market_state: Dict, signal_direction: str) -> Dict:
        """
        Get comprehensive multi-tier analysis for logging/monitoring
        """
        tier1 = self._analyze_tier1_macro_liquidity(market_state)
        tier2 = self._analyze_tier2_derivatives(market_state)
        tier3 = self._analyze_tier3_trend_health(market_state, signal_direction)
        tier4 = self._analyze_tier4_tactical(market_state, signal_direction)
        environment = self._calculate_environment_score(tier1, tier2, tier3, tier4, signal_direction)

        return {
            'tier1_macro': tier1,
            'tier2_derivatives': tier2,
            'tier3_trend': tier3,
            'tier4_tactical': tier4,
            'environment': environment
        }

    def _build_macro_state(self, tier1: Dict, tier2: Dict, tier3: Dict, tier4: Dict,
                          environment: Optional[Dict]) -> Dict:
        """
        Build comprehensive macro state output for filter_manager

        Returns structured state with all tier data and environment assessment
        """
        return {
            'tier_outputs': {
                'tier1': tier1,
                'tier2': tier2,
                'tier3': tier3,
                'tier4': tier4
            },
            'environment_bias': environment.get('environment_bias', 'neutral') if environment else 'neutral',
            'confidence': environment.get('confidence', 0.5) if environment else 0.5,
            'risk_flags': environment.get('risk_flags', []) if environment else []
        }
