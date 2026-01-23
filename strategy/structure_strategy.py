"""
Elite Market Structure Strategy

Uses the MarketStructureAnalyzer to generate trades based on:
1. Support/Resistance bounces and breaks
2. Market structure breaks (trend reversals)
3. Volume profile zones
4. Overall trend bias

This strategy sees the market like a professional - understanding
structure, not just looking for patterns.

Signal Types:
- Structure Break: Trend reversal detected
- Support Bounce: Price bouncing off support in uptrend
- Resistance Rejection: Price rejected at resistance in downtrend
- Level Break: Clean break of key S/R level
- Trend Continuation: Strong bias with structure alignment
"""

from typing import Dict, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class StructureStrategy:
    """
    Elite Market Structure Strategy.
    
    Generates signals based on market structure analysis:
    - S/R levels
    - Structure breaks
    - Volume profile zones
    - Trend bias
    """
    
    def __init__(self):
        self.name = "Structure"
        self.signals_generated = 0
        self.signals_blocked = 0
        
        # Initialize analyzer
        try:
            from data_feed.market_structure import MarketStructureAnalyzer
            self.analyzer = MarketStructureAnalyzer(
                level_tolerance_pct=0.5,
                min_touches=2,
                swing_lookback=5,
                volume_bins=20
            )
            self.analyzer_available = True
        except ImportError as e:
            logger.warning(f"⚠️ {self.name}: MarketStructureAnalyzer not available: {e}")
            self.analyzer_available = False
            self.analyzer = None
        
        logger.info(f"✅ {self.name}: Strategy initialized (S/R + Structure + Volume)")
    
    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market structure and generate signal if setup found.
        
        Args:
            market_state: Complete market state from MarketDataFeed
            
        Returns:
            Signal dict if setup found, None otherwise
        """
        import config
        
        if not getattr(config, 'STRUCTURE_STRATEGY_ENABLED', True):
            return None
        
        if not self.analyzer_available or not self.analyzer:
            return None
        
        try:
            # Get config
            timeframe = getattr(config, 'STRUCTURE_TIMEFRAME', '15m')
            min_confidence = getattr(config, 'STRUCTURE_MIN_CONFIDENCE', 0.5)
            atr_stop_mult = getattr(config, 'STRUCTURE_ATR_STOP_MULT', 1.5)
            tp1_rr = getattr(config, 'STRUCTURE_TP1_RR', 1.5)
            tp2_rr = getattr(config, 'STRUCTURE_TP2_RR', 2.5)
            
            # Get timeframe data
            timeframes = market_state.get('timeframes', {})
            tf_data = timeframes.get(timeframe, {})
            
            if not tf_data:
                return None
            
            candles = tf_data.get('candles', [])
            if len(candles) < 30:
                return None
            
            # Convert candles to dict format if needed
            candle_dicts = []
            for c in candles:
                if isinstance(c, dict):
                    candle_dicts.append(c)
                else:
                    # Assume list format [ts, open, high, low, close, volume]
                    candle_dicts.append({
                        'open': float(c[1]) if len(c) > 1 else 0,
                        'high': float(c[2]) if len(c) > 2 else 0,
                        'low': float(c[3]) if len(c) > 3 else 0,
                        'close': float(c[4]) if len(c) > 4 else 0,
                        'volume': float(c[5]) if len(c) > 5 else 0
                    })
            
            # Run structure analysis
            analysis = self.analyzer.analyze(candle_dicts)
            
            if analysis['analysis_quality'] == 'insufficient_data':
                return None
            
            # Get ATR for stop calculation
            atr_data = tf_data.get('atr', {})
            atr = atr_data.get('atr', 0)
            
            if atr == 0:
                # Calculate ATR manually
                atr = self._calculate_atr(candle_dicts)
            
            # Log structure info
            logger.debug(f"{self.name}: Structure={analysis['structure']}, "
                        f"Bias={analysis['trend_bias']:.2f}, "
                        f"AtSupport={analysis['at_support']}, "
                        f"AtResistance={analysis['at_resistance']}")
            
            # Get trade setup from analyzer
            setup = self.analyzer.get_trade_setup(analysis)
            
            if not setup:
                # No setup from standard checks, try additional setups
                setup = self._check_additional_setups(analysis, candle_dicts)
            
            if not setup:
                return None
            
            if setup['confidence'] < min_confidence:
                logger.debug(f"{self.name}: Setup confidence too low ({setup['confidence']:.2f} < {min_confidence})")
                self.signals_blocked += 1
                return None
            
            # Build signal
            current_price = analysis['current_price']
            direction = setup['direction']
            
            # Calculate stop loss and targets
            if direction == 'long':
                # Stop below support or ATR-based
                support = analysis['nearest_support']
                if support and (current_price - support) < (atr * 3):
                    stop_loss = support - (atr * 0.3)  # Below support with buffer
                else:
                    stop_loss = current_price - (atr * atr_stop_mult)
                
                risk = current_price - stop_loss
                take_profit_1 = current_price + (risk * tp1_rr)
                take_profit_2 = current_price + (risk * tp2_rr)
                
                # If resistance is close, use it as TP1
                resistance = analysis['nearest_resistance']
                if resistance and resistance < take_profit_1:
                    take_profit_1 = resistance - (atr * 0.1)  # Just below resistance
                
            else:  # short
                # Stop above resistance or ATR-based
                resistance = analysis['nearest_resistance']
                if resistance and (resistance - current_price) < (atr * 3):
                    stop_loss = resistance + (atr * 0.3)  # Above resistance with buffer
                else:
                    stop_loss = current_price + (atr * atr_stop_mult)
                
                risk = stop_loss - current_price
                take_profit_1 = current_price - (risk * tp1_rr)
                take_profit_2 = current_price - (risk * tp2_rr)
                
                # If support is close, use it as TP1
                support = analysis['nearest_support']
                if support and support > take_profit_1:
                    take_profit_1 = support + (atr * 0.1)  # Just above support
            
            # Validate R:R
            if direction == 'long':
                rr_ratio = (take_profit_1 - current_price) / (current_price - stop_loss) if current_price > stop_loss else 0
            else:
                rr_ratio = (current_price - take_profit_1) / (stop_loss - current_price) if stop_loss > current_price else 0
            
            if rr_ratio < 1.0:
                logger.debug(f"{self.name}: R:R too low ({rr_ratio:.2f})")
                self.signals_blocked += 1
                return None
            
            self.signals_generated += 1
            
            signal = {
                'strategy': self.name,
                'direction': direction,
                'entry_price': round(current_price, 4),
                'stop_loss': round(stop_loss, 4),
                'stop_price': round(stop_loss, 4),
                'take_profit_1': round(take_profit_1, 4),
                'take_profit_2': round(take_profit_2, 4),
                'take_profit': round(take_profit_1, 4),
                'target_price': round(take_profit_2, 4),
                'timestamp': datetime.now().isoformat(),
                'metadata': {
                    'setup_type': setup['type'],
                    'setup_reason': setup['reason'],
                    'setup_confidence': setup['confidence'],
                    'structure': analysis['structure'],
                    'trend_bias': round(analysis['trend_bias'], 2),
                    'at_support': analysis['at_support'],
                    'at_resistance': analysis['at_resistance'],
                    'nearest_support': analysis['nearest_support'],
                    'nearest_resistance': analysis['nearest_resistance'],
                    'rr_ratio': round(rr_ratio, 2)
                }
            }
            
            logger.info(f"🏗️ {self.name}: {direction.upper()} - {setup['type']}")
            logger.info(f"   {setup['reason']}")
            logger.info(f"   Structure: {analysis['structure']}, Bias: {analysis['trend_bias']:.2f}")
            logger.info(f"   Entry: {current_price:.2f}, SL: {stop_loss:.2f}, TP1: {take_profit_1:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ {self.name}: Error during analysis: {e}")
            return None
    
    def _check_additional_setups(self, analysis: Dict, candles: List[Dict]) -> Optional[Dict]:
        """
        Check for additional setups - STRICT VERSION.
        
        Only triggers on very high-quality setups with strong confirmation.
        Previous version was too permissive (generated 88 losing trades).
        """
        current_price = analysis['current_price']
        trend_bias = analysis['trend_bias']
        structure = analysis['structure']
        
        if len(candles) < 20:
            return None
        
        # Calculate volume confirmation
        volumes = [c.get('volume', 0) for c in candles[-20:]]
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 0
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # STRICT: Require volume confirmation (1.5x average)
        if volume_ratio < 1.5:
            return None
        
        # Check recent price action
        recent_closes = [c['close'] for c in candles[-10:]]
        price_change_pct = ((recent_closes[-1] - recent_closes[0]) / recent_closes[0]) * 100
        
        # STRICT: Only very strong momentum moves (>2% instead of 1%)
        # AND strong bias (>0.5 instead of 0.3)
        # AND volume confirmation
        if price_change_pct > 2.0 and trend_bias > 0.5 and volume_ratio > 1.5:
            return {
                'type': 'strong_momentum',
                'direction': 'long',
                'reason': f'Strong momentum ({price_change_pct:.1f}%) + bias ({trend_bias:.2f}) + volume ({volume_ratio:.1f}x)',
                'confidence': 0.75  # Higher confidence for stricter criteria
            }
        
        if price_change_pct < -2.0 and trend_bias < -0.5 and volume_ratio > 1.5:
            return {
                'type': 'strong_momentum',
                'direction': 'short',
                'reason': f'Strong momentum ({price_change_pct:.1f}%) + bias ({trend_bias:.2f}) + volume ({volume_ratio:.1f}x)',
                'confidence': 0.75
            }
        
        # REMOVED: Range bias setup (was too noisy, generated many losses)
        # Only structure breaks and strong momentum now
        
        return None
    
    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> float:
        """Calculate ATR from candles."""
        if len(candles) < period + 1:
            return 0
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i-1]['close']
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        
        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges) if true_ranges else 0
        
        return sum(true_ranges[-period:]) / period
    
    def get_statistics(self) -> Dict:
        """Get strategy statistics."""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated,
            'signals_blocked': self.signals_blocked,
            'analyzer_available': self.analyzer_available
        }
