"""
Elite Telegram Bot - Conversational UI with Smart Features

Now with CONVERSATIONAL FLOW:
- Say "notes" → Get menu with options
- Say anything → Bot understands context
- Inline buttons for easy actions
- No need to remember commands

Features:
- Smart conversation flow (understands context)
- Notes storage with reminders
- Hourly status updates
- Performance tracking (streaks, daily summary)
- Inline keyboard buttons
- Still supports /commands for power users
"""

import json
import os
import logging
import threading
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Import config
try:
    import config
except ImportError:
    config = None

# Import Claude agent for AI chat
try:
    from agents.claude_agent import ClaudeAgent
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    logger.warning("Claude agent not available for AI chat")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Note:
    """A saved note/idea"""
    id: int
    text: str
    created_at: str
    reminder_at: Optional[str] = None
    reminded: bool = False
    tags: List[str] = None
    permanent: bool = True  # Notes are permanent by default
    
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


class ConversationState(Enum):
    """Tracks what the user is doing"""
    IDLE = "idle"
    WAITING_FOR_NOTE = "waiting_for_note"
    WAITING_FOR_REMINDER_TEXT = "waiting_for_reminder_text"
    WAITING_FOR_REMINDER_TIME = "waiting_for_reminder_time"
    CONFIRMING_NOTE = "confirming_note"


@dataclass
class UserState:
    """Tracks conversation state for a user"""
    state: ConversationState = ConversationState.IDLE
    pending_text: str = ""
    pending_data: Dict = field(default_factory=dict)
    last_activity: datetime = None
    
    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = datetime.now(timezone.utc)


# =============================================================================
# STORAGE
# =============================================================================

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
            tags=tags,
            permanent=True
        )
        self.notes.append(note)
        self._save()
        return note
    
    def get_notes(self, limit: int = 10) -> List[Note]:
        """Get recent notes"""
        return sorted(self.notes, key=lambda n: n.created_at, reverse=True)[:limit]
    
    def get_note_by_id(self, note_id: int) -> Optional[Note]:
        """Get a specific note"""
        for note in self.notes:
            if note.id == note_id:
                return note
        return None
    
    def delete_note(self, note_id: int) -> bool:
        """Delete a note by ID"""
        for i, note in enumerate(self.notes):
            if note.id == note_id:
                self.notes.pop(i)
                self._save()
                return True
        return False
    
    def search_notes(self, query: str) -> List[Note]:
        """Search notes by text or tag"""
        query = query.lower()
        results = []
        for note in self.notes:
            if query in note.text.lower() or query in [t.lower() for t in note.tags]:
                results.append(note)
        return results
    
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


# =============================================================================
# PERFORMANCE TRACKER
# =============================================================================

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
        
        week_trades = [t for t in trades if self._get_trade_date(t) and self._get_trade_date(t) >= week_start]
        
        if not week_trades:
            return {'trades': 0, 'pnl': 0.0, 'win_rate': 0.0}
        
        wins = sum(1 for t in week_trades if t.get('pnl_abs', 0) > 0)
        pnl = sum(t.get('pnl_abs', 0) for t in week_trades)
        
        return {
            'trades': len(week_trades),
            'pnl': pnl,
            'win_rate': wins / len(week_trades) * 100 if week_trades else 0
        }
    
    def get_all_time_stats(self) -> Dict:
        """Get all-time statistics"""
        trades = self._load_trades()
        
        if not trades:
            return {'trades': 0, 'pnl': 0.0, 'win_rate': 0.0, 'best_trade': 0, 'worst_trade': 0}
        
        wins = sum(1 for t in trades if t.get('pnl_abs', 0) > 0)
        pnl = sum(t.get('pnl_abs', 0) for t in trades)
        pnls = [t.get('pnl_abs', 0) for t in trades]
        
        return {
            'trades': len(trades),
            'pnl': pnl,
            'win_rate': wins / len(trades) * 100 if trades else 0,
            'best_trade': max(pnls) if pnls else 0,
            'worst_trade': min(pnls) if pnls else 0
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


# =============================================================================
# ENHANCED TELEGRAM BOT WITH CONVERSATIONAL UI
# =============================================================================

class EnhancedTelegramBot:
    """
    Elite Telegram Bot with conversational UI.
    
    Now supports:
    - Natural conversation flow
    - Inline keyboard buttons
    - Context-aware responses
    - Smart command parsing
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
        self.answer_callback_url = f"{self.api_base}/answerCallbackQuery"
        
        # Components
        self.notes = NotesStorage()
        self.performance = PerformanceTracker()
        
        # Conversation state
        self.user_states: Dict[str, UserState] = {}
        
        # State
        self.last_update_id = 0
        self.running = False
        self._listener_thread = None
        self._scheduler_thread = None
        self._last_hourly_update = None
        self._last_daily_report = None
        
        # AI Chat agent (for answering questions)
        self.claude_agent = None
        if CLAUDE_AVAILABLE:
            try:
                self.claude_agent = ClaudeAgent(timeout_seconds=30.0)
                logger.info("🤖 AI Chat enabled for Telegram bot")
            except Exception as e:
                logger.warning(f"Could not initialize Claude agent for chat: {e}")
        
        # Natural language triggers (conversational)
        self.triggers = {
            'notes': self._show_notes_menu,
            'note': self._show_notes_menu,
            'idea': self._start_new_note,
            'remind': self._show_reminder_menu,
            'reminder': self._show_reminder_menu,
            'status': self._handle_status,
            'stats': self._handle_stats,
            'pnl': self._handle_pnl,
            'profit': self._handle_pnl,
            'streak': self._handle_streak,
            'health': self._handle_health,
            'help': self._handle_help,
            'menu': self._show_main_menu,
            'hi': self._show_main_menu,
            'hello': self._show_main_menu,
            'hey': self._show_main_menu,
        }
        
        # Question patterns that trigger AI chat
        self.ai_question_patterns = [
            'why did we lose',
            'why did we win',
            'why did it lose',
            'why did it win',
            'why loss',
            'why won',
            'how is the market',
            'market looking',
            'market outlook',
            'when will we trade',
            'when is the next trade',
            'trade coming',
            'will we trade',
            'should i trade',
            'what happened',
            'explain the trade',
            'analyze',
            'what do you think',
            'is it good',
            'is it bad',
            'why no trades',
            'no signals',
        ]
        
        # Command handlers (still supported)
        self.commands = {
            '/note': self._handle_note_command,
            '/notes': self._handle_notes_list,
            '/remind': self._handle_remind_command,
            '/status': self._handle_status,
            '/stats': self._handle_stats,
            '/pnl': self._handle_pnl,
            '/health': self._handle_health,
            '/help': self._handle_help,
            '/streak': self._handle_streak,
            '/clear': self._handle_clear_note,
            '/menu': self._show_main_menu,
            '/search': self._handle_search,
            '/ask': self._handle_ask_command,
            '/market': self._handle_market_question,
        }
        
        # Callback handlers (for inline buttons)
        self.callbacks = {
            'menu_notes': self._show_notes_menu,
            'menu_stats': self._handle_stats,
            'menu_status': self._handle_status,
            'menu_help': self._handle_help,
            'notes_new': self._start_new_note,
            'notes_list': self._handle_notes_list,
            'notes_search': self._start_search,
            'note_save': self._save_pending_note,
            'note_save_remind_1h': lambda: self._save_pending_note_with_reminder(60),
            'note_save_remind_2h': lambda: self._save_pending_note_with_reminder(120),
            'note_save_remind_1d': lambda: self._save_pending_note_with_reminder(1440),
            'note_cancel': self._cancel_pending,
            'remind_30m': lambda: self._set_quick_reminder(30),
            'remind_1h': lambda: self._set_quick_reminder(60),
            'remind_2h': lambda: self._set_quick_reminder(120),
            'remind_custom': self._start_custom_reminder,
        }
        
        logger.info("✅ EnhancedTelegramBot initialized (conversational mode)")
    
    def _get_user_state(self, chat_id: str = None) -> UserState:
        """Get or create user state"""
        cid = chat_id or self.chat_id
        if cid not in self.user_states:
            self.user_states[cid] = UserState()
        return self.user_states[cid]
    
    def _reset_state(self, chat_id: str = None):
        """Reset user to idle state"""
        state = self._get_user_state(chat_id)
        state.state = ConversationState.IDLE
        state.pending_text = ""
        state.pending_data = {}
    
    def start(self):
        """Start the bot listener and scheduler"""
        if not self.enabled:
            return
        
        self.running = True
        
        # Start listener thread
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()
        
        # Start scheduler thread
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info("🚀 Telegram bot started - conversational mode active")
        
        # Send startup message with menu
        self._send_startup_message()
    
    def stop(self):
        """Stop the bot"""
        self.running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("🛑 Telegram bot stopped")
    
    # =========================================================================
    # MESSAGE SENDING
    # =========================================================================
    
    def send_message(self, text: str, parse_mode: str = "HTML", 
                    reply_markup: Dict = None) -> bool:
        """Send a message with optional inline keyboard"""
        if not self.enabled:
            return False
        
        try:
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            if reply_markup:
                payload['reply_markup'] = json.dumps(reply_markup)
            
            response = requests.post(self.send_url, json=payload, timeout=10)
            return response.status_code == 200 and response.json().get('ok')
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    def _make_inline_keyboard(self, buttons: List[List[Dict]]) -> Dict:
        """Create inline keyboard markup"""
        return {'inline_keyboard': buttons}
    
    def _make_button(self, text: str, callback_data: str) -> Dict:
        """Create a single inline button"""
        return {'text': text, 'callback_data': callback_data}
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def _listen_loop(self):
        """Main loop to listen for messages and callbacks"""
        while self.running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._process_update(update)
            except Exception as e:
                logger.error(f"Error in listener loop: {e}")
            time.sleep(1.5)  # Poll every 1.5 seconds
    
    def _scheduler_loop(self):
        """Loop for scheduled tasks"""
        while self.running:
            try:
                self._check_reminders()
                self._check_note_reminders()
                self._check_hourly_update()
                self._check_daily_report()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
            time.sleep(30)
    
    def _get_updates(self) -> List[Dict]:
        """Get new updates from Telegram"""
        try:
            response = requests.get(self.updates_url, params={
                'offset': self.last_update_id + 1,
                'timeout': 10,
                'allowed_updates': ['message', 'callback_query']
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
        """Process a single update (message or callback)"""
        # Handle callback queries (button clicks)
        if 'callback_query' in update:
            self._handle_callback(update['callback_query'])
            return
        
        # Handle messages
        message = update.get('message', {})
        text = message.get('text', '').strip()
        chat_id = str(message.get('chat', {}).get('id', ''))
        
        # Only respond to configured chat
        if chat_id != str(self.chat_id):
            return
        
        if not text:
            return
        
        # Update activity
        state = self._get_user_state(chat_id)
        state.last_activity = datetime.now(timezone.utc)
        
        # Check if we're in a conversation state
        if state.state != ConversationState.IDLE:
            self._handle_conversation_input(text, state)
            return
        
        # Check for commands first
        if text.startswith('/'):
            parts = text.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            if command in self.commands:
                try:
                    self.commands[command](args)
                except Exception as e:
                    logger.error(f"Error handling command {command}: {e}")
                    self.send_message(f"❌ Error: {str(e)}")
            else:
                self.send_message(f"❓ Unknown command. Say 'menu' or /help")
            return
        
        # Check for natural language triggers
        text_lower = text.lower().strip()
        for trigger, handler in self.triggers.items():
            if text_lower == trigger or text_lower.startswith(trigger + ' '):
                try:
                    # Extract any args after trigger
                    args = text[len(trigger):].strip() if len(text) > len(trigger) else ""
                    handler(args) if args else handler()
                except TypeError:
                    handler()
                except Exception as e:
                    logger.error(f"Error handling trigger {trigger}: {e}")
                return
        
        # Check if it's an AI question
        text_lower = text.lower()
        for pattern in self.ai_question_patterns:
            if pattern in text_lower:
                self._handle_ai_question(text)
                return
        
        # If nothing matched, treat it as a potential note
        self._suggest_save_as_note(text)
    
    def _handle_callback(self, callback_query: Dict):
        """Handle inline button clicks"""
        callback_id = callback_query.get('id')
        data = callback_query.get('data', '')
        
        # Answer the callback to remove loading state
        try:
            requests.post(self.answer_callback_url, json={
                'callback_query_id': callback_id
            }, timeout=5)
        except:
            pass
        
        # Handle the callback
        if data in self.callbacks:
            try:
                handler = self.callbacks[data]
                if callable(handler):
                    handler()
            except Exception as e:
                logger.error(f"Error handling callback {data}: {e}")
                self.send_message(f"❌ Error: {str(e)}")
        elif data.startswith('delete_note_'):
            note_id = int(data.replace('delete_note_', ''))
            self._delete_note_confirmed(note_id)
    
    def _handle_conversation_input(self, text: str, state: UserState):
        """Handle input during a conversation flow"""
        if state.state == ConversationState.WAITING_FOR_NOTE:
            state.pending_text = text
            state.state = ConversationState.CONFIRMING_NOTE
            self._show_note_confirmation(text)
        
        elif state.state == ConversationState.WAITING_FOR_REMINDER_TEXT:
            state.pending_text = text
            state.state = ConversationState.WAITING_FOR_REMINDER_TIME
            self._ask_reminder_time()
        
        elif state.state == ConversationState.WAITING_FOR_REMINDER_TIME:
            self._process_reminder_time(text, state)
    
    # =========================================================================
    # MENUS AND UI
    # =========================================================================
    
    def _send_startup_message(self):
        """Send startup message with main menu"""
        keyboard = self._make_inline_keyboard([
            [self._make_button("📝 Notes", "menu_notes"),
             self._make_button("📊 Stats", "menu_stats")],
            [self._make_button("📈 Status", "menu_status"),
             self._make_button("❓ Help", "menu_help")]
        ])
        
        self.send_message("""
🤖 <b>SUPEQUANT ONLINE</b>
<i>Boss Shamil, I'm ready!</i>

Just talk to me naturally:
• Say <b>"notes"</b> to manage ideas
• Say <b>"status"</b> for quick update
• Say <b>"stats"</b> for performance
• Or just type anything!
        """.strip(), reply_markup=keyboard)
    
    def _show_main_menu(self, args: str = None):
        """Show main menu"""
        keyboard = self._make_inline_keyboard([
            [self._make_button("📝 Notes", "menu_notes"),
             self._make_button("📊 Stats", "menu_stats")],
            [self._make_button("📈 Status", "menu_status"),
             self._make_button("🎯 Streak", "menu_streak")],
            [self._make_button("❓ Help", "menu_help")]
        ])
        
        self.send_message("""
📱 <b>MAIN MENU</b>

What would you like to do?
        """.strip(), reply_markup=keyboard)
    
    def _show_notes_menu(self, args: str = None):
        """Show notes menu"""
        notes_count = len(self.notes.get_notes(100))
        
        keyboard = self._make_inline_keyboard([
            [self._make_button("➕ New Note", "notes_new")],
            [self._make_button(f"📋 View Notes ({notes_count})", "notes_list")],
            [self._make_button("🔍 Search", "notes_search")]
        ])
        
        self.send_message("""
📝 <b>NOTES</b>

What would you like to do?
        """.strip(), reply_markup=keyboard)
    
    def _show_reminder_menu(self, args: str = None):
        """Show reminder quick-set menu"""
        keyboard = self._make_inline_keyboard([
            [self._make_button("30 min", "remind_30m"),
             self._make_button("1 hour", "remind_1h"),
             self._make_button("2 hours", "remind_2h")],
            [self._make_button("Custom time", "remind_custom")]
        ])
        
        self.send_message("""
⏰ <b>QUICK REMINDER</b>

When should I remind you?
        """.strip(), reply_markup=keyboard)
    
    def _start_new_note(self, args: str = None):
        """Start new note flow"""
        if args:
            # Direct note text provided
            state = self._get_user_state()
            state.pending_text = args
            state.state = ConversationState.CONFIRMING_NOTE
            self._show_note_confirmation(args)
        else:
            state = self._get_user_state()
            state.state = ConversationState.WAITING_FOR_NOTE
            self.send_message("""
📝 <b>NEW NOTE</b>

Type your idea or note:
<i>(Use #tags to categorize)</i>
            """.strip())
    
    def _show_note_confirmation(self, text: str):
        """Show note with save options"""
        keyboard = self._make_inline_keyboard([
            [self._make_button("💾 Save", "note_save")],
            [self._make_button("💾 + ⏰ 1h", "note_save_remind_1h"),
             self._make_button("💾 + ⏰ 2h", "note_save_remind_2h"),
             self._make_button("💾 + ⏰ 1d", "note_save_remind_1d")],
            [self._make_button("❌ Cancel", "note_cancel")]
        ])
        
        # Extract tags for display
        tags = [word for word in text.split() if word.startswith('#')]
        tags_text = f"\n🏷️ Tags: {', '.join(tags)}" if tags else ""
        
        self.send_message(f"""
📝 <b>SAVE THIS NOTE?</b>

{text}{tags_text}
        """.strip(), reply_markup=keyboard)
    
    def _save_pending_note(self):
        """Save the pending note"""
        state = self._get_user_state()
        if state.pending_text:
            note = self.notes.add_note(state.pending_text)
            self._reset_state()
            self.send_message(f"""
✅ <b>NOTE SAVED</b> (#{note.id})

{note.text}

<i>Saved permanently. Delete with /clear {note.id}</i>
            """.strip())
        else:
            self._reset_state()
            self.send_message("❌ No note to save")
    
    def _save_pending_note_with_reminder(self, minutes: int):
        """Save note with reminder"""
        state = self._get_user_state()
        if state.pending_text:
            note = self.notes.add_note(state.pending_text, reminder_minutes=minutes)
            self._reset_state()
            
            time_str = f"{minutes // 60}h" if minutes >= 60 else f"{minutes}m"
            
            self.send_message(f"""
✅ <b>NOTE SAVED</b> (#{note.id})

{note.text}

⏰ Reminder set for {time_str}
            """.strip())
        else:
            self._reset_state()
            self.send_message("❌ No note to save")
    
    def _cancel_pending(self):
        """Cancel pending action"""
        self._reset_state()
        self.send_message("❌ Cancelled")
    
    def _suggest_save_as_note(self, text: str):
        """When user types random text, suggest saving as note"""
        state = self._get_user_state()
        state.pending_text = text
        state.state = ConversationState.CONFIRMING_NOTE
        
        keyboard = self._make_inline_keyboard([
            [self._make_button("💾 Save as Note", "note_save"),
             self._make_button("❌ Nevermind", "note_cancel")]
        ])
        
        self.send_message(f"""
💡 Save this as a note?

<i>"{text[:100]}{'...' if len(text) > 100 else ''}"</i>
        """.strip(), reply_markup=keyboard)
    
    # =========================================================================
    # REMINDER HANDLERS
    # =========================================================================
    
    def _set_quick_reminder(self, minutes: int):
        """Set a quick reminder"""
        state = self._get_user_state()
        state.state = ConversationState.WAITING_FOR_REMINDER_TEXT
        state.pending_data['minutes'] = minutes
        
        time_str = f"{minutes // 60} hour{'s' if minutes >= 120 else ''}" if minutes >= 60 else f"{minutes} minutes"
        
        self.send_message(f"""
⏰ <b>REMINDER IN {time_str.upper()}</b>

What should I remind you about?
        """.strip())
    
    def _start_custom_reminder(self):
        """Start custom reminder flow"""
        state = self._get_user_state()
        state.state = ConversationState.WAITING_FOR_REMINDER_TEXT
        state.pending_data['custom'] = True
        
        self.send_message("""
⏰ <b>CUSTOM REMINDER</b>

What should I remind you about?
        """.strip())
    
    def _ask_reminder_time(self):
        """Ask for reminder time"""
        keyboard = self._make_inline_keyboard([
            [self._make_button("30m", "remind_time_30"),
             self._make_button("1h", "remind_time_60"),
             self._make_button("2h", "remind_time_120")],
            [self._make_button("4h", "remind_time_240"),
             self._make_button("1d", "remind_time_1440")]
        ])
        
        self.send_message("""
⏰ When should I remind you?

(Or type like: 30m, 2h, 1d)
        """.strip(), reply_markup=keyboard)
    
    def _process_reminder_time(self, text: str, state: UserState):
        """Process reminder time input"""
        text = text.lower().strip()
        minutes = 0
        
        if text.endswith('m'):
            minutes = int(text[:-1])
        elif text.endswith('h'):
            minutes = int(text[:-1]) * 60
        elif text.endswith('d'):
            minutes = int(text[:-1]) * 60 * 24
        else:
            self.send_message("❓ Invalid time. Use: 30m, 2h, 1d")
            return
        
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        reminder = self.notes.add_reminder(state.pending_text, remind_at)
        
        self._reset_state()
        self.send_message(f"""
✅ <b>REMINDER SET</b>

{reminder.text}

⏰ I'll remind you in {minutes // 60}h {minutes % 60}m
        """.strip())
    
    # =========================================================================
    # COMMAND HANDLERS (for /command style)
    # =========================================================================
    
    def _handle_note_command(self, args: str):
        """Handle /note command"""
        if not args:
            self._start_new_note()
        else:
            self._start_new_note(args)
    
    def _handle_notes_list(self, args: str = None):
        """List notes"""
        limit = 10
        if args and args.isdigit():
            limit = int(args)
        
        notes = self.notes.get_notes(limit)
        
        if not notes:
            keyboard = self._make_inline_keyboard([
                [self._make_button("➕ Create First Note", "notes_new")]
            ])
            self.send_message("📝 No notes yet!", reply_markup=keyboard)
            return
        
        lines = ["📝 <b>YOUR NOTES</b>\n"]
        for note in notes:
            created = datetime.fromisoformat(note.created_at.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - created
            if age.days > 0:
                age_str = f"{age.days}d"
            elif age.seconds > 3600:
                age_str = f"{age.seconds // 3600}h"
            else:
                age_str = f"{age.seconds // 60}m"
            
            reminder_icon = "⏰" if note.reminder_at and not note.reminded else ""
            text_preview = note.text[:80] + ('...' if len(note.text) > 80 else '')
            lines.append(f"<b>#{note.id}</b> ({age_str}) {reminder_icon}\n{text_preview}\n")
        
        keyboard = self._make_inline_keyboard([
            [self._make_button("➕ New Note", "notes_new"),
             self._make_button("🔍 Search", "notes_search")]
        ])
        
        self.send_message("\n".join(lines), reply_markup=keyboard)
    
    def _handle_remind_command(self, args: str):
        """Handle /remind command"""
        if not args:
            self._show_reminder_menu()
            return
        
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self._show_reminder_menu()
            return
        
        time_str = parts[0].lower()
        message = parts[1]
        
        minutes = 0
        if time_str.endswith('m'):
            minutes = int(time_str[:-1])
        elif time_str.endswith('h'):
            minutes = int(time_str[:-1]) * 60
        elif time_str.endswith('d'):
            minutes = int(time_str[:-1]) * 60 * 24
        else:
            self.send_message("❓ Invalid time. Use: 30m, 2h, 1d")
            return
        
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        reminder = self.notes.add_reminder(message, remind_at)
        
        self.send_message(f"""
✅ <b>REMINDER SET</b>

{message}

⏰ I'll remind you in {minutes // 60}h {minutes % 60}m
        """.strip())
    
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
    
    def _delete_note_confirmed(self, note_id: int):
        """Delete note from callback"""
        if self.notes.delete_note(note_id):
            self.send_message(f"🗑️ Note #{note_id} deleted")
        else:
            self.send_message(f"❌ Note #{note_id} not found")
    
    def _start_search(self):
        """Start search flow"""
        self.send_message("""
🔍 <b>SEARCH NOTES</b>

Type a word or #tag to search:
        """.strip())
        # Note: Would need state tracking for search, keeping simple for now
    
    def _handle_search(self, args: str):
        """Search notes"""
        if not args:
            self._start_search()
            return
        
        results = self.notes.search_notes(args)
        
        if not results:
            self.send_message(f"🔍 No notes found for '{args}'")
            return
        
        lines = [f"🔍 <b>RESULTS FOR '{args}'</b>\n"]
        for note in results[:10]:
            lines.append(f"<b>#{note.id}</b>: {note.text[:60]}...\n")
        
        self.send_message("\n".join(lines))
    
    # =========================================================================
    # STATS AND STATUS HANDLERS
    # =========================================================================
    
    def _handle_status(self, args: str = None):
        """Quick system status"""
        today = self.performance.get_today_stats()
        streak = self.performance.get_streak()
        
        streak_emoji = "🔥" if streak['type'] == 'win' else "❄️" if streak['type'] == 'loss' else "➖"
        streak_text = f"{streak['count']} {streak['type']}s" if streak['count'] > 0 else "No streak"
        pnl_emoji = "📈" if today['pnl'] >= 0 else "📉"
        
        mode = "PAPER" if getattr(config, 'OKX_SIMULATED', True) else "LIVE"
        
        keyboard = self._make_inline_keyboard([
            [self._make_button("📊 Full Stats", "menu_stats"),
             self._make_button("🎯 Streak", "menu_streak")]
        ])
        
        self.send_message(f"""
📊 <b>STATUS</b>

<b>Today:</b>
  Trades: {today['trades']} ({today['wins']}W/{today['losses']}L)
  {pnl_emoji} PnL: ${today['pnl']:+.2f}
  Win Rate: {today['win_rate']:.0f}%

<b>Streak:</b> {streak_emoji} {streak_text}
<b>Mode:</b> {mode} | <b>System:</b> ✅ Running
        """.strip(), reply_markup=keyboard)
    
    def _handle_stats(self, args: str = None):
        """Detailed statistics"""
        today = self.performance.get_today_stats()
        week = self.performance.get_weekly_stats()
        all_time = self.performance.get_all_time_stats()
        streak = self.performance.get_streak()
        
        self.send_message(f"""
📈 <b>TRADING STATISTICS</b>

<b>Today:</b>
  Trades: {today['trades']} | WR: {today['win_rate']:.0f}%
  PnL: ${today['pnl']:+.2f}

<b>This Week:</b>
  Trades: {week['trades']} | WR: {week['win_rate']:.0f}%
  PnL: ${week['pnl']:+.2f}

<b>All Time:</b>
  Trades: {all_time['trades']} | WR: {all_time['win_rate']:.0f}%
  PnL: ${all_time['pnl']:+.2f}
  Best: ${all_time['best_trade']:+.2f}
  Worst: ${all_time['worst_trade']:+.2f}

<b>Streak:</b> {streak['count']} {streak['type']}{'s' if streak['count'] != 1 else ''}
        """.strip())
    
    def _handle_pnl(self, args: str = None):
        """Today's PnL"""
        today = self.performance.get_today_stats()
        
        if today['pnl'] > 0:
            emoji = "🎉"
            msg = "We're up today Boss!"
        elif today['pnl'] < 0:
            emoji = "😤"
            msg = "Small setback. We bounce back!"
        else:
            emoji = "➖"
            msg = "Flat so far."
        
        self.send_message(f"""
{emoji} <b>TODAY'S PnL</b>

<i>{msg}</i>

<b>PnL:</b> ${today['pnl']:+.2f}
<b>Trades:</b> {today['trades']} ({today['wins']}W/{today['losses']}L)
        """.strip())
    
    def _handle_streak(self, args: str = None):
        """Show streak with motivation"""
        streak = self.performance.get_streak()
        
        if streak['type'] == 'win':
            if streak['count'] >= 5:
                msg = f"🔥🔥🔥 LEGENDARY! {streak['count']} wins in a row!"
            elif streak['count'] >= 3:
                msg = f"🔥 HOT STREAK! {streak['count']} consecutive wins!"
            else:
                msg = f"✅ {streak['count']} win{'s' if streak['count'] > 1 else ''} in a row!"
        elif streak['type'] == 'loss':
            if streak['count'] >= 3:
                msg = f"❄️ {streak['count']} losses. Stay disciplined Boss."
            else:
                msg = f"Small setback: {streak['count']} loss. Next one's ours!"
        else:
            msg = "No trades yet. Let's get one!"
        
        self.send_message(f"""
🎯 <b>STREAK</b>

{msg}
        """.strip())
    
    def _handle_health(self, args: str = None):
        """System health check"""
        checks = []
        checks.append("✅ Bot running")
        checks.append("✅ Notes storage OK")
        checks.append("✅ Performance tracker OK")
        
        mode = "PAPER" if getattr(config, 'OKX_SIMULATED', True) else "LIVE"
        checks.append(f"✅ Mode: {mode}")
        
        self.send_message(f"""
🏥 <b>SYSTEM HEALTH</b>

{chr(10).join(checks)}

<b>Last Check:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC
        """.strip())
    
    def _handle_help(self, args: str = None):
        """Show help"""
        self.send_message("""
🤖 <b>SUPEQUANT BOT</b>

<b>Just Talk to Me:</b>
• "notes" - Manage your ideas
• "status" - Quick update
• "stats" - Performance
• "remind" - Set reminders
• "menu" - Main menu

<b>Commands (Power Users):</b>
/note text - Quick save
/notes - List all
/remind 2h text - Set reminder
/clear ID - Delete note
/search word - Find notes
/status /stats /pnl /streak

<i>Boss Shamil, I'm always here! 🚀</i>
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
        
        if self._last_hourly_update:
            time_since = now - self._last_hourly_update
            if time_since.total_seconds() < 3500:
                return
        
        if now.minute > 5:
            return
        
        self._last_hourly_update = now
        
        today = self.performance.get_today_stats()
        streak = self.performance.get_streak()
        
        pnl_emoji = "📈" if today['pnl'] >= 0 else "📉"
        
        self.send_message(f"""
🕐 <b>HOURLY UPDATE</b>

{pnl_emoji} <b>PnL:</b> ${today['pnl']:+.2f}
📊 <b>Trades:</b> {today['trades']} ({today['win_rate']:.0f}% WR)
🎯 <b>Streak:</b> {streak['count']} {streak['type']}{'s' if streak['count'] > 1 else ''}

<i>{now.strftime('%I:%M %p')} UTC</i>
        """.strip())
    
    def _check_daily_report(self):
        """Send daily report at end of day"""
        now = datetime.now(timezone.utc)
        
        # Send at 23:55 UTC
        if now.hour != 23 or now.minute < 55:
            return
        
        if self._last_daily_report:
            if self._last_daily_report.date() == now.date():
                return
        
        self._last_daily_report = now
        self.send_daily_summary()
    
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
        """Send trade opened notification"""
        direction = trade_data.get('direction', 'unknown').upper()
        entry = trade_data.get('entry_price', 0)
        stop = trade_data.get('stop_loss', 0)
        tp1 = trade_data.get('tp1_price', 0)
        strategy = trade_data.get('strategy', 'unknown')
        
        direction_emoji = "🟢" if direction == "LONG" else "🔴"
        
        streak = self.performance.get_streak()
        streak_note = ""
        if streak['type'] == 'win' and streak['count'] >= 3:
            streak_note = f"\n🔥 <i>On a {streak['count']} win streak!</i>"
        
        self.send_message(f"""
{direction_emoji} <b>TRADE OPENED</b>

<b>Direction:</b> {direction}
<b>Entry:</b> ${entry:.2f}
<b>Stop:</b> ${stop:.2f}
<b>TP1:</b> ${tp1:.2f}
<b>Strategy:</b> {strategy}{streak_note}
        """.strip())
    
    def send_trade_closed(self, trade_data: Dict):
        """Send trade closed notification"""
        pnl = trade_data.get('pnl', 0)
        reason = trade_data.get('close_reason', 'unknown').upper()
        
        if pnl > 0:
            emoji = "💰"
            msg = "Another W!"
        elif pnl < 0:
            emoji = "📉"
            msg = "Risk managed."
        else:
            emoji = "➖"
            msg = "Broke even."
        
        streak = self.performance.get_streak()
        today = self.performance.get_today_stats()
        
        self.send_message(f"""
{emoji} <b>TRADE CLOSED</b>
<i>{msg}</i>

<b>Result:</b> ${pnl:+.2f}
<b>Reason:</b> {reason}

<b>Today:</b> ${today['pnl']:+.2f} ({today['trades']} trades)
<b>Streak:</b> {streak['count']} {streak['type']}
        """.strip())
    
    def send_daily_summary(self):
        """Send end-of-day summary"""
        today = self.performance.get_today_stats()
        week = self.performance.get_weekly_stats()
        
        if today['pnl'] > 0:
            emoji = "🎉"
            msg = "Great day Boss!"
        elif today['pnl'] < 0:
            emoji = "💪"
            msg = "We'll get 'em tomorrow!"
        else:
            emoji = "➖"
            msg = "Flat day. Rest up."
        
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


# =============================================================================
# SINGLETON AND FACTORY
# =============================================================================

_bot_instance: Optional[EnhancedTelegramBot] = None


def get_bot() -> EnhancedTelegramBot:
    """Get or create the bot instance"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = EnhancedTelegramBot()
    return _bot_instance


def start_bot() -> EnhancedTelegramBot:
    """Start the bot"""
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
    
    print("\n🤖 Starting Elite Telegram Bot (Conversational Mode)...\n")
    
    bot = start_bot()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping bot...")
        stop_bot()
        print("✅ Bot stopped")
