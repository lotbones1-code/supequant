"""
Telegram Notifier - Real-time trade notifications via Telegram

Sends alerts for:
- Trade entries
- Take profit hits (TP1, TP2)
- Stop loss triggers
- Position closes
- System errors
- Periodic performance reports

Setup:
1. Create bot via @BotFather on Telegram
2. Get bot token
3. Message your bot, then get chat_id from:
   https://api.telegram.org/bot<TOKEN>/getUpdates
4. Add to .env:
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
5. Set TELEGRAM_ENABLED=True in config.py
"""

import logging
import requests
from datetime import datetime, timezone
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Import config - handle both module and direct execution
try:
    import config
except ImportError:
    config = None


class TelegramNotifier:
    """
    Telegram notification service for trading alerts.
    
    Features:
    - Real-time trade alerts
    - Periodic performance reports
    - Graceful failure (never crashes trading)
    - HTML formatting for clean messages
    """
    
    def __init__(self, bot_token: str = None, chat_id: str = None, enabled: bool = None):
        """
        Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Telegram chat ID to send messages to
            enabled: Override config enabled flag
        """
        # Read from config if not provided
        if config:
            self.bot_token = bot_token or getattr(config, 'TELEGRAM_BOT_TOKEN', '')
            self.chat_id = chat_id or getattr(config, 'TELEGRAM_CHAT_ID', '')
            self.enabled = enabled if enabled is not None else getattr(config, 'TELEGRAM_ENABLED', False)
            self.send_trade_alerts = getattr(config, 'TELEGRAM_SEND_TRADE_ALERTS', True)
            self.send_error_alerts = getattr(config, 'TELEGRAM_SEND_ERROR_ALERTS', True)
            self.send_reports = getattr(config, 'TELEGRAM_SEND_PERIODIC_REPORTS', True)
            self.send_sentiment_alerts = getattr(config, 'TELEGRAM_SEND_SENTIMENT_ALERTS', True)
        else:
            self.bot_token = bot_token or ''
            self.chat_id = chat_id or ''
            self.enabled = enabled if enabled is not None else False
            self.send_trade_alerts = True
            self.send_error_alerts = True
            self.send_reports = True
            self.send_sentiment_alerts = True
        
        # Validate configuration
        if self.enabled and (not self.bot_token or not self.chat_id):
            logger.warning("⚠️ Telegram enabled but missing bot_token or chat_id - disabling")
            self.enabled = False
        
        # API endpoint
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        # Track last message times for rate limiting (optional)
        self._last_messages: Dict[str, datetime] = {}
    
    def _get_footer(self) -> str:
        """Get clean timestamp footer for messages."""
        now = datetime.now(timezone.utc)
        return f"\n━━━━━━━━━━━━━━━━\n🕐 {now.strftime('%b %d, %Y • %I:%M %p')} UTC"
        
        if self.enabled:
            logger.info("✅ TelegramNotifier initialized")
        else:
            logger.info("ℹ️ TelegramNotifier disabled (set TELEGRAM_ENABLED=True to enable)")
    
    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send message to Telegram.
        
        Args:
            text: Message text (can include HTML tags)
            parse_mode: Parse mode (HTML or Markdown)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            response = requests.post(self.api_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.debug(f"Telegram message sent successfully")
                    return True
                else:
                    logger.warning(f"Telegram API error: {result.get('description', 'Unknown error')}")
                    return False
            else:
                logger.warning(f"Telegram HTTP error: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.warning("Telegram request timed out")
            return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Telegram request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False
    
    def send_trade_entry(self, position: Dict[str, Any]) -> bool:
        """
        Send trade entry alert.
        
        Args:
            position: Position dictionary with trade details
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_trade_alerts:
            return False
        
        try:
            symbol = position.get('symbol', 'UNKNOWN')
            direction = position.get('direction', 'unknown').upper()
            entry_price = position.get('entry_price', 0)
            size = position.get('actual_entry_size', position.get('entry_size', 0))
            stop_loss = position.get('stop_loss', 0)
            tp1 = position.get('tp1_price', 0)
            tp2 = position.get('tp2_price', 0)
            strategy = position.get('strategy', 'manual')
            
            # Calculate percentages
            sl_pct = ((stop_loss - entry_price) / entry_price * 100) if entry_price > 0 else 0
            tp1_pct = ((tp1 - entry_price) / entry_price * 100) if entry_price > 0 else 0
            tp2_pct = ((tp2 - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            # Direction emoji
            direction_emoji = "🟢" if direction == "LONG" else "🔴"
            
            message = f"""
{direction_emoji} <b>TRADE OPENED</b>
<i>Boss Shamil, we're in!</i>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Entry:</b> ${entry_price:.2f}
<b>Size:</b> {size:.4f} SOL
━━━━━━━━━━━━━━━━
<b>Stop Loss:</b> ${stop_loss:.2f} ({sl_pct:+.1f}%)
<b>TP1:</b> ${tp1:.2f} ({tp1_pct:+.1f}%)
<b>TP2:</b> ${tp2:.2f} ({tp2_pct:+.1f}%)
━━━━━━━━━━━━━━━━
<b>Strategy:</b> {strategy}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting trade entry alert: {e}")
            return False
    
    def send_tp_hit(self, position: Dict[str, Any], tp_level: int, 
                    fill_price: float, pnl: float, remaining_size: float = 0) -> bool:
        """
        Send take profit hit alert.
        
        Args:
            position: Position dictionary
            tp_level: TP level (1 or 2)
            fill_price: Price at which TP filled
            pnl: Profit from this TP
            remaining_size: Remaining position size
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_trade_alerts:
            return False
        
        try:
            symbol = position.get('symbol', 'UNKNOWN')
            entry_price = position.get('entry_price', 0)
            entry_time = position.get('entry_time')
            
            # Calculate duration
            duration_str = "N/A"
            if entry_time:
                if isinstance(entry_time, str):
                    entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                duration = (datetime.now(timezone.utc) - entry_time.replace(tzinfo=timezone.utc)).total_seconds()
                if duration < 3600:
                    duration_str = f"{int(duration // 60)} min"
                else:
                    duration_str = f"{int(duration // 3600)}h {int((duration % 3600) // 60)}m"
            
            # Calculate percentage
            pnl_pct = ((fill_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            message = f"""
💰 <b>TP{tp_level} HIT</b>
<i>Boss Shamil, profit secured!</i>

<b>Symbol:</b> {symbol}
<b>Exit Price:</b> ${fill_price:.2f}
<b>Profit:</b> ${pnl:+.2f} ({pnl_pct:+.1f}%)
<b>Duration:</b> {duration_str}
<b>Remaining:</b> {remaining_size:.4f} SOL
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting TP alert: {e}")
            return False
    
    def send_sl_hit(self, position: Dict[str, Any], fill_price: float, pnl: float) -> bool:
        """
        Send stop loss hit alert.
        
        Args:
            position: Position dictionary
            fill_price: Price at which SL filled
            pnl: Loss from this trade
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_trade_alerts:
            return False
        
        try:
            symbol = position.get('symbol', 'UNKNOWN')
            entry_price = position.get('entry_price', 0)
            entry_time = position.get('entry_time')
            
            # Calculate duration
            duration_str = "N/A"
            if entry_time:
                if isinstance(entry_time, str):
                    entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                duration = (datetime.now(timezone.utc) - entry_time.replace(tzinfo=timezone.utc)).total_seconds()
                if duration < 3600:
                    duration_str = f"{int(duration // 60)} min"
                else:
                    duration_str = f"{int(duration // 3600)}h {int((duration % 3600) // 60)}m"
            
            # Calculate percentage
            pnl_pct = ((fill_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            message = f"""
🛑 <b>STOP LOSS HIT</b>
<i>Boss Shamil, risk managed. We live to trade another day.</i>

<b>Symbol:</b> {symbol}
<b>Exit Price:</b> ${fill_price:.2f}
<b>Loss:</b> ${pnl:.2f} ({pnl_pct:.1f}%)
<b>Duration:</b> {duration_str}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting SL alert: {e}")
            return False
    
    def send_position_closed(self, position: Dict[str, Any]) -> bool:
        """
        Send position closed summary.
        
        Args:
            position: Position dictionary with final details
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_trade_alerts:
            return False
        
        try:
            symbol = position.get('symbol', 'UNKNOWN')
            direction = position.get('direction', 'unknown').upper()
            entry_price = position.get('entry_price', 0)
            realized_pnl = position.get('realized_pnl', 0)
            close_reason = position.get('close_reason', 'unknown').upper()
            entry_time = position.get('entry_time')
            
            # Calculate duration
            duration_str = "N/A"
            if entry_time:
                if isinstance(entry_time, str):
                    entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                duration = (datetime.now(timezone.utc) - entry_time.replace(tzinfo=timezone.utc)).total_seconds()
                if duration < 3600:
                    duration_str = f"{int(duration // 60)} min"
                else:
                    duration_str = f"{int(duration // 3600)}h {int((duration % 3600) // 60)}m"
            
            # Result emoji
            if realized_pnl > 0:
                result_emoji = "✅ WIN"
            elif realized_pnl < 0:
                result_emoji = "❌ LOSS"
            else:
                result_emoji = "➖ BREAK EVEN"
            
            # PnL percentage
            size = position.get('actual_entry_size', 0)
            notional = entry_price * size if entry_price and size else 1
            pnl_pct = (realized_pnl / notional * 100) if notional > 0 else 0
            
            # Custom message based on result
            if realized_pnl > 0:
                boss_msg = "Boss Shamil, another win in the books!"
            elif realized_pnl < 0:
                boss_msg = "Boss Shamil, small setback. The system is learning."
            else:
                boss_msg = "Boss Shamil, broke even on this one."
            
            message = f"""
📊 <b>POSITION CLOSED</b>
<i>{boss_msg}</i>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Result:</b> {result_emoji}
━━━━━━━━━━━━━━━━
<b>Entry:</b> ${entry_price:.2f}
<b>PnL:</b> ${realized_pnl:+.2f} ({pnl_pct:+.1f}%)
<b>Reason:</b> {close_reason}
<b>Duration:</b> {duration_str}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting position closed alert: {e}")
            return False
    
    def send_error(self, error_msg: str, context: str = None) -> bool:
        """
        Send system error alert.
        
        Args:
            error_msg: Error message
            context: Optional context about where error occurred
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_error_alerts:
            return False
        
        try:
            context_line = f"\n<b>Context:</b> {context}" if context else ""
            
            message = f"""
⚠️ <b>SYSTEM ALERT</b>
<i>Boss Shamil, heads up on this:</i>

<b>Error:</b> {error_msg}{context_line}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting error alert: {e}")
            return False
    
    def send_periodic_report(self, report: Dict[str, Any]) -> bool:
        """
        Send periodic performance report.
        
        Args:
            report: Report dictionary from PerformanceAnalytics
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_reports:
            return False
        
        try:
            period = report.get('period', {})
            overall = report.get('overall', {})
            by_close_reason = report.get('by_close_reason', {})
            
            # Extract metrics
            total_trades = overall.get('total_trades', 0)
            win_rate = overall.get('win_rate_pct', 0)
            total_pnl = overall.get('total_pnl', 0)
            profit_factor = overall.get('profit_factor', 0)
            
            # PnL emoji
            pnl_emoji = "📈" if total_pnl >= 0 else "📉"
            
            # Build close reason breakdown
            reason_lines = []
            for reason, data in sorted(by_close_reason.items()):
                count = data.get('trade_count', 0)
                if count > 0:
                    reason_lines.append(f"  • {reason.upper()}: {count}")
            reason_breakdown = "\n".join(reason_lines) if reason_lines else "  No trades"
            
            # Custom message based on performance
            if total_pnl > 0:
                boss_msg = "Boss Shamil, the system is printing!"
            elif total_pnl < 0:
                boss_msg = "Boss Shamil, here's the current status."
            else:
                boss_msg = "Boss Shamil, your performance report is ready."
            
            message = f"""
{pnl_emoji} <b>PERFORMANCE REPORT</b>
<i>{boss_msg}</i>

<b>Period:</b> {period.get('start', 'N/A')} to {period.get('end', 'N/A')}
━━━━━━━━━━━━━━━━
<b>Trades:</b> {total_trades}
<b>Win Rate:</b> {win_rate:.1f}%
<b>Total PnL:</b> ${total_pnl:+.2f}
<b>Profit Factor:</b> {profit_factor}
━━━━━━━━━━━━━━━━
<b>By Close Reason:</b>
{reason_breakdown}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting periodic report: {e}")
            return False
    
    def send_sentiment_alert(self, sentiment_data: Dict[str, Any]) -> bool:
        """
        Send market sentiment alert.
        
        Args:
            sentiment_data: Dictionary with sentiment info:
                - overall: "bullish", "bearish", "neutral"
                - score: -100 to +100
                - sol_sentiment: SOL-specific sentiment
                - btc_sentiment: BTC sentiment (leader)
                - key_events: List of important events
                - recommendation: Trading recommendation
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_sentiment_alerts:
            return False
        
        try:
            overall = sentiment_data.get('overall', 'neutral').upper()
            score = sentiment_data.get('score', 0)
            sol_sentiment = sentiment_data.get('sol_sentiment', 'neutral')
            btc_sentiment = sentiment_data.get('btc_sentiment', 'neutral')
            key_events = sentiment_data.get('key_events', [])
            recommendation = sentiment_data.get('recommendation', 'No change')
            
            # Sentiment emoji
            if score > 30:
                sentiment_emoji = "🟢"
                mood = "BULLISH"
            elif score < -30:
                sentiment_emoji = "🔴"
                mood = "BEARISH"
            else:
                sentiment_emoji = "🟡"
                mood = "NEUTRAL"
            
            # Format key events
            events_text = ""
            if key_events:
                events_list = "\n".join([f"  • {event}" for event in key_events[:5]])
                events_text = f"\n<b>Key Events:</b>\n{events_list}"
            
            message = f"""
{sentiment_emoji} <b>MARKET SENTIMENT UPDATE</b>
<i>Boss Shamil, here's the market pulse:</i>

<b>Overall:</b> {mood} ({score:+d}/100)
━━━━━━━━━━━━━━━━
<b>SOL:</b> {sol_sentiment.upper()}
<b>BTC:</b> {btc_sentiment.upper()}
{events_text}
━━━━━━━━━━━━━━━━
<b>Trading Note:</b> {recommendation}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting sentiment alert: {e}")
            return False
    
    def send_market_summary(self, summary_data: Dict[str, Any]) -> bool:
        """
        Send quick market summary.
        
        Args:
            summary_data: Dictionary with:
                - sol_price: Current SOL price
                - sol_change_24h: 24h change %
                - btc_price: Current BTC price
                - btc_change_24h: 24h change %
                - trend: "up", "down", "sideways"
                - volatility: "low", "medium", "high"
            
        Returns:
            True if sent, False if failed/disabled
        """
        if not self.enabled or not self.send_sentiment_alerts:
            return False
        
        try:
            sol_price = summary_data.get('sol_price', 0)
            sol_change = summary_data.get('sol_change_24h', 0)
            btc_price = summary_data.get('btc_price', 0)
            btc_change = summary_data.get('btc_change_24h', 0)
            trend = summary_data.get('trend', 'sideways').upper()
            volatility = summary_data.get('volatility', 'medium').upper()
            
            # Trend emoji
            if trend == "UP":
                trend_emoji = "📈"
            elif trend == "DOWN":
                trend_emoji = "📉"
            else:
                trend_emoji = "➡️"
            
            # Volatility emoji
            if volatility == "HIGH":
                vol_emoji = "🔥"
            elif volatility == "LOW":
                vol_emoji = "😴"
            else:
                vol_emoji = "⚡"
            
            # Change formatting
            sol_arrow = "🟢" if sol_change >= 0 else "🔴"
            btc_arrow = "🟢" if btc_change >= 0 else "🔴"
            
            message = f"""
{trend_emoji} <b>MARKET SUMMARY</b>
<i>Boss Shamil, quick market check:</i>

{sol_arrow} <b>SOL:</b> ${sol_price:.2f} ({sol_change:+.1f}%)
{btc_arrow} <b>BTC:</b> ${btc_price:,.0f} ({btc_change:+.1f}%)
━━━━━━━━━━━━━━━━
<b>Trend:</b> {trend} {trend_emoji}
<b>Volatility:</b> {volatility} {vol_emoji}
{self._get_footer()}
""".strip()
            
            return self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error formatting market summary: {e}")
            return False
    
    def send_test_message(self) -> bool:
        """
        Send a test message to verify configuration.
        
        Returns:
            True if sent successfully
        """
        message = f"""
🤖 <b>SUPEQUANT ONLINE</b>
<i>Boss Shamil, your trading system is locked and loaded!</i>

✅ Telegram notifications active
✅ Real-time trade alerts enabled
✅ Market sentiment alerts enabled
✅ System ready to execute
{self._get_footer()}
""".strip()
        
        result = self._send_message(message)
        if result:
            logger.info("✅ Test message sent successfully")
        else:
            logger.error("❌ Test message failed")
        return result


# CLI for testing
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n📱 Telegram Notifier Test\n")
    
    # Check if we have credentials
    notifier = TelegramNotifier()
    
    if not notifier.enabled:
        print("❌ Telegram is disabled or missing credentials")
        print("\nTo enable:")
        print("1. Create bot via @BotFather")
        print("2. Add to .env:")
        print("   TELEGRAM_BOT_TOKEN=your_token")
        print("   TELEGRAM_CHAT_ID=your_chat_id")
        print("3. Set TELEGRAM_ENABLED=True in config.py")
        sys.exit(1)
    
    # Send test message
    print("Sending test message...")
    if notifier.send_test_message():
        print("✅ Test message sent! Check your Telegram.")
    else:
        print("❌ Failed to send test message")
