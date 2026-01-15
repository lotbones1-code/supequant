"""
OKX API Client
Handles all direct interactions with OKX exchange API
Includes rate limiting, retries, and error handling

DRY_RUN MODE: When enabled, skips all authenticated endpoints
and uses simulated data for paper trading without API keys.
"""

import time
import hmac
import base64
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
from config import (
    OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, OKX_SIMULATED,
    API_RATE_LIMIT_MS, MAX_RETRIES, RETRY_DELAY_MS
)
import logging

logger = logging.getLogger(__name__)

# Check for DRY_RUN mode
DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'true'


class OKXClient:
    """
    OKX Exchange API Client with built-in rate limiting and retry logic
    
    DRY_RUN mode: Skips all authenticated API calls and returns simulated data
    """

    def __init__(self):
        self.api_key = OKX_API_KEY
        self.secret_key = OKX_SECRET_KEY
        self.passphrase = OKX_PASSPHRASE
        self.simulated = OKX_SIMULATED
        self.dry_run = DRY_RUN

        # API endpoints
        self.base_url = "https://www.okx.com"
        
        if self.dry_run:
            logger.info("🧪 OKX Client initialized in DRY RUN mode (no API auth)")
            logger.info("   📊 Public market data: ENABLED")
            logger.info("   💰 Account/Trading: SIMULATED LOCALLY")
        elif self.simulated:
            logger.info("🟡 OKX Client initialized in SIMULATED mode")
        else:
            logger.info("🔴 OKX Client initialized in LIVE mode")

        self.last_request_time = 0
        self.request_count = 0
        self.error_count = 0
        
        # Simulated account for dry run
        self._dry_run_balance = 10000.0
        self._dry_run_positions = []

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """Generate signature for authenticated requests"""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return base64.b64encode(mac.digest()).decode()

    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """Generate headers for API request"""
        timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
        signature = self._generate_signature(timestamp, method, request_path, body)

        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }

        if self.simulated:
            headers['x-simulated-trading'] = '1'

        return headers

    def _rate_limit(self):
        """Implement rate limiting to avoid API throttling"""
        elapsed = (time.time() * 1000) - self.last_request_time
        if elapsed < API_RATE_LIMIT_MS:
            time.sleep((API_RATE_LIMIT_MS - elapsed) / 1000)
        self.last_request_time = time.time() * 1000

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 body: Optional[Dict] = None, authenticated: bool = False) -> Optional[Dict]:
        """Make HTTP request to OKX API with retry logic"""
        
        # DRY RUN: Skip authenticated requests entirely
        if self.dry_run and authenticated:
            logger.debug(f"🧪 DRY RUN: Skipping authenticated request to {endpoint}")
            return None
            
        self._rate_limit()

        url = self.base_url + endpoint
        request_body = json.dumps(body) if body else ''

        for attempt in range(MAX_RETRIES):
            try:
                if authenticated:
                    headers = self._get_headers(method, endpoint, request_body)
                else:
                    headers = {'Content-Type': 'application/json'}

                if method == 'GET':
                    response = requests.get(url, params=params, headers=headers, timeout=10)
                elif method == 'POST':
                    response = requests.post(url, data=request_body, headers=headers, timeout=10)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # Try to parse response
                try:
                    data = response.json()
                except:
                    data = None

                if response.status_code != 200:
                    logger.error(f"❌ HTTP {response.status_code} from {endpoint}")
                    if data:
                        logger.error(f"   OKX Error: {data}")

                response.raise_for_status()

                if data.get('code') != '0':
                    error_msg = data.get('msg', 'Unknown error')
                    error_code = data.get('code', 'unknown')
                    logger.error(f"❌ OKX API Error [{error_code}]: {error_msg}")
                    self.error_count += 1
                    return None

                self.request_count += 1
                self.error_count = 0
                return data

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                self.error_count += 1

                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_MS / 1000)
                else:
                    logger.error(f"Max retries reached for {endpoint}")
                    return None

        return None

    # =====================================
    # PUBLIC MARKET DATA ENDPOINTS (work in DRY_RUN)
    # =====================================

    def get_candles(self, symbol: str, timeframe: str, limit: int = 100,
                    after: Optional[str] = None, before: Optional[str] = None) -> Optional[List[List]]:
        """
        Get candlestick data - PUBLIC endpoint, works in DRY_RUN
        
        For maximum recent candles without pagination, don't pass before/after.
        For pagination, pass 'after' to get older candles (candles with ts < after).
        """
        endpoint = '/api/v5/market/candles'
        params = {
            'instId': symbol,
            'bar': timeframe,
            'limit': min(limit, 300)
        }

        # Add pagination params if provided
        if after:
            params['after'] = after
        if before:
            params['before'] = before

        response = self._request('GET', endpoint, params=params, authenticated=False)
        if response and response.get('data'):
            return response['data']
        return None

    def get_history_candles(self, symbol: str, timeframe: str, limit: int = 100,
                           after: Optional[str] = None, before: Optional[str] = None) -> Optional[List[List]]:
        """
        Get historical candlestick data - PUBLIC endpoint
        
        OKX has TWO endpoints:
        1. /api/v5/market/candles - For RECENT data (last 3 months)
        2. /api/v5/market/history-candles - For OLD data (> 3 months)
        
        This method automatically selects the correct endpoint based on the date range.
        
        OKX Pagination Parameters (IMPORTANT - naming is counterintuitive!):
        - 'after': Pagination key. Returns records with timestamp EARLIER than 'after' (older data)
        - 'before': Pagination key. Returns records with timestamp LATER than 'before' (newer data)
        
        To paginate backwards in time (get older candles):
        1. First call without after/before to get most recent candles
        2. Take the OLDEST timestamp from results
        3. Pass that as 'after' to get candles even older than that
        
        OKX_SIMULATED does NOT affect this - it's a public endpoint and always returns real data.
        """
        # Determine which endpoint to use based on date range
        now_ms = int(time.time() * 1000)
        three_months_ago_ms = now_ms - (90 * 24 * 60 * 60 * 1000)  # 90 days in milliseconds
        
        use_history_endpoint = False
        
        # Check if we're requesting data older than 3 months
        if after and after is not None:
            try:
                after_ts = int(after)
                if after_ts < three_months_ago_ms:
                    use_history_endpoint = True
                    logger.debug(f"   Using history-candles endpoint (data older than 3 months)")
            except (ValueError, TypeError):
                pass
        elif before and before is not None:
            try:
                before_ts = int(before)
                if before_ts < three_months_ago_ms:
                    use_history_endpoint = True
                    logger.debug(f"   Using history-candles endpoint (data older than 3 months)")
            except (ValueError, TypeError):
                pass
        
        # Select appropriate endpoint
        if use_history_endpoint:
            endpoint = '/api/v5/market/history-candles'
            max_limit = 100  # history-candles max is 100
        else:
            endpoint = '/api/v5/market/candles'
            max_limit = 300  # regular candles max is 300
        
        params = {
            'instId': symbol,
            'bar': timeframe,
            'limit': min(limit, max_limit)
        }

        # ALWAYS pass pagination params if provided - this enables pagination!
        # The previous code incorrectly skipped these for regular candles endpoint,
        # which broke pagination completely.
        if after and after is not None:
            params['after'] = after
        if before and before is not None:
            params['before'] = before

        # Log request details for debugging
        logger.debug(f"📡 OKX {endpoint.split('/')[-1]} request: symbol={symbol}, timeframe={timeframe}, after={after}, before={before}, limit={params['limit']}")

        # Explicitly use authenticated=False for public endpoint
        response = self._request('GET', endpoint, params=params, authenticated=False)
        
        if response:
            response_code = response.get('code', 'unknown')
            response_msg = response.get('msg', 'N/A')
            data = response.get('data', [])
            
            if data and len(data) > 0:
                logger.debug(f"✅ OKX {endpoint.split('/')[-1]}: Received {len(data)} candles (code: {response_code})")
                
                # Log data range for debugging
                first_ts = int(data[0][0])
                first_dt = datetime.fromtimestamp(first_ts / 1000)
                last_ts = int(data[-1][0])
                last_dt = datetime.fromtimestamp(last_ts / 1000)
                
                logger.debug(f"   Data range: {first_dt} to {last_dt}")
                
                return data
            else:
                logger.warning(f"⚠️  OKX {endpoint.split('/')[-1]}: API returned success but NO DATA")
                logger.warning(f"   Response code: {response_code}, msg: {response_msg}")
                logger.warning(f"   Params: {params}")
        else:
            logger.warning(f"⚠️  OKX {endpoint.split('/')[-1]}: No response returned")
            logger.warning(f"   Params: {params}")
        
        return None

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker price - PUBLIC endpoint, works in DRY_RUN"""
        endpoint = '/api/v5/market/ticker'
        params = {'instId': symbol}

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Get funding rate - PUBLIC endpoint"""
        endpoint = '/api/v5/public/funding-rate'
        params = {'instId': symbol}

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_open_interest(self, symbol: str) -> Optional[Dict]:
        """Get open interest - PUBLIC endpoint"""
        endpoint = '/api/v5/public/open-interest'
        params = {'instId': symbol}

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """Get orderbook - PUBLIC endpoint"""
        endpoint = '/api/v5/market/books'
        params = {
            'instId': symbol,
            'sz': min(depth, 400)
        }

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    # =====================================
    # AUTHENTICATED ENDPOINTS (simulated in DRY_RUN)
    # =====================================

    def get_account_balance(self) -> Optional[List[Dict]]:
        """Get account balance - SIMULATED in DRY_RUN mode"""
        if self.dry_run:
            logger.info(f"🧪 DRY RUN: Returning simulated balance ${self._dry_run_balance:.2f}")
            return [{
                'details': [{
                    'ccy': 'USDT',
                    'availEq': str(self._dry_run_balance),
                    'eq': str(self._dry_run_balance)
                }]
            }]
            
        endpoint = '/api/v5/account/balance'
        response = self._request('GET', endpoint, authenticated=True)
        if response and response.get('data'):
            return response['data']
        return None

    def get_positions(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """Get positions - SIMULATED in DRY_RUN mode"""
        if self.dry_run:
            logger.debug(f"🧪 DRY RUN: Returning {len(self._dry_run_positions)} simulated positions")
            return self._dry_run_positions
            
        endpoint = '/api/v5/account/positions'
        params = {}
        if symbol:
            params['instId'] = symbol

        response = self._request('GET', endpoint, params=params, authenticated=True)
        if response and response.get('data'):
            return response['data']
        return None

    def place_order(self, symbol: str, side: str, order_type: str, size: str,
                   price: Optional[str] = None, **kwargs) -> Optional[Dict]:
        """Place order - SIMULATED in DRY_RUN mode"""
        if self.dry_run:
            order_id = f"DRY-{int(time.time()*1000)}"
            logger.info(f"🧪 DRY RUN: Simulated {side.upper()} order placed")
            logger.info(f"   Symbol: {symbol}")
            logger.info(f"   Size: {size}")
            logger.info(f"   Type: {order_type}")
            logger.info(f"   Order ID: {order_id}")
            
            return {
                'ordId': order_id,
                'clOrdId': '',
                'sCode': '0',
                'sMsg': 'DRY RUN - Order simulated'
            }
            
        endpoint = '/api/v5/trade/order'
        body = {
            'instId': symbol,
            'tdMode': kwargs.get('tdMode', 'cross'),
            'side': side,
            'ordType': order_type,
            'sz': size,
        }

        if price:
            body['px'] = price

        if 'reduce_only' in kwargs:
            body['reduceOnly'] = kwargs['reduce_only']
        if 'stop_loss' in kwargs:
            body['slTriggerPx'] = kwargs['stop_loss']
        if 'take_profit' in kwargs:
            body['tpTriggerPx'] = kwargs['take_profit']

        response = self._request('POST', endpoint, body=body, authenticated=True)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Cancel order - SIMULATED in DRY_RUN mode"""
        if self.dry_run:
            logger.info(f"🧪 DRY RUN: Simulated cancel for order {order_id}")
            return {'ordId': order_id, 'sCode': '0', 'sMsg': 'DRY RUN - Order cancelled'}
            
        endpoint = '/api/v5/trade/cancel-order'
        body = {
            'instId': symbol,
            'ordId': order_id
        }

        response = self._request('POST', endpoint, body=body, authenticated=True)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Get order details - SIMULATED in DRY_RUN mode"""
        if self.dry_run:
            return {
                'ordId': order_id,
                'state': 'filled',
                'fillSz': '1',
                'avgPx': '100'
            }
            
        endpoint = '/api/v5/trade/order'
        params = {
            'instId': symbol,
            'ordId': order_id
        }

        response = self._request('GET', endpoint, params=params, authenticated=True)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    # =====================================
    # DRY RUN HELPERS
    # =====================================
    
    def update_dry_run_balance(self, pnl: float):
        """Update simulated balance (for DRY_RUN mode)"""
        if self.dry_run:
            self._dry_run_balance += pnl
            logger.info(f"🧪 DRY RUN: Balance updated to ${self._dry_run_balance:.2f} (PnL: ${pnl:+.2f})")

    def add_dry_run_position(self, position: Dict):
        """Add simulated position (for DRY_RUN mode)"""
        if self.dry_run:
            self._dry_run_positions.append(position)
            
    def remove_dry_run_position(self, position_id: str):
        """Remove simulated position (for DRY_RUN mode)"""
        if self.dry_run:
            self._dry_run_positions = [p for p in self._dry_run_positions if p.get('posId') != position_id]

    # =====================================
    # UTILITY METHODS
    # =====================================

    def get_health_status(self) -> Dict[str, Any]:
        """Get client health metrics"""
        return {
            'request_count': self.request_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.request_count, 1),
            'simulated_mode': self.simulated,
            'dry_run_mode': self.dry_run
        }
