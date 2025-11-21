"""
SOL Playbook Engine
Encodes manual SOL trading playbook into automated logic

Implements:
- Long/short setup identification
- Entry zone calculation
- Stop placement (1.5x ATR)
- Target calculation (T1/T2/T3)
- Invalidation conditions
- Confidence scoring
"""

from typing import Dict, Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)


class SOLPlaybookEngine:
    """
    Playbook-based trading logic for SOL

    Converts discretionary playbook rules into systematic checks
    """

    def __init__(self):
        self.name = "SOLPlaybook"

    def analyze(self, market_state: Dict, btc_market_state: Optional[Dict] = None) -> Dict:
        """
        Analyze market state through playbook lens

        Returns playbook assessment with:
        - bias (bullish/bearish/neutral)
        - setup type (long_breakout, long_pullback, short_rejection, short_breakdown, none)
        - entry zone
        - stop zone
        - targets (T1, T2, T3)
        - invalidation conditions
        - confidence (0-1)
        """
        try:
            timeframes = market_state.get('timeframes', {})

            # Get current price and key levels
            current_price = market_state.get('current_price', 0)
            if current_price == 0:
                return self._empty_playbook()

            # Calculate pivot levels (simplified)
            pivot_levels = self._calculate_pivot_levels(timeframes)

            # Get ATR for stop sizing
            atr = self._get_atr(timeframes)

            # Determine market bias
            bias = self._determine_bias(timeframes, current_price, pivot_levels, btc_market_state)

            # Identify setup type
            setup = self._identify_setup(timeframes, current_price, pivot_levels, bias)

            # If no setup, return early
            if setup['type'] == 'none':
                return {
                    'bias': bias,
                    'setup': 'none',
                    'entry_zone': None,
                    'stop_zone': None,
                    'targets': None,
                    'invalidation_conditions': [],
                    'confidence': 0.0,
                    'reason': setup['reason']
                }

            # Calculate entry, stop, targets
            entry_zone = setup['entry_zone']
            stop_zone = self._calculate_stop_zone(setup, atr, pivot_levels)
            targets = self._calculate_targets(setup, entry_zone, stop_zone, pivot_levels)
            invalidations = self._define_invalidations(setup, pivot_levels)
            confidence = self._calculate_confidence(setup, timeframes, pivot_levels)

            playbook_result = {
                'bias': bias,
                'setup': setup['type'],
                'entry_zone': entry_zone,
                'stop_zone': stop_zone,
                'targets': targets,
                'invalidation_conditions': invalidations,
                'confidence': confidence,
                'reason': setup['reason']
            }

            logger.info(f"📖 {self.name}: {bias.upper()} bias, {setup['type']} setup (confidence: {confidence:.2f})")

            return playbook_result

        except Exception as e:
            logger.error(f"❌ {self.name}: Error in analysis: {e}")
            return self._empty_playbook()

    def _empty_playbook(self) -> Dict:
        """Return empty playbook result"""
        return {
            'bias': 'neutral',
            'setup': 'none',
            'entry_zone': None,
            'stop_zone': None,
            'targets': None,
            'invalidation_conditions': [],
            'confidence': 0.0,
            'reason': 'No valid playbook setup'
        }

    def _calculate_pivot_levels(self, timeframes: Dict) -> Dict:
        """
        Calculate pivot, support, resistance levels

        Simplified implementation using recent highs/lows
        """
        if '4H' not in timeframes:
            return {'pivot': 0, 'r1': 0, 's1': 0}

        candles = timeframes['4H'].get('candles', [])
        if len(candles) < 20:
            return {'pivot': 0, 'r1': 0, 's1': 0}

        # Use last 20 candles for pivot calculation
        recent = candles[-20:]
        high = max([c['high'] for c in recent])
        low = min([c['low'] for c in recent])
        close = recent[-1]['close']

        # Classic pivot formula
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high

        return {
            'pivot': pivot,
            'r1': r1,
            's1': s1,
            'swing_high': high,
            'swing_low': low
        }

    def _get_atr(self, timeframes: Dict) -> float:
        """Get current ATR for stop sizing"""
        if '15m' in timeframes:
            atr_data = timeframes['15m'].get('atr', {})
            return atr_data.get('atr', 0)
        return 0

    def _determine_bias(self, timeframes: Dict, current_price: float,
                       pivot_levels: Dict, btc_state: Optional[Dict]) -> str:
        """
        Determine overall market bias: bullish / bearish / neutral

        Factors:
        - Price vs pivot
        - Trend on 1H/4H
        - BTC regime (if available)
        """
        bias = 'neutral'

        # Check price vs pivot
        pivot = pivot_levels.get('pivot', 0)
        if pivot > 0:
            if current_price > pivot * 1.01:  # 1% above
                bias = 'bullish'
            elif current_price < pivot * 0.99:  # 1% below
                bias = 'bearish'

        # Confirm with trend
        if '4H' in timeframes:
            trend = timeframes['4H'].get('trend', {})
            trend_direction = trend.get('trend_direction', 'sideways')
            trend_strength = trend.get('trend_strength', 0)

            if trend_strength > 0.6:
                if trend_direction == 'up':
                    bias = 'bullish'
                elif trend_direction == 'down':
                    bias = 'bearish'

        # Consider BTC if strongly opposing
        if btc_state:
            btc_timeframes = btc_state.get('timeframes', {})
            if '4H' in btc_timeframes:
                btc_trend = btc_timeframes['4H'].get('trend', {})
                btc_direction = btc_trend.get('trend_direction', 'sideways')
                btc_strength = btc_trend.get('trend_strength', 0)

                # If BTC strongly opposite, neutralize bias
                if btc_strength > 0.7:
                    if bias == 'bullish' and btc_direction == 'down':
                        bias = 'neutral'
                    elif bias == 'bearish' and btc_direction == 'up':
                        bias = 'neutral'

        return bias

    def _identify_setup(self, timeframes: Dict, current_price: float,
                       pivot_levels: Dict, bias: str) -> Dict:
        """
        Identify specific setup type based on price action

        Setup types:
        - long_breakout: Breaking above R1 or swing high
        - long_pullback: Pullback to pivot/S1 with support
        - short_rejection: Rejection from pivot/R1
        - short_breakdown: Breaking below S1 or swing low
        - none: No clear setup
        """
        r1 = pivot_levels.get('r1', 0)
        s1 = pivot_levels.get('s1', 0)
        pivot = pivot_levels.get('pivot', 0)
        swing_high = pivot_levels.get('swing_high', 0)
        swing_low = pivot_levels.get('swing_low', 0)

        if not all([r1, s1, pivot]):
            return {'type': 'none', 'reason': 'Missing pivot levels', 'entry_zone': None}

        # LONG SETUPS
        if bias == 'bullish':
            # Breakout above R1
            if current_price > r1 * 1.001:  # 0.1% above R1
                return {
                    'type': 'long_breakout',
                    'reason': f'Breakout above R1 ({r1:.2f})',
                    'entry_zone': [r1, r1 * 1.01],
                    'breakout_level': r1
                }

            # Pullback to pivot
            if pivot * 0.99 < current_price < pivot * 1.01:  # Within 1% of pivot
                return {
                    'type': 'long_pullback',
                    'reason': f'Pullback to pivot ({pivot:.2f})',
                    'entry_zone': [pivot * 0.995, pivot * 1.005],
                    'support_level': pivot
                }

        # SHORT SETUPS
        elif bias == 'bearish':
            # Breakdown below S1
            if current_price < s1 * 0.999:  # 0.1% below S1
                return {
                    'type': 'short_breakdown',
                    'reason': f'Breakdown below S1 ({s1:.2f})',
                    'entry_zone': [s1 * 0.99, s1],
                    'breakdown_level': s1
                }

            # Rejection from pivot
            if pivot * 0.99 < current_price < pivot * 1.01:  # At pivot
                # Check if rejecting (recent wick above)
                if '15m' in timeframes:
                    candles = timeframes['15m'].get('candles', [])
                    if len(candles) >= 3:
                        recent = candles[-3:]
                        max_high = max([c['high'] for c in recent])
                        if max_high > pivot:
                            return {
                                'type': 'short_rejection',
                                'reason': f'Rejection from pivot ({pivot:.2f})',
                                'entry_zone': [pivot * 0.995, pivot * 1.005],
                                'resistance_level': pivot
                            }

        # No setup identified
        return {'type': 'none', 'reason': 'No clear playbook setup', 'entry_zone': None}

    def _calculate_stop_zone(self, setup: Dict, atr: float, pivot_levels: Dict) -> List[float]:
        """
        Calculate stop loss zone (1.5x ATR based)
        """
        entry_zone = setup.get('entry_zone', [0, 0])
        if not entry_zone or atr == 0:
            return [0, 0]

        entry_mid = (entry_zone[0] + entry_zone[1]) / 2

        # 1.5x ATR stop
        if setup['type'] in ['long_breakout', 'long_pullback']:
            stop = entry_mid - (1.5 * atr)
            return [stop * 0.99, stop]  # Small zone around stop
        else:  # Short setups
            stop = entry_mid + (1.5 * atr)
            return [stop, stop * 1.01]

    def _calculate_targets(self, setup: Dict, entry_zone: List[float],
                          stop_zone: List[float], pivot_levels: Dict) -> Dict:
        """
        Calculate T1, T2, T3 targets based on R:R and key levels
        """
        if not entry_zone or not stop_zone:
            return {'t1': 0, 't2': 0, 't3': 0}

        entry = (entry_zone[0] + entry_zone[1]) / 2
        stop = (stop_zone[0] + stop_zone[1]) / 2
        risk = abs(entry - stop)

        if setup['type'] in ['long_breakout', 'long_pullback']:
            t1 = entry + (risk * 1.5)  # 1.5R
            t2 = entry + (risk * 2.5)  # 2.5R
            t3 = entry + (risk * 4.0)  # 4R

            # Adjust targets to key levels if close
            r1 = pivot_levels.get('r1', 0)
            if r1 > 0 and abs(t1 - r1) / r1 < 0.02:  # Within 2%
                t1 = r1

        else:  # Short setups
            t1 = entry - (risk * 1.5)
            t2 = entry - (risk * 2.5)
            t3 = entry - (risk * 4.0)

            # Adjust to key levels
            s1 = pivot_levels.get('s1', 0)
            if s1 > 0 and abs(t1 - s1) / s1 < 0.02:
                t1 = s1

        return {'t1': t1, 't2': t2, 't3': t3}

    def _define_invalidations(self, setup: Dict, pivot_levels: Dict) -> List[str]:
        """
        Define conditions that invalidate the setup
        """
        invalidations = []
        pivot = pivot_levels.get('pivot', 0)

        if setup['type'] in ['long_breakout', 'long_pullback']:
            invalidations.append(f"Price closes below pivot ({pivot:.2f})")
            if 'support_level' in setup:
                invalidations.append(f"Support at {setup['support_level']:.2f} breaks")

        elif setup['type'] in ['short_rejection', 'short_breakdown']:
            invalidations.append(f"Price closes above pivot ({pivot:.2f})")
            if 'resistance_level' in setup:
                invalidations.append(f"Resistance at {setup['resistance_level']:.2f} breaks")

        return invalidations

    def _calculate_confidence(self, setup: Dict, timeframes: Dict, pivot_levels: Dict) -> float:
        """
        Calculate confidence score for the setup (0-1)

        Higher confidence when:
        - Strong trend alignment
        - Clear level respect
        - Volume confirmation
        - BTC not opposing
        """
        confidence = 0.5  # Start neutral

        # Factor 1: Setup clarity (+0.2)
        if setup['type'] != 'none':
            confidence += 0.1

        # Factor 2: Trend alignment (+0.2)
        if '4H' in timeframes:
            trend = timeframes['4H'].get('trend', {})
            trend_strength = trend.get('trend_strength', 0)
            if trend_strength > 0.6:
                confidence += 0.2

        # Factor 3: Volume confirmation (+0.1)
        if '15m' in timeframes:
            volume = timeframes['15m'].get('volume', {})
            volume_ratio = volume.get('volume_ratio', 1.0)
            if volume_ratio > 1.2:
                confidence += 0.1

        # Factor 4: Clean price action (+0.1)
        # (Would check for no recent fakeouts/traps)
        confidence += 0.05

        # Cap at 1.0
        return min(confidence, 1.0)
