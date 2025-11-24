"""
OKX API Client
Handles all direct interactions with OKX exchange API
Includes rate limiting, retries, and error handling
"""

import time
import hmac
import base64
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
from config import (
    OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, OKX_SIMULATED,
    API_RATE_LIMIT_MS, MAX_RETRIES, RETRY_DELAY_MS
)
import logging

logger = logging.getLogger(__name__)


class OKXClient:
    """
    OKX Exchange API Client with built-in rate limiting and retry logic
    """

    def __init__(self):
        self.api_key = OKX_API_KEY
        self.secret_key = OKX_SECRET_KEY
        self.passphrase = OKX_PASSPHRASE
        self.simulated = OKX_SIMULATED

        # API endpoints
        if self.simulated:
            self.base_url = "https://www.okx.com"
            logger.info("🟡 OKX Client initialized in SIMULATED mode")
        else:
            self.base_url = "https://www.okx.com"
            logger.info("🔴 OKX Client initialized in LIVE mode")

        self.last_request_time = 0
        self.request_count = 0
        self.error_count = 0

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """
        Generate signature for authenticated requests
        """
        message = timestamp + method + request_path + body
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return base64.b64encode(mac.digest()).decode()

    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """
        Generate headers for API request
        """
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
        """
        Implement rate limiting to avoid API throttling
        """
        elapsed = (time.time() * 1000) - self.last_request_time
        if elapsed < API_RATE_LIMIT_MS:
            time.sleep((API_RATE_LIMIT_MS - elapsed) / 1000)
        self.last_request_time = time.time() * 1000

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 body: Optional[Dict] = None, authenticated: bool = False) -> Optional[Dict]:
        """
        Make HTTP request to OKX API with retry logic
        """
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

                # Try to parse response even if status code is error
                try:
                    data = response.json()
                except:
                    data = None

                # Log detailed error info for debugging
                if response.status_code != 200:
                    logger.error(f"❌ HTTP {response.status_code} from {endpoint}")
                    if data:
                        logger.error(f"   OKX Error: {data}")
                    else:
                        logger.error(f"   Response body: {response.text[:500]}")

                response.raise_for_status()


                # Check OKX specific error codes
                if data.get('code') != '0':
                    error_msg = data.get('msg', 'Unknown error')
                    error_code = data.get('code', 'unknown')
                    logger.error(f"❌ OKX API Error [{error_code}]: {error_msg}")
                    logger.error(f"   Endpoint: {endpoint}")
                    logger.error(f"   Params: {params}")
                    logger.error(f"   Response: {data}")
                    self.error_count += 1
                    return None

                self.request_count += 1
                self.error_count = 0  # Reset error count on success

                # Log successful responses for debugging
                logger.debug(f"✅ OKX API Success: {endpoint} (code: {data.get('code')})")

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
    # PUBLIC MARKET DATA ENDPOINTS
    # =====================================

    def get_candles(self, symbol: str, timeframe: str, limit: int = 100,
                    after: Optional[str] = None, before: Optional[str] = None) -> Optional[List[List]]:
        """
        Get candlestick data

        Args:
            symbol: Trading pair (e.g., 'BTC-USDT')
            timeframe: Timeframe (e.g., '1m', '5m', '15m', '1h', '4h')
            limit: Number of candles (max 300)
            after: Pagination - get candles after (older than) this timestamp
            before: Pagination - get candles before (newer than) this timestamp

        Returns:
            List of candles [[timestamp, open, high, low, close, volume, volumeCcy], ...]
            Note: OKX returns candles in reverse chronological order (newest first)
        """
        endpoint = '/api/v5/market/candles'
        params = {
            'instId': symbol,
            'bar': timeframe,
            'limit': min(limit, 300)
        }

        if after:
            params['after'] = after
        if before:
            params['before'] = before

        # Try authenticated request if using pagination parameters
        # Some OKX endpoints require auth even though they're "public"
        use_auth = bool(after or before)

        response = self._request('GET', endpoint, params=params, authenticated=use_auth)
        if response and response.get('data'):
            return response['data']
        return None

    def get_history_candles(self, symbol: str, timeframe: str, limit: int = 100,
                           after: Optional[str] = None, before: Optional[str] = None) -> Optional[List[List]]:
        """
        Get historical candlestick data (for backtesting)

        This endpoint provides access to years of historical data, unlike get_candles()
        which only returns recent candles.

        Args:
            symbol: Trading pair (e.g., 'BTC-USDT')
            timeframe: Timeframe (e.g., '1m', '5m', '15m', '1H', '4H')
            limit: Number of candles (max 100 for history endpoint vs 300 for live)
            after: Pagination - get candles after (older than) this timestamp
            before: Pagination - get candles before (newer than) this timestamp

        Returns:
            List of candles [[timestamp, open, high, low, close, volume, volumeCcy], ...]
            Note: OKX returns candles in reverse chronological order (newest first)
        """
        endpoint = '/api/v5/market/history-candles'
        params = {
            'instId': symbol,
            'bar': timeframe,
            'limit': min(limit, 100)  # History endpoint max is 100
        }

        if after:
            params['after'] = after
        if before:
            params['before'] = before

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data']
        return None

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Get ticker price for symbol
        """
        endpoint = '/api/v5/market/ticker'
        params = {'instId': symbol}

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Get current funding rate for perpetual contracts
        """
        endpoint = '/api/v5/public/funding-rate'
        params = {'instId': symbol}

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_open_interest(self, symbol: str) -> Optional[Dict]:
        """
        Get open interest data
        """
        endpoint = '/api/v5/public/open-interest'
        params = {'instId': symbol}

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data'][0] if response['data'] else None
        return None

    def get_liquidation_orders(self, symbol: str, uly: Optional[str] = None,
                              state: str = 'filled', limit: int = 100) -> Optional[List[Dict]]:
        """
        Get liquidation orders (for heatmap data)
        """
        endpoint = '/api/v5/public/liquidation-orders'
        params = {
            'instId': symbol,
            'state': state,
            'limit': min(limit, 100)
        }

        if uly:
            params['uly'] = uly

        response = self._request('GET', endpoint, params=params)
        if response and response.get('data'):
            return response['data']
        return None

    def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """
        Get orderbook depth
        """
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
    # AUTHENTICATED TRADING ENDPOINTS
    # =====================================

    def get_account_balance(self) -> Optional[List[Dict]]:
        """
        Get account balance
        """
        endpoint = '/api/v5/account/balance'
        response = self._request('GET', endpoint, authenticated=True)
        if response and response.get('data'):
            return response['data']
        return None

    def get_positions(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Get open positions
        """
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
        """
        Place an order

        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            order_type: 'market', 'limit', 'post_only', etc.
            size: Order size
            price: Limit price (for limit orders)
            **kwargs: Additional order parameters
        """
        endpoint = '/api/v5/trade/order'
        body = {
            'instId': symbol,
            'tdMode': kwargs.get('tdMode', 'cross'),  # cross or isolated
            'side': side,
            'ordType': order_type,
            'sz': size,
        }

        if price:
            body['px'] = price

        # Add optional parameters
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
        """
        Cancel an order
        """
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
        """
        Get order details
        """
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
    # UTILITY METHODS
    # =====================================

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get client health metrics
        """
        return {
            'request_count': self.request_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.request_count, 1),
            'simulated_mode': self.simulated
        }
