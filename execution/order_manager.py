"""
Order Manager
Handles order creation, modification, and cancellation on OKX
"""

from typing import Dict, Optional, List
import logging
from datetime import datetime
from data_feed.okx_client import OKXClient
from config import (
    TRADING_SYMBOL, TRADING_MODE, MAX_RISK_PER_TRADE, 
    GROWTH_MODE_ENABLED, GROWTH_LEVERAGE,
    SPOT_FALLBACK_ENABLED, SPOT_SYMBOL,
    LIMIT_ORDER_ENTRY_ENABLED, LIMIT_ORDER_IMPROVEMENT,
    LIMIT_ORDER_TIMEOUT, LIMIT_ORDER_MARKET_FALLBACK
)
import time

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order lifecycle on OKX exchange
    """

    def __init__(self, okx_client: Optional[OKXClient] = None):
        self.client = okx_client or OKXClient()
        self.active_orders = {}
        self.order_history = []
        # Track orders placed in current session (to avoid canceling them)
        self._session_order_ids = set()

    def place_market_order(self, signal: Dict, position_size: float) -> Optional[Dict]:
        """
        Place market order based on signal
        
        Strategy:
        1. Try perpetual (SOL-USDT-SWAP) with leverage first
        2. If compliance error (51155), fallback to spot (SOL-USDT)
        
        Args:
            signal: Trading signal from strategy
            position_size: Position size in base currency

        Returns:
            Order details or None if failed
        """
        try:
            symbol = TRADING_SYMBOL
            direction = signal['direction']
            side = 'buy' if direction == 'long' else 'sell'
            is_spot = TRADING_MODE == 'spot'
            used_spot_fallback = False

            logger.info(f"📤 Placing {side.upper()} market order: {position_size:.4f} @ market")

            # PERPETUAL MODE (default)
            if not is_spot:
                td_mode = 'cross'
                leverage = None
                use_leverage = GROWTH_MODE_ENABLED and GROWTH_LEVERAGE > 1
                
                if use_leverage:
                    leverage_set = self.client.set_leverage(
                        symbol=symbol,
                        leverage=GROWTH_LEVERAGE,
                        margin_mode='isolated'
                    )
                    
                    if leverage_set:
                        td_mode = 'isolated'
                        leverage = GROWTH_LEVERAGE
                        logger.info(f"⚡ Using {GROWTH_LEVERAGE}x leverage (isolated margin)")
                    else:
                        logger.warning(f"⚠️  Could not set isolated leverage - using cross margin")
                        td_mode = 'cross'

                # Validate minimum (0.1 for perpetual)
                min_size = 0.1
                if position_size < min_size:
                    logger.warning(f"⚠️  Position size {position_size:.4f} below minimum {min_size}")
                    position_size = min_size

                # Try perpetual order
                order_kwargs = {
                    'symbol': symbol,
                    'side': side,
                    'order_type': 'market',
                    'size': str(round(position_size, 2)),
                    'tdMode': td_mode
                }
                
                order_result = self.client.place_order(**order_kwargs)

                # If isolated failed, try cross
                if not order_result and td_mode == 'isolated':
                    logger.warning(f"⚠️  Isolated margin failed - trying cross margin...")
                    order_kwargs['tdMode'] = 'cross'
                    order_result = self.client.place_order(**order_kwargs)
                    if order_result:
                        td_mode = 'cross'

                # Check if we got compliance error (51155) - fallback to spot
                if not order_result and SPOT_FALLBACK_ENABLED:
                    last_error = getattr(self.client, '_last_error_code', None)
                    if last_error == '51155':
                        logger.warning(f"⚠️  Compliance restriction on perpetuals (51155)")
                        logger.info(f"🔄 Falling back to SPOT trading ({SPOT_SYMBOL})...")
                        is_spot = True
                        used_spot_fallback = True
                        symbol = SPOT_SYMBOL
                    else:
                        logger.error("❌ Failed to place perpetual order")
                        return None
                elif not order_result:
                    logger.error("❌ Failed to place perpetual order")
                    return None

            # SPOT MODE (or fallback)
            if is_spot:
                td_mode = 'cash'
                leverage = None
                
                if used_spot_fallback:
                    logger.info(f"💵 Using SPOT mode (compliance fallback) - no leverage")
                    
                    # CRITICAL: Recalculate position size for spot (no leverage!)
                    # The original position_size was calculated with leverage for perpetuals
                    # For spot, we need to use actual available USDT
                    usdt_balance = self.client.get_trading_balance('USDT')
                    if usdt_balance and usdt_balance > 0:
                        # Get current price to calculate how much SOL we can buy
                        current_price = signal.get('entry_price', 0)
                        if current_price > 0:
                            # Calculate max SOL we can buy with available USDT
                            # Use 95% of balance to account for fees
                            max_sol = (usdt_balance * 0.95) / current_price
                            
                            if position_size > max_sol:
                                logger.warning(f"⚠️  Original size ({position_size:.4f}) exceeds spot capacity")
                                logger.info(f"   📊 Available USDT: ${usdt_balance:.2f}")
                                logger.info(f"   📊 Max SOL buyable: {max_sol:.4f}")
                                logger.info(f"   📝 Adjusting position size for SPOT (no leverage)")
                                position_size = max_sol
                else:
                    logger.info(f"💵 Using SPOT mode - no leverage")

                # Validate minimum for spot (0.01 SOL practical minimum)
                min_size = 0.01
                if position_size < min_size:
                    logger.warning(f"⚠️  Position size {position_size:.4f} below minimum {min_size}")
                    position_size = min_size

                order_kwargs = {
                    'symbol': symbol,
                    'side': side,
                    'order_type': 'market',
                    'size': str(round(position_size, 4)),
                    'tdMode': 'cash'
                }
                
                order_result = self.client.place_order(**order_kwargs)
                
                if not order_result:
                    logger.error("❌ Failed to place spot order")
                    return None

            order_id = order_result.get('ordId')

            # Create order record
            order = {
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'type': 'market',
                'size': position_size,
                'signal': signal,
                'timestamp': datetime.now(),
                'status': 'filled',
                'margin_mode': td_mode,
                'leverage': leverage,
                'trading_mode': 'spot' if is_spot else 'perp',
                'used_fallback': used_spot_fallback
            }

            self.active_orders[order_id] = order
            self.order_history.append(order)

            logger.info(f"✅ Market order placed: {order_id}")
            if is_spot:
                logger.info(f"   Mode: SPOT (cash){' [FALLBACK]' if used_spot_fallback else ''}")
            else:
                logger.info(f"   Mode: {td_mode.upper()}, Leverage: {leverage or 1}x")

            return order

        except Exception as e:
            logger.error(f"❌ Error placing market order: {e}", exc_info=True)
            return None

    def place_limit_entry_order(self, signal: Dict, position_size: float) -> Optional[Dict]:
        """
        Place limit order for entry at a better price, with market fallback.
        
        This method attempts to get a better entry by placing a limit order
        slightly below current price (for longs) or above (for shorts).
        
        If the limit order doesn't fill within LIMIT_ORDER_TIMEOUT seconds,
        it cancels and falls back to a market order.
        
        Args:
            signal: Trading signal from strategy
            position_size: Position size in base currency
            
        Returns:
            Order details or None if failed
        """
        # If limit orders disabled, use market directly
        if not LIMIT_ORDER_ENTRY_ENABLED:
            return self.place_market_order(signal, position_size)
        
        try:
            symbol = TRADING_SYMBOL
            direction = signal['direction']
            side = 'buy' if direction == 'long' else 'sell'
            current_price = signal.get('entry_price', 0)
            
            if current_price <= 0:
                logger.warning("⚠️  No entry price in signal, using market order")
                return self.place_market_order(signal, position_size)
            
            # Calculate limit price with improvement
            improvement = LIMIT_ORDER_IMPROVEMENT
            if direction == 'long':
                # Better entry for long = lower price
                limit_price = current_price * (1 - improvement)
            else:
                # Better entry for short = higher price
                limit_price = current_price * (1 + improvement)
            
            limit_price = round(limit_price, 2)
            
            logger.info(f"📤 Placing LIMIT {side.upper()} order: {position_size:.4f} @ ${limit_price:.2f}")
            logger.info(f"   Target improvement: {improvement*100:.2f}% ({direction})")
            logger.info(f"   Current price: ${current_price:.2f} → Limit: ${limit_price:.2f}")
            
            is_spot = TRADING_MODE == 'spot'
            td_mode = 'cash' if is_spot else 'cross'
            
            # Set leverage for perpetuals if needed
            if not is_spot and GROWTH_MODE_ENABLED and GROWTH_LEVERAGE > 1:
                leverage_set = self.client.set_leverage(
                    symbol=symbol,
                    leverage=GROWTH_LEVERAGE,
                    margin_mode='isolated'
                )
                if leverage_set:
                    td_mode = 'isolated'
                    logger.info(f"⚡ Using {GROWTH_LEVERAGE}x leverage (isolated margin)")
            
            # Validate minimum size
            min_size = 0.01 if is_spot else 0.1
            if position_size < min_size:
                position_size = min_size
            
            # Place limit order
            order_kwargs = {
                'symbol': symbol,
                'side': side,
                'order_type': 'limit',
                'size': str(round(position_size, 4 if is_spot else 2)),
                'price': str(limit_price),
                'tdMode': td_mode
            }
            
            order_result = self.client.place_order(**order_kwargs)
            
            if not order_result:
                logger.warning("⚠️  Limit order failed, falling back to market")
                return self.place_market_order(signal, position_size)
            
            order_id = order_result.get('ordId')
            logger.info(f"⏳ Limit order placed: {order_id}, waiting for fill...")
            
            # Wait for fill with timeout
            timeout = LIMIT_ORDER_TIMEOUT
            start_time = time.time()
            filled = False
            fill_price = None
            
            while time.time() - start_time < timeout:
                time.sleep(1)  # Check every second
                
                # Check order status
                order_status = self.client.get_order(symbol, order_id)
                if order_status:
                    state = order_status.get('state', '')
                    
                    if state == 'filled':
                        filled = True
                        fill_price = float(order_status.get('avgPx', limit_price))
                        logger.info(f"✅ Limit order FILLED @ ${fill_price:.2f}")
                        break
                    elif state in ['canceled', 'cancelled']:
                        logger.warning("⚠️  Limit order was cancelled externally")
                        break
                
                elapsed = time.time() - start_time
                logger.debug(f"   Waiting... {elapsed:.0f}s / {timeout}s")
            
            if not filled:
                # Cancel unfilled limit order
                logger.info(f"⏰ Limit order timeout ({timeout}s), cancelling...")
                self.client.cancel_order(symbol, order_id)
                
                if LIMIT_ORDER_MARKET_FALLBACK:
                    logger.info("🔄 Falling back to market order")
                    return self.place_market_order(signal, position_size)
                else:
                    logger.warning("❌ Limit order not filled and fallback disabled")
                    return None
            
            # Calculate actual improvement
            actual_improvement = 0
            if direction == 'long':
                actual_improvement = (current_price - fill_price) / current_price * 100
            else:
                actual_improvement = (fill_price - current_price) / current_price * 100
            
            logger.info(f"   💰 Entry improvement: {actual_improvement:.3f}%")
            
            # Create order record
            order = {
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'type': 'limit',
                'size': position_size,
                'limit_price': limit_price,
                'fill_price': fill_price,
                'signal': signal,
                'timestamp': datetime.now(),
                'status': 'filled',
                'margin_mode': td_mode,
                'entry_improvement': actual_improvement,
                'trading_mode': 'spot' if is_spot else 'perp'
            }
            
            self.active_orders[order_id] = order
            self.order_history.append(order)
            
            return order
            
        except Exception as e:
            logger.error(f"❌ Error placing limit entry order: {e}", exc_info=True)
            if LIMIT_ORDER_MARKET_FALLBACK:
                logger.info("🔄 Falling back to market order after error")
                return self.place_market_order(signal, position_size)
            return None

    def place_stop_loss(self, position: Dict, stop_price: float) -> Optional[Dict]:
        """
        Place stop loss order for position
        
        For SPOT trading: Stop loss is tracked internally (no native SL orders)
        For PERP trading: Uses conditional orders

        Args:
            position: Position details
            stop_price: Stop loss price

        Returns:
            Order details or None
        """
        try:
            symbol = position.get('symbol', TRADING_SYMBOL)
            direction = position['direction']
            # Check if this position used spot fallback
            is_spot = position.get('trading_mode') == 'spot' or TRADING_MODE == 'spot'

            # Stop loss side is opposite of position
            side = 'sell' if direction == 'long' else 'buy'
            size = position['size']

            logger.info(f"🛡️  Placing stop loss @ ${stop_price:.2f}")

            if is_spot:
                # SPOT trading: OKX spot doesn't have native stop-loss orders
                # Track internally and close manually when triggered
                logger.info(f"   📝 SPOT mode: Stop loss will be monitored internally")
                
                order = {
                    'order_id': f"VIRTUAL-SL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    'symbol': symbol,
                    'side': side,
                    'type': 'stop_loss',
                    'size': size,
                    'stop_price': stop_price,
                    'position_id': position.get('position_id'),
                    'timestamp': datetime.now(),
                    'status': 'virtual',
                    'is_virtual': True
                }
                
                self.active_orders[order['order_id']] = order
                self.order_history.append(order)
                
                logger.info(f"✅ Virtual stop loss set: ${stop_price:.2f}")
                return order
            else:
                # PERP trading: Use conditional orders
                order_result = self.client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type='conditional',
                    size=str(size),
                    stop_loss=str(stop_price),
                    reduce_only=True
                )

                if not order_result:
                    logger.error("❌ Failed to place stop loss")
                    return None

                order_id = order_result.get('ordId')

                order = {
                    'order_id': order_id,
                    'symbol': symbol,
                    'side': side,
                    'type': 'stop_loss',
                    'size': size,
                    'stop_price': stop_price,
                    'position_id': position.get('position_id'),
                    'timestamp': datetime.now(),
                    'status': 'active'
                }

                self.active_orders[order_id] = order
                self.order_history.append(order)

                logger.info(f"✅ Stop loss placed: {order_id}")

                return order

        except Exception as e:
            logger.error(f"❌ Error placing stop loss: {e}")
            return None

    def place_take_profit(self, position: Dict, tp_price: float,
                         size: Optional[float] = None) -> Optional[Dict]:
        """
        Place take profit order
        
        For both SPOT and PERP: Uses limit sell orders

        Args:
            position: Position details
            tp_price: Take profit price
            size: Size to close (None = full position)

        Returns:
            Order details or None
        """
        try:
            symbol = position.get('symbol', TRADING_SYMBOL)
            direction = position['direction']
            # Check if this position used spot fallback
            is_spot = position.get('trading_mode') == 'spot' or TRADING_MODE == 'spot'

            # TP side is opposite of position
            side = 'sell' if direction == 'long' else 'buy'
            close_size = size or position['size']

            logger.info(f"🎯 Placing take profit @ ${tp_price:.2f}")

            # Build order kwargs
            order_kwargs = {
                'symbol': symbol,
                'side': side,
                'order_type': 'limit',
                'size': str(round(close_size, 4 if is_spot else 2)),
                'price': str(round(tp_price, 2))
            }
            
            # For spot, do NOT pass tdMode (okx_client will detect spot and skip it)
            # For perp, use reduce_only
            if not is_spot:
                order_kwargs['reduce_only'] = True

            # For spot orders, verify balance and wait for settlement
            if is_spot:
                import time
                logger.info(f"   ⏳ Waiting 1 second for spot order settlement...")
                time.sleep(1)
                
                # First check balance
                sol_balance = self.client.get_currency_balance('SOL')
                if sol_balance is not None:
                    logger.info(f"   💰 Available SOL balance: {sol_balance:.4f}")
                    
                    # If balance is too low, try canceling old orders to free it up
                    min_order_size = 0.001
                    if sol_balance < close_size:
                        logger.info(f"   🔄 Balance may be locked by old orders - checking...")
                        
                        # Cancel old orders, but NOT orders we just placed in this session
                        cancelled = self._cancel_old_orders(symbol)
                        if cancelled > 0:
                            logger.info(f"   ✅ Cancelled {cancelled} old order(s) to free up balance")
                            time.sleep(0.5)  # Brief wait for cancellation to process
                            
                            # Re-check balance after cancellation
                            sol_balance = self.client.get_currency_balance('SOL')
                            if sol_balance is not None:
                                logger.info(f"   💰 Updated SOL balance: {sol_balance:.4f}")
                    
                    # Now check if we have enough
                    if sol_balance < min_order_size:
                        logger.warning(f"   ⚠️  Insufficient SOL balance ({sol_balance:.4f}) - skipping this TP")
                        return None
                    
                    if sol_balance < close_size:
                        logger.warning(f"   ⚠️  Requested size ({close_size:.4f}) exceeds available balance ({sol_balance:.4f})")
                        logger.warning(f"   📝 Adjusting TP order size to available balance")
                        close_size = sol_balance
                        order_kwargs['size'] = str(round(close_size, 4))
                else:
                    logger.warning(f"   ⚠️  Could not verify SOL balance, proceeding anyway...")

            order_result = self.client.place_order(**order_kwargs)

            if not order_result:
                logger.error("❌ Failed to place take profit")
                return None

            order_id = order_result.get('ordId')
            
            # Track this order so we don't accidentally cancel it later
            self._session_order_ids.add(order_id)

            order = {
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'type': 'take_profit',
                'size': close_size,
                'tp_price': tp_price,
                'position_id': position.get('position_id'),
                'timestamp': datetime.now(),
                'status': 'active',
                'trading_mode': 'spot' if is_spot else 'perp'
            }

            self.active_orders[order_id] = order
            self.order_history.append(order)

            logger.info(f"✅ Take profit placed: {order_id}")

            return order

        except Exception as e:
            logger.error(f"❌ Error placing take profit: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        try:
            if order_id not in self.active_orders:
                logger.warning(f"Order {order_id} not found in active orders")
                return False

            order = self.active_orders[order_id]
            symbol = order['symbol']

            logger.info(f"❌ Cancelling order: {order_id}")

            result = self.client.cancel_order(symbol, order_id)

            if result:
                order['status'] = 'cancelled'
                del self.active_orders[order_id]
                logger.info(f"✅ Order cancelled: {order_id}")
                return True
            else:
                logger.error(f"❌ Failed to cancel order: {order_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Error cancelling order: {e}")
            return False

    def _cancel_old_orders(self, symbol: str) -> int:
        """
        Cancel old open orders for a symbol, but preserve orders placed in current session.
        
        This prevents accidentally canceling TP1 when placing TP2.
        
        Args:
            symbol: Trading symbol (e.g., 'SOL-USDT')
            
        Returns:
            Number of orders cancelled
        """
        open_orders = self.client.get_open_orders(symbol)
        if not open_orders:
            return 0
            
        cancelled = 0
        for order in open_orders:
            order_id = order.get('ordId')
            if order_id:
                # Skip orders we just placed in this session
                if order_id in self._session_order_ids:
                    logger.info(f"   📝 Keeping session order: {order_id}")
                    continue
                    
                result = self.client.cancel_order(symbol, order_id)
                if result:
                    cancelled += 1
                    logger.info(f"   🗑️  Cancelled old order: {order_id}")
                    
        return cancelled

    def clear_session_orders(self):
        """Clear the session order tracking (call at start of new trade session)"""
        self._session_order_ids.clear()

    def update_order_status(self, order_id: str) -> Optional[str]:
        """
        Update order status from exchange

        Returns:
            Updated status or None
        """
        try:
            if order_id not in self.active_orders:
                return None

            order = self.active_orders[order_id]
            symbol = order['symbol']

            # Fetch order details from exchange
            order_details = self.client.get_order(symbol, order_id)

            if not order_details:
                return None

            status = order_details.get('state', 'unknown')
            order['status'] = status

            # If filled or cancelled, remove from active
            if status in ['filled', 'cancelled']:
                del self.active_orders[order_id]

            return status

        except Exception as e:
            logger.error(f"❌ Error updating order status: {e}")
            return None

    def get_active_orders(self) -> List[Dict]:
        """Get all active orders"""
        return list(self.active_orders.values())

    def get_order_history(self, limit: int = 50) -> List[Dict]:
        """Get recent order history"""
        return self.order_history[-limit:] if self.order_history else []

    def close_position(self, position: Dict) -> bool:
        """
        Close position at market
        
        For SPOT: Sells the asset
        For PERP: Closes the perpetual position

        Args:
            position: Position to close

        Returns:
            True if successful
        """
        try:
            symbol = position.get('symbol', TRADING_SYMBOL)
            direction = position['direction']
            # Check if this position used spot fallback
            is_spot = position.get('trading_mode') == 'spot' or TRADING_MODE == 'spot'

            # Close side is opposite of position
            side = 'sell' if direction == 'long' else 'buy'
            size = position['size']

            logger.info(f"🔄 Closing position: {side.upper()} {size} @ market")

            order_kwargs = {
                'symbol': symbol,
                'side': side,
                'order_type': 'market',
                'size': str(round(size, 4 if is_spot else 2))
            }
            
            if is_spot:
                order_kwargs['tdMode'] = 'cash'
            else:
                order_kwargs['reduce_only'] = True

            order_result = self.client.place_order(**order_kwargs)

            if order_result:
                logger.info(f"✅ Position closed")
                return True
            else:
                logger.error(f"❌ Failed to close position")
                return False

        except Exception as e:
            logger.error(f"❌ Error closing position: {e}")
            return False
