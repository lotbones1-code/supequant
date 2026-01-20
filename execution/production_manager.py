"""
Production-Grade Order & Position Manager
Handles complete trade lifecycle with auto-cleanup and smart execution

Features:
1. Pre-Trade Cleanup - Cancel orders, sell SOL, verify clean state
2. Position Tracking - Track actual fills, not theoretical sizes
3. Smart TP Placement - Limit orders with virtual fallback
4. Position Lifecycle - Full state machine tracking
5. Logging & History - Complete audit trail
"""

import logging
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass, field

from data_feed.okx_client import OKXClient
from config import (
    TRADING_SYMBOL, SPOT_SYMBOL, TRADING_MODE,
    LIMIT_ORDER_ENTRY_ENABLED, LIMIT_ORDER_IMPROVEMENT,
    LIMIT_ORDER_TIMEOUT, LIMIT_ORDER_MARKET_FALLBACK
)

logger = logging.getLogger(__name__)


class PositionState(Enum):
    """Position lifecycle states"""
    PENDING = "pending"           # Waiting to execute
    ENTRY_PLACED = "entry_placed" # Entry order sent
    ENTRY_FILLED = "entry_filled" # Entry filled, TPs being placed
    ACTIVE = "active"             # Position active with TPs
    TP1_FILLED = "tp1_filled"     # First TP hit
    TP2_FILLED = "tp2_filled"     # Second TP hit (fully closed)
    STOPPED_OUT = "stopped_out"   # Stop loss hit
    CLOSED = "closed"             # Position fully closed
    FAILED = "failed"             # Something went wrong


@dataclass
class ManagedPosition:
    """Complete position tracking with all details"""
    position_id: str
    symbol: str
    direction: str  # 'long' or 'short'
    
    # Entry details
    entry_price: float = 0.0
    entry_size: float = 0.0
    actual_entry_size: float = 0.0  # What actually filled
    entry_order_id: str = ""
    entry_time: datetime = None
    
    # Stop loss
    stop_loss: float = 0.0
    sl_order_id: str = ""
    sl_is_virtual: bool = True  # For spot, SL is always virtual
    
    # Take profits
    tp1_price: float = 0.0
    tp1_size: float = 0.0
    tp1_order_id: str = ""
    tp1_is_virtual: bool = False
    tp1_filled: bool = False
    tp1_fill_price: float = 0.0
    tp1_fill_time: datetime = None
    
    tp2_price: float = 0.0
    tp2_size: float = 0.0
    tp2_order_id: str = ""
    tp2_is_virtual: bool = False
    tp2_filled: bool = False
    tp2_fill_price: float = 0.0
    tp2_fill_time: datetime = None
    
    # State tracking
    state: PositionState = PositionState.PENDING
    trading_mode: str = "spot"  # 'spot' or 'perp'
    
    # PnL tracking
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Metadata
    strategy: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    closed_at: datetime = None
    close_reason: str = ""  # 'tp1', 'tp2', 'sl', 'manual'
    
    # Filter tracking (for analytics)
    filters_passed: list = field(default_factory=list)
    confidence_score: float = None
    
    # Arbitrage/time-based exit fields (Phase 4.2)
    strategy_type: str = ""  # 'momentum', 'arbitrage', etc.
    exit_after_funding: bool = False  # For arb: exit after funding collection
    max_hold_hours: float = 0.0  # Max hours to hold (arb: ~9h)
    expected_funding_time: datetime = None  # When funding is paid


class ProductionOrderManager:
    """
    Production-grade order & position manager
    
    Handles complete trade lifecycle:
    1. Pre-trade cleanup (cancel orders, sell SOL, verify clean)
    2. Entry execution with actual fill tracking
    3. Smart TP placement (limit with virtual fallback)
    4. Position lifecycle management
    5. Background monitoring for virtual orders
    6. Automatic trade journaling for analytics
    7. Telegram notifications for trade events
    """
    
    def __init__(self, okx_client: Optional[OKXClient] = None, trade_journal=None, notifier=None):
        self.client = okx_client or OKXClient()
        
        # Trade journal for logging (optional)
        self.trade_journal = trade_journal
        
        # Telegram notifier for alerts (optional)
        self.notifier = notifier
        
        # Current managed position
        self.current_position: Optional[ManagedPosition] = None
        
        # Trade history
        self.trade_history: List[ManagedPosition] = []
        
        # Virtual order monitoring
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self._monitor_interval = 5  # seconds between price checks
        
        # Callbacks
        self._on_tp_hit: Optional[Callable] = None
        self._on_sl_hit: Optional[Callable] = None
        
        journal_status = "enabled" if trade_journal else "disabled"
        notifier_status = "enabled" if notifier else "disabled"
        logger.info(f"✅ ProductionOrderManager initialized (journal: {journal_status}, notifications: {notifier_status})")
    
    # =========================================================================
    # 1. PRE-TRADE CLEANUP
    # =========================================================================
    
    def prepare_for_trade(self, symbol: str = 'SOL-USDT') -> bool:
        """
        Prepare account for a fresh trade by cleaning up any existing state.
        
        Steps:
        1. Cancel all open orders for the symbol
        2. Sell any existing SOL at market
        3. Wait for settlement
        4. Verify clean state
        
        Returns:
            True if account is ready for trading
        """
        logger.info("\n" + "="*60)
        logger.info("🧹 PREPARING ACCOUNT FOR TRADE")
        logger.info("="*60)
        
        try:
            # Step 1: Cancel all open orders
            logger.info("\n📋 Step 1: Canceling open orders...")
            cancelled = self._cancel_all_orders(symbol)
            logger.info(f"   Cancelled {cancelled} order(s)")
            
            # Step 2: Sell any existing SOL
            logger.info("\n💰 Step 2: Checking for existing SOL...")
            sol_balance = self.client.get_currency_balance('SOL')
            
            if sol_balance and sol_balance > 0.001:  # More than dust
                logger.info(f"   Found {sol_balance:.4f} SOL - selling at market...")
                sell_result = self._sell_all_sol(symbol, sol_balance)
                if sell_result:
                    logger.info(f"   ✅ Sold {sol_balance:.4f} SOL")
                else:
                    logger.warning(f"   ⚠️  Could not sell SOL - may have open orders")
            else:
                logger.info(f"   No SOL to sell (balance: {sol_balance or 0:.4f})")
            
            # Step 3: Wait for settlement
            logger.info("\n⏳ Step 3: Waiting for settlement...")
            time.sleep(2)
            
            # Step 4: Verify clean state
            logger.info("\n✅ Step 4: Verifying clean state...")
            
            # Check no open orders
            open_orders = self.client.get_open_orders(symbol)
            if open_orders and len(open_orders) > 0:
                logger.warning(f"   ⚠️  Still have {len(open_orders)} open orders")
                return False
            logger.info("   ✓ No open orders")
            
            # Check no SOL balance
            sol_balance = self.client.get_currency_balance('SOL')
            if sol_balance and sol_balance > 0.001:
                logger.warning(f"   ⚠️  Still have {sol_balance:.4f} SOL")
                # Not a blocker, but note it
            else:
                logger.info("   ✓ No SOL balance")
            
            # Check USDT available
            usdt_balance = self.client.get_trading_balance('USDT')
            if not usdt_balance or usdt_balance < 1:
                logger.error(f"   ❌ Insufficient USDT: ${usdt_balance or 0:.2f}")
                return False
            logger.info(f"   ✓ USDT available: ${usdt_balance:.2f}")
            
            logger.info("\n" + "="*60)
            logger.info("✅ ACCOUNT READY FOR TRADING")
            logger.info("="*60 + "\n")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error preparing for trade: {e}")
            return False
    
    def _cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol"""
        open_orders = self.client.get_open_orders(symbol)
        if not open_orders:
            return 0
            
        cancelled = 0
        for order in open_orders:
            order_id = order.get('ordId')
            if order_id:
                result = self.client.cancel_order(symbol, order_id)
                if result:
                    cancelled += 1
                    logger.info(f"   🗑️  Cancelled: {order_id}")
        
        return cancelled
    
    def _sell_all_sol(self, symbol: str, amount: float) -> bool:
        """Sell all SOL at market price"""
        try:
            result = self.client.place_order(
                symbol=symbol,
                side='sell',
                order_type='market',
                size=str(round(amount, 4)),
                tdMode='cash'
            )
            return result is not None
        except Exception as e:
            logger.error(f"Error selling SOL: {e}")
            return False
    
    # =========================================================================
    # 2. TRADE EXECUTION
    # =========================================================================
    
    def _parse_funding_time(self, funding_time) -> Optional[datetime]:
        """Parse funding time from various formats."""
        if not funding_time:
            return None
        
        if isinstance(funding_time, datetime):
            return funding_time
        
        if isinstance(funding_time, str):
            try:
                # ISO format
                return datetime.fromisoformat(funding_time.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return None
        
        if isinstance(funding_time, (int, float)):
            try:
                # Timestamp (milliseconds or seconds)
                ts = funding_time / 1000 if funding_time > 1e12 else funding_time
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OSError):
                return None
        
        return None
    
    def execute_trade(self, signal: Dict, max_position_size: float) -> Optional[ManagedPosition]:
        """
        Execute a complete trade with proper tracking.
        
        Args:
            signal: Trading signal with entry, SL, TP levels
            max_position_size: Maximum position size (will be adjusted for spot)
            
        Returns:
            ManagedPosition object or None if failed
        """
        symbol = SPOT_SYMBOL  # Always use spot for OKX US compliance
        
        logger.info("\n" + "="*60)
        logger.info("🚀 EXECUTING TRADE")
        logger.info("="*60)
        
        # Create position object
        position_id = f"pos_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Handle arb signals (no TP1/TP2, time-based exit)
        is_arb = signal.get('strategy_type') == 'arbitrage' or signal.get('exit_after_funding', False)
        
        # For arb: Use very far TP prices (won't be used, time-based exit instead)
        if is_arb:
            tp1_price = signal['entry_price'] * 1.10  # 10% away (won't trigger)
            tp2_price = signal['entry_price'] * 1.15  # 15% away (won't trigger)
        else:
            tp1_price = signal.get('take_profit_1') or signal['entry_price'] * 1.015
            tp2_price = signal.get('take_profit_2') or tp1_price * 1.02
        
        position = ManagedPosition(
            position_id=position_id,
            symbol=symbol,
            direction=signal['direction'],
            entry_price=signal['entry_price'],
            stop_loss=signal['stop_loss'],
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            strategy=signal.get('strategy', 'manual'),
            trading_mode='spot',
            filters_passed=signal.get('filters_passed', []),
            confidence_score=signal.get('confidence_score'),
            # Arbitrage/time-based exit fields (Phase 4.2)
            strategy_type=signal.get('strategy_type', 'momentum'),
            exit_after_funding=signal.get('exit_after_funding', False),
            max_hold_hours=signal.get('max_hold_hours', 0.0),
            expected_funding_time=self._parse_funding_time(signal.get('expected_funding_time'))
        )
        
        try:
            # Calculate actual position size based on available USDT
            usdt_balance = self.client.get_trading_balance('USDT')
            if not usdt_balance or usdt_balance < 1:
                logger.error(f"❌ Insufficient USDT: ${usdt_balance or 0:.2f}")
                position.state = PositionState.FAILED
                return None
            
            # For spot: position_size = (USDT * 0.95) / price
            current_price = signal['entry_price']
            actual_size = (usdt_balance * 0.95) / current_price
            
            # Cap at max_position_size if smaller
            if max_position_size < actual_size:
                actual_size = max_position_size
            
            position.entry_size = actual_size
            
            logger.info(f"\n📊 Trade Details:")
            logger.info(f"   Symbol: {symbol}")
            logger.info(f"   Direction: {signal['direction'].upper()}")
            logger.info(f"   Size: {actual_size:.4f} SOL")
            logger.info(f"   Entry: ${current_price:.2f}")
            logger.info(f"   Stop Loss: ${signal['stop_loss']:.2f}")
            logger.info(f"   TP1: ${position.tp1_price:.2f}")
            logger.info(f"   TP2: ${position.tp2_price:.2f}")
            
            # Place entry order (limit or market)
            position.state = PositionState.ENTRY_PLACED
            side = 'buy' if signal['direction'] == 'long' else 'sell'
            
            entry_result = None
            used_limit = False
            
            # Try limit order for better entry if enabled
            if LIMIT_ORDER_ENTRY_ENABLED and current_price > 0:
                logger.info(f"\n📤 Placing LIMIT entry order for better price...")
                
                # Calculate limit price with improvement
                improvement = LIMIT_ORDER_IMPROVEMENT
                if signal['direction'] == 'long':
                    limit_price = current_price * (1 - improvement)
                else:
                    limit_price = current_price * (1 + improvement)
                limit_price = round(limit_price, 2)
                
                logger.info(f"   Target improvement: {improvement*100:.2f}%")
                logger.info(f"   Current: ${current_price:.2f} → Limit: ${limit_price:.2f}")
                
                entry_result = self.client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type='limit',
                    size=str(round(actual_size, 4)),
                    price=str(limit_price),
                    tdMode='cash'
                )
                
                if entry_result:
                    used_limit = True
                    order_id = entry_result.get('ordId', '')
                    logger.info(f"   ⏳ Limit order placed: {order_id}, waiting for fill...")
                    
                    # Wait for fill with timeout
                    timeout = LIMIT_ORDER_TIMEOUT
                    start_time = time.time()
                    filled = False
                    
                    while time.time() - start_time < timeout:
                        time.sleep(1)
                        order_status = self.client.get_order(symbol, order_id)
                        if order_status:
                            state = order_status.get('state', '')
                            if state == 'filled':
                                filled = True
                                fill_price = float(order_status.get('avgPx', limit_price))
                                actual_improvement = abs(current_price - fill_price) / current_price * 100
                                logger.info(f"   ✅ Limit FILLED @ ${fill_price:.2f}")
                                logger.info(f"   💰 Entry improvement: {actual_improvement:.3f}%")
                                break
                            elif state in ['canceled', 'cancelled']:
                                logger.warning("   ⚠️  Limit order cancelled externally")
                                break
                    
                    if not filled:
                        # Cancel unfilled limit order
                        logger.info(f"   ⏰ Timeout ({timeout}s), cancelling limit order...")
                        self.client.cancel_order(symbol, order_id)
                        entry_result = None  # Will fallback to market
            
            # Fallback to market order if limit not used or failed
            if not entry_result:
                if used_limit and LIMIT_ORDER_MARKET_FALLBACK:
                    logger.info(f"   🔄 Falling back to market order...")
                else:
                    logger.info(f"\n📤 Placing market entry order...")
                
                entry_result = self.client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type='market',
                    size=str(round(actual_size, 4)),
                    tdMode='cash'
                )
            
            if not entry_result:
                logger.error("❌ Failed to place entry order")
                position.state = PositionState.FAILED
                return None
            
            position.entry_order_id = entry_result.get('ordId', '')
            position.entry_time = datetime.now()
            logger.info(f"   ✅ Entry order placed: {position.entry_order_id}")
            
            # Wait for fill and get actual size
            time.sleep(1)
            
            # Get actual filled size from balance
            sol_balance = self.client.get_currency_balance('SOL')
            if sol_balance and sol_balance > 0:
                position.actual_entry_size = sol_balance
                logger.info(f"   📊 Actual fill size: {sol_balance:.4f} SOL")
            else:
                position.actual_entry_size = actual_size
                logger.warning(f"   ⚠️  Could not verify fill, using requested: {actual_size:.4f}")
            
            position.state = PositionState.ENTRY_FILLED
            
            # Calculate TP sizes based on ACTUAL entry size (50/50 split)
            tp1_size = position.actual_entry_size * 0.5
            tp2_size = position.actual_entry_size * 0.5
            
            position.tp1_size = tp1_size
            position.tp2_size = tp2_size
            
            logger.info(f"\n🎯 TP Sizes (based on actual fill):")
            logger.info(f"   TP1: {tp1_size:.4f} SOL @ ${position.tp1_price:.2f}")
            logger.info(f"   TP2: {tp2_size:.4f} SOL @ ${position.tp2_price:.2f}")
            
            # Place take profit orders with smart fallback
            logger.info(f"\n📈 Placing take profit orders...")
            
            # TP1
            tp1_placed = self._place_smart_tp(position, 1, position.tp1_price, tp1_size)
            if tp1_placed:
                logger.info(f"   ✅ TP1: {'Virtual' if position.tp1_is_virtual else 'Limit'} @ ${position.tp1_price:.2f}")
            
            # TP2
            tp2_placed = self._place_smart_tp(position, 2, position.tp2_price, tp2_size)
            if tp2_placed:
                logger.info(f"   ✅ TP2: {'Virtual' if position.tp2_is_virtual else 'Limit'} @ ${position.tp2_price:.2f}")
            
            # Set up virtual stop loss (spot doesn't support native SL)
            position.sl_is_virtual = True
            logger.info(f"\n🛡️  Stop Loss: Virtual @ ${position.stop_loss:.2f}")
            
            position.state = PositionState.ACTIVE
            self.current_position = position
            
            # Start monitoring if we have virtual orders
            if position.tp1_is_virtual or position.tp2_is_virtual or position.sl_is_virtual:
                self._start_monitoring()
            
            logger.info("\n" + "="*60)
            logger.info("✅ TRADE EXECUTED SUCCESSFULLY")
            logger.info(f"   Position ID: {position.position_id}")
            logger.info("="*60 + "\n")
            
            # Send Telegram notification
            if self.notifier:
                try:
                    self.notifier.send_trade_entry(position.__dict__)
                except Exception as e:
                    logger.warning(f"Failed to send trade entry notification: {e}")
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}", exc_info=True)
            position.state = PositionState.FAILED
            return None
    
    # =========================================================================
    # 3. SMART TP PLACEMENT
    # =========================================================================
    
    def _place_smart_tp(self, position: ManagedPosition, tp_num: int, 
                        price: float, size: float) -> bool:
        """
        Place take profit with smart fallback.
        
        1. Try limit order first
        2. If fails (51008), create virtual TP
        
        Args:
            position: The managed position
            tp_num: 1 or 2
            price: TP price
            size: Size to sell
            
        Returns:
            True if TP is set (limit or virtual)
        """
        try:
            # Check available balance
            sol_balance = self.client.get_currency_balance('SOL')
            if not sol_balance or sol_balance < 0.001:
                logger.warning(f"   ⚠️  TP{tp_num}: No SOL balance, setting as virtual")
                self._set_virtual_tp(position, tp_num, price, size)
                return True
            
            # Adjust size if needed
            if size > sol_balance:
                logger.warning(f"   ⚠️  TP{tp_num}: Adjusting size {size:.4f} -> {sol_balance:.4f}")
                size = sol_balance
            
            # Try limit order
            result = self.client.place_order(
                symbol=position.symbol,
                side='sell',
                order_type='limit',
                size=str(round(size, 4)),
                price=str(round(price, 2)),
                tdMode='cash'
            )
            
            if result:
                order_id = result.get('ordId', '')
                if tp_num == 1:
                    position.tp1_order_id = order_id
                    position.tp1_is_virtual = False
                    position.tp1_size = size
                else:
                    position.tp2_order_id = order_id
                    position.tp2_is_virtual = False
                    position.tp2_size = size
                return True
            else:
                # Limit order failed - use virtual
                logger.warning(f"   ⚠️  TP{tp_num}: Limit order failed, using virtual")
                self._set_virtual_tp(position, tp_num, price, size)
                return True
                
        except Exception as e:
            logger.error(f"   ❌ TP{tp_num} error: {e}")
            self._set_virtual_tp(position, tp_num, price, size)
            return True
    
    def _set_virtual_tp(self, position: ManagedPosition, tp_num: int, 
                        price: float, size: float):
        """Set a virtual TP that will be monitored"""
        virtual_id = f"VIRTUAL-TP{tp_num}-{datetime.now().strftime('%H%M%S')}"
        if tp_num == 1:
            position.tp1_order_id = virtual_id
            position.tp1_is_virtual = True
            position.tp1_size = size
        else:
            position.tp2_order_id = virtual_id
            position.tp2_is_virtual = True
            position.tp2_size = size
    
    # =========================================================================
    # 4. POSITION LIFECYCLE & MONITORING
    # =========================================================================
    
    def _start_monitoring(self):
        """Start background thread to monitor virtual orders"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return  # Already running
            
        self._stop_monitoring.clear()
        self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("🔍 Started position monitoring")
    
    def _stop_monitoring_thread(self):
        """Stop the monitoring thread"""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("⏹️  Stopped position monitoring")
    
    def _monitoring_loop(self):
        """Background loop to check prices and trigger virtual orders"""
        while not self._stop_monitoring.is_set():
            try:
                if self.current_position and self.current_position.state == PositionState.ACTIVE:
                    self._check_position()
                time.sleep(self._monitor_interval)
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(self._monitor_interval)
    
    def _check_position(self):
        """Check current position and trigger actions if needed"""
        position = self.current_position
        if not position:
            return
            
        try:
            # Get current price
            # For spot, we need to get the ticker price
            ticker = self.client.get_ticker(position.symbol)
            if not ticker:
                return
                
            current_price = float(ticker.get('last', 0))
            if current_price <= 0:
                return
            
            # Update unrealized PnL
            if position.direction == 'long':
                position.unrealized_pnl = (current_price - position.entry_price) * position.actual_entry_size
            else:
                position.unrealized_pnl = (position.entry_price - current_price) * position.actual_entry_size
            
            # Check stop loss (virtual)
            if position.sl_is_virtual and not position.state in [PositionState.STOPPED_OUT, PositionState.CLOSED]:
                if position.direction == 'long' and current_price <= position.stop_loss:
                    logger.warning(f"🛑 STOP LOSS TRIGGERED @ ${current_price:.2f}")
                    self._execute_stop_loss(position, current_price)
                    return
                elif position.direction == 'short' and current_price >= position.stop_loss:
                    logger.warning(f"🛑 STOP LOSS TRIGGERED @ ${current_price:.2f}")
                    self._execute_stop_loss(position, current_price)
                    return
            
            # Check time-based exit for arbitrage positions (Phase 4.2)
            if position.exit_after_funding and position.entry_time:
                time_exit_triggered = self._check_arb_time_exit(position, current_price)
                if time_exit_triggered:
                    return  # Position closed, no need to check TPs
            
            # Check TP1 (if virtual and not filled)
            if position.tp1_is_virtual and not position.tp1_filled:
                if position.direction == 'long' and current_price >= position.tp1_price:
                    logger.info(f"🎯 TP1 TRIGGERED @ ${current_price:.2f}")
                    self._execute_virtual_tp(position, 1, current_price)
                elif position.direction == 'short' and current_price <= position.tp1_price:
                    logger.info(f"🎯 TP1 TRIGGERED @ ${current_price:.2f}")
                    self._execute_virtual_tp(position, 1, current_price)
            
            # Check TP2 (if virtual and not filled, and TP1 is filled)
            if position.tp2_is_virtual and not position.tp2_filled and position.tp1_filled:
                if position.direction == 'long' and current_price >= position.tp2_price:
                    logger.info(f"🎯 TP2 TRIGGERED @ ${current_price:.2f}")
                    self._execute_virtual_tp(position, 2, current_price)
                elif position.direction == 'short' and current_price <= position.tp2_price:
                    logger.info(f"🎯 TP2 TRIGGERED @ ${current_price:.2f}")
                    self._execute_virtual_tp(position, 2, current_price)
            
            # Check if limit orders filled (for non-virtual TPs)
            self._check_limit_order_fills(position)
            
        except Exception as e:
            logger.error(f"Error checking position: {e}")
    
    def _execute_virtual_tp(self, position: ManagedPosition, tp_num: int, current_price: float):
        """Execute a virtual TP by placing market sell"""
        try:
            size = position.tp1_size if tp_num == 1 else position.tp2_size
            
            # Check actual balance
            sol_balance = self.client.get_currency_balance('SOL')
            if sol_balance and sol_balance < size:
                size = sol_balance
            
            if size < 0.001:
                logger.warning(f"   TP{tp_num}: No SOL to sell")
                return
            
            result = self.client.place_order(
                symbol=position.symbol,
                side='sell',
                order_type='market',
                size=str(round(size, 4)),
                tdMode='cash'
            )
            
            if result:
                if tp_num == 1:
                    position.tp1_filled = True
                    position.tp1_fill_price = current_price
                    position.tp1_fill_time = datetime.now()
                    position.state = PositionState.TP1_FILLED
                    pnl = (current_price - position.entry_price) * size
                    position.realized_pnl += pnl
                    logger.info(f"   ✅ TP1 executed: {size:.4f} SOL @ ${current_price:.2f} (PnL: ${pnl:.2f})")
                    # Send TP1 notification
                    if self.notifier:
                        remaining = position.tp2_size if not position.tp2_filled else 0
                        self.notifier.send_tp_hit(position.__dict__, 1, current_price, pnl, remaining)
                else:
                    position.tp2_filled = True
                    position.tp2_fill_price = current_price
                    position.tp2_fill_time = datetime.now()
                    position.state = PositionState.TP2_FILLED
                    pnl = (current_price - position.entry_price) * size
                    position.realized_pnl += pnl
                    logger.info(f"   ✅ TP2 executed: {size:.4f} SOL @ ${current_price:.2f} (PnL: ${pnl:.2f})")
                    # Send TP2 notification
                    if self.notifier:
                        self.notifier.send_tp_hit(position.__dict__, 2, current_price, pnl, 0)
                    self._close_position(position, 'tp2')
                    
        except Exception as e:
            logger.error(f"Error executing virtual TP{tp_num}: {e}")
    
    def _execute_stop_loss(self, position: ManagedPosition, current_price: float):
        """Execute stop loss by selling all remaining SOL"""
        try:
            sol_balance = self.client.get_currency_balance('SOL')
            if not sol_balance or sol_balance < 0.001:
                logger.warning("   No SOL to sell for stop loss")
                position.state = PositionState.STOPPED_OUT
                self._close_position(position, 'sl')
                return
            
            # Cancel any open TP orders first
            if position.tp1_order_id and not position.tp1_is_virtual and not position.tp1_filled:
                self.client.cancel_order(position.symbol, position.tp1_order_id)
            if position.tp2_order_id and not position.tp2_is_virtual and not position.tp2_filled:
                self.client.cancel_order(position.symbol, position.tp2_order_id)
            
            # Sell all remaining
            result = self.client.place_order(
                symbol=position.symbol,
                side='sell',
                order_type='market',
                size=str(round(sol_balance, 4)),
                tdMode='cash'
            )
            
            if result:
                pnl = (current_price - position.entry_price) * sol_balance
                position.realized_pnl += pnl
                position.state = PositionState.STOPPED_OUT
                logger.info(f"   ✅ Stop loss executed: {sol_balance:.4f} SOL @ ${current_price:.2f} (PnL: ${pnl:.2f})")
                # Send SL notification
                if self.notifier:
                    self.notifier.send_sl_hit(position.__dict__, current_price, pnl)
                self._close_position(position, 'sl')
                
        except Exception as e:
            logger.error(f"Error executing stop loss: {e}")
    
    def _check_limit_order_fills(self, position: ManagedPosition):
        """Check if limit TP orders have filled"""
        try:
            # Check TP1
            if position.tp1_order_id and not position.tp1_is_virtual and not position.tp1_filled:
                order = self.client.get_order(position.symbol, position.tp1_order_id)
                if order and order.get('state') == 'filled':
                    fill_price = float(order.get('avgPx', position.tp1_price))
                    fill_size = float(order.get('fillSz', position.tp1_size))
                    position.tp1_filled = True
                    position.tp1_fill_price = fill_price
                    position.tp1_fill_time = datetime.now()
                    position.state = PositionState.TP1_FILLED
                    pnl = (fill_price - position.entry_price) * fill_size
                    position.realized_pnl += pnl
                    logger.info(f"🎯 TP1 FILLED: {fill_size:.4f} SOL @ ${fill_price:.2f} (PnL: ${pnl:.2f})")
                    # Send TP1 notification
                    if self.notifier:
                        remaining = position.tp2_size if not position.tp2_filled else 0
                        self.notifier.send_tp_hit(position.__dict__, 1, fill_price, pnl, remaining)
            
            # Check TP2
            if position.tp2_order_id and not position.tp2_is_virtual and not position.tp2_filled:
                order = self.client.get_order(position.symbol, position.tp2_order_id)
                if order and order.get('state') == 'filled':
                    fill_price = float(order.get('avgPx', position.tp2_price))
                    fill_size = float(order.get('fillSz', position.tp2_size))
                    position.tp2_filled = True
                    position.tp2_fill_price = fill_price
                    position.tp2_fill_time = datetime.now()
                    position.state = PositionState.TP2_FILLED
                    pnl = (fill_price - position.entry_price) * fill_size
                    position.realized_pnl += pnl
                    logger.info(f"🎯 TP2 FILLED: {fill_size:.4f} SOL @ ${fill_price:.2f} (PnL: ${pnl:.2f})")
                    # Send TP2 notification
                    if self.notifier:
                        self.notifier.send_tp_hit(position.__dict__, 2, fill_price, pnl, 0)
                    self._close_position(position, 'tp2')
                    
        except Exception as e:
            logger.error(f"Error checking limit fills: {e}")
    
    def _check_arb_time_exit(self, position: ManagedPosition, current_price: float) -> bool:
        """
        Check if an arbitrage position should exit based on time.
        
        Phase 4.2 Elite: Time-based exit for funding arbitrage.
        
        Exit conditions:
        1. Max hold time exceeded (e.g., 9 hours)
        2. Funding time has passed + buffer (funding collected)
        
        Returns:
            True if position was closed, False otherwise
        """
        import config
        
        try:
            now = datetime.now(timezone.utc)
            
            # Get entry time (convert if needed)
            entry_time = position.entry_time
            if entry_time and entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            
            if not entry_time:
                return False
            
            # Calculate hours held
            hours_held = (now - entry_time).total_seconds() / 3600
            
            # Check 1: Max hold time exceeded
            max_hold = position.max_hold_hours or getattr(config, 'FR_MAX_HOLD_HOURS', 9.0)
            if hours_held >= max_hold:
                logger.info(f"⏰ ARB TIME EXIT: Held {hours_held:.1f}h (max: {max_hold}h)")
                self._execute_arb_exit(position, current_price, 'max_hold_time')
                return True
            
            # Check 2: Funding time passed + buffer
            if position.expected_funding_time:
                funding_time = position.expected_funding_time
                if funding_time.tzinfo is None:
                    funding_time = funding_time.replace(tzinfo=timezone.utc)
                
                buffer_minutes = getattr(config, 'FR_EXIT_BUFFER_MINUTES', 30)
                exit_time = funding_time + timedelta(minutes=buffer_minutes)
                
                if now >= exit_time:
                    logger.info(f"💰 FUNDING COLLECTED: Held {hours_held:.1f}h, funding passed at {funding_time.strftime('%H:%M')} UTC")
                    self._execute_arb_exit(position, current_price, 'funding_collected')
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking arb time exit: {e}")
            return False
    
    def _execute_arb_exit(self, position: ManagedPosition, current_price: float, reason: str):
        """
        Execute exit for an arbitrage position.
        
        Sells all remaining position at market price.
        """
        try:
            logger.info(f"💰 Executing ARB exit ({reason})")
            
            # Get actual balance
            sol_balance = self.client.get_currency_balance('SOL')
            if not sol_balance or sol_balance < 0.001:
                logger.warning(f"   ⚠️  No SOL to sell, marking as closed")
                self._close_position(position, reason)
                return
            
            # Calculate PnL (price-based + funding earned)
            if position.direction == 'long':
                price_pnl = (current_price - position.entry_price) * sol_balance
            else:
                price_pnl = (position.entry_price - current_price) * sol_balance
            
            # Note: Actual funding earned is calculated by exchange, not tracked here
            # The price PnL might be small positive or negative
            # The funding collected is the main profit source
            
            # Execute market sell
            result = self.client.place_order(
                symbol=position.symbol,
                side='sell',
                order_type='market',
                size=str(round(sol_balance, 4)),
                tdMode='cash'
            )
            
            if result:
                fill_price = float(result.get('fillPx', current_price))
                position.realized_pnl = price_pnl
                
                logger.info(f"   ✅ ARB EXIT COMPLETE: {sol_balance:.4f} SOL @ ${fill_price:.2f}")
                logger.info(f"   Price PnL: ${price_pnl:.2f} (funding collected separately)")
                
                # Send notification
                if self.notifier:
                    self.notifier.send_position_closed(position.__dict__, current_price, price_pnl)
                
                self._close_position(position, reason)
            else:
                logger.error(f"   ❌ ARB exit order failed!")
                
        except Exception as e:
            logger.error(f"Error executing arb exit: {e}")
    
    def _close_position(self, position: ManagedPosition, reason: str):
        """Mark position as closed and archive it"""
        position.state = PositionState.CLOSED
        position.closed_at = datetime.now()
        position.close_reason = reason
        
        # Add to history
        self.trade_history.append(position)
        
        # Clear current position
        self.current_position = None
        
        # Stop monitoring
        self._stop_monitoring_thread()
        
        # Calculate duration and exit price
        duration = (position.closed_at - position.entry_time).total_seconds() if position.entry_time else 0
        
        # Determine exit price based on close reason
        if reason == 'tp1':
            exit_price = position.tp1_fill_price or position.tp1_price
        elif reason == 'tp2':
            exit_price = position.tp2_fill_price or position.tp2_price
        elif reason == 'sl':
            exit_price = position.stop_loss
        else:
            exit_price = position.entry_price  # Manual close, use entry as fallback
        
        # Calculate PnL percentage
        pnl_pct = ((exit_price - position.entry_price) / position.entry_price * 100) if position.entry_price > 0 else 0
        if position.direction == 'short':
            pnl_pct = -pnl_pct
        
        # Log to trade journal
        if self.trade_journal:
            trade_record = {
                'timestamp_close': position.closed_at.isoformat(),
                'timestamp_entry': position.entry_time.isoformat() if position.entry_time else None,
                'position_id': position.position_id,
                'symbol': position.symbol,
                'side': position.direction,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'size': position.actual_entry_size,
                'pnl_abs': position.realized_pnl,
                'pnl_pct': pnl_pct,
                'strategy_name': position.strategy,
                'confidence_score': position.confidence_score,
                'filters_passed': position.filters_passed or [],
                'position_size_multiplier': 1.0,  # Will be populated when confidence sizing is implemented
                'duration_seconds': duration,
                'close_reason': reason,
                'trading_mode': position.trading_mode,
                'stop_loss': position.stop_loss,
                'tp1_price': position.tp1_price,
                'tp1_filled': position.tp1_filled,
                'tp1_fill_price': position.tp1_fill_price,
                'tp2_price': position.tp2_price,
                'tp2_filled': position.tp2_filled,
                'tp2_fill_price': position.tp2_fill_price,
                'entry_order_id': position.entry_order_id,
            }
            self.trade_journal.log_trade(trade_record)
        
        # Send position closed notification
        if self.notifier:
            try:
                self.notifier.send_position_closed(position.__dict__)
            except Exception as e:
                logger.warning(f"Failed to send position closed notification: {e}")
        
        # Log summary
        logger.info("\n" + "="*60)
        logger.info("📊 POSITION CLOSED")
        logger.info("="*60)
        logger.info(f"   Position ID: {position.position_id}")
        logger.info(f"   Close Reason: {reason.upper()}")
        logger.info(f"   Entry: ${position.entry_price:.2f}")
        logger.info(f"   Exit: ${exit_price:.2f}")
        logger.info(f"   Size: {position.actual_entry_size:.4f} SOL")
        logger.info(f"   Realized PnL: ${position.realized_pnl:.2f} ({pnl_pct:+.2f}%)")
        logger.info(f"   Duration: {duration:.0f} seconds")
        logger.info("="*60 + "\n")
    
    # =========================================================================
    # 5. LOGGING & HISTORY
    # =========================================================================
    
    def get_position_summary(self) -> Optional[Dict]:
        """Get current position summary"""
        if not self.current_position:
            return None
            
        pos = self.current_position
        return {
            'position_id': pos.position_id,
            'symbol': pos.symbol,
            'direction': pos.direction,
            'state': pos.state.value,
            'entry_price': pos.entry_price,
            'actual_size': pos.actual_entry_size,
            'stop_loss': pos.stop_loss,
            'tp1_price': pos.tp1_price,
            'tp1_filled': pos.tp1_filled,
            'tp2_price': pos.tp2_price,
            'tp2_filled': pos.tp2_filled,
            'realized_pnl': pos.realized_pnl,
            'unrealized_pnl': pos.unrealized_pnl
        }
    
    def get_trade_history(self) -> List[Dict]:
        """Get trade history as list of dicts"""
        return [
            {
                'position_id': p.position_id,
                'symbol': p.symbol,
                'direction': p.direction,
                'entry_price': p.entry_price,
                'entry_size': p.actual_entry_size,
                'close_reason': p.close_reason,
                'realized_pnl': p.realized_pnl,
                'entry_time': p.entry_time.isoformat() if p.entry_time else None,
                'close_time': p.closed_at.isoformat() if p.closed_at else None,
                'duration_seconds': (p.closed_at - p.entry_time).total_seconds() if p.closed_at and p.entry_time else 0
            }
            for p in self.trade_history
        ]
    
    def log_trade_history(self):
        """Log all trade history"""
        if not self.trade_history:
            logger.info("No trade history")
            return
            
        logger.info("\n" + "="*60)
        logger.info("📜 TRADE HISTORY")
        logger.info("="*60)
        
        total_pnl = 0
        wins = 0
        losses = 0
        
        for i, trade in enumerate(self.trade_history, 1):
            total_pnl += trade.realized_pnl
            if trade.realized_pnl > 0:
                wins += 1
            else:
                losses += 1
                
            logger.info(f"\n{i}. {trade.position_id}")
            logger.info(f"   {trade.direction.upper()} {trade.actual_entry_size:.4f} SOL @ ${trade.entry_price:.2f}")
            logger.info(f"   Closed: {trade.close_reason.upper()} | PnL: ${trade.realized_pnl:.2f}")
        
        logger.info("\n" + "-"*60)
        logger.info(f"Total Trades: {len(self.trade_history)}")
        logger.info(f"Win/Loss: {wins}/{losses}")
        logger.info(f"Total PnL: ${total_pnl:.2f}")
        logger.info("="*60 + "\n")
    
    # =========================================================================
    # MANUAL CONTROLS
    # =========================================================================
    
    def close_position_now(self, reason: str = 'manual') -> bool:
        """Manually close the current position at market"""
        if not self.current_position:
            logger.warning("No position to close")
            return False
            
        position = self.current_position
        
        try:
            # Cancel any open orders
            if position.tp1_order_id and not position.tp1_is_virtual:
                self.client.cancel_order(position.symbol, position.tp1_order_id)
            if position.tp2_order_id and not position.tp2_is_virtual:
                self.client.cancel_order(position.symbol, position.tp2_order_id)
            
            # Sell all SOL
            sol_balance = self.client.get_currency_balance('SOL')
            if sol_balance and sol_balance > 0.001:
                result = self.client.place_order(
                    symbol=position.symbol,
                    side='sell',
                    order_type='market',
                    size=str(round(sol_balance, 4)),
                    tdMode='cash'
                )
                
                if result:
                    ticker = self.client.get_ticker(position.symbol)
                    close_price = float(ticker.get('last', position.entry_price)) if ticker else position.entry_price
                    pnl = (close_price - position.entry_price) * sol_balance
                    position.realized_pnl += pnl
                    logger.info(f"✅ Position closed manually @ ${close_price:.2f} (PnL: ${pnl:.2f})")
            
            self._close_position(position, reason)
            return True
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
