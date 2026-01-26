# -*- coding: utf-8 -*-
"""
Trade Screenshots - Generates chart images when trades open/close

FREE - Uses matplotlib (already installed)
READ-ONLY - Does not affect trading logic

Saves images to: data/screenshots/
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import json

logger = logging.getLogger(__name__)

# Check if matplotlib is available
MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend for saving files
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    logger.warning("Matplotlib not available - screenshots disabled")


class TradeScreenshots:
    """
    Generates simple chart screenshots when trades open/close.

    Features:
    - Candlestick-style price chart (simplified)
    - Entry/exit markers
    - Stop loss and take profit lines
    - Saves to data/screenshots/
    """

    def __init__(self, output_dir: str = "data/screenshots"):
        """Initialize screenshot system."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.enabled = MATPLOTLIB_AVAILABLE

        if self.enabled:
            logger.info(f"📸 Trade screenshots enabled - saving to {self.output_dir}")
        else:
            logger.warning("📸 Trade screenshots disabled - matplotlib not available")

    def capture_trade_entry(self, signal: Dict, price_history: List[Dict],
                           position_details: Dict = None) -> Optional[str]:
        """
        Generate chart screenshot when trade opens.

        Args:
            signal: Trading signal with entry, stop, TP
            price_history: Recent OHLCV data
            position_details: Optional V4 details

        Returns:
            Path to saved image or None
        """
        if not self.enabled:
            return None

        try:
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            direction = signal.get('direction', 'unknown').upper()
            strategy = signal.get('strategy', 'unknown')[:10]

            filename = f"entry_{timestamp}_{direction}_{strategy}.png"
            filepath = self.output_dir / filename

            # Generate the chart
            self._generate_chart(
                price_history=price_history,
                entry_price=signal.get('entry_price'),
                stop_loss=signal.get('stop_loss'),
                take_profit=signal.get('take_profit_1'),
                direction=direction,
                title=f"ENTRY: {direction} {strategy}",
                position_details=position_details,
                filepath=filepath
            )

            logger.info(f"📸 Trade entry screenshot saved: {filename}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to capture entry screenshot: {e}")
            return None

    def capture_trade_exit(self, trade_data: Dict, price_history: List[Dict]) -> Optional[str]:
        """
        Generate chart screenshot when trade closes.

        Args:
            trade_data: Trade data with entry, exit, PnL
            price_history: Recent OHLCV data

        Returns:
            Path to saved image or None
        """
        if not self.enabled:
            return None

        try:
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            direction = trade_data.get('direction', 'unknown').upper()
            pnl = trade_data.get('pnl', 0)
            result = "WIN" if pnl > 0 else "LOSS"

            filename = f"exit_{timestamp}_{direction}_{result}.png"
            filepath = self.output_dir / filename

            # Generate the chart
            self._generate_chart(
                price_history=price_history,
                entry_price=trade_data.get('entry_price'),
                exit_price=trade_data.get('exit_price'),
                stop_loss=trade_data.get('stop_loss'),
                direction=direction,
                title=f"EXIT: {direction} {result} ${pnl:+.2f}",
                is_exit=True,
                pnl=pnl,
                filepath=filepath
            )

            logger.info(f"📸 Trade exit screenshot saved: {filename}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to capture exit screenshot: {e}")
            return None

    def _generate_chart(self, price_history: List[Dict], entry_price: float,
                       direction: str, title: str, filepath: Path,
                       stop_loss: float = None, take_profit: float = None,
                       exit_price: float = None, is_exit: bool = False,
                       pnl: float = None, position_details: Dict = None):
        """Generate and save the chart image."""

        if not price_history or len(price_history) < 5:
            logger.warning("Not enough price history for chart")
            return

        # Extract data
        times = []
        closes = []
        highs = []
        lows = []

        for candle in price_history[-50:]:  # Last 50 candles
            try:
                ts = candle.get('timestamp') or candle.get('time')
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                elif isinstance(ts, (int, float)):
                    dt = datetime.fromtimestamp(ts / 1000 if ts > 1e10 else ts, tz=timezone.utc)
                else:
                    continue

                times.append(dt)
                closes.append(float(candle.get('close', 0)))
                highs.append(float(candle.get('high', 0)))
                lows.append(float(candle.get('low', 0)))
            except Exception:
                continue

        if len(times) < 5:
            logger.warning("Could not parse enough price data")
            return

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot price line with high/low range
        ax.fill_between(times, lows, highs, alpha=0.3, color='gray', label='H/L Range')
        ax.plot(times, closes, 'b-', linewidth=1.5, label='Close')

        # Entry line
        if entry_price:
            ax.axhline(y=entry_price, color='blue', linestyle='--', linewidth=2, label=f'Entry ${entry_price:.2f}')

        # Stop loss line
        if stop_loss:
            ax.axhline(y=stop_loss, color='red', linestyle='--', linewidth=1.5, label=f'Stop ${stop_loss:.2f}')

        # Take profit line
        if take_profit:
            ax.axhline(y=take_profit, color='green', linestyle='--', linewidth=1.5, label=f'TP ${take_profit:.2f}')

        # Exit line (for exit charts)
        if is_exit and exit_price:
            color = 'green' if pnl and pnl > 0 else 'red'
            ax.axhline(y=exit_price, color=color, linestyle='-', linewidth=2, label=f'Exit ${exit_price:.2f}')

        # Styling
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Time (UTC)')
        ax.set_ylabel('Price (USDT)')
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)

        # Add V4 details if available
        if position_details:
            v4_mult = position_details.get('v4_multiplier', 1.0)
            if v4_mult != 1.0:
                ax.text(0.02, 0.98, f'V4 Mult: {v4_mult:.2f}x', transform=ax.transAxes,
                       fontsize=10, verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))

        # Add PnL for exit charts
        if is_exit and pnl is not None:
            color = 'green' if pnl > 0 else 'red'
            ax.text(0.98, 0.98, f'PnL: ${pnl:+.2f}', transform=ax.transAxes,
                   fontsize=12, verticalalignment='top', horizontalalignment='right',
                   bbox=dict(boxstyle='round', facecolor=color, alpha=0.3))

        plt.tight_layout()
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        plt.close(fig)

    def get_recent_screenshots(self, limit: int = 10) -> List[Dict]:
        """Get list of recent screenshots."""
        screenshots = []

        try:
            files = sorted(self.output_dir.glob('*.png'), key=os.path.getmtime, reverse=True)

            for f in files[:limit]:
                screenshots.append({
                    'filename': f.name,
                    'path': str(f),
                    'created': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    'type': 'entry' if f.name.startswith('entry_') else 'exit'
                })
        except Exception as e:
            logger.error(f"Error listing screenshots: {e}")

        return screenshots


# Singleton instance
_screenshot_system = None

def get_screenshot_system() -> TradeScreenshots:
    """Get singleton screenshot system instance."""
    global _screenshot_system
    if _screenshot_system is None:
        _screenshot_system = TradeScreenshots()
    return _screenshot_system
