"""
Risk Manager
Enforces all risk management rules:
- Position sizing
- Daily loss limits
- Maximum positions
- Emergency shutdown conditions
"""

from typing import Dict, Optional, Tuple
import logging
from datetime import datetime, date
from data_feed.okx_client import OKXClient
from config import (
    MAX_RISK_PER_TRADE,
    MAX_POSITIONS_OPEN,
    POSITION_SIZE_PCT,
    MAX_DAILY_LOSS_PCT,
    MAX_DAILY_DRAWDOWN,
    ENABLE_EMERGENCY_SHUTDOWN,
    EMERGENCY_VOLATILITY_MULTIPLIER,
    EMERGENCY_DRAWDOWN_PCT,
    ENABLE_KILL_SWITCH,
    KILL_SWITCH_FILE
)
import os

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages all risk-related decisions
    CRITICAL: This module prevents catastrophic losses
    """

    def __init__(self, okx_client: Optional[OKXClient] = None):
        self.client = okx_client or OKXClient()

        # Daily tracking
        self.daily_pnl = 0
        self.daily_trades = 0
        self.current_date = date.today()

        # Account tracking
        self.starting_balance = None
        self.current_balance = None

        # Emergency state
        self.emergency_shutdown = False
        self.shutdown_reason = None

        logger.info("✅ RiskManager initialized")

    def check_can_trade(self, num_open_positions: int) -> Tuple[bool, str]:
        """
        Check if new trade is allowed based on risk rules

        Returns:
            (allowed: bool, reason: str)
        """
        # Check 1: Kill switch
        if ENABLE_KILL_SWITCH and os.path.exists(KILL_SWITCH_FILE):
            self.emergency_shutdown = True
            self.shutdown_reason = "Kill switch activated"
            return False, "Kill switch file detected - trading disabled"

        # Check 2: Emergency shutdown
        if self.emergency_shutdown:
            return False, f"Emergency shutdown active: {self.shutdown_reason}"

        # Check 3: Max positions
        if num_open_positions >= MAX_POSITIONS_OPEN:
            return False, f"Max positions reached ({num_open_positions}/{MAX_POSITIONS_OPEN})"

        # Check 4: Daily loss limit
        if self.current_balance and self.starting_balance:
            daily_loss_pct = (self.starting_balance - self.current_balance) / self.starting_balance

            if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
                logger.error(f"❌ Daily loss limit reached: {daily_loss_pct*100:.2f}%")
                return False, f"Daily loss limit reached ({daily_loss_pct*100:.2f}%)"

        # Check 5: Account balance available
        if not self._fetch_current_balance():
            return False, "Could not fetch account balance"

        return True, "All risk checks passed"

    def calculate_position_size(self, signal: Dict, account_balance: float) -> Tuple[float, Dict]:
        """
        Calculate position size based on risk management rules

        Args:
            signal: Trading signal
            account_balance: Current account balance

        Returns:
            (position_size: float, details: Dict)
        """
        entry_price = signal['entry_price']
        stop_loss = signal['stop_loss']
        risk_amount = signal['risk_amount']

        # Method 1: Fixed percentage risk per trade
        max_loss_usd = account_balance * MAX_RISK_PER_TRADE

        # Calculate position size based on stop distance
        if risk_amount > 0:
            position_size = max_loss_usd / risk_amount
        else:
            # Fallback: use fixed percentage of account
            position_size = (account_balance * POSITION_SIZE_PCT) / entry_price

        # Calculate notional value
        notional_value = position_size * entry_price

        details = {
            'position_size': position_size,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'risk_per_trade_usd': max_loss_usd,
            'risk_per_trade_pct': MAX_RISK_PER_TRADE * 100,
            'notional_value': notional_value,
            'account_balance': account_balance
        }

        logger.info(f"💰 Position size: {position_size:.4f} (${notional_value:.2f})")
        logger.info(f"   Risk: ${max_loss_usd:.2f} ({MAX_RISK_PER_TRADE*100}%)")

        return position_size, details

    def check_emergency_conditions(self, market_state: Dict) -> Tuple[bool, str]:
        """
        Check for emergency shutdown conditions

        Returns:
            (trigger_shutdown: bool, reason: str)
        """
        if not ENABLE_EMERGENCY_SHUTDOWN:
            return False, "Emergency shutdown disabled"

        # Check 1: Extreme volatility
        timeframes = market_state.get('timeframes', {})
        if '15m' in timeframes:
            atr_data = timeframes['15m'].get('atr', {})
            atr_percentile = atr_data.get('atr_percentile', 50)

            # If ATR is in extreme territory
            if atr_percentile > 95:
                return True, f"Extreme volatility detected (ATR {atr_percentile}th percentile)"

        # Check 2: Account drawdown
        if self.starting_balance and self.current_balance:
            drawdown = (self.starting_balance - self.current_balance) / self.starting_balance

            if drawdown >= EMERGENCY_DRAWDOWN_PCT:
                return True, f"Emergency drawdown reached ({drawdown*100:.2f}%)"

        # Check 3: API failures
        health = self.client.get_health_status()
        if health['error_rate'] > 0.5:  # More than 50% API failures
            return True, f"High API error rate ({health['error_rate']*100:.0f}%)"

        return False, "No emergency conditions"

    def trigger_emergency_shutdown(self, reason: str):
        """
        Activate emergency shutdown

        Args:
            reason: Reason for shutdown
        """
        self.emergency_shutdown = True
        self.shutdown_reason = reason

        logger.critical("🚨" * 20)
        logger.critical(f"EMERGENCY SHUTDOWN TRIGGERED")
        logger.critical(f"Reason: {reason}")
        logger.critical("🚨" * 20)

        # TODO: Close all open positions
        # TODO: Cancel all open orders
        # TODO: Send alert notification

    def update_daily_pnl(self, pnl: float):
        """
        Update daily PnL tracking

        Args:
            pnl: PnL to add
        """
        # Check if new day
        today = date.today()
        if today != self.current_date:
            logger.info(f"📅 New trading day - Reset daily PnL")
            logger.info(f"   Previous day PnL: ${self.daily_pnl:.2f}")
            self.daily_pnl = 0
            self.daily_trades = 0
            self.current_date = today

        self.daily_pnl += pnl
        self.daily_trades += 1

        logger.info(f"📊 Daily PnL: ${self.daily_pnl:.2f} ({self.daily_trades} trades)")

    def _fetch_current_balance(self) -> bool:
        """Fetch current account balance from exchange"""
        try:
            # If in simulated mode and balance fetch fails, use demo balance
            balance_data = self.client.get_account_balance()

            if not balance_data:
                # Use demo balance for simulated mode
                if self.client.simulated:
                    logger.warning("⚠️  Using demo balance (10000 USDT) - could not fetch real balance")
                    if self.starting_balance is None:
                        self.starting_balance = 10000.0
                    self.current_balance = 10000.0
                    return True
                return False

            # Extract USDT balance (or main balance)
            for balance in balance_data:
                details = balance.get('details', [])
                for detail in details:
                    if detail.get('ccy') == 'USDT':
                        available = float(detail.get('availEq', 0))

                        if self.starting_balance is None:
                            self.starting_balance = available
                            logger.info(f"💰 Starting balance: ${available:.2f}")

                        self.current_balance = available
                        return True

            return False

        except Exception as e:
            logger.error(f"❌ Error fetching balance: {e}")
            return False

    def get_account_balance(self) -> Optional[float]:
        """Get current account balance"""
        if self._fetch_current_balance():
            return self.current_balance
        return None

    def get_risk_statistics(self) -> Dict:
        """Get risk management statistics"""
        stats = {
            'starting_balance': self.starting_balance,
            'current_balance': self.current_balance,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'emergency_shutdown': self.emergency_shutdown,
            'shutdown_reason': self.shutdown_reason
        }

        if self.starting_balance and self.current_balance:
            stats['total_pnl'] = self.current_balance - self.starting_balance
            stats['total_pnl_pct'] = ((self.current_balance - self.starting_balance) / self.starting_balance) * 100
            stats['drawdown_pct'] = ((self.starting_balance - self.current_balance) / self.starting_balance) * 100 if self.current_balance < self.starting_balance else 0
        else:
            stats['total_pnl'] = 0
            stats['total_pnl_pct'] = 0
            stats['drawdown_pct'] = 0

        return stats

    def reset_emergency_shutdown(self):
        """Reset emergency shutdown (use with caution!)"""
        logger.warning("⚠️  Resetting emergency shutdown")
        self.emergency_shutdown = False
        self.shutdown_reason = None

    def create_kill_switch(self):
        """Create kill switch file to stop trading"""
        try:
            with open(KILL_SWITCH_FILE, 'w') as f:
                f.write(f"Kill switch activated at {datetime.now()}\n")
            logger.critical(f"🛑 Kill switch file created: {KILL_SWITCH_FILE}")
        except Exception as e:
            logger.error(f"❌ Failed to create kill switch: {e}")

    def remove_kill_switch(self):
        """Remove kill switch file to resume trading"""
        try:
            if os.path.exists(KILL_SWITCH_FILE):
                os.remove(KILL_SWITCH_FILE)
                logger.info(f"✅ Kill switch file removed")
        except Exception as e:
            logger.error(f"❌ Failed to remove kill switch: {e}")
