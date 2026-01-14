"""
Binance USD-M Futures API Client
Handles rate limiting, backoff, and data fetching for SOLUSDT and BTCUSDT
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """
    Binance USD-M Futures API client with proper rate limiting
    
    Features:
    - Monitors used-weight headers
    - Handles 429 with exponential backoff
    - Prevents 418 IP bans
    - Fetches klines, markPriceKlines, fundingRate
    - Supports testnet/mainnet venue switching
    """
    
    # Base URLs for different venues
    MAINNET_BASE_URL = "https://fapi.binance.com"
    TESTNET_BASE_URL = "https://demo-fapi.binance.com"
    
    # Rate limits (from Binance docs)
    WEIGHT_LIMIT_PER_MINUTE = 2400
    REQUESTS_PER_MINUTE = 1200
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 venue: str = "mainnet"):
        """
        Initialize Binance client
        
        Args:
            api_key: Optional API key (not needed for public endpoints)
            api_secret: Optional API secret (not needed for public endpoints)
            venue: "testnet" or "mainnet" (default: "mainnet")
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.venue = venue.lower()
        
        # Set base URL based on venue
        if self.venue == "testnet":
            self.BASE_URL = self.TESTNET_BASE_URL
        elif self.venue == "mainnet":
            self.BASE_URL = self.MAINNET_BASE_URL
        else:
            raise ValueError(f"Invalid venue: {venue}. Must be 'testnet' or 'mainnet'")
        
        logger.info(f"✅ BinanceFuturesClient initialized (venue: {self.venue}, base_url: {self.BASE_URL})")
        
        # Rate limiting state
        self.used_weight_1m = 0
        self.used_weight_1m_reset_time = time.time() + 60
        self.request_count_1m = 0
        self.request_count_1m_reset_time = time.time() + 60
        
        # Track 429 errors to avoid spam
        self.last_429_time = 0
        self.consecutive_429_count = 0
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        logger.info("✅ BinanceFuturesClient initialized")

    def _check_rate_limits(self):
        """Check and reset rate limit counters"""
        now = time.time()
        
        # Reset 1-minute counters if needed
        if now >= self.used_weight_1m_reset_time:
            self.used_weight_1m = 0
            self.used_weight_1m_reset_time = now + 60
        
        if now >= self.request_count_1m_reset_time:
            self.request_count_1m = 0
            self.request_count_1m_reset_time = now + 60

    def _wait_for_rate_limit(self, required_weight: int = 1):
        """
        Wait if rate limits would be exceeded
        
        Args:
            required_weight: Weight required for this request
        """
        self._check_rate_limits()
        
        # Check weight limit
        if self.used_weight_1m + required_weight > self.WEIGHT_LIMIT_PER_MINUTE:
            wait_time = self.used_weight_1m_reset_time - time.time()
            if wait_time > 0:
                logger.warning(f"⏳ Weight limit approaching, waiting {wait_time:.1f}s")
                time.sleep(wait_time + 0.1)  # Small buffer
                self._check_rate_limits()
        
        # Check request count limit
        if self.request_count_1m >= self.REQUESTS_PER_MINUTE:
            wait_time = self.request_count_1m_reset_time - time.time()
            if wait_time > 0:
                logger.warning(f"⏳ Request limit approaching, waiting {wait_time:.1f}s")
                time.sleep(wait_time + 0.1)
                self._check_rate_limits()

    def _handle_429(self, response: requests.Response) -> bool:
        """
        Handle 429 rate limit response with exponential backoff
        
        Returns:
            True if should retry, False if should abort
        """
        now = time.time()
        
        # Get retry-after header if present
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            wait_time = int(retry_after)
        else:
            # Exponential backoff based on consecutive 429s
            self.consecutive_429_count += 1
            wait_time = min(2 ** self.consecutive_429_count, 60)  # Cap at 60s
        
        # If we got 429 recently, increase wait time to avoid 418 ban
        if now - self.last_429_time < 60:
            wait_time = max(wait_time, 10)  # Minimum 10s between 429s
        
        self.last_429_time = now
        
        logger.warning(f"⚠️  Rate limit exceeded (429). Waiting {wait_time}s before retry")
        logger.warning(f"   Consecutive 429s: {self.consecutive_429_count}")
        
        if self.consecutive_429_count >= 5:
            logger.error("❌ Too many consecutive 429 errors. Aborting to avoid IP ban.")
            return False
        
        time.sleep(wait_time)
        return True

    def _request(self, endpoint: str, params: Optional[Dict] = None, 
                weight: int = 1) -> Optional[Dict]:
        """
        Make API request with rate limiting
        
        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
            weight: Request weight (default: 1)
        
        Returns:
            Response JSON or None if failed
        """
        self._wait_for_rate_limit(weight)
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            # Handle 429
            if response.status_code == 429:
                if not self._handle_429(response):
                    return None
                # Retry the request
                return self._request(endpoint, params, weight)
            
            # Reset 429 counter on success
            if response.status_code == 200:
                self.consecutive_429_count = 0
            
            response.raise_for_status()
            
            # Update rate limit counters from headers
            used_weight = response.headers.get('X-MBX-USED-WEIGHT-1M')
            if used_weight:
                self.used_weight_1m = int(used_weight)
            
            self.request_count_1m += 1
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API request failed: {e}")
            return None

    def get_klines(self, symbol: str, interval: str, start_time: Optional[int] = None,
                   end_time: Optional[int] = None, limit: int = 1500) -> List[Dict]:
        """
        Get klines (candlestick data)
        
        Args:
            symbol: Trading symbol (e.g., 'SOLUSDT')
            interval: Kline interval (1m, 5m, 15m, 1h, 4h, 1d, etc.)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            limit: Number of klines (max 1500)
        
        Returns:
            List of kline dicts
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1500)
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        # Weight: 1 per request
        data = self._request('/fapi/v1/klines', params, weight=1)
        
        if not data:
            return []
        
        # Convert to structured format
        klines = []
        for k in data:
            klines.append({
                'timestamp': int(k[0]),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'close_time': int(k[6]),
                'quote_volume': float(k[7]),
                'trades': int(k[8]),
                'taker_buy_base_volume': float(k[9]),
                'taker_buy_quote_volume': float(k[10]),
                'ignore': int(k[11])
            })
        
        return klines

    def get_mark_price_klines(self, symbol: str, interval: str,
                              start_time: Optional[int] = None,
                              end_time: Optional[int] = None,
                              limit: int = 1500) -> List[Dict]:
        """
        Get mark price klines
        
        Args:
            symbol: Trading symbol (e.g., 'SOLUSDT')
            interval: Kline interval
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            limit: Number of klines (max 1500)
        
        Returns:
            List of mark price kline dicts
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1500)
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        # Weight: 1 per request
        data = self._request('/fapi/v1/markPriceKlines', params, weight=1)
        
        if not data:
            return []
        
        # Convert to structured format
        klines = []
        for k in data:
            klines.append({
                'timestamp': int(k[0]),
                'mark_price': float(k[1]),
                'close': float(k[2])  # Mark price at close
            })
        
        return klines

    def get_funding_rate(self, symbol: str, start_time: Optional[int] = None,
                        end_time: Optional[int] = None,
                        limit: int = 1000) -> List[Dict]:
        """
        Get funding rate history
        
        Args:
            symbol: Trading symbol (e.g., 'SOLUSDT')
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            limit: Number of records (max 1000)
        
        Returns:
            List of funding rate dicts
        """
        params = {
            'symbol': symbol,
            'limit': min(limit, 1000)
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        # Weight: 1 per request
        data = self._request('/fapi/v1/fundingRate', params, weight=1)
        
        if not data:
            return []
        
        # Convert to structured format
        rates = []
        for r in data:
            rates.append({
                'symbol': r['symbol'],
                'funding_time': int(r['fundingTime']),
                'funding_rate': float(r['fundingRate']),
                'mark_price': float(r['markPrice'])
            })
        
        return rates

    def get_funding_rate_info(self, symbol: Optional[str] = None) -> Dict:
        """
        Get current funding rate info
        
        Args:
            symbol: Optional symbol (if None, returns all symbols)
        
        Returns:
            Funding rate info dict
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        # Weight: 1 per request
        data = self._request('/fapi/v1/premiumIndex', params, weight=1)
        
        if not data:
            return {}
        
        if symbol:
            # Single symbol response
            return {
                'symbol': data['symbol'],
                'mark_price': float(data['markPrice']),
                'index_price': float(data['indexPrice']),
                'estimated_settle_price': float(data.get('estimatedSettlePrice', 0)),
                'last_funding_rate': float(data['lastFundingRate']),
                'next_funding_time': int(data['nextFundingTime']),
                'interest_rate': float(data.get('interestRate', 0)),
                'time': int(data['time'])
            }
        else:
            # Multiple symbols response
            return {item['symbol']: {
                'mark_price': float(item['markPrice']),
                'index_price': float(item['indexPrice']),
                'last_funding_rate': float(item['lastFundingRate']),
                'next_funding_time': int(item['nextFundingTime']),
                'time': int(item['time'])
            } for item in data}

