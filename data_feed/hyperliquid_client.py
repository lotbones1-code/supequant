"""
Hyperliquid API Client - Drop-in replacement for OKXClient
Exposes identical interface so all callers work without modification.
Uses hyperliquid-python-sdk internally.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Timeframe mapping: OKX format -> Hyperliquid format
_TF_MAP = {
    '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
    '1H': '1h', '2H': '2h', '4H': '4h', '6H': '6h', '12H': '12h',
    '1D': '1d', '1W': '1w', '1M': '1M',
    # Also accept lowercase (pass through)
    '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '12h': '12h',
    '1d': '1d', '1w': '1w',
}

# Interval in milliseconds for pagination
_TF_MS = {
    '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000, '30m': 1_800_000,
    '1h': 3_600_000, '2h': 7_200_000, '4h': 14_400_000, '6h': 21_600_000,
    '12h': 43_200_000, '1d': 86_400_000, '1w': 604_800_000, '1M': 2_592_000_000,
}


class HyperliquidClient:
    """
    Hyperliquid API client with OKXClient-compatible interface.
    All public methods return data in the same format as OKXClient
    so callers don't need to change.
    """

    def __init__(self):
        from hyperliquid.exchange import Exchange
        from hyperliquid.utils import constants
        from eth_account import Account

        from config import (
            HYPERLIQUID_PRIVATE_KEY, HYPERLIQUID_WALLET_ADDRESS,
            HYPERLIQUID_MAINNET
        )

        self.dry_run = os.getenv('DRY_RUN', 'False').lower() == 'true'
        self.simulated = False  # Hyperliquid has no simulated mode

        base_url = constants.MAINNET_API_URL if HYPERLIQUID_MAINNET else constants.TESTNET_API_URL

        # Info client (read-only, no auth needed) - with retry for transient network failures
        self.info = self._init_info_with_retry(base_url)

        # Exchange client (requires auth for trading)
        if HYPERLIQUID_PRIVATE_KEY:
            self.wallet = Account.from_key(HYPERLIQUID_PRIVATE_KEY)
            self.exchange = Exchange(self.wallet, base_url, account_address=HYPERLIQUID_WALLET_ADDRESS)
        else:
            self.wallet = None
            self.exchange = None
            logger.warning("No Hyperliquid private key - read-only mode")

        self.address = HYPERLIQUID_WALLET_ADDRESS

        # Health tracking (same interface as OKXClient)
        self.request_count = 0
        self.error_count = 0

        # Cache asset metadata (szDecimals, etc.)
        self._sz_decimals = {}
        self._asset_indices = {}
        self._load_metadata()

        # DRY_RUN simulation state
        self._dry_run_balance = 10000.0
        self._dry_run_positions = []

        logger.info(f"HyperliquidClient initialized (mainnet={HYPERLIQUID_MAINNET}, address={self.address[:10]}...)")

    # ===== INITIALIZATION HELPERS =====

    def _init_info_with_retry(self, base_url: str, max_attempts: int = 3):
        """Initialize Info client with retry logic for transient network failures.

        The hyperliquid-python-sdk's Info class calls spot_meta() during __init__,
        which can fail with RemoteDisconnected errors. This method retries with
        exponential backoff.
        """
        from hyperliquid.info import Info

        for attempt in range(1, max_attempts + 1):
            try:
                info = Info(base_url, skip_ws=True)
                if attempt > 1:
                    logger.info(f"Hyperliquid Info client initialized successfully on attempt {attempt}")
                return info
            except Exception as e:
                logger.error(f"Info client init attempt {attempt}/{max_attempts} failed: {e}")
                if attempt < max_attempts:
                    wait_time = 2 * attempt  # 2s, 4s backoff
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)

        raise RuntimeError(
            "FATAL: Failed to connect to Hyperliquid API after 3 attempts. "
            "Check: 1) VPN is running (required for US users), "
            "2) Internet connection is working, "
            "3) Hyperliquid API is not down."
        )

    # ===== METADATA =====

    def _load_metadata(self):
        """Cache szDecimals from Hyperliquid metadata and update MIN_SOL_CONTRACT.

        Retries up to 3 times with backoff. Raises RuntimeError if all attempts
        fail, because trading with wrong lot sizes is dangerous.
        """
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                meta = self.info.meta()
                universe = meta.get("universe", [])
                for i, asset in enumerate(universe):
                    name = asset.get("name", "")
                    self._sz_decimals[name] = asset.get("szDecimals", 0)
                    self._asset_indices[name] = i

                if not self._sz_decimals:
                    raise ValueError("Metadata returned empty universe")

                sol_decimals = self._sz_decimals.get("SOL", 0)
                min_sol = 10 ** (-sol_decimals) if sol_decimals > 0 else 1.0

                # Update config dynamically
                import config
                config.MIN_SOL_CONTRACT = min_sol
                logger.info(f"Hyperliquid metadata: SOL szDecimals={sol_decimals}, MIN_SOL_CONTRACT={min_sol}")
                logger.info(f"Loaded {len(self._sz_decimals)} assets")
                return  # Success
            except Exception as e:
                logger.error(f"Metadata load attempt {attempt}/{max_attempts} failed: {e}")
                if attempt < max_attempts:
                    import time
                    time.sleep(2 * attempt)  # 2s, 4s backoff

        raise RuntimeError(
            "FATAL: Failed to load Hyperliquid metadata after 3 attempts. "
            "Cannot trade without correct lot sizes. Check network/API."
        )

    def _strip_symbol(self, symbol: str) -> str:
        """Convert any format ('SOL-USDT-SWAP', 'SOL-USDT', 'SOL') to bare coin name."""
        if not symbol:
            return symbol
        return symbol.replace('-USDT-SWAP', '').replace('-USDT', '').replace('-SWAP', '').replace('-PERP', '')

    def _round_size(self, coin: str, size: float) -> float:
        """Round size to Hyperliquid's szDecimals for the asset."""
        decimals = self._sz_decimals.get(coin, 0)
        if decimals == 0:
            return float(int(size))  # Whole numbers only
        factor = 10 ** decimals
        return int(size * factor) / factor  # Round down

    def _round_price(self, price: float, coin: str = "SOL") -> float:
        """Round price to appropriate precision for Hyperliquid."""
        # Hyperliquid allows up to 5 significant figures, max 6 decimals
        # For SOL ($100+), 2 decimal places is safe
        if price >= 100:
            return round(price, 2)
        elif price >= 10:
            return round(price, 3)
        elif price >= 1:
            return round(price, 4)
        else:
            return round(price, 5)

    # ===== MARKET DATA =====

    def get_candles(self, symbol: str, timeframe: str, limit: int = 100,
                    after: Optional[str] = None, before: Optional[str] = None) -> Optional[List[List]]:
        """Get candlestick data. Returns OKX-compatible format: [[ts, o, h, l, c, v, vCcy], ...]"""
        self.request_count += 1
        try:
            coin = self._strip_symbol(symbol)
            hl_tf = _TF_MAP.get(timeframe, timeframe.lower())
            hl_tf_key = hl_tf.replace('h', 'h').replace('H', 'h')
            interval_ms = _TF_MS.get(hl_tf_key, 3_600_000)

            now_ms = int(time.time() * 1000)

            # Calculate time range
            if after:
                # OKX 'after' = return records with ts < after (older data)
                end_time = int(after)
                start_time = end_time - (limit * interval_ms)
            elif before:
                # OKX 'before' = return records with ts > before (newer data)
                start_time = int(before)
                end_time = start_time + (limit * interval_ms)
            else:
                end_time = now_ms
                start_time = end_time - (limit * interval_ms)

            candles = self.info.candles_snapshot(coin, hl_tf, start_time, end_time)

            if not candles:
                return None

            # Convert Hyperliquid dict format to OKX list format
            result = []
            for c in candles:
                ts = str(c.get('t', c.get('T', 0)))
                o = str(c.get('o', '0'))
                h = str(c.get('h', '0'))
                l = str(c.get('l', '0'))
                close = str(c.get('c', '0'))
                v = str(c.get('v', '0'))
                result.append([ts, o, h, l, close, v, '0'])

            # OKX returns newest first
            result.sort(key=lambda x: int(x[0]), reverse=True)

            # Limit results
            if len(result) > limit:
                result = result[:limit]

            return result

        except Exception as e:
            self.error_count += 1
            logger.error(f"get_candles error: {e}")
            return None

    def get_history_candles(self, symbol: str, timeframe: str, limit: int = 100,
                           after: Optional[str] = None, before: Optional[str] = None,
                           force_history_endpoint: bool = False) -> Optional[List[List]]:
        """Get historical candles. Delegates to get_candles (Hyperliquid has unified endpoint)."""
        return self.get_candles(symbol, timeframe, limit, after, before)

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get current ticker price. Returns {'last': price_str, 'instId': symbol}."""
        self.request_count += 1
        try:
            coin = self._strip_symbol(symbol)
            mids = self.info.all_mids()
            if coin in mids:
                return {"last": str(mids[coin]), "instId": symbol}
            logger.warning(f"Ticker not found for {coin}")
            return None
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_ticker error: {e}")
            return None

    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Get current funding rate. Returns {'fundingRate': rate_str, ...}."""
        self.request_count += 1
        try:
            coin = self._strip_symbol(symbol)
            data = self.info.meta_and_asset_ctxs()
            meta = data[0]
            ctxs = data[1]
            for i, asset in enumerate(meta.get("universe", [])):
                if asset.get("name") == coin:
                    ctx = ctxs[i]
                    return {
                        "fundingRate": str(ctx.get("funding", "0")),
                        "fundingTime": str(int(time.time() * 1000)),
                        "nextFundingTime": str(int(time.time() * 1000) + 3_600_000),
                    }
            return None
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_funding_rate error: {e}")
            return None

    def get_open_interest(self, symbol: str) -> Optional[Dict]:
        """Get open interest. Returns {'oi': value, 'oiCcy': value}."""
        self.request_count += 1
        try:
            coin = self._strip_symbol(symbol)
            data = self.info.meta_and_asset_ctxs()
            meta = data[0]
            ctxs = data[1]
            for i, asset in enumerate(meta.get("universe", [])):
                if asset.get("name") == coin:
                    ctx = ctxs[i]
                    oi = str(ctx.get("openInterest", "0"))
                    return {"oi": oi, "oiCcy": oi, "ts": str(int(time.time() * 1000))}
            return None
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_open_interest error: {e}")
            return None

    def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """Get orderbook. Returns {'asks': [[px, sz, ...], ...], 'bids': [...]}."""
        self.request_count += 1
        try:
            coin = self._strip_symbol(symbol)
            snapshot = self.info.l2_snapshot(coin)
            if not snapshot:
                return None

            levels = snapshot.get("levels", [[], []])
            bids = []
            asks = []

            if len(levels) >= 2:
                for level in levels[0][:depth]:  # bids
                    bids.append([str(level.get("px", "0")), str(level.get("sz", "0")), "0", str(level.get("n", 1))])
                for level in levels[1][:depth]:  # asks
                    asks.append([str(level.get("px", "0")), str(level.get("sz", "0")), "0", str(level.get("n", 1))])

            return {"asks": asks, "bids": bids, "ts": str(int(time.time() * 1000))}
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_orderbook error: {e}")
            return None

    # ===== ACCOUNT & BALANCE =====

    def get_account_balance(self) -> Optional[List[Dict]]:
        """Get account balance in OKX-compatible format."""
        self.request_count += 1
        if self.dry_run:
            return [{"details": [{"ccy": "USDT", "availBal": str(self._dry_run_balance),
                                   "availEq": str(self._dry_run_balance),
                                   "eqUsd": str(self._dry_run_balance),
                                   "eq": str(self._dry_run_balance)}],
                      "totalEq": str(self._dry_run_balance)}]
        try:
            state = self.info.user_state(self.address)
            if not state:
                return None

            margin = state.get("marginSummary", {})
            account_value = str(margin.get("accountValue", "0"))
            withdrawable = str(state.get("withdrawable", account_value))

            # Return "USDT" as ccy for backward compatibility (actual currency is USDC)
            return [{
                "details": [{
                    "ccy": "USDT",
                    "availBal": withdrawable,
                    "availEq": account_value,
                    "eqUsd": account_value,
                    "eq": account_value
                }],
                "totalEq": account_value
            }]
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_account_balance error: {e}")
            return None

    def get_trading_balance(self, currency: str = 'USDT') -> Optional[float]:
        """Get available trading balance."""
        if self.dry_run:
            return self._dry_run_balance
        try:
            state = self.info.user_state(self.address)
            if not state:
                return None
            return float(state.get("withdrawable", 0))
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_trading_balance error: {e}")
            return None

    def get_currency_balance(self, currency: str = 'SOL') -> Optional[float]:
        """Get balance for specific currency. Returns 0 - no spot on Hyperliquid perps."""
        if self.dry_run:
            return 1.0 if currency == 'SOL' else 100.0
        return 0.0

    # ===== LEVERAGE =====

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'isolated',
                     pos_side: str = None) -> bool:
        """Set leverage for perpetual trading."""
        if self.dry_run:
            return True
        try:
            coin = self._strip_symbol(symbol)
            is_cross = (margin_mode == 'cross')
            self.exchange.update_leverage(leverage, coin, is_cross)
            logger.info(f"Set leverage: {coin} {leverage}x ({'cross' if is_cross else 'isolated'})")
            return True
        except Exception as e:
            logger.warning(f"Set leverage warning (non-critical): {e}")
            return True  # Non-fatal - may already be set

    def get_leverage(self, symbol: str, margin_mode: str = 'isolated') -> Optional[int]:
        """Get current leverage setting."""
        if self.dry_run:
            return 5
        try:
            state = self.info.user_state(self.address)
            coin = self._strip_symbol(symbol)
            for pos_data in state.get("assetPositions", []):
                pos = pos_data.get("position", {})
                if pos.get("coin") == coin:
                    lev = pos.get("leverage", {})
                    return int(float(lev.get("value", 5)))
            return 5  # Default if no position
        except Exception as e:
            logger.error(f"get_leverage error: {e}")
            return 5

    # ===== POSITIONS =====

    def get_positions(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """Get open positions in OKX-compatible format."""
        if self.dry_run:
            return self._dry_run_positions
        self.request_count += 1
        try:
            state = self.info.user_state(self.address)
            if not state:
                return []

            coin_filter = self._strip_symbol(symbol) if symbol else None
            positions = []

            for pos_data in state.get("assetPositions", []):
                pos = pos_data.get("position", {})
                coin = pos.get("coin", "")

                if coin_filter and coin != coin_filter:
                    continue

                szi = float(pos.get("szi", 0))
                if abs(szi) > 0.0001:
                    positions.append({
                        "instId": coin,
                        "pos": str(szi),
                        "posSide": "net",
                        "avgPx": str(pos.get("entryPx", "0")),
                        "upl": str(pos.get("unrealizedPnl", "0")),
                        "posId": coin,
                        "liqPx": str(pos.get("liquidationPx", "0")),
                        "lever": str(pos.get("leverage", {}).get("value", 5)),
                        "mgnMode": "cross" if pos.get("leverage", {}).get("type") == "cross" else "isolated"
                    })

            return positions
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_positions error: {e}")
            return []

    # ===== ORDER MANAGEMENT =====

    def place_order(self, symbol: str, side: str, order_type: str, size: str,
                    price: Optional[str] = None, **kwargs) -> Optional[Dict]:
        """Place order. Returns {'ordId': id, 'sCode': '0', 'sMsg': ''} or None."""
        self.request_count += 1

        if self.dry_run:
            dry_id = f"DRY-{int(time.time() * 1000)}"
            logger.info(f"[DRY RUN] Order: {side} {size} {symbol} @ {price or 'market'}")
            return {"ordId": dry_id, "clOrdId": "", "sCode": "0", "sMsg": ""}

        try:
            coin = self._strip_symbol(symbol)
            is_buy = (side.lower() == 'buy')
            sz = self._round_size(coin, float(size))

            if sz <= 0:
                logger.error(f"Order size too small after rounding: {size} -> {sz}")
                return None

            reduce_only = (kwargs.get('reduce_only', 'false') == 'true' or
                           kwargs.get('reduceOnly', False) == True)

            # tdMode is ignored (Hyperliquid doesn't use it)
            # But we log it for debugging
            td_mode = kwargs.get('tdMode', kwargs.get('td_mode', ''))
            if td_mode:
                logger.debug(f"Ignoring tdMode={td_mode} (not used on Hyperliquid)")

            logger.info(f"Placing order: {side} {sz} {coin} @ {'market' if order_type == 'market' else price} "
                        f"(reduce_only={reduce_only})")

            # Ensure leverage is set before opening new positions
            if not reduce_only:
                try:
                    import config as _cfg
                    lev = getattr(_cfg, 'GROWTH_LEVERAGE', 5)
                    self.exchange.update_leverage(lev, coin, is_cross=True)
                    logger.debug(f"Confirmed leverage {lev}x for {coin}")
                except Exception as lev_err:
                    logger.warning(f"Leverage set warning (non-fatal): {lev_err}")

            if order_type == 'market':
                if reduce_only:
                    # Close position - use market_close
                    result = self.exchange.market_close(coin, sz=sz)
                else:
                    result = self.exchange.market_open(coin, is_buy, sz)
            else:
                # Limit order
                px = self._round_price(float(price), coin)
                order_type_spec = {"limit": {"tif": "Gtc"}}
                result = self.exchange.order(coin, is_buy, sz, px, order_type_spec, reduce_only=reduce_only)

            # Parse response
            if result and result.get("status") == "ok":
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    oid = None
                    if "resting" in status:
                        oid = str(status["resting"]["oid"])
                        logger.info(f"Order resting: oid={oid}")
                    elif "filled" in status:
                        oid = str(status["filled"]["oid"])
                        avg_px = status["filled"].get("avgPx", "0")
                        total_sz = status["filled"].get("totalSz", "0")
                        logger.info(f"Order filled: oid={oid}, avgPx={avg_px}, sz={total_sz}")
                    elif "error" in status:
                        logger.error(f"Order error: {status['error']}")
                        return None

                    if oid:
                        return {"ordId": oid, "clOrdId": "", "sCode": "0", "sMsg": ""}

            logger.error(f"Order failed: {result}")
            return None

        except Exception as e:
            self.error_count += 1
            logger.error(f"place_order error: {e}")
            return None

    def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Cancel an open order."""
        if self.dry_run:
            return {"ordId": order_id, "sCode": "0", "sMsg": "Cancelled"}
        try:
            coin = self._strip_symbol(symbol)
            result = self.exchange.cancel(coin, int(order_id))
            if result and result.get("status") == "ok":
                return {"ordId": order_id, "sCode": "0", "sMsg": "Cancelled"}
            logger.warning(f"Cancel may have failed: {result}")
            return {"ordId": order_id, "sCode": "0", "sMsg": "Cancel attempted"}
        except Exception as e:
            self.error_count += 1
            logger.error(f"cancel_order error: {e}")
            return None

    def get_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Get order status. Returns {'ordId': id, 'state': 'filled'/'live', ...}."""
        if self.dry_run:
            return {"ordId": order_id, "state": "filled", "fillSz": "1", "avgPx": "0",
                    "sz": "1", "side": "buy"}
        self.request_count += 1
        try:
            # Check if order is still open
            open_orders = self.info.open_orders(self.address)
            for order in open_orders:
                if str(order.get("oid")) == str(order_id):
                    return {
                        "ordId": str(order_id),
                        "state": "live",
                        "fillSz": "0",
                        "avgPx": str(order.get("limitPx", "0")),
                        "sz": str(order.get("sz", "0")),
                        "side": "buy" if order.get("side", "").upper() == "B" else "sell"
                    }

            # Not in open orders - check fills
            try:
                fills = self.info.user_fills(self.address)
                for fill in reversed(fills):  # newest first
                    if str(fill.get("oid")) == str(order_id):
                        return {
                            "ordId": str(order_id),
                            "state": "filled",
                            "fillSz": str(fill.get("sz", "0")),
                            "avgPx": str(fill.get("px", "0")),
                            "sz": str(fill.get("sz", "0")),
                            "side": "buy" if fill.get("side", "").upper() == "B" else "sell"
                        }
            except Exception:
                pass

            # Order not found in open orders or fills - it was likely cancelled
            # DO NOT assume "filled" - this caused fake TP FILLED logs!
            return {"ordId": str(order_id), "state": "cancelled", "fillSz": "0", "avgPx": "0"}

        except Exception as e:
            self.error_count += 1
            logger.error(f"get_order error: {e}")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """Get open orders in OKX-compatible format."""
        if self.dry_run:
            return []
        self.request_count += 1
        try:
            open_orders = self.info.open_orders(self.address)
            coin_filter = self._strip_symbol(symbol) if symbol else None

            result = []
            for order in open_orders:
                coin = order.get("coin", "")
                if coin_filter and coin != coin_filter:
                    continue
                result.append({
                    "ordId": str(order.get("oid", "")),
                    "instId": coin,
                    "side": "buy" if order.get("side", "").upper() == "B" else "sell",
                    "sz": str(order.get("sz", "0")),
                    "px": str(order.get("limitPx", "0")),
                    "state": "live"
                })
            return result
        except Exception as e:
            self.error_count += 1
            logger.error(f"get_open_orders error: {e}")
            return []

    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count cancelled."""
        if self.dry_run:
            return 0
        try:
            orders = self.get_open_orders(symbol)
            if not orders:
                return 0
            count = 0
            for order in orders:
                result = self.cancel_order(symbol, order.get("ordId", ""))
                if result:
                    count += 1
            return count
        except Exception as e:
            logger.error(f"cancel_all_orders error: {e}")
            return 0

    # ===== DRY RUN SIMULATION =====

    def update_dry_run_balance(self, pnl: float):
        """Update simulated balance for DRY_RUN mode."""
        if self.dry_run:
            self._dry_run_balance += pnl

    def add_dry_run_position(self, position: Dict):
        """Add simulated position for DRY_RUN mode."""
        if self.dry_run:
            self._dry_run_positions.append(position)

    def remove_dry_run_position(self, position_id: str):
        """Remove simulated position for DRY_RUN mode."""
        if self.dry_run:
            self._dry_run_positions = [p for p in self._dry_run_positions
                                        if p.get('posId', '') != position_id]

    # ===== HEALTH =====

    def get_health_status(self) -> Dict[str, Any]:
        """Get client health metrics."""
        # Return error_rate as decimal (0.0-1.0) to match risk_manager expectations
        error_rate = self.error_count / max(1, self.request_count)
        return {
            'request_count': self.request_count,
            'error_count': self.error_count,
            'error_rate': error_rate,
            'simulated_mode': self.simulated,
            'dry_run_mode': self.dry_run,
            'exchange': 'hyperliquid'
        }

    def reset_error_counts(self):
        """Reset error tracking counters. Call after recovery from issues."""
        self.request_count = 0
        self.error_count = 0
        logger.info("Health counters reset")
