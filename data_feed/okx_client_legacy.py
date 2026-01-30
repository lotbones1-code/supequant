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
    OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, OKX_SIMULATED, OKX_API_DOMAIN,
    API_RATE_LIMIT_MS, MAX_RETRIES, RETRY_DELAY_MS, API_TIMEOUT_SECONDS
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
        # Strip any whitespace from passphrase (common issue with .env files)
        self.passphrase = OKX_PASSPHRASE.strip() if OKX_PASSPHRASE else ''
        self.simulated = OKX_SIMULATED
        # Live trading always overrides DRY_RUN - disable DRY_RUN if OKX_SIMULATED=False
        # This ensures real money trading always uses real API calls
        self.dry_run = DRY_RUN and OKX_SIMULATED

        # API endpoints - Use US domain for American accounts
        self.base_url = f"https://{OKX_API_DOMAIN}"
        
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

        # Ensure passphrase is clean (no extra spaces/newlines)
        # OKX v5 API requires passphrase as plain text (not encoded)
        passphrase_clean = self.passphrase.strip() if self.passphrase else ''

        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': passphrase_clean,
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
        
        # For authenticated GET requests, include query string in signature
        # OKX requires: signature = HMAC(timestamp + method + request_path_with_query + body)
        sign_path = endpoint
        if params and method == 'GET':
            query_string = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
            sign_path = f"{endpoint}?{query_string}"

        for attempt in range(MAX_RETRIES):
            try:
                if authenticated:
                    headers = self._get_headers(method, sign_path, request_body)
                else:
                    headers = {'Content-Type': 'application/json'}

                if method == 'GET':
                    response = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT_SECONDS)
                elif method == 'POST':
                    response = requests.post(url, data=request_body, headers=headers, timeout=API_TIMEOUT_SECONDS)
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
                        # Log detailed error info from data array
                        self._log_detailed_errors(data)

                response.raise_for_status()

                if data.get('code') != '0':
                    error_msg = data.get('msg', 'Unknown error')
                    error_code = data.get('code', 'unknown')
                    logger.error(f"❌ OKX API Error [{error_code}]: {error_msg}")
                    # Log detailed error info from data array
                    self._log_detailed_errors(data)
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

    def _log_detailed_errors(self, data: Dict):
        """Extract and log detailed error messages from OKX response"""
        if not isinstance(data, dict):
            return
        
        # Reset last error code
        self._last_error_code = None
        
        # OKX returns errors in the 'data' array with sCode and sMsg
        error_data = data.get('data', [])
        if isinstance(error_data, list):
            for item in error_data:
                if isinstance(item, dict):
                    s_code = item.get('sCode', '')
                    s_msg = item.get('sMsg', '')
                    
                    # Track the error code for fallback handling
                    if s_code and s_code != '0':
                        self._last_error_code = s_code
                    if s_code or s_msg:
                        logger.error(f"   📋 Detail [{s_code}]: {s_msg}")
                        
                        # Common OKX error codes with helpful messages
                        if s_code == '51000':
                            logger.error(f"      💡 Parameter error - check order parameters")
                        elif s_code == '51001':
                            logger.error(f"      💡 Instrument ID does not exist")
                        elif s_code == '51008':
                            logger.error(f"      💡 Order failed - check margin/leverage settings")
                        elif s_code == '51010':
                            logger.error(f"      💡 Insufficient account balance")
                        elif s_code == '51020':
                            logger.error(f"      💡 Order size too small - check minimum order size")
                        elif s_code == '51021':
                            logger.error(f"      💡 Order size increment invalid")
                        elif s_code == '51024':
                            logger.error(f"      💡 Leverage exceeds allowed maximum")
                        elif s_code == '51100':
                            logger.error(f"      💡 Risk ratio too high - reduce position or add margin")
                        elif s_code == '51101':
                            logger.error(f"      💡 Leverage ratio too high for current position")
                        elif s_code == '51102':
                            logger.error(f"      💡 Current leverage needs adjustment first")
                        elif s_code == '51103':
                            logger.error(f"      💡 Need to set leverage before trading isolated margin")
                        elif s_code == '51111':
                            logger.error(f"      💡 Margin mode mismatch - check cross vs isolated")
                        elif s_code == '51113':
                            logger.error(f"      💡 Position does not exist")
                        elif s_code == '51115':
                            logger.error(f"      💡 Cannot switch margin mode with open positions")
                        elif s_code == '51119':
                            logger.error(f"      💡 Current position or pending orders prevent this action")
                        elif s_code == '51127':
                            logger.error(f"      💡 Available balance insufficient for isolated margin")
                        elif s_code == '51131':
                            logger.error(f"      💡 Insufficient available balance for the order")
                        elif s_code == '59000':
                            logger.error(f"      💡 System busy - try again shortly")
                        elif s_code == '59001':
                            logger.error(f"      💡 Trading suspended for this instrument")

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
                           after: Optional[str] = None, before: Optional[str] = None,
                           force_history_endpoint: bool = False) -> Optional[List[List]]:
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
        # CRITICAL FIX: For backtesting, ALWAYS use history-candles endpoint
        # The regular candles endpoint only returns last 24 hours regardless of date parameters
        # If force_history_endpoint=True OR pagination params provided, use history endpoint
        use_history_endpoint = force_history_endpoint
        
        if force_history_endpoint:
            logger.debug(f"   Using history-candles endpoint (forced for backtesting)")
        elif after is not None:
            # 'after' parameter means we're paginating backwards for backtesting - ALWAYS use history endpoint
            use_history_endpoint = True
            logger.debug(f"   Using history-candles endpoint (backtesting with 'after' pagination)")
        elif before is not None:
            # 'before' parameter - also use history endpoint for backtesting
            use_history_endpoint = True
            logger.debug(f"   Using history-candles endpoint (backtesting with 'before' pagination)")
        
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
        # Only add if not None (None means get most recent)
        if after is not None:
            params['after'] = after
        if before is not None:
            params['before'] = before

        # Log request details for debugging
        logger.debug(f"📡 OKX {endpoint.split('/')[-1]} request: symbol={symbol}, timeframe={timeframe}, after={after}, before={before}, limit={params['limit']}")

        # Explicitly use authenticated=False for public endpoint
        response = self._request('GET', endpoint, params=params, authenticated=False)
        
        if response:
            response_code = response.get('code', 'unknown')
            response_msg = response.get('msg', 'N/A')
            data = response.get('data', [])
            
            # Log full response for debugging if no data
            if not data or len(data) == 0:
                logger.warning(f"⚠️  OKX {endpoint.split('/')[-1]}: API returned success but NO DATA")
                logger.warning(f"   Response code: {response_code}, msg: {response_msg}")
                logger.warning(f"   Params: {params}")
                logger.warning(f"   Full response: {json.dumps(response, indent=2)[:500]}")  # First 500 chars
                
                # If using history-candles and getting no data, might be date range issue
                if endpoint == '/api/v5/market/history-candles':
                    logger.warning(f"   💡 Tip: history-candles endpoint might not have data for this date range")
                    logger.warning(f"      Try checking if dates are too recent or symbol format is correct")
            
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
                    'eq': str(self._dry_run_balance),
                    'eqUsd': str(self._dry_run_balance)
                }],
                'totalEq': str(self._dry_run_balance)
            }]
            
        endpoint = '/api/v5/account/balance'
        response = self._request('GET', endpoint, authenticated=True)
        if response and response.get('data'):
            return response['data']
        return None

    def get_trading_balance(self, currency: str = 'USDT') -> Optional[float]:
        """
        Get available trading balance for a specific currency
        This returns ONLY the balance available for trading, not total equity
        
        For SOL trading with USDT margin:
        - Returns USDT available balance (availBal or availEq)
        - Does NOT include other assets like XRP
        
        Args:
            currency: Currency to get balance for (default: USDT)
            
        Returns:
            Available balance in the specified currency, or None if failed
        """
        if self.dry_run:
            return self._dry_run_balance
            
        balance_data = self.get_account_balance()
        if not balance_data:
            return None
        
        for balance in balance_data:
            details = balance.get('details', [])
            for detail in details:
                if detail.get('ccy') == currency:
                    # For trading, use availBal (available balance) or availEq
                    # availBal = balance available to transfer/trade
                    # availEq = equity available for trading (includes unrealized PnL)
                    avail_bal = detail.get('availBal', '')
                    avail_eq = detail.get('availEq', '')
                    
                    # Prefer availBal for actual tradeable amount
                    balance_str = avail_bal if avail_bal else avail_eq
                    
                    if balance_str:
                        try:
                            return float(balance_str)
                        except (ValueError, TypeError):
                            pass
        
        return None

    def get_currency_balance(self, currency: str = 'SOL') -> Optional[float]:
        """
        Get available balance for a specific currency (e.g., SOL for spot trading)
        
        Args:
            currency: Currency to get balance for (default: SOL)
            
        Returns:
            Available balance in the specified currency, or None if failed
        """
        if self.dry_run:
            # For dry run, return a mock balance
            return 1.0 if currency == 'SOL' else 100.0
            
        balance_data = self.get_account_balance()
        if not balance_data:
            return None
        
        for balance in balance_data:
            details = balance.get('details', [])
            for detail in details:
                if detail.get('ccy') == currency:
                    # For spot trading, use availBal (available balance)
                    avail_bal = detail.get('availBal', '')
                    
                    if avail_bal:
                        try:
                            return float(avail_bal)
                        except (ValueError, TypeError):
                            pass
        
        return None

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'isolated', 
                     pos_side: str = None) -> bool:
        """
        Set leverage for a symbol BEFORE placing orders
        
        OKX requires leverage to be set via this separate API call
        before placing orders with isolated margin.
        
        Args:
            symbol: Instrument ID (e.g., 'SOL-USDT-SWAP')
            leverage: Leverage multiplier (e.g., 5 for 5x)
            margin_mode: 'isolated' or 'cross'
            pos_side: Position side ('long', 'short', or None for net mode)
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            logger.info(f"🧪 DRY RUN: Simulated leverage set to {leverage}x ({margin_mode})")
            return True
            
        endpoint = '/api/v5/account/set-leverage'
        body = {
            'instId': symbol,
            'lever': str(leverage),
            'mgnMode': margin_mode
        }
        
        # Only add posSide if specified (required for long/short mode)
        if pos_side:
            body['posSide'] = pos_side
        
        logger.info(f"⚙️  Setting leverage: {leverage}x {margin_mode} for {symbol}")
        
        response = self._request('POST', endpoint, body=body, authenticated=True)
        
        if response and response.get('code') == '0':
            logger.info(f"✅ Leverage set to {leverage}x ({margin_mode})")
            return True
        else:
            # Log the error but don't fail - leverage might already be set
            if response:
                error_code = response.get('code', 'unknown')
                error_msg = response.get('msg', 'Unknown error')
                logger.warning(f"⚠️  Set leverage response [{error_code}]: {error_msg}")
                
                # Check if leverage is already set (not a critical failure)
                if error_code in ['51000', '51109']:  # Already set or parameter issues
                    logger.info(f"   Leverage may already be configured - continuing")
                    return True
            
            return False

    def get_leverage(self, symbol: str, margin_mode: str = 'isolated') -> Optional[int]:
        """
        Get current leverage setting for a symbol
        
        Args:
            symbol: Instrument ID
            margin_mode: 'isolated' or 'cross'
            
        Returns:
            Current leverage or None if failed
        """
        if self.dry_run:
            return 5  # Default simulated leverage
            
        endpoint = '/api/v5/account/leverage-info'
        params = {
            'instId': symbol,
            'mgnMode': margin_mode
        }
        
        response = self._request('GET', endpoint, params=params, authenticated=True)
        
        if response and response.get('data'):
            data = response['data']
            if isinstance(data, list) and len(data) > 0:
                lever = data[0].get('lever', '')
                if lever:
                    try:
                        return int(float(lever))
                    except (ValueError, TypeError):
                        pass
        
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
        
        # Detect if this is a spot order (no '-SWAP' suffix)
        is_spot = not symbol.upper().endswith('-SWAP')
        
        body = {
            'instId': symbol,
            'side': side,
            'ordType': order_type,
            'sz': size,
        }
        
        # tdMode is REQUIRED for all orders:
        # - SPOT trading: tdMode = 'cash'
        # - PERPETUAL/MARGIN trading: tdMode = 'cross' or 'isolated'
        if is_spot:
            body['tdMode'] = 'cash'
        else:
            body['tdMode'] = kwargs.get('tdMode', 'cross')
        
        if price:
            body['px'] = price

        # reduceOnly is only for perpetuals
        if 'reduce_only' in kwargs and not is_spot:
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

    def get_open_orders(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Get all open/pending orders
        
        Args:
            symbol: Optional instrument ID to filter by (e.g., 'SOL-USDT')
            
        Returns:
            List of open orders, or None if failed
        """
        if self.dry_run:
            return []
            
        endpoint = '/api/v5/trade/orders-pending'
        params = {}
        if symbol:
            params['instId'] = symbol

        response = self._request('GET', endpoint, params=params, authenticated=True)
        if response and response.get('data'):
            return response['data']
        return None

    def cancel_all_orders(self, symbol: str) -> int:
        """
        Cancel all open orders for a symbol
        
        Args:
            symbol: Instrument ID (e.g., 'SOL-USDT')
            
        Returns:
            Number of orders cancelled
        """
        if self.dry_run:
            logger.info(f"🧪 DRY RUN: Simulated cancel all orders for {symbol}")
            return 0
            
        open_orders = self.get_open_orders(symbol)
        if not open_orders:
            return 0
            
        cancelled = 0
        for order in open_orders:
            order_id = order.get('ordId')
            if order_id:
                result = self.cancel_order(symbol, order_id)
                if result:
                    cancelled += 1
                    logger.info(f"   🗑️  Cancelled order: {order_id}")
                    
        return cancelled

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
