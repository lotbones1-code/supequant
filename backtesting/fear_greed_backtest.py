"""
Fear & Greed Index for Backtesting

Uses historical Fear & Greed data to filter trades.
Logic: Use as contrarian signal for Mean Reversion
- Extreme Fear (<25) → Favor LONG trades
- Extreme Greed (>75) → Favor SHORT trades
- Neutral (25-75) → No filter effect

BACKTESTING ONLY - Does not affect live trading.
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FearGreedData:
    """Fear & Greed Index data point"""
    value: int  # 0-100
    classification: str  # 'Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'
    timestamp: datetime


class FearGreedBacktester:
    """
    Fear & Greed Index filter for backtesting.
    
    Uses the Alternative.me Fear & Greed API which provides historical data.
    
    Trading Logic (Contrarian for Mean Reversion):
    - Extreme Fear (0-24): BOOST long signals, BLOCK short signals
    - Fear (25-44): Slight boost to longs
    - Neutral (45-55): No effect
    - Greed (56-74): Slight boost to shorts
    - Extreme Greed (75-100): BOOST short signals, BLOCK long signals
    """
    
    def __init__(self,
                 extreme_fear_threshold: int = 25,
                 extreme_greed_threshold: int = 75,
                 block_contrarian: bool = True,
                 api_url: str = "https://api.alternative.me/fng/"):
        """
        Initialize Fear & Greed backtester.
        
        Args:
            extreme_fear_threshold: Below this = extreme fear
            extreme_greed_threshold: Above this = extreme greed
            block_contrarian: If True, block trades against extreme sentiment
            api_url: Fear & Greed API endpoint
        """
        self.extreme_fear_threshold = extreme_fear_threshold
        self.extreme_greed_threshold = extreme_greed_threshold
        self.block_contrarian = block_contrarian
        self.api_url = api_url
        
        # Historical data cache: date_str -> FearGreedData
        self.historical_data: Dict[str, FearGreedData] = {}
        
        # Stats
        self.stats = {
            'signals_checked': 0,
            'signals_boosted': 0,
            'signals_blocked': 0,
            'extreme_fear_days': 0,
            'extreme_greed_days': 0,
            'api_calls': 0,
        }
        
        logger.info(f"😱 FearGreedBacktester initialized (fear<{extreme_fear_threshold}, greed>{extreme_greed_threshold})")
    
    def load_historical_data(self, days: int = 365) -> bool:
        """
        Load historical Fear & Greed data from API.
        
        Args:
            days: Number of days of historical data to fetch
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.api_url}?limit={days}&format=json"
            logger.info(f"📊 Fetching {days} days of Fear & Greed data...")
            
            response = requests.get(url, timeout=30)
            self.stats['api_calls'] += 1
            
            if response.status_code != 200:
                logger.error(f"Fear & Greed API error: {response.status_code}")
                return False
            
            data = response.json()
            
            if 'data' not in data:
                logger.error("Fear & Greed API response missing 'data' field")
                return False
            
            # Parse and cache data
            for item in data['data']:
                try:
                    value = int(item['value'])
                    timestamp = datetime.fromtimestamp(int(item['timestamp']))
                    date_str = timestamp.strftime('%Y-%m-%d')
                    
                    classification = item.get('value_classification', self._classify(value))
                    
                    self.historical_data[date_str] = FearGreedData(
                        value=value,
                        classification=classification,
                        timestamp=timestamp
                    )
                    
                    # Track extreme days
                    if value < self.extreme_fear_threshold:
                        self.stats['extreme_fear_days'] += 1
                    elif value > self.extreme_greed_threshold:
                        self.stats['extreme_greed_days'] += 1
                        
                except Exception as e:
                    logger.debug(f"Error parsing Fear & Greed item: {e}")
                    continue
            
            logger.info(f"✅ Loaded {len(self.historical_data)} days of Fear & Greed data")
            logger.info(f"   Extreme Fear days: {self.stats['extreme_fear_days']}, Extreme Greed days: {self.stats['extreme_greed_days']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load Fear & Greed data: {e}")
            return False
    
    def _classify(self, value: int) -> str:
        """Classify Fear & Greed value."""
        if value < 25:
            return "Extreme Fear"
        elif value < 45:
            return "Fear"
        elif value < 56:
            return "Neutral"
        elif value < 75:
            return "Greed"
        else:
            return "Extreme Greed"
    
    def get_value_for_date(self, date: datetime) -> Optional[FearGreedData]:
        """Get Fear & Greed value for a specific date."""
        date_str = date.strftime('%Y-%m-%d')
        return self.historical_data.get(date_str)
    
    def evaluate_signal(self, direction: str, timestamp: datetime, strategy: str = None) -> Tuple[bool, float, str]:
        """
        Evaluate a trading signal against Fear & Greed sentiment.
        
        Args:
            direction: 'long' or 'short'
            timestamp: Signal timestamp
            strategy: Strategy name (for logging)
            
        Returns:
            Tuple of (allowed, confidence_multiplier, reason)
        """
        self.stats['signals_checked'] += 1
        direction = direction.lower()
        
        # Get Fear & Greed for this date
        fg_data = self.get_value_for_date(timestamp)
        
        if not fg_data:
            # No data for this date - allow with neutral multiplier
            return True, 1.0, "No Fear & Greed data for date"
        
        value = fg_data.value
        classification = fg_data.classification
        
        # Determine sentiment impact
        if value < self.extreme_fear_threshold:
            # EXTREME FEAR - Contrarian: favor longs, discourage shorts
            if direction == 'long':
                self.stats['signals_boosted'] += 1
                return True, 1.3, f"Extreme Fear ({value}) - BOOST long (contrarian buy)"
            else:  # short
                if self.block_contrarian:
                    self.stats['signals_blocked'] += 1
                    return False, 0.0, f"Extreme Fear ({value}) - BLOCK short (market oversold)"
                else:
                    return True, 0.7, f"Extreme Fear ({value}) - Reduce short size"
                    
        elif value > self.extreme_greed_threshold:
            # EXTREME GREED - Contrarian: favor shorts, discourage longs
            if direction == 'short':
                self.stats['signals_boosted'] += 1
                return True, 1.3, f"Extreme Greed ({value}) - BOOST short (contrarian sell)"
            else:  # long
                if self.block_contrarian:
                    self.stats['signals_blocked'] += 1
                    return False, 0.0, f"Extreme Greed ({value}) - BLOCK long (market overbought)"
                else:
                    return True, 0.7, f"Extreme Greed ({value}) - Reduce long size"
        
        elif value < 45:
            # Fear (not extreme) - slight boost to longs
            if direction == 'long':
                return True, 1.1, f"Fear ({value}) - slight boost to long"
            else:
                return True, 0.95, f"Fear ({value}) - slight reduction to short"
                
        elif value > 55:
            # Greed (not extreme) - slight boost to shorts
            if direction == 'short':
                return True, 1.1, f"Greed ({value}) - slight boost to short"
            else:
                return True, 0.95, f"Greed ({value}) - slight reduction to long"
        
        else:
            # Neutral (45-55)
            return True, 1.0, f"Neutral sentiment ({value})"
    
    def get_stats(self) -> Dict:
        """Get Fear & Greed backtester statistics."""
        total = self.stats['signals_checked']
        return {
            **self.stats,
            'data_points': len(self.historical_data),
            'block_rate': self.stats['signals_blocked'] / total if total > 0 else 0,
            'boost_rate': self.stats['signals_boosted'] / total if total > 0 else 0,
        }


# Convenience function for backtest integration
def create_fear_greed_backtester(
    fear_threshold: int = 25,
    greed_threshold: int = 75,
    block_contrarian: bool = True
) -> FearGreedBacktester:
    """Create a configured Fear & Greed backtester."""
    return FearGreedBacktester(
        extreme_fear_threshold=fear_threshold,
        extreme_greed_threshold=greed_threshold,
        block_contrarian=block_contrarian
    )
