"""
Reliability Utilities for 24/7 Trading

Features:
- Automatic error recovery with exponential backoff
- Connection health monitoring
- Heartbeat logging
- Graceful degradation
- Error rate tracking
"""

import time
import logging
import threading
import functools
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, Optional, Any
from collections import deque

logger = logging.getLogger(__name__)


class ErrorTracker:
    """Tracks error rates to detect systemic issues"""
    
    def __init__(self, window_minutes: int = 60, threshold: int = 10):
        self.window_minutes = window_minutes
        self.threshold = threshold
        self.errors: deque = deque()
        self._lock = threading.Lock()
    
    def record_error(self, error_type: str, error_msg: str):
        """Record an error occurrence"""
        with self._lock:
            now = datetime.now(timezone.utc)
            self.errors.append({
                'time': now,
                'type': error_type,
                'msg': error_msg
            })
            self._cleanup()
    
    def _cleanup(self):
        """Remove old errors outside window"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.window_minutes)
        while self.errors and self.errors[0]['time'] < cutoff:
            self.errors.popleft()
    
    def get_error_count(self) -> int:
        """Get number of errors in window"""
        with self._lock:
            self._cleanup()
            return len(self.errors)
    
    def is_critical(self) -> bool:
        """Check if error rate is critical"""
        return self.get_error_count() >= self.threshold
    
    def get_summary(self) -> Dict:
        """Get error summary"""
        with self._lock:
            self._cleanup()
            by_type = {}
            for err in self.errors:
                t = err['type']
                by_type[t] = by_type.get(t, 0) + 1
            return {
                'total': len(self.errors),
                'by_type': by_type,
                'is_critical': len(self.errors) >= self.threshold
            }


class Heartbeat:
    """Heartbeat monitor for system health"""
    
    def __init__(self, name: str, interval_seconds: int = 300):
        self.name = name
        self.interval = interval_seconds
        self.last_beat = datetime.now(timezone.utc)
        self._lock = threading.Lock()
    
    def beat(self):
        """Record a heartbeat"""
        with self._lock:
            self.last_beat = datetime.now(timezone.utc)
    
    def is_alive(self) -> bool:
        """Check if heartbeat is recent"""
        with self._lock:
            age = (datetime.now(timezone.utc) - self.last_beat).total_seconds()
            return age < self.interval * 2
    
    def get_age_seconds(self) -> float:
        """Get age of last heartbeat"""
        with self._lock:
            return (datetime.now(timezone.utc) - self.last_beat).total_seconds()


class ConnectionMonitor:
    """Monitor connection health"""
    
    def __init__(self):
        self.last_successful_call = datetime.now(timezone.utc)
        self.consecutive_failures = 0
        self._lock = threading.Lock()
    
    def record_success(self):
        """Record successful API call"""
        with self._lock:
            self.last_successful_call = datetime.now(timezone.utc)
            self.consecutive_failures = 0
    
    def record_failure(self):
        """Record failed API call"""
        with self._lock:
            self.consecutive_failures += 1
    
    def is_healthy(self) -> bool:
        """Check if connection is healthy"""
        with self._lock:
            age = (datetime.now(timezone.utc) - self.last_successful_call).total_seconds()
            return age < 300 and self.consecutive_failures < 5
    
    def get_status(self) -> Dict:
        """Get connection status"""
        with self._lock:
            age = (datetime.now(timezone.utc) - self.last_successful_call).total_seconds()
            return {
                'healthy': age < 300 and self.consecutive_failures < 5,
                'last_success_ago': age,
                'consecutive_failures': self.consecutive_failures
            }


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None
):
    """
    Decorator for automatic retry with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exceptions: Tuple of exceptions to catch
        on_retry: Optional callback on retry (receives exception, attempt)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(f"⚠️ {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                        logger.warning(f"   Retrying in {delay:.1f}s...")
                        
                        if on_retry:
                            on_retry(e, attempt)
                        
                        time.sleep(delay)
                    else:
                        logger.error(f"❌ {func.__name__} failed after {max_retries + 1} attempts: {e}")
            
            raise last_exception
        
        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    *args,
    default: Any = None,
    error_tracker: ErrorTracker = None,
    error_type: str = "unknown",
    log_errors: bool = True,
    **kwargs
) -> Any:
    """
    Safely execute a function with error handling.
    
    Args:
        func: Function to execute
        default: Default value to return on error
        error_tracker: Optional ErrorTracker instance
        error_type: Type label for error tracking
        log_errors: Whether to log errors
        
    Returns:
        Function result or default value
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"❌ Error in {func.__name__}: {e}")
        
        if error_tracker:
            error_tracker.record_error(error_type, str(e))
        
        return default


class SystemHealth:
    """
    Centralized system health monitoring.
    
    Tracks:
    - Error rates
    - Connection health
    - Component heartbeats
    - Overall system status
    """
    
    def __init__(self):
        self.error_tracker = ErrorTracker(window_minutes=60, threshold=20)
        self.connection_monitor = ConnectionMonitor()
        self.heartbeats: Dict[str, Heartbeat] = {}
        self.start_time = datetime.now(timezone.utc)
        self._status_callbacks: list = []
    
    def add_heartbeat(self, name: str, interval_seconds: int = 300):
        """Add a component heartbeat"""
        self.heartbeats[name] = Heartbeat(name, interval_seconds)
    
    def beat(self, name: str):
        """Record heartbeat for a component"""
        if name in self.heartbeats:
            self.heartbeats[name].beat()
    
    def record_error(self, error_type: str, error_msg: str):
        """Record an error"""
        self.error_tracker.record_error(error_type, error_msg)
        
        # Check if critical and notify
        if self.error_tracker.is_critical():
            for callback in self._status_callbacks:
                try:
                    callback('critical', f"Error rate critical: {error_type}")
                except:
                    pass
    
    def record_api_success(self):
        """Record successful API call"""
        self.connection_monitor.record_success()
    
    def record_api_failure(self):
        """Record failed API call"""
        self.connection_monitor.record_failure()
    
    def on_status_change(self, callback: Callable):
        """Register callback for status changes"""
        self._status_callbacks.append(callback)
    
    def get_status(self) -> Dict:
        """Get comprehensive system status"""
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        heartbeat_status = {}
        for name, hb in self.heartbeats.items():
            heartbeat_status[name] = {
                'alive': hb.is_alive(),
                'age_seconds': hb.get_age_seconds()
            }
        
        return {
            'healthy': self.is_healthy(),
            'uptime_seconds': uptime,
            'uptime_hours': uptime / 3600,
            'connection': self.connection_monitor.get_status(),
            'errors': self.error_tracker.get_summary(),
            'heartbeats': heartbeat_status
        }
    
    def is_healthy(self) -> bool:
        """Check if system is healthy overall"""
        # Check connection
        if not self.connection_monitor.is_healthy():
            return False
        
        # Check error rate
        if self.error_tracker.is_critical():
            return False
        
        # Check heartbeats
        for name, hb in self.heartbeats.items():
            if not hb.is_alive():
                logger.warning(f"⚠️ Heartbeat '{name}' is stale")
                return False
        
        return True
    
    def get_health_report(self) -> str:
        """Get formatted health report"""
        status = self.get_status()
        
        lines = ["🏥 SYSTEM HEALTH REPORT", "=" * 40]
        
        overall = "✅ HEALTHY" if status['healthy'] else "❌ UNHEALTHY"
        lines.append(f"Overall: {overall}")
        lines.append(f"Uptime: {status['uptime_hours']:.1f} hours")
        
        conn = status['connection']
        conn_status = "✅" if conn['healthy'] else "❌"
        lines.append(f"\nConnection: {conn_status}")
        lines.append(f"  Last success: {conn['last_success_ago']:.0f}s ago")
        lines.append(f"  Consecutive failures: {conn['consecutive_failures']}")
        
        errors = status['errors']
        error_status = "❌ CRITICAL" if errors['is_critical'] else "✅ OK"
        lines.append(f"\nErrors (last hour): {error_status}")
        lines.append(f"  Total: {errors['total']}")
        for etype, count in errors['by_type'].items():
            lines.append(f"    {etype}: {count}")
        
        if status['heartbeats']:
            lines.append(f"\nHeartbeats:")
            for name, hb in status['heartbeats'].items():
                hb_status = "✅" if hb['alive'] else "❌"
                lines.append(f"  {name}: {hb_status} ({hb['age_seconds']:.0f}s ago)")
        
        lines.append("=" * 40)
        return "\n".join(lines)


# Global system health instance
_system_health: Optional[SystemHealth] = None


def get_system_health() -> SystemHealth:
    """Get global system health instance"""
    global _system_health
    if _system_health is None:
        _system_health = SystemHealth()
    return _system_health


def init_system_health() -> SystemHealth:
    """Initialize system health monitoring"""
    health = get_system_health()
    health.add_heartbeat('trading_loop', interval_seconds=120)
    health.add_heartbeat('market_data', interval_seconds=300)
    logger.info("✅ System health monitoring initialized")
    return health
