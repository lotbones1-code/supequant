"""
System Health Monitor - Phase 1.5 Module 1

Real-time monitoring of system health including:
- API connectivity (OKX, Telegram, Database)
- Resource usage (CPU, Memory, Disk)
- Uptime tracking
- Error rate calculation
- Alert determination

Usage:
    from utils.system_monitor import SystemMonitor
    
    monitor = SystemMonitor()
    print(monitor.generate_report())
    
    should_alert, reasons = monitor.should_alert()
    if should_alert:
        notifier.send_error(f"System alert: {', '.join(reasons)}")
"""

import os
import sys
import time
import threading
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Import psutil with graceful fallback
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

# Import TradeJournal for trading stats
try:
    from utils.trade_journal import TradeJournal
    JOURNAL_AVAILABLE = True
except ImportError:
    JOURNAL_AVAILABLE = False
    TradeJournal = None

logger = logging.getLogger(__name__)


class SystemMonitor:
    """
    System health monitoring for the SupeQuant trading system.
    
    Provides real-time health checks, resource monitoring, and
    formatted reports for operational visibility.
    
    Thread-safe for use in multi-threaded trading environments.
    """
    
    def __init__(self):
        """
        Initialize the system monitor.
        
        Sets up:
        - Start time for uptime tracking
        - Thread-safe error log
        - Health check cache
        """
        self.start_time = datetime.now(timezone.utc)
        
        # Thread-safe error logging
        self._error_log: List[Dict[str, Any]] = []
        self._error_lock = threading.Lock()
        self._max_errors = 1000
        
        # Health check cache (to avoid hammering APIs)
        self._last_health_check: Optional[Dict] = None
        self._last_health_check_time: Optional[datetime] = None
        self._health_check_cache_seconds = 30
        
        # Database path
        self._db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "trading.db"
        )
        
        # Trade journal for stats
        self._trade_journal = None
        if JOURNAL_AVAILABLE:
            try:
                self._trade_journal = TradeJournal(
                    base_path=getattr(config, 'TRADE_JOURNAL_PATH', 'runs'),
                    enabled=True
                )
            except Exception as e:
                logger.warning(f"Could not initialize TradeJournal for monitor: {e}")
        
        logger.info("✅ SystemMonitor initialized")
    
    def get_api_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Check connectivity status of all APIs.
        
        Returns:
            Dict with status for each API:
            {
                "okx": {"connected": bool, "latency_ms": float, "error": str|None},
                "telegram": {"connected": bool, "latency_ms": float, "error": str|None},
                "database": {"connected": bool, "size_kb": float, "error": str|None}
            }
        """
        status = {}
        
        # Check OKX API
        status["okx"] = self._check_okx_api()
        
        # Check Telegram API (if enabled)
        status["telegram"] = self._check_telegram_api()
        
        # Check Database
        status["database"] = self._check_database()
        
        return status
    
    def _check_okx_api(self) -> Dict[str, Any]:
        """Check OKX API connectivity."""
        try:
            # Use configured domain (us.okx.com for US accounts)
            domain = getattr(config, 'OKX_API_DOMAIN', 'www.okx.com')
            url = f"https://{domain}/api/v5/public/time"
            
            start = time.time()
            response = requests.get(url, timeout=5)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return {
                    "connected": True,
                    "latency_ms": round(latency_ms, 1),
                    "error": None
                }
            else:
                return {
                    "connected": False,
                    "latency_ms": round(latency_ms, 1),
                    "error": f"HTTP {response.status_code}"
                }
        except requests.Timeout:
            return {"connected": False, "latency_ms": 5000, "error": "Timeout"}
        except requests.ConnectionError as e:
            return {"connected": False, "latency_ms": 0, "error": "Connection failed"}
        except Exception as e:
            return {"connected": False, "latency_ms": 0, "error": str(e)[:50]}
    
    def _check_telegram_api(self) -> Dict[str, Any]:
        """Check Telegram API connectivity (if enabled)."""
        if not getattr(config, 'TELEGRAM_ENABLED', False):
            return {"connected": None, "latency_ms": 0, "error": "Disabled"}
        
        bot_token = getattr(config, 'TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            return {"connected": False, "latency_ms": 0, "error": "No token"}
        
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getMe"
            start = time.time()
            response = requests.get(url, timeout=5)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200 and response.json().get('ok'):
                return {
                    "connected": True,
                    "latency_ms": round(latency_ms, 1),
                    "error": None
                }
            else:
                return {
                    "connected": False,
                    "latency_ms": round(latency_ms, 1),
                    "error": "Invalid response"
                }
        except requests.Timeout:
            return {"connected": False, "latency_ms": 5000, "error": "Timeout"}
        except Exception as e:
            return {"connected": False, "latency_ms": 0, "error": str(e)[:50]}
    
    def _check_database(self) -> Dict[str, Any]:
        """Check database connectivity and size."""
        try:
            if os.path.exists(self._db_path):
                size_bytes = os.path.getsize(self._db_path)
                size_kb = size_bytes / 1024
                
                # Try to open file to verify it's readable
                with open(self._db_path, 'rb') as f:
                    f.read(1)  # Read 1 byte to verify access
                
                return {
                    "connected": True,
                    "size_kb": round(size_kb, 1),
                    "error": None
                }
            else:
                return {
                    "connected": False,
                    "size_kb": 0,
                    "error": "File not found"
                }
        except PermissionError:
            return {"connected": False, "size_kb": 0, "error": "Permission denied"}
        except Exception as e:
            return {"connected": False, "size_kb": 0, "error": str(e)[:50]}
    
    def get_resource_usage(self) -> Dict[str, Any]:
        """
        Get current system resource usage.
        
        Returns:
            Dict with resource metrics:
            {
                "cpu_percent": float,
                "memory_percent": float,
                "memory_used_mb": float,
                "disk_percent": float,
                "disk_free_gb": float,
                "db_size_mb": float
            }
        """
        if not PSUTIL_AVAILABLE:
            return {
                "cpu_percent": 0,
                "memory_percent": 0,
                "memory_used_mb": 0,
                "disk_percent": 0,
                "disk_free_gb": 0,
                "db_size_mb": 0,
                "error": "psutil not installed"
            }
        
        try:
            # CPU usage (non-blocking, uses last interval)
            cpu_percent = psutil.cpu_percent(interval=None)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            
            # Disk usage (root partition)
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_free_gb = disk.free / (1024 * 1024 * 1024)
            
            # Database size
            db_size_mb = 0
            if os.path.exists(self._db_path):
                db_size_mb = os.path.getsize(self._db_path) / (1024 * 1024)
            
            return {
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory_percent, 1),
                "memory_used_mb": round(memory_used_mb, 1),
                "disk_percent": round(disk_percent, 1),
                "disk_free_gb": round(disk_free_gb, 1),
                "db_size_mb": round(db_size_mb, 2)
            }
        except Exception as e:
            logger.error(f"Error getting resource usage: {e}")
            return {
                "cpu_percent": 0,
                "memory_percent": 0,
                "memory_used_mb": 0,
                "disk_percent": 0,
                "disk_free_gb": 0,
                "db_size_mb": 0,
                "error": str(e)[:50]
            }
    
    def get_uptime(self) -> Dict[str, Any]:
        """
        Get system uptime since monitor start.
        
        Returns:
            Dict with uptime info:
            {
                "seconds": float,
                "readable": "2d 5h 30m"
            }
        """
        now = datetime.now(timezone.utc)
        delta = now - self.start_time
        total_seconds = delta.total_seconds()
        
        # Format readable string
        days = int(total_seconds // 86400)
        hours = int((total_seconds % 86400) // 3600)
        minutes = int((total_seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        
        readable = " ".join(parts)
        
        return {
            "seconds": round(total_seconds, 1),
            "readable": readable,
            "started_at": self.start_time.isoformat()
        }
    
    def log_error(self, error_msg: str, context: Optional[Dict] = None) -> None:
        """
        Log an error for tracking.
        
        Thread-safe. Keeps last 1000 errors.
        
        Args:
            error_msg: Error message
            context: Optional context dict
        """
        with self._error_lock:
            error_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": error_msg,
                "context": context or {}
            }
            
            self._error_log.append(error_entry)
            
            # Keep only last N errors
            if len(self._error_log) > self._max_errors:
                self._error_log = self._error_log[-self._max_errors:]
    
    def get_error_rate(self, window_hours: float = 1.0) -> float:
        """
        Calculate error rate within time window.
        
        Args:
            window_hours: Time window in hours
            
        Returns:
            Errors per hour
        """
        with self._error_lock:
            if not self._error_log:
                return 0.0
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
            cutoff_iso = cutoff.isoformat()
            
            # Count errors in window
            errors_in_window = sum(
                1 for e in self._error_log
                if e["timestamp"] >= cutoff_iso
            )
            
            # Calculate rate per hour
            return round(errors_in_window / window_hours, 2)
    
    def get_recent_errors(self, count: int = 5) -> List[Dict]:
        """
        Get most recent errors.
        
        Args:
            count: Number of errors to return
            
        Returns:
            List of recent error entries
        """
        with self._error_lock:
            return self._error_log[-count:] if self._error_log else []
    
    def get_trading_stats(self) -> Dict[str, Any]:
        """
        Get today's trading statistics.
        
        Returns:
            Dict with trading stats:
            {
                "trades_today": int,
                "wins_today": int,
                "losses_today": int,
                "pnl_today": float
            }
        """
        stats = {
            "trades_today": 0,
            "wins_today": 0,
            "losses_today": 0,
            "pnl_today": 0.0
        }
        
        if not self._trade_journal:
            return stats
        
        try:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            trades = self._trade_journal.get_trades_for_date(today_str)
            
            if trades:
                stats["trades_today"] = len(trades)
                stats["wins_today"] = sum(1 for t in trades if t.get('pnl_abs', 0) > 0)
                stats["losses_today"] = sum(1 for t in trades if t.get('pnl_abs', 0) <= 0)
                stats["pnl_today"] = round(sum(t.get('pnl_abs', 0) for t in trades), 2)
        except Exception as e:
            logger.warning(f"Error getting trading stats: {e}")
        
        return stats
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status.
        
        Returns:
            Complete health status dict with all metrics
        """
        # Check cache
        now = datetime.now(timezone.utc)
        if (self._last_health_check and 
            self._last_health_check_time and
            (now - self._last_health_check_time).total_seconds() < self._health_check_cache_seconds):
            return self._last_health_check
        
        # Gather all data
        api_status = self.get_api_status()
        resources = self.get_resource_usage()
        uptime = self.get_uptime()
        error_rate = self.get_error_rate(window_hours=1.0)
        recent_errors = self.get_recent_errors(5)
        trading_stats = self.get_trading_stats()
        
        # Determine overall status
        should_alert, alert_reasons = self.should_alert()
        
        if not should_alert:
            overall_status = "HEALTHY"
        elif any("critical" in r.lower() for r in alert_reasons):
            overall_status = "CRITICAL"
        else:
            overall_status = "WARNING"
        
        health = {
            "timestamp": now.isoformat(),
            "overall_status": overall_status,
            "uptime": uptime,
            "api_status": api_status,
            "resources": resources,
            "error_rate_per_hour": error_rate,
            "recent_errors": recent_errors,
            "trading": trading_stats,
            "alerts": alert_reasons if should_alert else []
        }
        
        # Cache result
        self._last_health_check = health
        self._last_health_check_time = now
        
        return health
    
    def should_alert(self) -> Tuple[bool, List[str]]:
        """
        Determine if system should trigger an alert.
        
        Returns:
            Tuple of (should_alert: bool, reasons: List[str])
        """
        reasons = []
        
        # Check API status
        api_status = self.get_api_status()
        
        # OKX is critical
        if api_status.get("okx", {}).get("connected") is False:
            reasons.append("OKX API disconnected")
        
        # Telegram warning (not critical)
        if (getattr(config, 'TELEGRAM_ENABLED', False) and 
            api_status.get("telegram", {}).get("connected") is False):
            reasons.append("Telegram API disconnected")
        
        # Database is critical
        if api_status.get("database", {}).get("connected") is False:
            reasons.append("Database disconnected")
        
        # Check resources
        resources = self.get_resource_usage()
        
        if resources.get("cpu_percent", 0) > 85:
            reasons.append(f"High CPU: {resources['cpu_percent']}%")
        
        if resources.get("memory_percent", 0) > 90:
            reasons.append(f"High Memory: {resources['memory_percent']}%")
        
        if resources.get("disk_percent", 0) > 95:
            reasons.append(f"Low Disk Space: {100 - resources['disk_percent']}% free")
        
        # Check error rate
        error_rate = self.get_error_rate(window_hours=1.0)
        if error_rate > 5.0:
            reasons.append(f"High error rate: {error_rate}/hour")
        
        return (len(reasons) > 0, reasons)
    
    def generate_report(self) -> str:
        """
        Generate formatted health report.
        
        Returns:
            Beautiful formatted report string
        """
        health = self.get_health_status()
        
        # Status icon
        status_icon = "✅" if health["overall_status"] == "HEALTHY" else "⚠️" if health["overall_status"] == "WARNING" else "❌"
        
        # Timestamp
        timestamp = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
        
        # Build report
        lines = []
        lines.append("╔══════════════════════════════════════════════════════╗")
        lines.append("║        SUPEQUANT SYSTEM HEALTH REPORT                ║")
        lines.append(f"║        {timestamp:<40} ║")
        lines.append("╠══════════════════════════════════════════════════════╣")
        lines.append(f"║ Status: {status_icon} {health['overall_status']:<43} ║")
        lines.append("╠══════════════════════════════════════════════════════╣")
        
        # API Connections
        lines.append("║ API CONNECTIONS                                      ║")
        
        api = health["api_status"]
        
        # OKX
        okx = api.get("okx", {})
        okx_icon = "✅" if okx.get("connected") else "❌"
        okx_latency = f"({okx.get('latency_ms', 0):.0f}ms)" if okx.get("connected") else f"({okx.get('error', 'Error')})"
        lines.append(f"║   OKX:      {okx_icon} {'Connected' if okx.get('connected') else 'Disconnected':<10} {okx_latency:<20} ║")
        
        # Telegram
        tg = api.get("telegram", {})
        if tg.get("connected") is None:
            tg_status = "⚪ Disabled"
        elif tg.get("connected"):
            tg_status = f"✅ Connected ({tg.get('latency_ms', 0):.0f}ms)"
        else:
            tg_status = f"❌ {tg.get('error', 'Error')}"
        lines.append(f"║   Telegram: {tg_status:<40} ║")
        
        # Database
        db = api.get("database", {})
        db_icon = "✅" if db.get("connected") else "❌"
        db_size = f"({db.get('size_kb', 0):.0f} KB)" if db.get("connected") else f"({db.get('error', 'Error')})"
        lines.append(f"║   Database: {db_icon} {'Connected' if db.get('connected') else 'Disconnected':<10} {db_size:<20} ║")
        
        lines.append("╠══════════════════════════════════════════════════════╣")
        
        # Resources
        lines.append("║ RESOURCES                                            ║")
        res = health["resources"]
        lines.append(f"║   CPU:      {res.get('cpu_percent', 0):.1f}%{' ':39} ║")
        lines.append(f"║   Memory:   {res.get('memory_used_mb', 0):.0f} MB ({res.get('memory_percent', 0):.1f}%){' ':27} ║")
        lines.append(f"║   Disk:     {res.get('disk_free_gb', 0):.1f} GB free{' ':32} ║")
        
        lines.append("╠══════════════════════════════════════════════════════╣")
        
        # Trading
        lines.append("║ TRADING                                              ║")
        uptime = health["uptime"]
        trading = health["trading"]
        lines.append(f"║   Uptime:   {uptime.get('readable', 'N/A'):<40} ║")
        
        trades_str = f"{trading['trades_today']} trades ({trading['wins_today']}W / {trading['losses_today']}L)"
        lines.append(f"║   Today:    {trades_str:<40} ║")
        
        error_rate = health["error_rate_per_hour"]
        lines.append(f"║   Errors:   {error_rate}/hour{' ':37} ║")
        
        lines.append("╠══════════════════════════════════════════════════════╣")
        
        # Alerts
        alerts = health.get("alerts", [])
        if alerts:
            lines.append(f"║ ALERTS: {len(alerts)} active{' ':36} ║")
            for alert in alerts[:3]:  # Show max 3
                lines.append(f"║   ⚠️  {alert[:45]:<46} ║")
        else:
            lines.append("║ ALERTS: None{' ':40} ║")
        
        lines.append("╚══════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)


# Module-level singleton for easy access
_monitor_instance: Optional[SystemMonitor] = None


def get_monitor() -> SystemMonitor:
    """
    Get or create the global SystemMonitor instance.
    
    Returns:
        SystemMonitor singleton
    """
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitor()
    return _monitor_instance


# CLI for testing
if __name__ == "__main__":
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n🔍 Testing SystemMonitor...\n")
    
    monitor = SystemMonitor()
    
    # Test individual methods
    print("📡 API Status:")
    api_status = monitor.get_api_status()
    for name, status in api_status.items():
        icon = "✅" if status.get("connected") else "❌" if status.get("connected") is False else "⚪"
        print(f"   {name}: {icon} {status}")
    
    print("\n💻 Resources:")
    resources = monitor.get_resource_usage()
    for key, value in resources.items():
        print(f"   {key}: {value}")
    
    print("\n⏱️  Uptime:")
    uptime = monitor.get_uptime()
    print(f"   {uptime}")
    
    print("\n📊 Trading Stats:")
    stats = monitor.get_trading_stats()
    print(f"   {stats}")
    
    print("\n🚨 Should Alert:")
    should_alert, reasons = monitor.should_alert()
    print(f"   Alert: {should_alert}")
    if reasons:
        print(f"   Reasons: {reasons}")
    
    print("\n" + "=" * 60)
    print(monitor.generate_report())
    print("=" * 60 + "\n")
    
    print("✅ SystemMonitor test complete!")
