# -*- coding: utf-8 -*-
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
import sys
import signal
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Ensure project root is on path so config/agents resolve when run standalone
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import config
try:
    import config
except ImportError:
    config = None

# Import ChatGPT agent for enhanced AI chat
try:
    from agents.chatgpt_agent import ChatGPTAgent
    CHATGPT_AVAILABLE = True
except ImportError:
    CHATGPT_AVAILABLE = False
    logger.warning("ChatGPT agent not available for AI chat")

# TradeJournal (runs/) - canonical live trade log
try:
    from utils.trade_journal import TradeJournal
    TRADE_JOURNAL_AVAILABLE = True
except ImportError:
    TRADE_JOURNAL_AVAILABLE = False

# Analytics helpers
try:
    from utils.scope_parser import parse_scope
    from utils.analytics_responder import analyze_trades
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False


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
        # Use TradeJournal to load live trades (runs/ directory)
        # Falls back to old paper_trades.jsonl if TradeJournal fails
        try:
            from utils.trade_journal import TradeJournal
            self.trade_journal = TradeJournal(base_path="runs", enabled=True)
            self.use_journal = True
        except Exception as e:
            logger.warning(f"Could not initialize TradeJournal, using file-based: {e}")
            self.trade_journal = None
            self.use_journal = False
        
        # Keep old path for backward compatibility
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
        """Load trades from TradeJournal (runs/ directory) or fallback to file"""
        trades = []
        
        # Try TradeJournal first (live trades from runs/ directory)
        if self.use_journal and self.trade_journal:
            try:
                trades = self.trade_journal.get_recent_trades(days=90)  # Last 90 days
                if trades:
                    logger.debug(f"Loaded {len(trades)} trades from TradeJournal")
                    return trades
            except Exception as e:
                logger.warning(f"Error loading from TradeJournal: {e}, falling back to file")
        
        # Fallback to old paper_trades.jsonl file (backward compatibility)
        if self.trades_path.exists():
            try:
                with open(self.trades_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            trades.append(json.loads(line))
                if trades:
                    logger.debug(f"Loaded {len(trades)} trades from {self.trades_path}")
            except Exception as e:
                logger.error(f"Error loading trades from file: {e}")
        
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
        self._lock_path = Path("telegram_bot.lock")
        self._pid = os.getpid()
        self._last_details: Optional[str] = None
        
        # AI Chat agent (ChatGPT only; no Claude fallback)
        self.chatgpt_agent = None
        if CHATGPT_AVAILABLE:
            try:
                self.chatgpt_agent = ChatGPTAgent(timeout_seconds=10.0)
                logger.info("🤖 ChatGPT enabled for enhanced Telegram bot responses")
            except Exception as e:
                logger.warning(f"Could not initialize ChatGPT agent: {e}")
        
        # Natural language triggers (conversational) - narrowed to reduce false note prompts
        self.triggers = {
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
            # note/remind only when explicitly asked
            'notes': self._show_notes_menu,
            'note': self._show_notes_menu,
            'remind': self._show_reminder_menu,
            'reminder': self._show_reminder_menu,
        }
        
        # Question patterns that trigger AI chat
        self.ai_question_patterns = [
            'why did we lose',
            'why did we win',
            'why loss',
            'why won',
            'how is the market',
            'market outlook',
            'when will we trade',
            'when is the next trade',
            'trade coming',
            'will we trade',
            'why no trades',
            'no signals',
            'what happened',
            'explain',
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

        # Single-instance lock
        if self._lock_path.exists():
            logger.warning("⚠️ Telegram bot lock found - another instance may be running")
        try:
            self._lock_path.write_text(str(self._pid))
        except Exception as e:
            logger.warning(f"Could not write lock file: {e}")
        
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
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except Exception:
            pass
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
        
        # If nothing matched, treat it as a generic AI question (no more forced notes)
        self._ask_ai_generic(text)
    
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
        regime_on = getattr(config, 'LIVE_REGIME_ADAPTIVE', False)
        regime = "ON" if regime_on else "OFF"
        last_trade_line = ""
        alerts_line = ""
        try:
            from utils.system_health import get_health_checker
            checker = get_health_checker()
            report = checker.get_health_report()
            staleness = report.get('data_staleness', {}) or {}
            alerts = report.get('alerts', []) or []
            if staleness.get('last_trade_age_hours') is not None:
                last_trade_line = f"  Last trade: {staleness['last_trade_age_hours']:.1f}h ago\n"
            if alerts:
                alerts_line = f"  Alerts: {', '.join(alerts[:3])}\n"
        except Exception:
            pass
        
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
<b>Mode:</b> {mode} | <b>Regime:</b> {regime} | <b>System:</b> ✅ Running
{last_trade_line}{alerts_line}
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
        mode = "PAPER" if getattr(config, 'OKX_SIMULATED', True) else "LIVE"
        try:
            from utils.system_health import get_health_checker
            checker = get_health_checker()
            report = checker.get_health_report()
            staleness = report.get('data_staleness', {}) or {}
            uptime = report.get('uptime', 'N/A')
            overall = report.get('overall_status', 'unknown').upper()
            error_rate = report.get('error_rate_per_hour', 0)
            alerts = report.get('alerts', []) or []
            last_trade_age = staleness.get('last_trade_age_hours')

            staleness_line = f"Last trade: {last_trade_age:.1f}h ago" if last_trade_age is not None else "Last trade: n/a"
            alerts_line = f"Alerts: {', '.join(alerts[:3])}" if alerts else "Alerts: none"

            self.send_message(f"""
🏥 <b>SYSTEM HEALTH</b>

• Status: {overall}
• Uptime: {uptime}
• Error rate: {error_rate}/hr
• {staleness_line}
• {alerts_line}
• Mode: {mode}
            """.strip())
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            self.send_message(f"""
🏥 <b>SYSTEM HEALTH</b>

• Status: UNKNOWN (health checker error)
• Mode: {mode}
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

<b>Ask Me Anything:</b>
• "Why did we lose?"
• "Why did we win?"
• "How is the market?"
• "When is the next trade?"
• "Analyze the market"

<b>Commands (Power Users):</b>
/note text - Quick save
/notes - List all
/remind 2h text - Set reminder
/ask question - Ask AI anything
/market - Market analysis
/status /stats /pnl /streak

<i>Boss Shamil, I'm always here! 🚀</i>
        """.strip())
    
    # =========================================================================
    # AI CHAT HANDLERS
    # =========================================================================
    
    def _handle_ai_question(self, question: str):
        """Handle natural language AI questions"""
        question_lower = question.lower()

        # Priority: system/health, then trading Qs, then generic AI
        if any(w in question_lower for w in ['errors', 'issues', 'problem', 'wrong', 'health']):
            self._handle_health()
        elif 'details' in question_lower:
            self._handle_details_request()
        elif any(w in question_lower for w in ['why did we lose', 'why loss', 'why did it lose']):
            self._analyze_last_trade('loss', question)
        elif any(w in question_lower for w in ['why did we win', 'why won', 'why did it win']):
            self._analyze_last_trade('win', question)
        elif any(w in question_lower for w in ['market', 'outlook', 'looking']):
            self._get_market_outlook(question)
        elif any(w in question_lower for w in ['next trade', 'trade coming', 'when will', 'will we trade', 'no trades', 'no signals']):
            self._get_trade_forecast(question)
        elif any(w in question_lower for w in ['what happened', 'explain']):
            self._analyze_last_trade(None, question)
        else:
            self._ask_ai_generic(question)
    
    def _handle_ask_command(self, args: str):
        """Handle /ask command"""
        if not args:
            self.send_message("""
🤖 <b>ASK ME ANYTHING</b>

Just type your question, for example:
• Why did we lose the last trade?
• How is the market looking?
• When will we get a trade?
• Analyze my performance
            """.strip())
            return
        
        self._ask_ai_generic(args)
    
    def _handle_market_question(self, args: str = None):
        """Handle /market command"""
        self._get_market_outlook(args or "How is the market looking?")
    
    def _analyze_last_trade(self, trade_type: str = None, question: str = ""):
        """Analyze why the last trade won or lost"""
        self.send_message("🔍 <i>Analyzing... one moment Boss</i>")
        
        # Get recent trades
        trades = self._get_recent_trades(limit=50)
        
        if not trades:
            self.send_message("""
📊 <b>NO RECENT TRADES</b>

Boss, I don't see any recent trades to analyze.
The system is scanning for opportunities.
            """.strip())
            return
        
        # Filter by type if specified
        if trade_type == 'loss':
            filtered = [t for t in trades if t.get('pnl_abs', 0) < 0]
            if not filtered:
                self.send_message("✅ No recent losses to analyze, Boss!")
                return
            trade_to_analyze = filtered[0]
        elif trade_type == 'win':
            filtered = [t for t in trades if t.get('pnl_abs', 0) > 0]
            if not filtered:
                self.send_message("📊 No recent wins to analyze yet.")
                return
            trade_to_analyze = filtered[0]
        else:
            trade_to_analyze = trades[0]
        
        # Scope-aware analysis (summary + details)
        analysis_scope = parse_scope(question) if ANALYTICS_AVAILABLE else None
        if ANALYTICS_AVAILABLE:
            analysis = analyze_trades(trades, scope=analysis_scope)
            self._last_details = analysis.details
            self.send_message(analysis.summary + ("\n\n<i>Say \"details\" for full breakdown.</i>" if analysis.details else ""))
            return

        # Build trade context
        direction = trade_to_analyze.get('direction', 'unknown').upper()
        entry = trade_to_analyze.get('entry_price', 0)
        exit_price = trade_to_analyze.get('exit_price', 0)
        pnl = trade_to_analyze.get('pnl_abs', 0)
        reason = trade_to_analyze.get('close_reason', 'unknown')
        strategy = trade_to_analyze.get('strategy', 'unknown')
        
        result_emoji = "💰" if pnl > 0 else "📉"
        result_text = "WIN" if pnl > 0 else "LOSS"
        
        # Try to get AI analysis (ChatGPT only)
        if self.chatgpt_agent:
            try:
                analysis = self._get_ai_trade_analysis(trade_to_analyze, question)
                if analysis:
                    self.send_message(f"""
{result_emoji} <b>TRADE ANALYSIS - {result_text}</b>

<b>Trade Details:</b>
• Direction: {direction}
• Entry: ${entry:.2f}
• Exit: ${exit_price:.2f}
• PnL: ${pnl:+.2f}
• Reason: {reason}
• Strategy: {strategy}

<b>🤖 AI Analysis:</b>
{analysis}
                    """.strip())
                    return
            except Exception as e:
                logger.error(f"AI analysis failed: {e}")
        self._send_basic_trade_analysis(trade_to_analyze)

    def _handle_details_request(self):
        """Send last stored details if available."""
        if self._last_details:
            self.send_message(f"🧠 <b>DETAILS</b>\n\n{self._last_details}")
        else:
            self.send_message("ℹ️ No details available yet. Ask an analysis question first (e.g., \"why did we lose last 10 trades?\").")
    
    def _send_basic_trade_analysis(self, trade: Dict):
        """Send basic trade analysis without AI"""
        direction = trade.get('direction', 'unknown').upper()
        entry = trade.get('entry_price', 0)
        exit_price = trade.get('exit_price', 0)
        pnl = trade.get('pnl_abs', 0)
        reason = trade.get('close_reason', 'unknown')
        
        result_emoji = "💰" if pnl > 0 else "📉"
        
        if pnl > 0:
            msg = "The trade hit take profit! Great setup."
        elif reason == 'stop_loss':
            msg = "Stop loss was hit. Risk was managed properly - that's the discipline!"
        else:
            msg = f"Trade closed due to: {reason}"
        
        self.send_message(f"""
{result_emoji} <b>TRADE ANALYSIS</b>

<b>Trade:</b> {direction}
<b>Entry:</b> ${entry:.2f} → Exit: ${exit_price:.2f}
<b>PnL:</b> ${pnl:+.2f}
<b>Closed:</b> {reason}

<b>Analysis:</b>
{msg}
        """.strip())
    
    def _get_market_outlook(self, question: str = ""):
        """Get AI market analysis"""
        self.send_message("🔍 <i>Analyzing market conditions...</i>")
        
        # Get current market data
        market_data = self._get_current_market_data()
        
        if self.chatgpt_agent:
            try:
                analysis = self._get_ai_market_analysis(market_data, question)
                if analysis:
                    self.send_message(f"""
📊 <b>MARKET ANALYSIS</b>

{analysis}

<i>This is AI-generated analysis. Always verify before trading.</i>
                    """.strip())
                    return
            except Exception as e:
                logger.error(f"AI market analysis failed: {e}")
        self._send_basic_market_outlook(market_data)
    
    def _send_basic_market_outlook(self, market_data: Dict):
        """Send basic market outlook without AI"""
        trend = market_data.get('trend', 'unknown')
        volatility = market_data.get('volatility', 'medium')
        
        self.send_message(f"""
📊 <b>MARKET OUTLOOK</b>

<b>Trend:</b> {trend.upper()}
<b>Volatility:</b> {volatility.upper()}

<i>For detailed AI analysis, ensure Claude API is configured.</i>
        """.strip())
    
    def _get_trade_forecast(self, question: str = ""):
        """Forecast when next trade might happen"""
        self.send_message("🔮 <i>Checking trading conditions...</i>")
        
        # Get stats
        today = self.performance.get_today_stats()
        all_time = self.performance.get_all_time_stats()
        market_data = self._get_current_market_data()
        
        if self.chatgpt_agent:
            try:
                forecast = self._get_ai_trade_forecast(today, all_time, market_data, question)
                if forecast:
                    self.send_message(f"""
🔮 <b>TRADE FORECAST</b>

{forecast}

<b>Current Status:</b>
• Trades Today: {today['trades']}
• Win Rate: {today['win_rate']:.0f}%
• System: ✅ Scanning

<i>The system trades when high-quality setups appear. Patience pays!</i>
                    """.strip())
                    return
            except Exception as e:
                logger.error(f"AI forecast failed: {e}")
        self._send_basic_forecast(today, market_data)
    
    def _send_basic_forecast(self, today: Dict, market_data: Dict):
        """Send basic forecast without AI"""
        trend = market_data.get('trend', 'unknown')
        
        self.send_message(f"""
🔮 <b>TRADE FORECAST</b>

<b>Status:</b> System actively scanning
<b>Trades Today:</b> {today['trades']}
<b>Market Trend:</b> {trend}

The system waits for high-quality setups. It uses:
• V1 Prediction System (the profitable one!)
• 4H HTF Filter
• Adaptive Thresholds
• Multiple strategy confirmation

<i>Stay patient Boss - quality over quantity!</i>
        """.strip())
    
    def _ask_ai_generic(self, question: str):
        """Handle generic AI questions with ChatGPT primary, Claude fallback"""
        if not self.chatgpt_agent:
            self.send_message("""
🤖 <b>AI CHAT UNAVAILABLE</b>

AI APIs are not configured. To enable:
1. Set OPENAI_API_KEY in .env
2. Restart the bot

<i>Basic commands still work: /status, /stats, /pnl</i>
            """.strip())
            return
        
        try:
            context = self._build_system_context()

            system_prompt = """You are Boss Shamil's personal trading AI assistant.
Keep it tight: 3-4 bullets, <60 words, no preamble.
Use the provided context (mode, PnL, streak, alerts, regime, recent trades).
If no trades, say when the last trade was and whether open positions exist.
Offer concrete next checks (errors/regime/market) but do not suggest executing trades.
Never claim you executed or changed anything."""
            
            messages = [
                {'role': 'user', 'content': f"{context}\n\nBoss Shamil asks: {question}"}
            ]
            
            response_content = None
            ai_source = "ChatGPT"
            response_content = self._call_ai_chatgpt(messages, system_prompt, max_tokens=400)
            
            if response_content:
                response_content = self._truncate_ai_response(response_content)
                self.send_message(f"""
🤖 <b>AI RESPONSE</b> <i>({ai_source})</i>

{response_content}
                """.strip())
            else:
                raise Exception("Both AI agents failed")
            
        except Exception as e:
            logger.error(f"Generic AI question failed: {e}")
            self.send_message(f"""
❌ <b>AI ERROR</b>

Couldn't process that question. Try:
• "Why did we lose?"
• "How is the market?"
• "When is the next trade?"

Or use /status for a quick update.
            """.strip())

    def _truncate_ai_response(self, text: str, max_words: int = 70, max_chars: int = 650) -> str:
        """Trim AI output to keep responses concise and readable."""
        cleaned = " ".join(text.strip().split())
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rsplit(" ", 1)[0] + "…"

        words = cleaned.split()
        if len(words) > max_words:
            cleaned = " ".join(words[:max_words]).rstrip() + "…"
        return cleaned

    def _build_system_context(self) -> str:
        """Build a compact system context for AI responses (read-only)."""
        today = self.performance.get_today_stats()
        streak = self.performance.get_streak()
        weekly = self.performance.get_weekly_stats()
        all_time = self.performance.get_all_time_stats()
        recent_trades = self._get_recent_trades(limit=5)
        mode = "PAPER" if getattr(config, 'OKX_SIMULATED', True) else "LIVE"
        regime_on = getattr(config, 'LIVE_REGIME_ADAPTIVE', False)

        last_trade = ""
        alerts = ""
        alert_count = 0
        try:
            from utils.system_health import get_health_checker
            checker = get_health_checker()
            report = checker.get_health_report()
            staleness = report.get('data_staleness', {})
            alert_list = report.get('alerts', []) or []
            alert_count = len(alert_list)
            if staleness.get('last_trade_age_hours') is not None:
                last_trade = f"- Last trade: {staleness['last_trade_age_hours']:.1f}h ago\n"
            if alert_list:
                alerts = f"- Alerts: {', '.join(alert_list[:3])}\n"
        except Exception:
            pass

        # Recent trade summary line items
        recent_lines = []
        for t in recent_trades:
            pnl = t.get('pnl_abs', t.get('pnl', 0))
            pnl_pct = t.get('pnl_pct', t.get('pnl_percent', 0))
            direction = t.get('direction', t.get('side', 'unknown')).upper()
            strat = t.get('strategy', t.get('strategy_name', 'unknown'))
            recent_lines.append(f"  • {strat} {direction} PnL ${pnl:+.2f} ({pnl_pct:+.1f}%)")
        recent_block = "\n".join(recent_lines) if recent_lines else "  • No recent trades"

        context = (
            "Trading System Context:\n"
            f"- Mode: {mode} | Regime: {'ON' if regime_on else 'OFF'}\n"
            f"- Today: {today['trades']} trades ({today['wins']}W/{today['losses']}L) PnL ${today['pnl']:+.2f} | Win {today['win_rate']:.0f}%\n"
            f"- Weekly: {weekly.get('trades',0)} trades PnL ${weekly.get('pnl',0):+.2f} | Win {weekly.get('win_rate',0):.0f}%\n"
            f"- All-time: {all_time.get('trades',0)} trades PnL ${all_time.get('pnl',0):+.2f} | Win {all_time.get('win_rate',0):.0f}%\n"
            f"- Streak: {streak['count']} {streak['type']}\n"
            f"{last_trade}"
            f"{alerts}"
            f"- Alerts count: {alert_count}\n"
            "Recent trades:\n"
            f"{recent_block}\n"
        )
        return context

    def _call_ai_chatgpt(self, messages: list, system: str, max_tokens: int = 400) -> Optional[str]:
        """Call ChatGPT agent and return content or None."""
        if not self.chatgpt_agent:
            return None
        try:
            response = self.chatgpt_agent._call_chatgpt(messages, system=system, max_tokens=max_tokens)
            return response.get('content', '')
        except Exception as e:
            logger.error(f"ChatGPT call failed: {e}")
            return None
    
    def _get_ai_trade_analysis(self, trade: Dict, question: str) -> Optional[str]:
        """Get AI analysis of a specific trade (ChatGPT only)"""
        direction = trade.get('direction', 'unknown')
        entry = trade.get('entry_price', 0)
        exit_price = trade.get('exit_price', 0)
        pnl = trade.get('pnl_abs', 0)
        reason = trade.get('close_reason', 'unknown')
        strategy = trade.get('strategy', 'unknown')
        
        prompt = f"""Analyze this trade for Boss Shamil:
- Direction: {direction}
- Entry: ${entry:.2f}
- Exit: ${exit_price:.2f}
- PnL: ${pnl:+.2f}
- Close reason: {reason}
- Strategy: {strategy}

Question: {question if question else 'Why did this trade result in a ' + ('win' if pnl > 0 else 'loss') + '?'}

Provide a brief (2-3 sentences) analysis focusing on:
1. What happened
2. Why it happened
3. What to learn from it

Be encouraging and supportive. Call him Boss."""
        
        system = "You are a supportive trading coach analyzing trades. Be concise and actionable."
        messages = [{'role': 'user', 'content': prompt}]
        
        return self._call_ai_chatgpt(messages, system, max_tokens=300)
    
    def _get_ai_market_analysis(self, market_data: Dict, question: str) -> Optional[str]:
        """Get AI market analysis (ChatGPT only)"""
        prompt = f"""Analyze current market conditions for SOL-USDT:
- Trend: {market_data.get('trend', 'unknown')}
- Volatility: {market_data.get('volatility', 'unknown')}
- Recent price action: {'bullish' if market_data.get('bullish', False) else 'bearish' if market_data.get('bearish', False) else 'mixed'}

Question: {question if question else 'How is the market looking?'}

Provide a brief market outlook (3-4 sentences) focusing on:
1. Current market condition
2. What to expect
3. Trading recommendation

Call him Boss. Be direct and actionable."""
        
        system = "You are a market analyst providing concise market updates. Focus on actionable insights."
        messages = [{'role': 'user', 'content': prompt}]
        
        return self._call_ai_chatgpt(messages, system, max_tokens=300)
    
    def _get_ai_trade_forecast(self, today: Dict, all_time: Dict, market_data: Dict, question: str) -> Optional[str]:
        """Get AI trade forecast (ChatGPT only)"""
        prompt = f"""Boss Shamil wants to know about upcoming trades.

Current status:
- Trades today: {today['trades']}
- Today's win rate: {today['win_rate']:.0f}%
- All-time trades: {all_time['trades']}
- All-time win rate: {all_time['win_rate']:.0f}%
- Market trend: {market_data.get('trend', 'unknown')}
- System: V1 Prediction (the profitable one with $8k backtest profit)

Question: {question}

Provide a brief forecast (2-3 sentences) about:
1. When a trade might come
2. What the system is looking for
3. Encouragement to be patient

Be supportive and call him Boss."""
        
        system = "You are a trading assistant helping set expectations about trade timing. Be encouraging but realistic."
        messages = [{'role': 'user', 'content': prompt}]
        
        return self._call_ai_chatgpt(messages, system, max_tokens=250)
    
    def _get_recent_trades(self, limit: int = 5) -> List[Dict]:
        """Get recent trades from TradeJournal (preferred) with log fallback"""
        trades: List[Dict] = []

        if TRADE_JOURNAL_AVAILABLE:
            try:
                base = getattr(config, 'TRADE_JOURNAL_PATH', 'runs')
                j = TradeJournal(base_path=base, enabled=True)
                trades = j.get_recent_trades(days=90)[:limit]
            except Exception as e:
                logger.error(f"TradeJournal read failed: {e}")
                trades = []

        if not trades:
            paths = [
                Path(os.path.join(os.path.dirname(__file__), '..', 'logs', 'paper_trades.jsonl')),
                Path(os.path.join(os.path.dirname(__file__), '..', 'logs', 'trade_journal.jsonl'))
            ]
            for p in paths:
                if p.exists():
                    try:
                        with open(p, 'r') as f:
                            for line in f:
                                if line.strip():
                                    trades.append(json.loads(line))
                    except Exception as e:
                        logger.error(f"Error reading {p}: {e}")

        trades.sort(key=lambda t: t.get('timestamp_close', t.get('_logged_at', '')), reverse=True)
        return trades[:limit]
    
    def _get_current_market_data(self) -> Dict:
        """Get current market data for analysis"""
        # Basic market data - in a real implementation, this would
        # pull from the market data feed
        try:
            # Try to get from live system if available
            import sys
            if 'main' in sys.modules:
                main_module = sys.modules['main']
                if hasattr(main_module, 'elite_system') and main_module.elite_system:
                    market_state = main_module.elite_system.market_feed.get_market_state()
                    if market_state:
                        tf_15m = market_state.get('timeframes', {}).get('15m', {})
                        trend_data = tf_15m.get('trend', {})
                        return {
                            'trend': trend_data.get('trend_direction', 'unknown'),
                            'volatility': 'high' if trend_data.get('trend_strength', 0) > 0.5 else 'medium',
                            'bullish': trend_data.get('trend_direction') == 'bullish',
                            'bearish': trend_data.get('trend_direction') == 'bearish'
                        }
        except Exception as e:
            logger.debug(f"Could not get live market data: {e}")
        
        # Return default data
        return {
            'trend': 'scanning',
            'volatility': 'medium',
            'bullish': False,
            'bearish': False
        }
    
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
