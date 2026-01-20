"""
Trade Journal - Automatic trade logging for analytics and ML

Logs every closed trade to disk in JSONL format for:
- Performance analytics
- ML training data
- Trade review and improvement

Files are stored in: runs/YYYY-MM-DD/trades.jsonl

Testing:
1. Run system in simulated mode (OKX_SIMULATED=True)
2. Force a test trade or let system execute naturally
3. Check runs/YYYY-MM-DD/trades.jsonl for logged trades
4. Verify JSON is valid: python -m json.tool < runs/YYYY-MM-DD/trades.jsonl
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class TradeJournal:
    """
    Trade journaling system that logs closed trades to disk.
    
    Features:
    - JSONL format (one JSON object per line) for easy parsing
    - Daily directories for organization
    - Graceful error handling (never crashes trading)
    - Complete trade details for analytics
    """
    
    def __init__(self, base_path: str = "runs", enabled: bool = True):
        """
        Initialize the trade journal.
        
        Args:
            base_path: Base directory for trade logs (default: "runs")
            enabled: Whether journaling is enabled
        """
        self.base_path = base_path
        self.enabled = enabled
        
        if self.enabled:
            # Ensure base directory exists
            try:
                os.makedirs(self.base_path, exist_ok=True)
                logger.info(f"✅ TradeJournal initialized (path: {self.base_path})")
            except Exception as e:
                logger.error(f"⚠️ TradeJournal: Could not create base path: {e}")
                self.enabled = False
    
    def log_trade(self, trade: Dict[str, Any]) -> bool:
        """
        Log a completed trade to disk.
        
        Expected trade keys:
        - timestamp_close: ISO 8601 string (when position closed)
        - symbol: Trading pair (e.g., 'SOL-USDT')
        - side: 'long' or 'short'
        - entry_price: float
        - exit_price: float (average or final)
        - size: float (actual filled size)
        - pnl_abs: float (absolute PnL in USDT)
        - pnl_pct: float (percentage PnL)
        - strategy_name: str
        - confidence_score: float or None (0-100)
        - duration_seconds: float
        - position_id: str
        - close_reason: str ('tp1', 'tp2', 'sl', 'manual')
        - entry_time: ISO 8601 string
        - tp1_filled: bool
        - tp1_price: float
        - tp2_filled: bool
        - tp2_price: float
        - stop_loss: float
        
        Args:
            trade: Dictionary with trade details
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Get today's date for directory
            today = datetime.utcnow().strftime("%Y-%m-%d")
            day_path = os.path.join(self.base_path, today)
            
            # Create daily directory if needed
            os.makedirs(day_path, exist_ok=True)
            
            # Build file path
            trades_file = os.path.join(day_path, "trades.jsonl")
            
            # Ensure all values are JSON serializable
            clean_trade = self._clean_for_json(trade)
            
            # Add metadata
            clean_trade['_logged_at'] = datetime.utcnow().isoformat()
            clean_trade['_journal_version'] = '1.0'
            
            # Append to JSONL file
            with open(trades_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(clean_trade, ensure_ascii=False) + '\n')
            
            logger.info(f"📝 Trade logged: {trade.get('position_id', 'unknown')} → {trades_file}")
            return True
            
        except Exception as e:
            # Never crash trading - just log the error
            logger.error(f"⚠️ TradeJournal: Failed to log trade: {e}")
            return False
    
    def _clean_for_json(self, data: Dict) -> Dict:
        """
        Clean data for JSON serialization.
        Handles datetime objects, None values, etc.
        """
        clean = {}
        for key, value in data.items():
            if value is None:
                clean[key] = None
            elif isinstance(value, datetime):
                clean[key] = value.isoformat()
            elif isinstance(value, (int, float, str, bool)):
                clean[key] = value
            elif isinstance(value, dict):
                clean[key] = self._clean_for_json(value)
            elif isinstance(value, list):
                clean[key] = [self._clean_for_json(v) if isinstance(v, dict) else v for v in value]
            else:
                # Convert to string as fallback
                clean[key] = str(value)
        return clean
    
    def get_trades_for_date(self, date_str: str) -> list:
        """
        Read all trades for a specific date.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            
        Returns:
            List of trade dictionaries
        """
        trades = []
        trades_file = os.path.join(self.base_path, date_str, "trades.jsonl")
        
        if not os.path.exists(trades_file):
            return trades
        
        try:
            with open(trades_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        trades.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading trades for {date_str}: {e}")
        
        return trades
    
    def get_recent_trades(self, days: int = 7) -> list:
        """
        Get trades from the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of trade dictionaries, sorted by time (newest first)
        """
        from datetime import timedelta
        
        all_trades = []
        today = datetime.utcnow().date()
        
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            trades = self.get_trades_for_date(date_str)
            all_trades.extend(trades)
        
        # Sort by close time (newest first)
        all_trades.sort(
            key=lambda t: t.get('timestamp_close', ''),
            reverse=True
        )
        
        return all_trades
    
    def get_summary_stats(self, trades: Optional[list] = None) -> Dict:
        """
        Calculate summary statistics from trades.
        
        Args:
            trades: List of trades (if None, uses last 30 days)
            
        Returns:
            Dictionary with stats
        """
        if trades is None:
            trades = self.get_recent_trades(days=30)
        
        if not trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0
            }
        
        wins = [t for t in trades if t.get('pnl_abs', 0) > 0]
        losses = [t for t in trades if t.get('pnl_abs', 0) <= 0]
        
        total_pnl = sum(t.get('pnl_abs', 0) for t in trades)
        total_wins = sum(t.get('pnl_abs', 0) for t in wins)
        total_losses = abs(sum(t.get('pnl_abs', 0) for t in losses))
        
        return {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(trades) if trades else 0.0,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / len(trades) if trades else 0.0,
            'avg_win': total_wins / len(wins) if wins else 0.0,
            'avg_loss': total_losses / len(losses) if losses else 0.0,
            'profit_factor': total_wins / total_losses if total_losses > 0 else float('inf')
        }
