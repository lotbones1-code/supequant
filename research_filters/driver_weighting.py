"""
Driver Tier Weighting System
Aggregates 4-tier macro driver analysis into unified market assessment

Combines:
- Tier 1: Macro & Liquidity (40% weight)
- Tier 2: Derivatives & Flows (30% weight)
- Tier 3: Trend & Health (20% weight)
- Tier 4: Tactical Tools (10% weight)

Outputs:
- Overall environment bias (bullish/bearish/neutral)
- Weighted confidence score
- Critical risk flags
- Recommended bias adjustment
"""

from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class DriverTierWeighting:
    """
    Aggregates multi-tier driver analysis into actionable assessment

    Takes input from MacroDriverFilter's 4-tier system and produces:
    - Environment bias with confidence
    - Position sizing recommendations
    - Risk warnings and flags
    """

    def __init__(self):
        self.name = "DriverWeighting"

        # Tier weights (must sum to 1.0)
        self.tier_weights = {
            'tier1': 0.40,  # Macro & Liquidity (most important)
            'tier2': 0.30,  # Derivatives & Flows
            'tier3': 0.20,  # Trend & Health
            'tier4': 0.10   # Tactical Tools
        }

    def aggregate_assessment(self, tier1: Dict, tier2: Dict,
                           tier3: Dict, tier4: Dict,
                           signal_direction: str) -> Dict:
        """
        Aggregate all tiers into unified market assessment

        Args:
            tier1: Macro & Liquidity tier output
            tier2: Derivatives & Flows tier output
            tier3: Trend & Health tier output
            tier4: Tactical Tools tier output
            signal_direction: Proposed trade direction ('long' or 'short')

        Returns:
            Aggregated assessment with bias, confidence, flags, recommendations
        """
        try:
            # Extract scores from each tier (0-100)
            scores = {
                'tier1': tier1.get('score', 50),
                'tier2': tier2.get('score', 50),
                'tier3': tier3.get('score', 50),
                'tier4': tier4.get('score', 50)
            }

            # Calculate weighted total score
            weighted_score = sum(
                scores[tier] * self.tier_weights[tier]
                for tier in scores
            )

            # Determine overall environment bias
            environment_bias = self._determine_environment_bias(
                tier1, tier2, tier3, tier4, weighted_score
            )

            # Calculate confidence in the assessment
            confidence = self._calculate_confidence(
                tier1, tier2, tier3, tier4, weighted_score
            )

            # Aggregate all risk flags
            risk_flags = self._aggregate_risk_flags(tier1, tier2, tier3, tier4)

            # Check alignment with proposed trade direction
            alignment = self._check_trade_alignment(
                environment_bias, signal_direction, confidence
            )

            # Calculate position size adjustment
            size_multiplier = self._calculate_size_multiplier(
                weighted_score, confidence, risk_flags, alignment
            )

            assessment = {
                'weighted_score': weighted_score,
                'environment_bias': environment_bias,
                'confidence': confidence,
                'risk_flags': risk_flags,
                'trade_alignment': alignment,
                'size_multiplier': size_multiplier,
                'tier_scores': scores,
                'tier_breakdown': {
                    'tier1': tier1.get('bias', 'neutral'),
                    'tier2': tier2.get('bias', 'neutral'),
                    'tier3': tier3.get('bias', 'neutral'),
                    'tier4': tier4.get('bias', 'neutral')
                }
            }

            logger.info(
                f"⚖️  {self.name}: Score={weighted_score:.1f}, Bias={environment_bias}, "
                f"Confidence={confidence:.2f}, Alignment={alignment['aligned']}, "
                f"SizeMultiplier={size_multiplier:.2f}"
            )

            return assessment

        except Exception as e:
            logger.error(f"❌ {self.name}: Error aggregating tiers: {e}")
            # Return neutral assessment on error
            return self._neutral_assessment()

    def _determine_environment_bias(self, tier1: Dict, tier2: Dict,
                                   tier3: Dict, tier4: Dict,
                                   weighted_score: float) -> str:
        """
        Determine overall environment bias based on tier outputs

        Prioritizes higher-weighted tiers (Tier 1 > Tier 2 > Tier 3 > Tier 4)
        """
        # Extract biases from each tier
        t1_bias = tier1.get('bias', 'neutral')
        t2_bias = tier2.get('bias', 'neutral')
        t3_bias = tier3.get('bias', 'neutral')
        t4_bias = tier4.get('bias', 'neutral')

        # If Tier 1 (40% weight) has strong view, it dominates
        t1_score = tier1.get('score', 50)
        if t1_score > 70:
            return t1_bias
        elif t1_score < 30:
            return t1_bias

        # Otherwise, use weighted score
        if weighted_score > 60:
            return 'bullish'
        elif weighted_score < 40:
            return 'bearish'
        else:
            return 'neutral'

    def _calculate_confidence(self, tier1: Dict, tier2: Dict,
                             tier3: Dict, tier4: Dict,
                             weighted_score: float) -> float:
        """
        Calculate confidence in the aggregated assessment (0-1)

        Higher confidence when:
        - Tiers are aligned
        - Tier 1 is decisive
        - No conflicting signals
        """
        confidence = 0.5  # Start neutral

        # Factor 1: Tier alignment (+0.3)
        biases = [
            tier1.get('bias', 'neutral'),
            tier2.get('bias', 'neutral'),
            tier3.get('bias', 'neutral'),
            tier4.get('bias', 'neutral')
        ]

        # Count consensus
        bullish_count = biases.count('bullish')
        bearish_count = biases.count('bearish')
        neutral_count = biases.count('neutral')

        max_agreement = max(bullish_count, bearish_count, neutral_count)
        alignment_score = max_agreement / 4  # 0.25 to 1.0

        confidence += alignment_score * 0.3

        # Factor 2: Tier 1 confidence (+0.3)
        t1_confidence = tier1.get('confidence', 0.5)
        confidence += t1_confidence * 0.3

        # Factor 3: Decisiveness of weighted score (+0.2)
        # Scores near 50 are indecisive
        decisiveness = abs(weighted_score - 50) / 50  # 0 to 1
        confidence += decisiveness * 0.2

        # Factor 4: Absence of major risk flags (+0.2)
        t1_flags = len(tier1.get('flags', []))
        if t1_flags == 0:
            confidence += 0.2
        elif t1_flags > 2:
            confidence -= 0.1

        return max(0, min(1.0, confidence))

    def _aggregate_risk_flags(self, tier1: Dict, tier2: Dict,
                             tier3: Dict, tier4: Dict) -> List[str]:
        """
        Collect all risk flags from all tiers

        Prioritizes critical Tier 1 flags
        """
        flags = []

        # Tier 1 flags are critical
        t1_flags = tier1.get('flags', [])
        for flag in t1_flags:
            flags.append(f"[T1-CRITICAL] {flag}")

        # Tier 2 flags are important
        t2_flags = tier2.get('flags', [])
        for flag in t2_flags:
            flags.append(f"[T2] {flag}")

        # Tier 3 flags are warnings
        t3_flags = tier3.get('flags', [])
        for flag in t3_flags:
            flags.append(f"[T3] {flag}")

        # Tier 4 flags are informational
        t4_flags = tier4.get('flags', [])
        for flag in t4_flags:
            flags.append(f"[T4] {flag}")

        return flags

    def _check_trade_alignment(self, environment_bias: str,
                              signal_direction: str,
                              confidence: float) -> Dict:
        """
        Check if proposed trade aligns with environment assessment

        Returns alignment status and recommendation
        """
        aligned = False
        recommendation = ""

        if environment_bias == 'neutral':
            aligned = True  # Neutral allows both directions
            recommendation = "Environment neutral, proceed with caution"

        elif environment_bias == 'bullish':
            if signal_direction == 'long':
                aligned = True
                recommendation = "Bullish environment supports long trade"
            else:
                aligned = False if confidence > 0.6 else True
                recommendation = "Warning: Short against bullish environment" if not aligned else "Weak bullish, short allowed"

        elif environment_bias == 'bearish':
            if signal_direction == 'short':
                aligned = True
                recommendation = "Bearish environment supports short trade"
            else:
                aligned = False if confidence > 0.6 else True
                recommendation = "Warning: Long against bearish environment" if not aligned else "Weak bearish, long allowed"

        return {
            'aligned': aligned,
            'recommendation': recommendation,
            'environment_bias': environment_bias,
            'trade_direction': signal_direction,
            'confidence': confidence
        }

    def _calculate_size_multiplier(self, weighted_score: float,
                                  confidence: float,
                                  risk_flags: List[str],
                                  alignment: Dict) -> float:
        """
        Calculate position size multiplier based on environment quality

        Returns multiplier (0.0 to 1.0):
        - 1.0 = Full size
        - 0.5-0.8 = Reduced size
        - 0.0 = Block trade
        """
        multiplier = 1.0

        # Factor 1: Trade alignment
        if not alignment['aligned']:
            multiplier *= 0.5  # Cut size in half for misaligned trades

        # Factor 2: Confidence
        if confidence < 0.4:
            multiplier *= 0.6  # Reduce size for low confidence
        elif confidence > 0.7:
            multiplier *= 1.0  # No reduction for high confidence

        # Factor 3: Risk flags
        critical_flags = [f for f in risk_flags if '[T1-CRITICAL]' in f]
        if len(critical_flags) >= 2:
            return 0.0  # Block trade on multiple critical flags

        if len(critical_flags) == 1:
            multiplier *= 0.4  # Heavy reduction on single critical flag

        if len(risk_flags) > 3:
            multiplier *= 0.7  # Moderate reduction for multiple warnings

        # Factor 4: Score extremes
        if weighted_score > 75 or weighted_score < 25:
            # Extreme scores = high conviction
            multiplier *= 1.1  # Slight boost (capped at 1.0 later)
        elif 45 <= weighted_score <= 55:
            # Indecisive scores
            multiplier *= 0.7

        # Cap multiplier between 0 and 1
        return max(0.0, min(1.0, multiplier))

    def _neutral_assessment(self) -> Dict:
        """Return neutral assessment on errors"""
        return {
            'weighted_score': 50.0,
            'environment_bias': 'neutral',
            'confidence': 0.5,
            'risk_flags': [],
            'trade_alignment': {
                'aligned': True,
                'recommendation': 'Neutral assessment (error fallback)',
                'environment_bias': 'neutral',
                'trade_direction': 'unknown',
                'confidence': 0.5
            },
            'size_multiplier': 0.7,  # Conservative on errors
            'tier_scores': {
                'tier1': 50,
                'tier2': 50,
                'tier3': 50,
                'tier4': 50
            },
            'tier_breakdown': {
                'tier1': 'neutral',
                'tier2': 'neutral',
                'tier3': 'neutral',
                'tier4': 'neutral'
            }
        }

    def format_report(self, assessment: Dict) -> str:
        """
        Format assessment as human-readable report
        """
        lines = [
            "=" * 60,
            f"DRIVER TIER AGGREGATION REPORT",
            "=" * 60,
            f"Overall Score: {assessment['weighted_score']:.1f}/100",
            f"Environment Bias: {assessment['environment_bias'].upper()}",
            f"Confidence: {assessment['confidence']:.1%}",
            "",
            "Tier Breakdown:",
            f"  T1 (Macro & Liquidity, 40%): {assessment['tier_scores']['tier1']:.1f} - {assessment['tier_breakdown']['tier1']}",
            f"  T2 (Derivatives & Flows, 30%): {assessment['tier_scores']['tier2']:.1f} - {assessment['tier_breakdown']['tier2']}",
            f"  T3 (Trend & Health, 20%): {assessment['tier_scores']['tier3']:.1f} - {assessment['tier_breakdown']['tier3']}",
            f"  T4 (Tactical Tools, 10%): {assessment['tier_scores']['tier4']:.1f} - {assessment['tier_breakdown']['tier4']}",
            "",
            f"Trade Alignment: {'✅ ALIGNED' if assessment['trade_alignment']['aligned'] else '⚠️  MISALIGNED'}",
            f"  {assessment['trade_alignment']['recommendation']}",
            "",
            f"Position Size Multiplier: {assessment['size_multiplier']:.1%}",
        ]

        if assessment['risk_flags']:
            lines.append("")
            lines.append("Risk Flags:")
            for flag in assessment['risk_flags']:
                lines.append(f"  ⚠️  {flag}")

        lines.append("=" * 60)

        return "\n".join(lines)
