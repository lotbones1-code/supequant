"""
Position Tracker
Tracks open positions and manages position lifecycle
"""

from typing import Dict, Optional, List
import logging
from datetime import datetime
from data_feed.okx_client import OKXClient
from config import TRADING_SYMBOL

logger = logging.getLogger(__name__)


class PositionTracker:
    """
    Tracks and manages trading positions
    """

    def __init__(self, okx_client: Optional[OKXClient] = None):
        self.client = okx_client or OKXClient()
        self.positions = {}
        self.closed_positions = []

    def create_position(self, signal: Dict, entry_order: Dict) -> Dict:
        """
        Create position from signal and entry order

        Args:
            signal: Trading signal
            entry_order: Entry order details

        Returns:
            Position dict
        """
        position_id = f"pos_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Use symbol from entry_order (important for spot fallback)
        # If entry used spot fallback, it will have the spot symbol
        symbol = entry_order.get('symbol', TRADING_SYMBOL)
        trading_mode = entry_order.get('trading_mode', 'perp')
        used_fallback = entry_order.get('used_fallback', False)
        
        if used_fallback:
            logger.info(f"   📝 Position uses SPOT fallback (symbol: {symbol})")

        # Support V3 multiple TP levels and position splits
        position = {
            'position_id': position_id,
            'symbol': symbol,
            'trading_mode': trading_mode,
            'used_fallback': used_fallback,
            'direction': signal['direction'],
            'entry_price': signal['entry_price'],
            'size': entry_order['size'],
            'remaining_size': entry_order['size'],  # Track remaining for partial exits
            'stop_loss': signal['stop_loss'],
            'take_profit_1': signal.get('take_profit_1'),
            'take_profit_2': signal.get('take_profit_2'),
            'take_profit_3': signal.get('take_profit_3'),
            'position_split': signal.get('position_split', {1: 0.5, 2: 0.3, 3: 0.2}),
            'tp1_exited': False,
            'tp2_exited': False,
            'tp3_exited': False,
            'partial_exits_pnl': 0.0,
            'strategy': signal['strategy'],
            'entry_time': datetime.now(),
            'status': 'open',
            'pnl': 0,
            'pnl_pct': 0,
            'risk_amount': signal.get('risk_amount', 0),
            'orders': {
                'entry': entry_order.get('order_id'),
                'stop_loss': None,
                'take_profit_1': None,
                'take_profit_2': None,
                'take_profit_3': None
            }
        }

        self.positions[position_id] = position
        logger.info(f"📊 Position created: {position_id} - {signal['direction'].upper()}")

        return position

    def update_position_pnl(self, position_id: str, current_price: float):
        """
        Update position PnL based on current price

        Args:
            position_id: Position ID
            current_price: Current market price
        """
        if position_id not in self.positions:
            return

        position = self.positions[position_id]
        entry_price = position['entry_price']
        size = position['size']
        direction = position['direction']

        # Calculate PnL
        if direction == 'long':
            pnl = (current_price - entry_price) * size
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl = (entry_price - current_price) * size
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        position['pnl'] = pnl
        position['pnl_pct'] = pnl_pct
        position['current_price'] = current_price

    def get_position(self, position_id: str) -> Optional[Dict]:
        """Get position by ID"""
        return self.positions.get(position_id)

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions"""
        return [p for p in self.positions.values() if p['status'] == 'open']

    def close_position(self, position_id: str, close_price: float, reason: str):
        """
        Mark position as closed

        Args:
            position_id: Position ID
            close_price: Exit price
            reason: Reason for closing (stop_loss, take_profit, manual, etc.)
        """
        if position_id not in self.positions:
            logger.warning(f"Position {position_id} not found")
            return

        position = self.positions[position_id]
        position['status'] = 'closed'
        position['exit_price'] = close_price
        position['exit_time'] = datetime.now()
        position['close_reason'] = reason

        # Calculate final PnL
        entry_price = position['entry_price']
        size = position['size']
        direction = position['direction']

        if direction == 'long':
            pnl = (close_price - entry_price) * size
            pnl_pct = ((close_price - entry_price) / entry_price) * 100
        else:
            pnl = (entry_price - close_price) * size
            pnl_pct = ((entry_price - close_price) / entry_price) * 100

        position['pnl'] = pnl
        position['pnl_pct'] = pnl_pct

        # Move to closed positions
        self.closed_positions.append(position)
        del self.positions[position_id]

        logger.info(f"📊 Position closed: {position_id} - {reason}")
        logger.info(f"   PnL: ${pnl:.2f} ({pnl_pct:+.2f}%)")

    def get_closed_positions(self, limit: int = 50) -> List[Dict]:
        """Get recent closed positions"""
        return self.closed_positions[-limit:] if self.closed_positions else []

    def get_total_pnl(self) -> float:
        """Get total PnL from all closed positions"""
        return sum(p['pnl'] for p in self.closed_positions)

    def get_win_rate(self) -> float:
        """Calculate win rate from closed positions"""
        if not self.closed_positions:
            return 0.0

        wins = sum(1 for p in self.closed_positions if p['pnl'] > 0)
        return wins / len(self.closed_positions)

    def get_statistics(self) -> Dict:
        """Get position statistics"""
        closed = self.closed_positions

        if not closed:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'largest_win': 0,
                'largest_loss': 0
            }

        wins = [p for p in closed if p['pnl'] > 0]
        losses = [p for p in closed if p['pnl'] <= 0]

        return {
            'total_trades': len(closed),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(closed),
            'total_pnl': sum(p['pnl'] for p in closed),
            'avg_win': sum(p['pnl'] for p in wins) / len(wins) if wins else 0,
            'avg_loss': sum(p['pnl'] for p in losses) / len(losses) if losses else 0,
            'largest_win': max((p['pnl'] for p in wins), default=0),
            'largest_loss': min((p['pnl'] for p in losses), default=0),
            'avg_win_pct': sum(p['pnl_pct'] for p in wins) / len(wins) if wins else 0,
            'avg_loss_pct': sum(p['pnl_pct'] for p in losses) / len(losses) if losses else 0
        }
