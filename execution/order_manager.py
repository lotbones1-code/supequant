"""
Order Manager
Handles order creation, modification, and cancellation on OKX
"""

from typing import Dict, Optional, List
import logging
from datetime import datetime
from data_feed.okx_client import OKXClient
from config import TRADING_SYMBOL, MAX_RISK_PER_TRADE

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order lifecycle on OKX exchange
    """

    def __init__(self, okx_client: Optional[OKXClient] = None):
        self.client = okx_client or OKXClient()
        self.active_orders = {}
        self.order_history = []

    def place_market_order(self, signal: Dict, position_size: float) -> Optional[Dict]:
        """
        Place market order based on signal

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

            logger.info(f"📤 Placing {side.upper()} market order: {position_size} @ market")

            # Place market order
            order_result = self.client.place_order(
                symbol=symbol,
                side=side,
                order_type='market',
                size=str(position_size),
                tdMode='cross'
            )

            if not order_result:
                logger.error("❌ Failed to place market order")
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
                'status': 'filled'  # Market orders fill immediately
            }

            self.active_orders[order_id] = order
            self.order_history.append(order)

            logger.info(f"✅ Market order placed: {order_id}")

            return order

        except Exception as e:
            logger.error(f"❌ Error placing market order: {e}")
            return None

    def place_stop_loss(self, position: Dict, stop_price: float) -> Optional[Dict]:
        """
        Place stop loss order for position

        Args:
            position: Position details
            stop_price: Stop loss price

        Returns:
            Order details or None
        """
        try:
            symbol = TRADING_SYMBOL
            direction = position['direction']

            # Stop loss side is opposite of position
            side = 'sell' if direction == 'long' else 'buy'
            size = position['size']

            logger.info(f"🛡️  Placing stop loss @ {stop_price}")

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

        Args:
            position: Position details
            tp_price: Take profit price
            size: Size to close (None = full position)

        Returns:
            Order details or None
        """
        try:
            symbol = TRADING_SYMBOL
            direction = position['direction']

            # TP side is opposite of position
            side = 'sell' if direction == 'long' else 'buy'
            close_size = size or position['size']

            logger.info(f"🎯 Placing take profit @ {tp_price}")

            order_result = self.client.place_order(
                symbol=symbol,
                side=side,
                order_type='limit',
                size=str(close_size),
                price=str(tp_price),
                reduce_only=True
            )

            if not order_result:
                logger.error("❌ Failed to place take profit")
                return None

            order_id = order_result.get('ordId')

            order = {
                'order_id': order_id,
                'symbol': symbol,
                'side': side,
                'type': 'take_profit',
                'size': close_size,
                'tp_price': tp_price,
                'position_id': position.get('position_id'),
                'timestamp': datetime.now(),
                'status': 'active'
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

        Args:
            position: Position to close

        Returns:
            True if successful
        """
        try:
            symbol = TRADING_SYMBOL
            direction = position['direction']

            # Close side is opposite of position
            side = 'sell' if direction == 'long' else 'buy'
            size = position['size']

            logger.info(f"🔄 Closing position: {side.upper()} {size} @ market")

            order_result = self.client.place_order(
                symbol=symbol,
                side=side,
                order_type='market',
                size=str(size),
                reduce_only=True
            )

            if order_result:
                logger.info(f"✅ Position closed")
                return True
            else:
                logger.error(f"❌ Failed to close position")
                return False

        except Exception as e:
            logger.error(f"❌ Error closing position: {e}")
            return False
