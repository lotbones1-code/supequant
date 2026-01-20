"""
BTC-SOL Correlation Filter (Enhanced - Phase 2.2)

Ensures BTC and SOL are aligned before trading SOL.
BTC leads the market, SOL follows - this filter validates the relationship.

Phase 2.2 Enhancements:
- Multi-timeframe price drop analysis (15m, 1H, 4H)
- Velocity detection (flash crash warning)
- Cascade detection (capitulation - consecutive red candles)
- Recovery detection (don't reject bounces)
- Volume confirmation
- Pump protection for shorts (symmetrical)
- Score adjustment system (-25 to +20)
"""

from typing import Dict, Optional, Tuple
import numpy as np
import logging
import config
from config import (
    BTC_SOL_CORRELATION_ENABLED,
    BTC_SOL_MIN_CORRELATION,
    BTC_SOL_TREND_AGREEMENT_REQUIRED,
    BTC_SOL_DIVERGENCE_MAX,
    REFERENCE_SYMBOL
)

logger = logging.getLogger(__name__)


class BTCSOLCorrelationFilter:
    """
    Filter #5: BTC-SOL Correlation (Enhanced)
    
    Validates that Bitcoin and Solana are moving in harmony.
    BTC leads, SOL follows - this ensures the relationship is healthy.
    
    Phase 2.2 adds intelligent dump/pump protection with:
    - Multi-factor analysis across timeframes
    - Recovery awareness (don't reject bounces)
    - Score adjustments (not just binary pass/fail)
    """

    def __init__(self):
        self.name = "BTC-SOL-Correlation"
        
        # Phase 2.2: Track analysis for dashboard and scoring
        self.last_btc_analysis = None
        self.last_score_adjustment = 0

    def check(self, sol_market_state: Dict, btc_market_state: Dict,
             signal_direction: str) -> Tuple[bool, str]:
        """
        Check if BTC and SOL relationship allows trading.

        Enhanced Logic (Phase 2.2):
        - Check 1: BTC Dump/Pump Protection (NEW - multi-factor analysis)
        - Check 2: Strong opposing BTC trend
        - Check 3: Extreme BTC volatility
        - Check 4: Divergence warning (soft)

        Args:
            sol_market_state: Solana market state
            btc_market_state: Bitcoin market state
            signal_direction: 'long' or 'short'

        Returns:
            (passed: bool, reason: str)
        """
        if not BTC_SOL_CORRELATION_ENABLED:
            return True, "Correlation filter disabled"

        try:
            # Check 1: HARD GATE - BTC Dump/Pump Protection (Phase 2.2 Elite)
            # Multi-factor analysis of BTC price movement
            if getattr(config, 'BTC_DUMP_FILTER_ENABLED', True):
                dump_passed, dump_reason, dump_score = self._check_btc_dump_protection(
                    btc_market_state, signal_direction
                )
                self.last_score_adjustment = dump_score
                
                if not dump_passed:
                    logger.warning(f"❌ {self.name}: {dump_reason}")
                    return False, dump_reason
                
                if dump_score != 0:
                    logger.info(f"📊 {self.name}: {dump_reason} (score: {dump_score:+d})")
            
            # Check 2: HARD GATE - Strong Opposing BTC Trend
            # Only reject if BTC is STRONGLY moving against our signal
            opposing_check = self._check_strong_opposition(
                btc_market_state,
                signal_direction
            )
            if not opposing_check[0]:
                return opposing_check

            # Check 3: HARD GATE - Extreme BTC Volatility
            # Reject if BTC is going crazy (unsafe conditions)
            volatility_check = self._check_btc_volatility_extreme(
                btc_market_state
            )
            if not volatility_check[0]:
                return volatility_check

            # Check 4: SOFT WARNING - Divergence Detection
            # Log warning but don't block trade
            divergence_check = self._check_dangerous_divergence(
                sol_market_state,
                btc_market_state,
                signal_direction
            )
            if not divergence_check[0]:
                logger.warning(f"⚠️  {self.name}: {divergence_check[1]} (allowing trade)")

            logger.info(f"✅ {self.name}: BTC conditions acceptable for SOL trade")
            return True, "BTC not opposing SOL trade"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            # Fail open (allow trade) on errors in this filter
            logger.warning(f"⚠️  {self.name}: Error occurred, allowing trade as fallback")
            return True, f"Filter error (allowed): {e}"

    def _check_strong_opposition(self, btc_state: Dict, signal_direction: str) -> Tuple[bool, str]:
        """
        NEW: Only reject if BTC is STRONGLY opposing the trade direction

        Allows:
        - Neutral/sideways BTC
        - Weak trends
        - Mixed signals

        Rejects ONLY:
        - Strong downtrend on 1H+4H when going long
        - Strong uptrend on 1H+4H when going short
        """
        btc_timeframes = btc_state.get('timeframes', {})

        # Check 1H and 4H trends
        h1_trend = btc_timeframes.get('1H', {}).get('trend', {})
        h4_trend = btc_timeframes.get('4H', {}).get('trend', {})

        if not h1_trend or not h4_trend:
            # Can't determine, allow trade
            return True, "BTC trend data insufficient (allowing)"

        h1_direction = h1_trend.get('trend_direction', 'sideways')
        h1_strength = h1_trend.get('trend_strength', 0)
        h4_direction = h4_trend.get('trend_direction', 'sideways')
        h4_strength = h4_trend.get('trend_strength', 0)

        # For LONG signals: Only reject if BTC STRONGLY bearish
        if signal_direction == 'long':
            # Both 1H and 4H must be down AND strong
            if (h1_direction == 'down' and h1_strength > 0.6 and
                h4_direction == 'down' and h4_strength > 0.6):
                return False, f"BTC strongly bearish (1H: {h1_strength:.2f}, 4H: {h4_strength:.2f})"

        # For SHORT signals: Only reject if BTC STRONGLY bullish
        elif signal_direction == 'short':
            # Both 1H and 4H must be up AND strong
            if (h1_direction == 'up' and h1_strength > 0.6 and
                h4_direction == 'up' and h4_strength > 0.6):
                return False, f"BTC strongly bullish (1H: {h1_strength:.2f}, 4H: {h4_strength:.2f})"

        # BTC not strongly opposing - allow trade
        return True, f"BTC not strongly opposing (1H: {h1_direction}, 4H: {h4_direction})"

    def _check_btc_volatility_extreme(self, btc_state: Dict) -> Tuple[bool, str]:
        """
        NEW: Reject if BTC volatility is extreme (unsafe conditions)

        Checks for:
        - Huge ATR spikes (volatility explosion)
        - Large wicks (stop hunts)
        - Unusual short-term volatility on 1m/5m
        """
        btc_timeframes = btc_state.get('timeframes', {})

        # Check 1: ATR percentile (if in extreme territory)
        if '15m' in btc_timeframes:
            atr_data = btc_timeframes['15m'].get('atr', {})
            atr_percentile = atr_data.get('atr_percentile', 50)

            # If BTC ATR > 95th percentile = extreme volatility
            if atr_percentile > 95:
                return False, f"BTC volatility extreme (ATR {atr_percentile}th percentile)"

        # Check 2: Recent wick sizes (stop hunts)
        if '5m' in btc_timeframes:
            candles = btc_timeframes['5m'].get('candles', [])
            if len(candles) >= 5:
                recent = candles[-5:]
                for candle in recent:
                    body = abs(candle['close'] - candle['open'])
                    upper_wick = candle['high'] - max(candle['close'], candle['open'])
                    lower_wick = min(candle['close'], candle['open']) - candle['low']

                    if body > 0:
                        if upper_wick / body > 4 or lower_wick / body > 4:
                            return False, f"BTC stop hunt detected (large wicks)"

        # Volatility acceptable
        return True, "BTC volatility acceptable"

    def _check_dangerous_divergence(self, sol_state: Dict, btc_state: Dict,
                                    signal_direction: str) -> Tuple[bool, str]:
        """
        NEW: Soft warning for dangerous divergences
        Returns False + reason for logging, but doesn't block trade

        Detects:
        - SOL pumping while BTC nuking (unstable)
        - Extreme opposite movements
        """
        sol_timeframes = sol_state.get('timeframes', {})
        btc_timeframes = btc_state.get('timeframes', {})

        # Check recent price action
        if '15m' not in sol_timeframes or '15m' not in btc_timeframes:
            return True, "No divergence data"

        sol_candles = sol_timeframes['15m'].get('candles', [])
        btc_candles = btc_timeframes['15m'].get('candles', [])

        if len(sol_candles) < 5 or len(btc_candles) < 5:
            return True, "Not enough data for divergence check"

        # Calculate recent moves (last 5 candles)
        sol_move = (sol_candles[-1]['close'] - sol_candles[-5]['close']) / sol_candles[-5]['close']
        btc_move = (btc_candles[-1]['close'] - btc_candles[-5]['close']) / btc_candles[-5]['close']

        # For LONG: Warn if SOL pumping but BTC dumping hard
        if signal_direction == 'long':
            if sol_move > 0.02 and btc_move < -0.02:  # SOL +2%, BTC -2%
                return False, f"SOL pumping (+{sol_move*100:.1f}%) while BTC dumping ({btc_move*100:.1f}%)"

        # For SHORT: Warn if SOL dumping but BTC pumping hard
        elif signal_direction == 'short':
            if sol_move < -0.02 and btc_move > 0.02:  # SOL -2%, BTC +2%
                return False, f"SOL dumping ({sol_move*100:.1f}%) while BTC pumping (+{btc_move*100:.1f}%)"

        return True, "No dangerous divergence"

    # =========================================================================
    # PHASE 2.2: Elite BTC Dump/Pump Protection
    # =========================================================================
    
    def _analyze_btc_movement(self, btc_state: Dict) -> Dict:
        """
        Comprehensive BTC movement analysis (Phase 2.2).
        
        Analyzes BTC across multiple timeframes to determine:
        - Direction (dump/pump/stable)
        - Severity (severe/moderate/mild/none)
        - Velocity (how fast it's moving)
        - Recovery status
        - Cascade (consecutive red/green candles)
        
        Returns:
            Dict with full analysis including score_adjustment
        """
        result = {
            'direction': 'stable',
            'severity': 'none',
            'velocity': 0.0,
            'recovery': False,
            'cascade': 0,
            'volume_confirmed': False,
            'changes': {'15m': 0.0, '1h': 0.0, '4h': 0.0},
            'score_adjustment': 0
        }
        
        btc_timeframes = btc_state.get('timeframes', {})
        if not btc_timeframes:
            return result
        
        # === STEP 1: Calculate price changes across timeframes ===
        for tf, tf_key in [('15m', '15m'), ('1H', '1h'), ('4H', '4h')]:
            candles = btc_timeframes.get(tf, {}).get('candles', [])
            if len(candles) >= 2:
                current = candles[-1]['close']
                previous = candles[-2]['close']
                if previous > 0:
                    change_pct = ((current - previous) / previous) * 100
                    result['changes'][tf_key] = round(change_pct, 2)
        
        # === STEP 2: Determine direction and severity ===
        changes = result['changes']
        
        # Weighted severity (15m matters most for immediate danger)
        weighted_change = (
            changes['15m'] * 0.5 +   # 50% weight on immediate
            changes['1h'] * 0.3 +    # 30% weight on short-term
            changes['4h'] * 0.2      # 20% weight on medium-term
        )
        
        # Get thresholds from config
        SEVERE_THRESHOLD = getattr(config, 'BTC_SEVERE_DROP_PCT', 4.0)
        MODERATE_THRESHOLD = getattr(config, 'BTC_MODERATE_DROP_PCT', 2.5)
        MILD_THRESHOLD = getattr(config, 'BTC_MILD_DROP_PCT', 1.5)
        
        # Determine direction and severity
        if weighted_change < -SEVERE_THRESHOLD:
            result['direction'] = 'dump'
            result['severity'] = 'severe'
        elif weighted_change < -MODERATE_THRESHOLD:
            result['direction'] = 'dump'
            result['severity'] = 'moderate'
        elif weighted_change < -MILD_THRESHOLD:
            result['direction'] = 'dump'
            result['severity'] = 'mild'
        elif weighted_change > SEVERE_THRESHOLD:
            result['direction'] = 'pump'
            result['severity'] = 'severe'
        elif weighted_change > MODERATE_THRESHOLD:
            result['direction'] = 'pump'
            result['severity'] = 'moderate'
        elif weighted_change > MILD_THRESHOLD:
            result['direction'] = 'pump'
            result['severity'] = 'mild'
        
        # === STEP 3: Calculate velocity (danger detection) ===
        # 15m change extrapolated to hourly rate
        result['velocity'] = abs(changes['15m']) * 4  # 4x 15m periods = 1 hour
        
        # === STEP 4: Cascade detection (consecutive candles) ===
        candles_15m = btc_timeframes.get('15m', {}).get('candles', [])
        if len(candles_15m) >= 5:
            consecutive = 0
            for candle in reversed(candles_15m[-5:]):
                if candle['close'] < candle['open']:  # Red candle
                    consecutive += 1
                else:
                    break
            result['cascade'] = consecutive
        
        # === STEP 5: Recovery detection ===
        if len(candles_15m) >= 2:
            last_candle = candles_15m[-1]
            prev_candle = candles_15m[-2]
            # Current candle is green after red = potential recovery
            if (last_candle['close'] > last_candle['open'] and 
                prev_candle['close'] < prev_candle['open']):
                result['recovery'] = True
        
        # === STEP 6: Volume confirmation ===
        volume_data = btc_timeframes.get('15m', {}).get('volume', {})
        current_vol = volume_data.get('current_volume', 0)
        avg_vol = volume_data.get('average_volume', 1)
        if avg_vol > 0 and current_vol > avg_vol * 1.5:
            result['volume_confirmed'] = True
        
        # === STEP 7: Calculate base score adjustment ===
        if result['direction'] == 'dump':
            if result['severity'] == 'severe':
                result['score_adjustment'] = -25
            elif result['severity'] == 'moderate':
                result['score_adjustment'] = -15
            elif result['severity'] == 'mild':
                result['score_adjustment'] = -5
            
            # Volume confirms the dump = more severe
            if result['volume_confirmed']:
                result['score_adjustment'] -= 5
            
            # Recovery detected = less severe
            if result['recovery']:
                result['score_adjustment'] += 10
                
        elif result['direction'] == 'pump':
            if result['severity'] == 'severe':
                result['score_adjustment'] = 20
            elif result['severity'] == 'moderate':
                result['score_adjustment'] = 10
            elif result['severity'] == 'mild':
                result['score_adjustment'] = 5
        
        return result
    
    def _check_btc_dump_protection(self, btc_state: Dict, 
                                    signal_direction: str) -> Tuple[bool, str, int]:
        """
        Elite BTC dump/pump protection (Phase 2.2).
        
        Multi-factor analysis that:
        - Rejects longs during BTC dumps
        - Rejects shorts during BTC pumps
        - Boosts aligned trades (shorts in dumps, longs in pumps)
        - Considers recovery and velocity
        
        Args:
            btc_state: BTC market state
            signal_direction: 'long' or 'short'
            
        Returns:
            (passed: bool, reason: str, score_adjustment: int)
        """
        if not btc_state:
            return True, "No BTC data available", 0
        
        # Get comprehensive BTC analysis
        analysis = self._analyze_btc_movement(btc_state)
        
        direction = analysis['direction']
        severity = analysis['severity']
        changes = analysis['changes']
        velocity = analysis['velocity']
        cascade = analysis['cascade']
        recovery = analysis['recovery']
        score_adj = analysis['score_adjustment']
        
        # Store for external access (dashboard, etc.)
        self.last_btc_analysis = analysis
        
        # Get cascade threshold from config
        CASCADE_THRESHOLD = getattr(config, 'BTC_CASCADE_REJECT_COUNT', 4)
        
        # === DECISION LOGIC ===
        
        # LONG signals during BTC dump
        if signal_direction == 'long' and direction == 'dump':
            
            # SEVERE: Hard reject
            if severity == 'severe':
                return False, (
                    f"🚨 BTC SEVERE DUMP: 15m={changes['15m']:+.1f}%, "
                    f"1H={changes['1h']:+.1f}%, velocity={velocity:.1f}%/hr"
                ), score_adj
            
            # CASCADE: Hard reject (capitulation)
            if cascade >= CASCADE_THRESHOLD:
                return False, (
                    f"🚨 BTC CAPITULATION: {cascade} consecutive red candles"
                ), score_adj - 10
            
            # MODERATE: Soft reject unless recovering
            if severity == 'moderate':
                if recovery:
                    return True, (
                        f"⚠️ BTC moderate dump BUT recovering: {changes['1h']:+.1f}%"
                    ), score_adj
                else:
                    return False, (
                        f"⛔ BTC MODERATE DUMP: 1H={changes['1h']:+.1f}%, "
                        f"4H={changes['4h']:+.1f}%"
                    ), score_adj
            
            # MILD: Allow but penalize score
            if severity == 'mild':
                return True, (
                    f"⚠️ BTC mild weakness: 1H={changes['1h']:+.1f}% (score penalty)"
                ), score_adj
        
        # SHORT signals during BTC pump
        elif signal_direction == 'short' and direction == 'pump':
            
            # SEVERE pump: Hard reject shorts
            if severity == 'severe':
                return False, (
                    f"🚀 BTC PUMPING: 15m={changes['15m']:+.1f}%, "
                    f"1H={changes['1h']:+.1f}% - Don't short into strength"
                ), -score_adj  # Negative for shorts (it's a penalty)
            
            # MODERATE: Soft reject
            if severity == 'moderate':
                return False, (
                    f"📈 BTC strength: 1H={changes['1h']:+.1f}% - Risky to short"
                ), -score_adj
        
        # LONG signals during BTC pump = BOOST
        elif signal_direction == 'long' and direction == 'pump':
            return True, (
                f"🚀 BTC pumping {changes['1h']:+.1f}% - Riding the wave!"
            ), score_adj
        
        # SHORT signals during BTC dump = BOOST
        elif signal_direction == 'short' and direction == 'dump':
            return True, (
                f"📉 BTC dumping {changes['1h']:+.1f}% - Short opportunity!"
            ), abs(score_adj)  # Positive boost for aligned shorts
        
        # Stable BTC = neutral
        return True, f"BTC stable ({changes['1h']:+.1f}%)", 0
    
    def get_btc_status(self) -> Dict:
        """
        Get current BTC status for dashboard display.
        
        Returns:
            Dict with status, emoji, changes, and recommendation
        """
        if not self.last_btc_analysis:
            return {
                'status': 'UNKNOWN',
                'emoji': '❓',
                'message': 'No BTC data yet',
                'changes': {'15m': 0, '1h': 0, '4h': 0},
                'velocity': '0%/hr',
                'cascade': 0,
                'recovery': False,
                'score_adjustment': 0
            }
        
        a = self.last_btc_analysis
        
        # Status emoji mapping
        status_emoji = {
            ('dump', 'severe'): '🚨',
            ('dump', 'moderate'): '⛔',
            ('dump', 'mild'): '⚠️',
            ('pump', 'severe'): '🚀',
            ('pump', 'moderate'): '📈',
            ('pump', 'mild'): '📊',
            ('stable', 'none'): '✅'
        }
        
        emoji = status_emoji.get((a['direction'], a['severity']), '❓')
        
        # Format status string
        if a['direction'] == 'stable':
            status = 'STABLE'
        else:
            status = f"{a['direction'].upper()} ({a['severity'].upper()})"
        
        return {
            'status': status,
            'emoji': emoji,
            'changes': a['changes'],
            'velocity': f"{a['velocity']:.1f}%/hr",
            'cascade': a['cascade'],
            'recovery': a['recovery'],
            'volume_confirmed': a['volume_confirmed'],
            'score_adjustment': a['score_adjustment'],
            'message': f"{emoji} BTC {a['direction']} - 1H: {a['changes']['1h']:+.1f}%"
        }

    def get_correlation_score(self, sol_state: Dict, btc_state: Dict) -> float:
        """
        Calculate overall BTC-SOL correlation score (0-1)

        Returns:
            Score where 1.0 = perfect correlation
        """
        score = 0.0
        checks = 0

        # Trend agreement
        for direction in ['long', 'short']:
            trend_check = self._check_trend_agreement(sol_state, btc_state, direction)
            if trend_check[0]:
                score += 1
                break
        checks += 1

        # Price correlation
        corr_check = self._check_price_correlation(sol_state, btc_state)
        if corr_check[0]:
            score += 1
        checks += 1

        # Momentum alignment
        for direction in ['long', 'short']:
            mom_check = self._check_momentum_alignment(sol_state, btc_state, direction)
            if mom_check[0]:
                score += 1
                break
        checks += 1

        return score / checks if checks > 0 else 0
