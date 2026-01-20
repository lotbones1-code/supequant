"""
Enhanced Telegram Bot - Two-way communication with elite features

Features:
- Receives commands from Boss Shamil
- Notes storage with reminders
- Hourly status updates
- Quick stats on demand
- Performance tracking (streaks, daily summary)
- System health monitoring

Commands:
/note <text>       - Save a note/idea
/notes             - List all notes
/remind <time> <text> - Set a reminder
/status            - Quick system status
/stats             - Trading statistics
/pnl               - Today's PnL
/health            - System health check
/help              - Show all commands
"""

import json
import os
import logging
import threading
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Import config
try:
    import config
except ImportError:
    config = None


@dataclass
class Note:
    """A saved note/idea"""
    id: int
    text: str
    created_at: str
    reminder_at: Optional[str] = None
    reminded: bool = False
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass 
class Reminder:
    """A scheduled reminder"""
    id: int
    text: str
    remind_at: str
    created_at: str
    sent: bool = False


class NotesStorage:
    """Persistent storage for notes and reminders"""
    
    def __init__(self, storage_path: str = None):
        if storage_path is None:
            storage_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'notes.json')
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.notes: List[Note] = []
        self.reminders: List[Reminder] = []
        self._load()
    
    def _load(self):
        """Load notes and reminders from file"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.notes = [Note(**n) for n in data.get('notes', [])]
                    self.reminders = [Reminder(**r) for r in data.get('reminders', [])]
                logger.info(f"📝 Loaded {len(self.notes)} notes, {len(self.reminders)} reminders")
            except Exception as e:
                logger.error(f"Error loading notes: {e}")
                self.notes = []
                self.reminders = []
    
    def _save(self):
        """Save notes and reminders to file"""
        try:
            data = {
                'notes': [asdict(n) for n in self.notes],
                'reminders': [asdict(r) for r in self.reminders]
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving notes: {e}")
    
    def add_note(self, text: str, reminder_minutes: int = None) -> Note:
        """Add a new note"""
        note_id = max([n.id for n in self.notes], default=0) + 1
        now = datetime.now(timezone.utc)
        
        reminder_at = None
        if reminder_minutes:
            reminder_at = (now + timedelta(minutes=reminder_minutes)).isoformat()
        
        # Extract tags (words starting with #)
        tags = [word[1:] for word in text.split() if word.startswith('#')]
        
        note = Note(
            id=note_id,
            text=text,
            created_at=now.isoformat(),
            reminder_at=reminder_at,
            tags=tags
        )
        self.notes.append(note)
        self._save()
        return note
    
    def get_notes(self, limit: int = 10) -> List[Note]:
        """Get recent notes"""
        return sorted(self.notes, key=lambda n: n.created_at, reverse=True)[:limit]
    
    def delete_note(self, note_id: int) -> bool:
        """Delete a note by ID"""
        for i, note in enumerate(self.notes):
            if note.id == note_id:
                self.notes.pop(i)
                self._save()
                return True
        return False
    
    def add_reminder(self, text: str, remind_at: datetime) -> Reminder:
        """Add a new reminder"""
        reminder_id = max([r.id for r in self.reminders], default=0) + 1
        reminder = Reminder(
            id=reminder_id,
            text=text,
            remind_at=remind_at.isoformat(),
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self.reminders.append(reminder)
        self._save()
        return reminder
    
    def get_due_reminders(self) -> List[Reminder]:
        """Get reminders that are due"""
        now = datetime.now(timezone.utc)
        due = []
        for reminder in self.reminders:
            if not reminder.sent:
                remind_at = datetime.fromisoformat(reminder.remind_at.replace('Z', '+00:00'))
                if remind_at <= now:
                    due.append(reminder)
        return due
    
    def mark_reminder_sent(self, reminder_id: int):
        """Mark a reminder as sent"""
        for reminder in self.reminders:
            if reminder.id == reminder_id:
                reminder.sent = True
                self._save()
                break
    
    def get_notes_needing_reminder(self) -> List[Note]:
        """Get notes with due reminders"""
        now = datetime.now(timezone.utc)
        due = []
        for note in self.notes:
            if note.reminder_at and not note.reminded:
                remind_at = datetime.fromisoformat(note.reminder_at.replace('Z', '+00:00'))
                if remind_at <= now:
                    due.append(note)
        return due
    
    def mark_note_reminded(self, note_id: int):
        """Mark a note's reminder as sent"""
        for note in self.notes:
            if note.id == note_id:
                note.reminded = True
                self._save()
                break


class PerformanceTracker:
    """Track trading performance for stats"""
    
    def __init__(self, trades_path: str = None):
        if trades_path is None:
            trades_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'paper_trades.jsonl')
        self.trades_path = Path(trades_path)
        
    def get_today_stats(self) -> Dict:
        """Get today's trading statistics"""
        today = datetime.now(timezone.utc).date()
        trades = self._load_trades()
        
        today_trades = [t for t in trades if self._get_trade_date(t) == today]
        
        if not today_trades:
            return {
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'pnl': 0.0,
                'win_rate': 0.0
            }
        
        wins = sum(1 for t in today_trades if t.get('pnl_abs', 0) > 0)
        losses = sum(1 for t in today_trades if t.get('pnl_abs', 0) < 0)
        pnl = sum(t.get('pnl_abs', 0) for t in today_trades)
        
        return {
            'trades': len(today_trades),
            'wins': wins,
            'losses': losses,
            'pnl': pnl,
            'win_rate': wins / len(today_trades) * 100 if today_trades else 0
        }
    
    def get_streak(self) -> Dict:
        """Get current win/loss streak"""
        trades = self._load_trades()
        if not trades:
            return {'type': 'none', 'count': 0}
        
        # Sort by timestamp
        trades = sorted(trades, key=lambda t: t.get('timestamp_close', ''), reverse=True)
        
        if not trades:
            return {'type': 'none', 'count': 0}
        
        # Determine streak
        first_result = trades[0].get('pnl_abs', 0) > 0
        streak_type = 'win' if first_result else 'loss'
        streak_count = 0
        
        for trade in trades:
            is_win = trade.get('pnl_abs', 0) > 0
            if (streak_type == 'win' and is_win) or (streak_type == 'loss' and not is_win):
                streak_count += 1
            else:
                break
        
        return {'type': streak_type, 'count': streak_count}
    
    def get_weekly_stats(self) -> Dict:
        """Get this week's statistics"""
        today = datetime.now(timezone.utc).date()
        week_start = today - timedelta(days=today.weekday())
        trades = self._load_trades()
        
        week_trades = [t for t in trades if self._get_trade_date(t) >= week_start]
        
        if not week_trades:
            return {'trades': 0, 'pnl': 0.0, 'win_rate': 0.0}
        
        wins = sum(1 for t in week_trades if t.get('pnl_abs', 0) > 0)
        pnl = sum(t.get('pnl_abs', 0) for t in week_trades)
        
        return {
            'trades': len(week_trades),
            'pnl': pnl,
            'win_rate': wins / len(week_trades) * 100 if week_trades else 0
        }
    
    def _load_trades(self) -> List[Dict]:
        """Load trades from file"""
        trades = []
        if self.trades_path.exists():
            try:
                with open(self.trades_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            trades.append(json.loads(line))
            except Exception as e:
                logger.error(f"Error loading trades: {e}")
        return trades
    
    def _get_trade_date(self, trade: Dict):
        """Get date from trade"""
        ts = trade.get('timestamp_close', trade.get('_logged_at', ''))
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.date()
            except:
                pass
        return None


class EnhancedTelegramBot:
    """
    Enhanced Telegram Bot with two-way communication.
    
    Features:
    - Command handling
    - Notes storage
    - Reminders
    - Hourly updates
    - Performance tracking
    """
    
    def __init__(self):
        # Get config
        self.bot_token = getattr(config, 'TELEGRAM_BOT_TOKEN', '') if config else ''
        self.chat_id = getattr(config, 'TELEGRAM_CHAT_ID', '') if config else ''
        self.enabled = getattr(config, 'TELEGRAM_ENABLED', False) if config else False
        
        if not self.bot_token or not self.chat_id:
            self.enabled = False
            logger.warning("⚠️ Telegram bot disabled - missing credentials")
            return
        
        # API URLs
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self.send_url = f"{self.api_base}/sendMessage"
        self.updates_url = f"{self.api_base}/getUpdates"
        
        # Components
        self.notes = NotesStorage()
        self.performance = PerformanceTracker()
        
        # State
        self.last_update_id = 0
        self.running = False
        self._listener_thread = None
        self._scheduler_thread = None
        self._last_hourly_update = None
        
        # Commands
        self.commands = {
            '/note': self._handle_note,
            '/notes': self._handle_notes_list,
            '/remind': self._handle_remind,
            '/status': self._handle_status,
            '/stats': self._handle_stats,
            '/pnl': self._handle_pnl,
            '/health': self._handle_health,
            '/help': self._handle_help,
            '/streak': self._handle_streak,
            '/clear': self._handle_clear_note,
        }
        
        logger.info("✅ EnhancedTelegramBot initialized")
    
    def start(self):
        """Start the bot listener and scheduler"""
        if not self.enabled:
            return
        
        self.running = True
        
        # Start listener thread
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()
        
        # Start scheduler thread (for reminders and hourly updates)
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info("🚀 Telegram bot started - listening for commands")
        
        # Send startup message
        self.send_message("""
🤖 <b>SUPEQUANT BOT ONLINE</b>
<i>Boss Shamil, I'm ready for commands!</i>

Type /help to see what I can do.
        """.strip())
    
    def stop(self):
        """Stop the bot"""
        self.running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("🛑 Telegram bot stopped")
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message"""
        if not self.enabled:
            return False
        
        try:
            response = requests.post(self.send_url, json={
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }, timeout=10)
            return response.status_code == 200 and response.json().get('ok')
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    def _listen_loop(self):
        """Main loop to listen for commands"""
        while self.running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._process_update(update)
            except Exception as e:
                logger.error(f"Error in listener loop: {e}")
            time.sleep(2)  # Poll every 2 seconds
    
    def _scheduler_loop(self):
        """Loop for scheduled tasks (reminders, hourly updates)"""
        while self.running:
            try:
                # Check reminders
                self._check_reminders()
                
                # Check note reminders
                self._check_note_reminders()
                
                # Hourly update
                self._check_hourly_update()
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
            time.sleep(30)  # Check every 30 seconds
    
    def _get_updates(self) -> List[Dict]:
        """Get new updates from Telegram"""
        try:
            response = requests.get(self.updates_url, params={
                'offset': self.last_update_id + 1,
                'timeout': 10
            }, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    updates = data.get('result', [])
                    if updates:
                        self.last_update_id = updates[-1]['update_id']
                    return updates
        except Exception as e:
            logger.debug(f"Error getting updates: {e}")
        return []
    
    def _process_update(self, update: Dict):
        """Process a single update"""
        message = update.get('message', {})
        text = message.get('text', '').strip()
        chat_id = message.get('chat', {}).get('id')
        
        # Only respond to configured chat
        if str(chat_id) != str(self.chat_id):
            return
        
        if not text:
            return
        
        # Parse command
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Handle command
        if command in self.commands:
            try:
                self.commands[command](args)
            except Exception as e:
                logger.error(f"Error handling command {command}: {e}")
                self.send_message(f"❌ Error: {str(e)}")
        elif text.startswith('/'):
            self.send_message(f"❓ Unknown command: {command}\nType /help for available commands.")
    
    # =========================================================================
    # COMMAND HANDLERS
    # =========================================================================
    
    def _handle_note(self, args: str):
        """Save a note"""
        if not args:
            self.send_message("📝 Usage: /note <your idea here>\n\nExample: /note Add trailing stop feature #feature")
            return
        
        # Check for reminder syntax: /note 2h Remember to check this
        reminder_minutes = None
        if args[0].isdigit():
            parts = args.split(maxsplit=1)
            time_str = parts[0].lower()
            if time_str.endswith('h'):
                reminder_minutes = int(time_str[:-1]) * 60
                args = parts[1] if len(parts) > 1 else ""
            elif time_str.endswith('m'):
                reminder_minutes = int(time_str[:-1])
                args = parts[1] if len(parts) > 1 else ""
            elif time_str.endswith('d'):
                reminder_minutes = int(time_str[:-1]) * 60 * 24
                args = parts[1] if len(parts) > 1 else ""
        
        note = self.notes.add_note(args, reminder_minutes)
        
        reminder_text = ""
        if reminder_minutes:
            reminder_text = f"\n⏰ Reminder set for {reminder_minutes // 60}h {reminder_minutes % 60}m"
        
        tags_text = ""
        if note.tags:
            tags_text = f"\n🏷️ Tags: {', '.join(note.tags)}"
        
        self.send_message(f"""
✅ <b>NOTE SAVED</b> (#{note.id})

{note.text}{tags_text}{reminder_text}
        """.strip())
    
    def _handle_notes_list(self, args: str):
        """List notes"""
        limit = 10
        if args.isdigit():
            limit = int(args)
        
        notes = self.notes.get_notes(limit)
        
        if not notes:
            self.send_message("📝 No notes yet. Save one with /note <your idea>")
            return
        
        lines = ["📝 <b>YOUR NOTES</b>\n"]
        for note in notes:
            created = datetime.fromisoformat(note.created_at.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - created
            if age.days > 0:
                age_str = f"{age.days}d ago"
            elif age.seconds > 3600:
                age_str = f"{age.seconds // 3600}h ago"
            else:
                age_str = f"{age.seconds // 60}m ago"
            
            reminder_icon = "⏰" if note.reminder_at and not note.reminded else ""
            lines.append(f"<b>#{note.id}</b> ({age_str}) {reminder_icon}\n{note.text[:100]}{'...' if len(note.text) > 100 else ''}\n")
        
        lines.append("\n<i>Delete with /clear [id]</i>")
        self.send_message("\n".join(lines))
    
    def _handle_clear_note(self, args: str):
        """Delete a note"""
        if not args or not args.isdigit():
            self.send_message("Usage: /clear <note_id>")
            return
        
        note_id = int(args)
        if self.notes.delete_note(note_id):
            self.send_message(f"🗑️ Note #{note_id} deleted")
        else:
            self.send_message(f"❌ Note #{note_id} not found")
    
    def _handle_remind(self, args: str):
        """Set a reminder"""
        if not args:
            self.send_message("""
⏰ <b>REMINDER USAGE</b>

/remind 30m Check the trade
/remind 2h Review strategy
/remind 1d Weekly review

Or save a note with reminder:
/note 2h Check if this setup worked
            """.strip())
            return
        
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self.send_message("Usage: /remind <time> <message>")
            return
        
        time_str = parts[0].lower()
        message = parts[1]
        
        # Parse time
        minutes = 0
        if time_str.endswith('m'):
            minutes = int(time_str[:-1])
        elif time_str.endswith('h'):
            minutes = int(time_str[:-1]) * 60
        elif time_str.endswith('d'):
            minutes = int(time_str[:-1]) * 60 * 24
        else:
            self.send_message("Invalid time format. Use: 30m, 2h, 1d")
            return
        
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        reminder = self.notes.add_reminder(message, remind_at)
        
        self.send_message(f"""
⏰ <b>REMINDER SET</b>

{message}

Will remind you in {minutes // 60}h {minutes % 60}m
        """.strip())
    
    def _handle_status(self, args: str):
        """Quick system status"""
        today = self.performance.get_today_stats()
        streak = self.performance.get_streak()
        
        streak_emoji = "🔥" if streak['type'] == 'win' else "❄️" if streak['type'] == 'loss' else "➖"
        streak_text = f"{streak['count']} {streak['type']}s" if streak['count'] > 0 else "No streak"
        
        pnl_emoji = "📈" if today['pnl'] >= 0 else "📉"
        
        self.send_message(f"""
📊 <b>SYSTEM STATUS</b>

<b>Today:</b>
  Trades: {today['trades']}
  Wins: {today['wins']} | Losses: {today['losses']}
  {pnl_emoji} PnL: ${today['pnl']:+.2f}
  Win Rate: {today['win_rate']:.0f}%

<b>Streak:</b> {streak_emoji} {streak_text}

<b>System:</b> ✅ Running
<b>Mode:</b> {'LIVE' if not getattr(config, 'OKX_SIMULATED', True) else 'PAPER'}
        """.strip())
    
    def _handle_stats(self, args: str):
        """Detailed statistics"""
        today = self.performance.get_today_stats()
        week = self.performance.get_weekly_stats()
        streak = self.performance.get_streak()
        
        self.send_message(f"""
📈 <b>TRADING STATISTICS</b>

<b>Today:</b>
  Trades: {today['trades']} | WR: {today['win_rate']:.0f}%
  PnL: ${today['pnl']:+.2f}

<b>This Week:</b>
  Trades: {week['trades']} | WR: {week['win_rate']:.0f}%
  PnL: ${week['pnl']:+.2f}

<b>Current Streak:</b>
  {streak['count']} consecutive {streak['type']}{'s' if streak['count'] != 1 else ''}
        """.strip())
    
    def _handle_pnl(self, args: str):
        """Today's PnL"""
        today = self.performance.get_today_stats()
        
        if today['pnl'] > 0:
            emoji = "🎉"
            msg = "Boss Shamil, we're up today!"
        elif today['pnl'] < 0:
            emoji = "😤"
            msg = "Small setback, we'll bounce back!"
        else:
            emoji = "➖"
            msg = "Flat so far today."
        
        self.send_message(f"""
{emoji} <b>TODAY'S PnL</b>

<i>{msg}</i>

<b>PnL:</b> ${today['pnl']:+.2f}
<b>Trades:</b> {today['trades']} ({today['wins']}W/{today['losses']}L)
        """.strip())
    
    def _handle_streak(self, args: str):
        """Show current streak with motivation"""
        streak = self.performance.get_streak()
        
        if streak['type'] == 'win':
            if streak['count'] >= 5:
                msg = f"🔥🔥🔥 LEGENDARY! {streak['count']} wins in a row! Keep it going Boss!"
            elif streak['count'] >= 3:
                msg = f"🔥 HOT STREAK! {streak['count']} consecutive wins!"
            else:
                msg = f"✅ {streak['count']} win{'s' if streak['count'] > 1 else ''} in a row. Nice!"
        elif streak['type'] == 'loss':
            if streak['count'] >= 3:
                msg = f"❄️ {streak['count']} losses. Stay disciplined, the edge is still there."
            else:
                msg = f"Small setback: {streak['count']} loss{'es' if streak['count'] > 1 else ''}. Next one's ours!"
        else:
            msg = "No trades yet. Let's get one!"
        
        self.send_message(f"""
🎯 <b>STREAK STATUS</b>

{msg}
        """.strip())
    
    def _handle_health(self, args: str):
        """System health check"""
        # Check various components
        checks = []
        
        # Config check
        if config:
            checks.append("✅ Config loaded")
        else:
            checks.append("❌ Config missing")
        
        # Trading mode
        mode = "PAPER" if getattr(config, 'OKX_SIMULATED', True) else "LIVE"
        checks.append(f"✅ Mode: {mode}")
        
        # Notes storage
        try:
            _ = self.notes.get_notes(1)
            checks.append("✅ Notes storage OK")
        except:
            checks.append("❌ Notes storage error")
        
        # Performance tracker
        try:
            _ = self.performance.get_today_stats()
            checks.append("✅ Performance tracker OK")
        except:
            checks.append("❌ Performance tracker error")
        
        self.send_message(f"""
🏥 <b>SYSTEM HEALTH</b>

{chr(10).join(checks)}

<b>Uptime:</b> Running
<b>Last Check:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC
        """.strip())
    
    def _handle_help(self, args: str):
        """Show help"""
        self.send_message("""
🤖 <b>SUPEQUANT BOT COMMANDS</b>

<b>📝 Notes:</b>
/note &lt;text&gt; - Save an idea
/note 2h &lt;text&gt; - Save with 2h reminder
/notes - List your notes
/clear &lt;id&gt; - Delete a note

<b>⏰ Reminders:</b>
/remind 30m &lt;text&gt; - Remind in 30 min
/remind 2h &lt;text&gt; - Remind in 2 hours

<b>📊 Trading:</b>
/status - Quick system status
/stats - Detailed statistics
/pnl - Today's PnL
/streak - Win/loss streak

<b>🔧 System:</b>
/health - System health check
/help - This message

<i>Boss Shamil, I'm always here for you! 🚀</i>
        """.strip())
    
    # =========================================================================
    # SCHEDULED TASKS
    # =========================================================================
    
    def _check_reminders(self):
        """Check and send due reminders"""
        due = self.notes.get_due_reminders()
        for reminder in due:
            self.send_message(f"""
⏰ <b>REMINDER</b>

{reminder.text}

<i>Set {self._format_age(reminder.created_at)} ago</i>
            """.strip())
            self.notes.mark_reminder_sent(reminder.id)
    
    def _check_note_reminders(self):
        """Check and send due note reminders"""
        due = self.notes.get_notes_needing_reminder()
        for note in due:
            self.send_message(f"""
📝 <b>NOTE REMINDER</b>

{note.text}

<i>Note #{note.id} from {self._format_age(note.created_at)} ago</i>
            """.strip())
            self.notes.mark_note_reminded(note.id)
    
    def _check_hourly_update(self):
        """Send hourly status update"""
        now = datetime.now(timezone.utc)
        
        # Check if we should send (every hour, on the hour)
        if self._last_hourly_update:
            time_since = now - self._last_hourly_update
            if time_since.total_seconds() < 3500:  # ~58 minutes
                return
        
        # Only send if it's close to the hour
        if now.minute > 5:
            return
        
        self._last_hourly_update = now
        
        # Get stats
        today = self.performance.get_today_stats()
        streak = self.performance.get_streak()
        
        pnl_emoji = "📈" if today['pnl'] >= 0 else "📉"
        streak_text = f"{streak['count']} {streak['type']}{'s' if streak['count'] > 1 else ''}" if streak['count'] > 0 else "No streak"
        
        self.send_message(f"""
🕐 <b>HOURLY UPDATE</b>

{pnl_emoji} <b>Today's PnL:</b> ${today['pnl']:+.2f}
📊 <b>Trades:</b> {today['trades']} ({today['win_rate']:.0f}% WR)
🎯 <b>Streak:</b> {streak_text}

<i>{now.strftime('%I:%M %p')} UTC</i>
        """.strip())
    
    def _format_age(self, iso_timestamp: str) -> str:
        """Format timestamp as age string"""
        try:
            dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - dt
            if age.days > 0:
                return f"{age.days}d"
            elif age.seconds > 3600:
                return f"{age.seconds // 3600}h"
            else:
                return f"{age.seconds // 60}m"
        except:
            return "?"
    
    # =========================================================================
    # SPECIAL NOTIFICATIONS
    # =========================================================================
    
    def send_trade_opened(self, trade_data: Dict):
        """Send enhanced trade opened notification"""
        direction = trade_data.get('direction', 'unknown').upper()
        entry = trade_data.get('entry_price', 0)
        stop = trade_data.get('stop_loss', 0)
        tp1 = trade_data.get('tp1_price', 0)
        strategy = trade_data.get('strategy', 'unknown')
        
        direction_emoji = "🟢" if direction == "LONG" else "🔴"
        
        # Get streak for context
        streak = self.performance.get_streak()
        streak_note = ""
        if streak['type'] == 'win' and streak['count'] >= 3:
            streak_note = f"\n🔥 <i>On a {streak['count']} win streak!</i>"
        
        self.send_message(f"""
{direction_emoji} <b>TRADE OPENED</b>
<i>Boss Shamil, we're in!</i>

<b>Direction:</b> {direction}
<b>Entry:</b> ${entry:.2f}
<b>Stop:</b> ${stop:.2f}
<b>TP1:</b> ${tp1:.2f}
<b>Strategy:</b> {strategy}{streak_note}
        """.strip())
    
    def send_trade_closed(self, trade_data: Dict):
        """Send enhanced trade closed notification"""
        pnl = trade_data.get('pnl_abs', 0)
        reason = trade_data.get('close_reason', 'unknown').upper()
        
        if pnl > 0:
            emoji = "💰"
            msg = "Another W in the books!"
        elif pnl < 0:
            emoji = "📉"
            msg = "Small loss, risk managed."
        else:
            emoji = "➖"
            msg = "Broke even on this one."
        
        # Get updated streak
        streak = self.performance.get_streak()
        today = self.performance.get_today_stats()
        
        self.send_message(f"""
{emoji} <b>TRADE CLOSED</b>
<i>{msg}</i>

<b>Result:</b> ${pnl:+.2f}
<b>Reason:</b> {reason}

<b>Today:</b> ${today['pnl']:+.2f} ({today['trades']} trades)
<b>Streak:</b> {streak['count']} {streak['type']}{'s' if streak['count'] > 1 else ''}
        """.strip())
    
    def send_daily_summary(self):
        """Send end-of-day summary"""
        today = self.performance.get_today_stats()
        week = self.performance.get_weekly_stats()
        
        if today['pnl'] > 0:
            emoji = "🎉"
            msg = "Great day Boss Shamil!"
        elif today['pnl'] < 0:
            emoji = "💪"
            msg = "We'll get 'em tomorrow!"
        else:
            emoji = "➖"
            msg = "Flat day. Rest up for tomorrow."
        
        self.send_message(f"""
{emoji} <b>DAILY SUMMARY</b>
<i>{msg}</i>

<b>Today:</b>
  Trades: {today['trades']}
  Win Rate: {today['win_rate']:.0f}%
  PnL: ${today['pnl']:+.2f}

<b>This Week:</b>
  Trades: {week['trades']}
  PnL: ${week['pnl']:+.2f}

<i>See you tomorrow! 🌙</i>
        """.strip())


# Singleton instance
_bot_instance: Optional[EnhancedTelegramBot] = None


def get_bot() -> EnhancedTelegramBot:
    """Get or create the bot instance"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = EnhancedTelegramBot()
    return _bot_instance


def start_bot():
    """Start the bot (call from main.py)"""
    bot = get_bot()
    bot.start()
    return bot


def stop_bot():
    """Stop the bot"""
    global _bot_instance
    if _bot_instance:
        _bot_instance.stop()
        _bot_instance = None


# CLI for testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n🤖 Starting Enhanced Telegram Bot...\n")
    
    bot = start_bot()
    
    try:
        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping bot...")
        stop_bot()
        print("✅ Bot stopped")
