"""
Trading Checklist Filter
Converts manual trading checklist into automated scoring system

Aggregates multiple signals into a 0-100 checklist score:
- Macro/geopolitical risk (from macro driver filter)
- Market sentiment (fear & greed, risk appetite)
- Market structure & trend quality
- AI model agreement (ensemble consensus)
- Flow data (ETF, institutional)
- Social sentiment (Twitter, Reddit, news)

Thresholds:
- < 60: Block trade
- 60-80: Reduce position size
- > 80: Full size allowed
"""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class TradingChecklistFilter:
    """
    Automated trading checklist scorer

    Aggregates all available market intelligence into single quality score
    """

    def __init__(self, config):
        self.name = "TradingChecklist"
        self.config = config

        # Thresholds
        self.block_threshold = config.get('CHECKLIST_BLOCK_THRESHOLD', 60)
        self.reduce_threshold = config.get('CHECKLIST_REDUCE_THRESHOLD', 80)

        # Component weights (must sum to 1.0)
        self.weights = {
            'macro_risk': 0.25,      # Geopolitical, liquidity environment
            'sentiment': 0.20,        # Fear & greed, risk appetite
            'structure': 0.25,        # Trend quality, market structure
            'ai_agreement': 0.15,     # Model consensus
            'flows': 0.10,            # ETF, institutional flows
            'social': 0.05            # Social sentiment
        }

    def check(self, market_state: Dict, macro_state: Optional[Dict] = None,
             ai_signals: Optional[Dict] = None) -> Tuple[bool, str, Dict]:
        """
        Calculate checklist score and determine trade approval

        Returns:
            - passed (bool): Whether checklist allows trade
            - reason (str): Explanation
            - details (dict): Breakdown of score
        """
        try:
            # Calculate each component score (0-100)
            scores = {
                'macro_risk': self._score_macro_risk(macro_state),
                'sentiment': self._score_sentiment(market_state),
                'structure': self._score_market_structure(market_state),
                'ai_agreement': self._score_ai_agreement(ai_signals),
                'flows': self._score_flows(market_state),
                'social': self._score_social_sentiment(market_state)
            }

            # Calculate weighted total score
            total_score = sum(
                scores[component] * self.weights[component]
                for component in scores
            )

            # Determine action based on thresholds
            if total_score < self.block_threshold:
                passed = False
                action = "BLOCK"
                reason = f"Checklist score too low ({total_score:.1f} < {self.block_threshold})"
            elif total_score < self.reduce_threshold:
                passed = True
                action = "REDUCE_SIZE"
                reason = f"Checklist marginal ({total_score:.1f}), reduce position size"
            else:
                passed = True
                action = "FULL_SIZE"
                reason = f"Checklist strong ({total_score:.1f} ≥ {self.reduce_threshold})"

            details = {
                'total_score': total_score,
                'action': action,
                'component_scores': scores,
                'weights': self.weights
            }

            logger.info(
                f"📋 {self.name}: Score={total_score:.1f}, Action={action} "
                f"(Macro:{scores['macro_risk']:.0f}, Sentiment:{scores['sentiment']:.0f}, "
                f"Structure:{scores['structure']:.0f}, AI:{scores['ai_agreement']:.0f})"
            )

            return passed, reason, details

        except Exception as e:
            logger.error(f"❌ {self.name}: Error calculating checklist: {e}")
            # Fail open - allow trade but with warning
            return True, f"Checklist error (allowed): {e}", {}

    def _score_macro_risk(self, macro_state: Optional[Dict]) -> float:
        """
        Score macro/geopolitical risk environment (0-100)

        Uses macro driver filter output:
        - High risk flags → lower score
        - Favorable liquidity → higher score
        - Stable regime → higher score
        """
        if not macro_state:
            # No macro data available, assume neutral
            return 60.0

        score = 70.0  # Start neutral-positive

        # Check risk flags
        risk_flags = macro_state.get('risk_flags', [])
        if 'liquidity_crisis' in risk_flags:
            score -= 30
        if 'credit_stress' in risk_flags:
            score -= 20
        if 'vol_regime_spike' in risk_flags:
            score -= 15
        if 'recession_signal' in risk_flags:
            score -= 25

        # Bonus for favorable conditions
        if macro_state.get('environment_bias') == 'bullish':
            score += 15
        elif macro_state.get('environment_bias') == 'bearish':
            score -= 15

        # Confidence adjustment
        confidence = macro_state.get('confidence', 0.5)
        if confidence < 0.3:
            score -= 10  # Low confidence in macro read

        return max(0, min(100, score))

    def _score_sentiment(self, market_state: Dict) -> float:
        """
        Score market sentiment (0-100)

        Factors:
        - Fear & Greed Index (if available)
        - Risk appetite indicators
        - Volatility regime
        - Market breadth
        """
        score = 60.0  # Start neutral

        timeframes = market_state.get('timeframes', {})

        # Check volatility regime
        if '15m' in timeframes:
            vol_data = timeframes['15m'].get('volatility', {})
            vol_regime = vol_data.get('volatility_regime', 'normal')

            if vol_regime == 'low':
                score += 10  # Calm market, good for entries
            elif vol_regime == 'extreme':
                score -= 20  # Panic/euphoria, dangerous

        # Check funding rate (sentiment proxy for crypto)
        if 'funding_rate' in market_state:
            funding = market_state['funding_rate']
            if abs(funding) > 0.001:  # 0.1% funding
                # Extreme funding = overstretched sentiment
                score -= 15
            elif abs(funding) < 0.0003:  # Low funding = balanced
                score += 10

        # Check open interest trend
        if 'open_interest_change' in market_state:
            oi_change = market_state['open_interest_change']
            if oi_change > 0.2:  # 20% OI spike
                score -= 10  # Overcrowded trade

        # TODO: Integrate actual Fear & Greed Index when available
        # TODO: Add social sentiment scores (Twitter, Reddit)

        return max(0, min(100, score))

    def _score_market_structure(self, market_state: Dict) -> float:
        """
        Score market structure and trend quality (0-100)

        Factors:
        - Trend strength and consistency
        - Clean price action vs choppy
        - Support/resistance respect
        - Structural integrity
        """
        score = 50.0  # Start neutral

        timeframes = market_state.get('timeframes', {})

        # Check 4H trend (primary timeframe)
        if '4H' in timeframes:
            tf_4h = timeframes['4H']

            # Trend quality
            trend = tf_4h.get('trend', {})
            trend_strength = trend.get('trend_strength', 0)
            trend_direction = trend.get('trend_direction', 'sideways')

            if trend_direction in ['up', 'down']:
                # Strong trend = good structure
                score += trend_strength * 30  # Up to +30 for strong trend
            else:
                # Sideways = poor structure for trend trading
                score -= 20

            # Check for clean price action (low wicks, consistent candles)
            candles = tf_4h.get('candles', [])
            if len(candles) >= 10:
                recent = candles[-10:]

                # Calculate average wick ratio
                wick_ratios = []
                for c in recent:
                    body = abs(c['close'] - c['open'])
                    total = c['high'] - c['low']
                    if total > 0:
                        wick_ratio = (total - body) / total
                        wick_ratios.append(wick_ratio)

                if wick_ratios:
                    avg_wick = sum(wick_ratios) / len(wick_ratios)
                    if avg_wick < 0.3:
                        score += 15  # Clean candles, strong conviction
                    elif avg_wick > 0.6:
                        score -= 15  # Wicky candles, indecision

        # Check 1H structure alignment
        if '1H' in timeframes:
            tf_1h = timeframes['1H']
            trend_1h = tf_1h.get('trend', {})

            # If 1H and 4H aligned, bonus points
            if '4H' in timeframes:
                trend_4h = timeframes['4H'].get('trend', {})
                if (trend_1h.get('trend_direction') == trend_4h.get('trend_direction')
                    and trend_1h.get('trend_direction') in ['up', 'down']):
                    score += 20  # Strong multi-timeframe alignment

        # Check for recent pattern failures (trap detection)
        pattern_data = market_state.get('recent_patterns', {})
        if pattern_data.get('recent_trap_detected', False):
            score -= 25  # Recent fake-out, poor structure

        return max(0, min(100, score))

    def _score_ai_agreement(self, ai_signals: Optional[Dict]) -> float:
        """
        Score AI model consensus (0-100)

        When multiple models/strategies agree, confidence increases
        For now, placeholder implementation
        """
        if not ai_signals:
            # No AI signals available, neutral
            return 60.0

        score = 50.0

        # Check model confidence
        confidence = ai_signals.get('confidence', 0.5)
        score += confidence * 40  # Up to +40 for high confidence

        # Check ensemble agreement (if available)
        if 'ensemble_agreement' in ai_signals:
            agreement = ai_signals['ensemble_agreement']  # 0-1
            score += agreement * 30  # Up to +30 for full agreement

        # Check historical accuracy
        if 'recent_accuracy' in ai_signals:
            accuracy = ai_signals['recent_accuracy']
            if accuracy > 0.65:
                score += 20
            elif accuracy < 0.45:
                score -= 20

        return max(0, min(100, score))

    def _score_flows(self, market_state: Dict) -> float:
        """
        Score institutional/ETF flows (0-100)

        Placeholder: Will integrate when flow data available
        """
        score = 60.0  # Start neutral

        # TODO: Integrate actual flow data when available
        # - ETF inflows/outflows
        # - Institutional activity
        # - Whale wallet movements
        # - Exchange flows (deposits/withdrawals)

        # For now, use volume as proxy
        timeframes = market_state.get('timeframes', {})
        if '15m' in timeframes:
            volume = timeframes['15m'].get('volume', {})
            volume_ratio = volume.get('volume_ratio', 1.0)

            if volume_ratio > 1.5:
                score += 15  # Strong volume, institutional participation
            elif volume_ratio < 0.7:
                score -= 15  # Weak volume, lack of conviction

        return max(0, min(100, score))

    def _score_social_sentiment(self, market_state: Dict) -> float:
        """
        Score social media sentiment (0-100)

        Placeholder: Will integrate when sentiment data available
        """
        score = 60.0  # Start neutral

        # TODO: Integrate actual sentiment analysis when available
        # - Twitter sentiment (trending topics, key influencers)
        # - Reddit discussions (r/cryptocurrency, r/solana)
        # - News sentiment
        # - Google Trends

        # For now, return neutral score
        return score

    def get_position_size_multiplier(self, checklist_score: float) -> float:
        """
        Calculate position size multiplier based on checklist score

        Returns:
            - 0.0: Block trade (score < 60)
            - 0.5: Reduce size (score 60-80)
            - 1.0: Full size (score > 80)
        """
        if checklist_score < self.block_threshold:
            return 0.0
        elif checklist_score < self.reduce_threshold:
            # Linear interpolation between 0.5 and 1.0
            pct = (checklist_score - self.block_threshold) / (self.reduce_threshold - self.block_threshold)
            return 0.5 + (pct * 0.5)
        else:
            return 1.0
