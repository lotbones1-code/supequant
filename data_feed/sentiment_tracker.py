"""
Sentiment Tracker (Elite)

Fetches real market sentiment data:
- Fear & Greed Index (Alternative.me API - free)
- Provides score adjustments based on sentiment

The Fear & Greed Index ranges from 0-100:
- 0-24: Extreme Fear (contrarian bullish)
- 25-44: Fear (cautiously bullish)
- 45-55: Neutral
- 56-74: Greed (cautiously bearish)
- 75-100: Extreme Greed (contrarian bearish)

Elite Logic:
- Extreme Fear + Long signal = BOOST (smart money buying)
- Extreme Greed + Short signal = BOOST (smart money selling)
- Sentiment aligned with position = small boost
- Sentiment against position = small penalty (but don't block)
"""

import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SentimentTracker:
    """
    Tracks market sentiment using Fear & Greed Index.
    
    Uses Alternative.me's free API for crypto sentiment.
    Caches results to avoid excessive API calls.
    """
    
    # Fear & Greed classification thresholds
    EXTREME_FEAR_MAX = 24
    FEAR_MAX = 44
    NEUTRAL_MAX = 55
    GREED_MAX = 74
    # Above 74 = Extreme Greed
    
    def __init__(self, cache_seconds: int = 3600):
        """
        Initialize sentiment tracker.
        
        Args:
            cache_seconds: How long to cache sentiment data (default 1 hour)
        """
        self.cache_seconds = cache_seconds
        self._cached_sentiment: Optional[Dict] = None
        self._cache_time: Optional[datetime] = None
        self._api_available = True
        self._last_error: Optional[str] = None
        
        logger.info(f"✅ SentimentTracker: Initialized (cache: {cache_seconds}s)")
    
    def get_fear_greed_index(self) -> Optional[Dict]:
        """
        Get current Fear & Greed Index.
        
        Returns:
            Dict with:
                - value: 0-100 score
                - classification: 'Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'
                - timestamp: When data was fetched
                - cached: Whether this is cached data
            
            None if API unavailable
        """
        # Check cache first
        if self._cached_sentiment and self._cache_time:
            cache_age = (datetime.now() - self._cache_time).total_seconds()
            if cache_age < self.cache_seconds:
                return {**self._cached_sentiment, 'cached': True}
        
        # Fetch fresh data
        try:
            import urllib.request
            import json
            
            url = "https://api.alternative.me/fng/?limit=1"
            
            request = urllib.request.Request(
                url,
                headers={'User-Agent': 'SuperQuant/1.0'}
            )
            
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            if 'data' not in data or len(data['data']) == 0:
                logger.warning("SentimentTracker: Invalid API response")
                return self._get_fallback()
            
            fng_data = data['data'][0]
            value = int(fng_data.get('value', 50))
            classification = fng_data.get('value_classification', 'Neutral')
            
            # Cache the result
            self._cached_sentiment = {
                'value': value,
                'classification': classification,
                'timestamp': datetime.now().isoformat(),
                'source': 'alternative.me'
            }
            self._cache_time = datetime.now()
            self._api_available = True
            self._last_error = None
            
            logger.info(f"📊 SentimentTracker: Fear & Greed = {value} ({classification})")
            
            return {**self._cached_sentiment, 'cached': False}
            
        except Exception as e:
            self._last_error = str(e)
            logger.warning(f"⚠️ SentimentTracker: API error - {e}")
            
            # Return cached data if available
            if self._cached_sentiment:
                return {**self._cached_sentiment, 'cached': True, 'stale': True}
            
            return self._get_fallback()
    
    def _get_fallback(self) -> Dict:
        """Return neutral fallback when API unavailable."""
        return {
            'value': 50,
            'classification': 'Neutral',
            'timestamp': datetime.now().isoformat(),
            'source': 'fallback',
            'cached': False
        }
    
    def get_sentiment_classification(self, value: int) -> str:
        """Classify sentiment value."""
        if value <= self.EXTREME_FEAR_MAX:
            return 'Extreme Fear'
        elif value <= self.FEAR_MAX:
            return 'Fear'
        elif value <= self.NEUTRAL_MAX:
            return 'Neutral'
        elif value <= self.GREED_MAX:
            return 'Greed'
        else:
            return 'Extreme Greed'
    
    def get_score_adjustment(self, signal_direction: str) -> Tuple[int, str]:
        """
        Get score adjustment based on sentiment and signal direction.
        
        Elite Contrarian Logic:
        - Extreme Fear + Long = Big boost (buy when others fearful)
        - Extreme Greed + Short = Big boost (sell when others greedy)
        - Aligned sentiment = small boost
        - Opposed sentiment = small penalty
        
        Args:
            signal_direction: 'long' or 'short'
            
        Returns:
            (adjustment: int, reason: str)
        """
        fng = self.get_fear_greed_index()
        if not fng:
            return 0, "Sentiment data unavailable"
        
        value = fng['value']
        classification = fng['classification']
        
        # Extreme Fear scenarios
        if value <= self.EXTREME_FEAR_MAX:
            if signal_direction == 'long':
                return 15, f"Extreme Fear ({value}) + Long = Contrarian boost"
            else:
                return -5, f"Extreme Fear ({value}) + Short = Against contrarian"
        
        # Fear scenarios
        elif value <= self.FEAR_MAX:
            if signal_direction == 'long':
                return 8, f"Fear ({value}) + Long = Favorable"
            else:
                return -3, f"Fear ({value}) + Short = Slightly unfavorable"
        
        # Neutral - no adjustment
        elif value <= self.NEUTRAL_MAX:
            return 0, f"Neutral sentiment ({value})"
        
        # Greed scenarios
        elif value <= self.GREED_MAX:
            if signal_direction == 'short':
                return 8, f"Greed ({value}) + Short = Favorable"
            else:
                return -3, f"Greed ({value}) + Long = Slightly unfavorable"
        
        # Extreme Greed scenarios
        else:
            if signal_direction == 'short':
                return 15, f"Extreme Greed ({value}) + Short = Contrarian boost"
            else:
                return -5, f"Extreme Greed ({value}) + Long = Against contrarian"
    
    def get_market_sentiment_score(self) -> float:
        """
        Get normalized sentiment score (0-100) for filter use.
        
        Returns:
            Score where:
            - 0-30: Bearish sentiment (fear)
            - 30-70: Neutral
            - 70-100: Bullish sentiment (greed)
        """
        fng = self.get_fear_greed_index()
        if not fng:
            return 50.0  # Neutral fallback
        
        # Fear & Greed Index already 0-100
        # But we want to flip it for "bullish score"
        # High fear (low FGI) = Low bullish score
        # High greed (high FGI) = High bullish score
        return float(fng['value'])
    
    def get_status(self) -> Dict:
        """Get tracker status for dashboard."""
        fng = self.get_fear_greed_index()
        
        return {
            'enabled': True,
            'api_available': self._api_available,
            'last_error': self._last_error,
            'current_value': fng['value'] if fng else None,
            'classification': fng['classification'] if fng else None,
            'cached': fng.get('cached', False) if fng else None,
            'cache_age_seconds': (datetime.now() - self._cache_time).total_seconds() if self._cache_time else None
        }


# Singleton instance for easy access
_sentiment_tracker: Optional[SentimentTracker] = None


def get_sentiment_tracker() -> SentimentTracker:
    """Get or create singleton sentiment tracker."""
    global _sentiment_tracker
    if _sentiment_tracker is None:
        _sentiment_tracker = SentimentTracker()
    return _sentiment_tracker
