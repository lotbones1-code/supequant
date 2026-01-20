"""
SupeQuant Trading Dashboard
Real-time monitoring of trades, balance, and bot status

Enhanced in Phase 1.4 with:
- Live positions with confidence indicators
- Confidence breakdown analytics
- Trade history from journal
- Daily summary stats
"""

from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import threading
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import trade journal and analytics (with graceful fallback)
try:
    from utils.trade_journal import TradeJournal
    from utils.performance_analytics import PerformanceAnalytics
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    TradeJournal = None
    PerformanceAnalytics = None

# Import OKX client for live data
try:
    from data_feed.okx_client import OKXClient
    OKX_AVAILABLE = True
except ImportError:
    OKX_AVAILABLE = False
    OKXClient = None

logger = logging.getLogger(__name__)

# Global OKX client instance (lazy loaded)
_okx_client = None


def _get_okx_client():
    """Get or create OKX client instance"""
    global _okx_client
    if _okx_client is None and OKX_AVAILABLE:
        try:
            _okx_client = OKXClient()
            logger.info("✅ Dashboard connected to OKX API")
        except Exception as e:
            logger.warning(f"Could not initialize OKX client: {e}")
    return _okx_client

# Global data store for dashboard
dashboard_data = {
    'balance': 0.0,
    'equity': 0.0,
    'unrealized_pnl': 0.0,
    'daily_pnl': 0.0,
    'daily_pnl_pct': 0.0,
    'total_trades': 0,
    'winning_trades': 0,
    'losing_trades': 0,
    'win_rate': 0.0,
    'open_positions': [],
    'recent_trades': [],
    'signals': [],
    'filter_stats': {},
    'bot_status': 'stopped',
    'last_update': None,
    'current_price': 0.0,
    'btc_price': 0.0,
    'market_regime': 'unknown',
    'errors': []
}

# Initialize analytics (lazy loaded)
_trade_journal = None
_performance_analytics = None


def _get_trade_journal():
    """Get or create trade journal instance"""
    global _trade_journal
    if _trade_journal is None and ANALYTICS_AVAILABLE:
        try:
            _trade_journal = TradeJournal(base_path="runs", enabled=True)
        except Exception as e:
            logger.warning(f"Could not initialize TradeJournal: {e}")
    return _trade_journal


def _get_performance_analytics():
    """Get or create performance analytics instance"""
    global _performance_analytics
    if _performance_analytics is None and ANALYTICS_AVAILABLE:
        try:
            _performance_analytics = PerformanceAnalytics(journal_path="runs")
        except Exception as e:
            logger.warning(f"Could not initialize PerformanceAnalytics: {e}")
    return _performance_analytics


def get_confidence_color(confidence):
    """
    Map confidence score to display color.
    
    Args:
        confidence: Score from 0-100 or None
        
    Returns:
        Color string: "green", "yellow", "orange", "red", or "gray"
    """
    if confidence is None:
        return "gray"
    try:
        conf = float(confidence)
        if conf >= 90:
            return "green"
        elif conf >= 70:
            return "yellow"
        elif conf >= 50:
            return "orange"
        else:
            return "red"
    except (TypeError, ValueError):
        return "gray"


def _calculate_duration_minutes(entry_time):
    """Calculate duration in minutes from entry time to now"""
    if not entry_time:
        return 0
    try:
        if isinstance(entry_time, str):
            # Parse ISO format
            if entry_time.endswith('Z'):
                entry_time = entry_time[:-1] + '+00:00'
            entry_dt = datetime.fromisoformat(entry_time)
        elif isinstance(entry_time, datetime):
            entry_dt = entry_time
        else:
            return 0
        
        # Make timezone-aware if needed
        now = datetime.now(timezone.utc)
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        
        duration = (now - entry_dt).total_seconds() / 60
        return round(duration, 1)
    except Exception:
        return 0

def create_app():
    """Create Flask dashboard application"""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    app.config['SECRET_KEY'] = os.getenv('DASHBOARD_SECRET_KEY', 'supequant-2026')
    
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/api/status')
    def api_status():
        """Get current bot status"""
        return jsonify({
            'status': dashboard_data['bot_status'],
            'last_update': dashboard_data['last_update'],
            'balance': dashboard_data['balance'],
            'equity': dashboard_data['equity'],
            'current_price': dashboard_data['current_price'],
            'btc_price': dashboard_data['btc_price']
        })
    
    @app.route('/api/balance')
    def api_balance():
        """Get balance and PnL info"""
        return jsonify({
            'balance': dashboard_data['balance'],
            'equity': dashboard_data['equity'],
            'unrealized_pnl': dashboard_data['unrealized_pnl'],
            'daily_pnl': dashboard_data['daily_pnl'],
            'daily_pnl_pct': dashboard_data['daily_pnl_pct']
        })
    
    @app.route('/api/trades')
    def api_trades():
        """Get recent trades"""
        return jsonify({
            'total_trades': dashboard_data['total_trades'],
            'winning_trades': dashboard_data['winning_trades'],
            'losing_trades': dashboard_data['losing_trades'],
            'win_rate': dashboard_data['win_rate'],
            'recent_trades': dashboard_data['recent_trades'][-50:]  # Last 50
        })
    
    @app.route('/api/positions')
    def api_positions():
        """
        Get open positions with enhanced data.
        
        Returns positions with:
        - Confidence score and color
        - TP/SL levels
        - Duration in minutes
        """
        positions = dashboard_data['open_positions']
        enhanced_positions = []
        
        for pos in positions:
            # Build enhanced position object
            confidence = pos.get('confidence') or pos.get('confidence_score')
            entry_time = pos.get('entry_time') or pos.get('entry_timestamp')
            
            enhanced = {
                'symbol': pos.get('symbol', 'SOL-USDT-SWAP'),
                'direction': pos.get('direction', pos.get('side', 'unknown')),
                'entry_price': float(pos.get('entry_price', 0)),
                'current_price': float(pos.get('current_price', dashboard_data['current_price'])),
                'size': float(pos.get('size', pos.get('quantity', 0))),
                'pnl': float(pos.get('pnl', 0)),
                'pnl_pct': float(pos.get('pnl_pct', pos.get('pnl_percent', 0))),
                'confidence': confidence,
                'confidence_color': get_confidence_color(confidence),
                'tp1': pos.get('take_profit_1') or pos.get('tp1'),
                'tp2': pos.get('take_profit_2') or pos.get('tp2'),
                'sl': pos.get('stop_loss') or pos.get('sl'),
                'entry_time': entry_time,
                'duration_minutes': _calculate_duration_minutes(entry_time),
                'strategy': pos.get('strategy', 'unknown')
            }
            enhanced_positions.append(enhanced)
        
        return jsonify({
            'positions': enhanced_positions
        })
    
    @app.route('/api/signals')
    def api_signals():
        """Get recent signals"""
        return jsonify({
            'signals': dashboard_data['signals'][-100:]  # Last 100
        })
    
    @app.route('/api/filters')
    def api_filters():
        """Get filter statistics"""
        return jsonify(dashboard_data['filter_stats'])
    
    @app.route('/api/all')
    def api_all():
        """Get all dashboard data"""
        return jsonify(dashboard_data)
    
    @app.route('/api/confidence-breakdown')
    def api_confidence_breakdown():
        """
        Get trade performance breakdown by confidence level.
        
        Uses PerformanceAnalytics to bucket trades by confidence:
        - high: 90-100%
        - medium: 70-89%
        - low: 50-69%
        - very_low: 0-49%
        - unknown: No confidence score
        """
        analytics = _get_performance_analytics()
        
        if not analytics:
            # Return empty breakdown if analytics not available
            return jsonify({
                'breakdown': {},
                'error': 'Analytics not available'
            })
        
        try:
            # Load recent trades and calculate breakdown
            trades = analytics.load_trades(days=30)
            by_confidence = analytics.calculate_metrics_by_confidence(trades)
            
            # Format for frontend with colors
            color_map = {
                'high': 'green',
                'medium': 'yellow', 
                'low': 'orange',
                'very_low': 'red',
                'unknown': 'gray'
            }
            
            total_trades = sum(
                data.get('trade_count', 0) 
                for data in by_confidence.values()
            )
            
            breakdown = {}
            for level, data in by_confidence.items():
                count = data.get('trade_count', 0)
                if count > 0 or level in ['high', 'medium', 'low']:  # Always show main buckets
                    breakdown[level] = {
                        'count': count,
                        'percentage': round(count / total_trades * 100, 1) if total_trades > 0 else 0,
                        'win_rate': round(data.get('win_rate_pct', 0), 1),
                        'total_pnl': data.get('total_pnl', 0),
                        'color': color_map.get(level, 'gray')
                    }
            
            return jsonify({
                'breakdown': breakdown,
                'total_trades': total_trades
            })
            
        except Exception as e:
            logger.error(f"Error in confidence breakdown: {e}")
            return jsonify({
                'breakdown': {},
                'error': str(e)
            })
    
    @app.route('/api/trade-history')
    def api_trade_history():
        """
        Get recent closed trades from the trade journal.
        
        Returns last 50 trades with:
        - Entry/exit prices
        - PnL (absolute and percentage)
        - Confidence score and color
        - Duration and strategy
        - Close reason (tp1, tp2, sl, manual)
        """
        journal = _get_trade_journal()
        
        if not journal:
            # Fall back to in-memory trades
            trades = dashboard_data['recent_trades'][-50:]
            return jsonify({
                'trades': trades,
                'source': 'memory'
            })
        
        try:
            # Get trades from journal (last 30 days, limit 50)
            raw_trades = journal.get_recent_trades(days=30)[:50]
            
            formatted_trades = []
            for trade in raw_trades:
                confidence = trade.get('confidence_score')
                
                formatted = {
                    'timestamp': trade.get('timestamp_close', trade.get('_logged_at', '')),
                    'symbol': trade.get('symbol', 'SOL-USDT-SWAP'),
                    'direction': trade.get('side', trade.get('direction', 'unknown')),
                    'entry_price': float(trade.get('entry_price', 0)),
                    'exit_price': float(trade.get('exit_price', 0)),
                    'pnl_pct': round(float(trade.get('pnl_pct', 0)), 2),
                    'pnl_abs': round(float(trade.get('pnl_abs', 0)), 2),
                    'confidence': confidence,
                    'confidence_color': get_confidence_color(confidence),
                    'duration_minutes': round(float(trade.get('duration_seconds', 0)) / 60, 1),
                    'strategy': trade.get('strategy_name', 'unknown'),
                    'close_reason': trade.get('close_reason', 'unknown')
                }
                formatted_trades.append(formatted)
            
            return jsonify({
                'trades': formatted_trades,
                'source': 'journal'
            })
            
        except Exception as e:
            logger.error(f"Error loading trade history: {e}")
            # Fall back to in-memory
            return jsonify({
                'trades': dashboard_data['recent_trades'][-50:],
                'source': 'memory',
                'error': str(e)
            })
    
    @app.route('/api/live')
    def api_live():
        """
        Get LIVE data directly from OKX API.
        
        Fetches real-time:
        - SOL and USDT balances only
        - SOL and BTC prices
        - Open positions
        """
        client = _get_okx_client()
        
        if not client:
            return jsonify({
                'error': 'OKX client not available',
                'usdt_balance': 0,
                'usdt_equity_usd': 0,
                'sol_balance': 0,
                'sol_equity_usd': 0,
                'total_equity': 0,
                'sol_price': 0,
                'btc_price': 0,
                'positions': [],
                'connected': False
            })
        
        try:
            # Fetch account balance
            balance_data = client.get_account_balance()
            
            # Initialize balances
            usdt_balance = 0
            usdt_equity_usd = 0
            sol_balance = 0
            sol_equity_usd = 0
            
            if balance_data and isinstance(balance_data, list):
                for account in balance_data:
                    # Parse each currency from details
                    for detail in account.get('details', []):
                        ccy = detail.get('ccy', '')
                        avail_bal = float(detail.get('availBal', 0) or 0)
                        eq_usd = float(detail.get('eqUsd', 0) or 0)
                        
                        if ccy == 'USDT':
                            usdt_balance = avail_bal
                            usdt_equity_usd = eq_usd
                        elif ccy == 'SOL':
                            sol_balance = avail_bal
                            sol_equity_usd = eq_usd
            
            # Calculate total equity (SOL + USDT only)
            total_equity = usdt_equity_usd + sol_equity_usd
            
            # Fetch SOL price
            sol_price = 0
            sol_ticker = client.get_ticker('SOL-USDT-SWAP')
            if sol_ticker and 'data' in sol_ticker and sol_ticker['data']:
                sol_price = float(sol_ticker['data'][0].get('last', 0))
            
            # Fetch BTC price
            btc_price = 0
            btc_ticker = client.get_ticker('BTC-USDT-SWAP')
            if btc_ticker and 'data' in btc_ticker and btc_ticker['data']:
                btc_price = float(btc_ticker['data'][0].get('last', 0))
            
            # Fetch open positions
            positions = []
            pos_data = client.get_positions()
            if pos_data and 'data' in pos_data:
                for pos in pos_data.get('data', []):
                    if float(pos.get('pos', 0)) != 0:
                        positions.append({
                            'symbol': pos.get('instId', ''),
                            'direction': 'long' if pos.get('posSide') == 'long' else 'short',
                            'size': abs(float(pos.get('pos', 0))),
                            'entry_price': float(pos.get('avgPx', 0)),
                            'current_price': float(pos.get('last', sol_price)),
                            'pnl': float(pos.get('upl', 0)),
                            'pnl_pct': float(pos.get('uplRatio', 0)) * 100,
                            'leverage': pos.get('lever', '1')
                        })
            
            # Update dashboard_data for other endpoints
            dashboard_data['balance'] = usdt_balance
            dashboard_data['equity'] = total_equity
            dashboard_data['current_price'] = sol_price
            dashboard_data['btc_price'] = btc_price
            dashboard_data['last_update'] = datetime.now(timezone.utc).isoformat()
            
            return jsonify({
                'usdt_balance': round(usdt_balance, 2),
                'usdt_equity_usd': round(usdt_equity_usd, 2),
                'sol_balance': round(sol_balance, 6),
                'sol_equity_usd': round(sol_equity_usd, 2),
                'total_equity': round(total_equity, 2),
                'sol_price': round(sol_price, 2),
                'btc_price': round(btc_price, 2),
                'positions': positions,
                'last_update': datetime.now(timezone.utc).isoformat(),
                'connected': True
            })
            
        except Exception as e:
            logger.error(f"Error fetching live data: {e}")
            return jsonify({
                'error': str(e),
                'usdt_balance': 0,
                'usdt_equity_usd': 0,
                'sol_balance': 0,
                'sol_equity_usd': 0,
                'total_equity': 0,
                'sol_price': 0,
                'btc_price': 0,
                'positions': [],
                'connected': False
            })
    
    @app.route('/api/daily-summary')
    def api_daily_summary():
        """
        Get today's trading summary.
        
        Returns:
        - trades_today: Number of trades closed today
        - wins_today: Number of winning trades
        - losses_today: Number of losing trades  
        - win_rate_today: Win rate percentage
        - pnl_today: Total PnL in dollars
        """
        journal = _get_trade_journal()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Default empty response
        summary = {
            'trades_today': 0,
            'wins_today': 0,
            'losses_today': 0,
            'win_rate_today': 0.0,
            'pnl_today': 0.0,
            'date': today_str
        }
        
        if not journal:
            return jsonify(summary)
        
        try:
            # Get today's trades from journal
            today_trades = journal.get_trades_for_date(today_str)
            
            if not today_trades:
                return jsonify(summary)
            
            wins = [t for t in today_trades if t.get('pnl_abs', 0) > 0]
            losses = [t for t in today_trades if t.get('pnl_abs', 0) <= 0]
            total_pnl = sum(t.get('pnl_abs', 0) for t in today_trades)
            
            summary = {
                'trades_today': len(today_trades),
                'wins_today': len(wins),
                'losses_today': len(losses),
                'win_rate_today': round(len(wins) / len(today_trades) * 100, 1) if today_trades else 0,
                'pnl_today': round(total_pnl, 2),
                'date': today_str
            }
            
            return jsonify(summary)
            
        except Exception as e:
            logger.error(f"Error calculating daily summary: {e}")
            return jsonify(summary)
    
    # =========================================================================
    # Phase 1.5 Analytics Endpoints
    # =========================================================================
    
    @app.route('/api/system-health')
    def api_system_health():
        """
        Get system health metrics from SystemMonitor.
        Returns API status, resource usage, uptime, error rate.
        """
        try:
            from utils.system_monitor import SystemMonitor
            monitor = SystemMonitor()
            health = monitor.get_health_status()
            return jsonify(health)
        except ImportError:
            return jsonify({'error': 'SystemMonitor not available', 'status': 'unknown'})
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return jsonify({'error': str(e), 'status': 'error'})
    
    @app.route('/api/filter-scores')
    def api_filter_scores():
        """
        Get filter effectiveness scores from FilterScorer.
        Returns scores for each filter based on trade outcomes.
        """
        try:
            from utils.filter_scorer import FilterScorer
            scorer = FilterScorer()
            summary = scorer.get_summary()
            return jsonify(summary)
        except ImportError:
            return jsonify({'error': 'FilterScorer not available'})
        except Exception as e:
            logger.error(f"Error getting filter scores: {e}")
            return jsonify({'error': str(e)})
    
    @app.route('/api/risk-exposure')
    def api_risk_exposure():
        """
        Get risk exposure metrics from RiskDashboard.
        Returns current exposure, drawdown, VaR, Kelly criterion.
        """
        try:
            from utils.risk_dashboard import RiskDashboard
            # Create dashboard without managers (will show limited data)
            # Full data requires integration with main.py
            dashboard = RiskDashboard()
            summary = dashboard.get_summary()
            return jsonify(summary)
        except ImportError:
            return jsonify({'error': 'RiskDashboard not available'})
        except Exception as e:
            logger.error(f"Error getting risk exposure: {e}")
            return jsonify({'error': str(e)})
    
    @app.route('/api/trade-quality')
    def api_trade_quality():
        """
        Get trade quality analysis from TradeQualityInspector.
        Returns hourly stats, duration analysis, close reasons, strategies.
        """
        try:
            from utils.trade_quality import TradeQualityInspector
            inspector = TradeQualityInspector()
            summary = inspector.get_summary()
            return jsonify(summary)
        except ImportError:
            return jsonify({'error': 'TradeQualityInspector not available'})
        except Exception as e:
            logger.error(f"Error getting trade quality: {e}")
            return jsonify({'error': str(e)})
    
    @app.route('/api/analytics-summary')
    def api_analytics_summary():
        """
        Get combined summary of all Phase 1.5 analytics.
        Single endpoint for dashboard overview.
        """
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_health': None,
            'filter_scores': None,
            'risk_exposure': None,
            'trade_quality': None
        }
        
        # System Health
        try:
            from utils.system_monitor import SystemMonitor
            monitor = SystemMonitor()
            health = monitor.get_health_status()
            summary['system_health'] = {
                'status': health.get('overall_status', 'unknown'),
                'uptime': health.get('uptime_readable', 'N/A'),
                'error_rate': health.get('error_rate_per_hour', 0)
            }
        except Exception as e:
            summary['system_health'] = {'status': 'error', 'message': str(e)}
        
        # Filter Scores
        try:
            from utils.filter_scorer import FilterScorer
            scorer = FilterScorer()
            scores = scorer.get_summary()
            summary['filter_scores'] = {
                'filters_analyzed': scores.get('filters_analyzed', 0),
                'effective': scores.get('filters_effective', 0),
                'warning': scores.get('filters_warning', 0)
            }
        except Exception as e:
            summary['filter_scores'] = {'status': 'error', 'message': str(e)}
        
        # Risk Exposure
        try:
            from utils.risk_dashboard import RiskDashboard
            dashboard = RiskDashboard()
            risk = dashboard.get_summary()
            exposure = risk.get('exposure', {})
            summary['risk_exposure'] = {
                'has_position': exposure.get('has_position', False),
                'status': exposure.get('status', 'unknown'),
                'risk_percent': exposure.get('risk_percent', 0)
            }
        except Exception as e:
            summary['risk_exposure'] = {'status': 'error', 'message': str(e)}
        
        # Trade Quality
        try:
            from utils.trade_quality import TradeQualityInspector
            inspector = TradeQualityInspector()
            quality = inspector.get_summary()
            overall = quality.get('overall', {})
            summary['trade_quality'] = {
                'total_trades': overall.get('total_trades', 0),
                'win_rate': overall.get('win_rate', 0),
                'total_pnl': overall.get('total_pnl', 0)
            }
        except Exception as e:
            summary['trade_quality'] = {'status': 'error', 'message': str(e)}
        
        return jsonify(summary)
    
    return app


def update_balance(balance, equity, unrealized_pnl=0):
    """Update balance data"""
    dashboard_data['balance'] = balance
    dashboard_data['equity'] = equity
    dashboard_data['unrealized_pnl'] = unrealized_pnl
    dashboard_data['last_update'] = datetime.now().isoformat()


def update_daily_pnl(pnl, pnl_pct):
    """Update daily PnL"""
    dashboard_data['daily_pnl'] = pnl
    dashboard_data['daily_pnl_pct'] = pnl_pct


def add_trade(trade_data):
    """Add a completed trade"""
    dashboard_data['recent_trades'].append({
        **trade_data,
        'timestamp': datetime.now().isoformat()
    })
    dashboard_data['total_trades'] += 1
    
    if trade_data.get('pnl', 0) > 0:
        dashboard_data['winning_trades'] += 1
    else:
        dashboard_data['losing_trades'] += 1
    
    if dashboard_data['total_trades'] > 0:
        dashboard_data['win_rate'] = (
            dashboard_data['winning_trades'] / dashboard_data['total_trades'] * 100
        )
    
    # Keep only last 500 trades
    if len(dashboard_data['recent_trades']) > 500:
        dashboard_data['recent_trades'] = dashboard_data['recent_trades'][-500:]


def update_positions(positions):
    """Update open positions"""
    dashboard_data['open_positions'] = positions


def add_signal(signal_data):
    """Add a signal event"""
    dashboard_data['signals'].append({
        **signal_data,
        'timestamp': datetime.now().isoformat()
    })
    # Keep only last 500 signals
    if len(dashboard_data['signals']) > 500:
        dashboard_data['signals'] = dashboard_data['signals'][-500:]


def update_filter_stats(stats):
    """Update filter statistics"""
    dashboard_data['filter_stats'] = stats


def set_bot_status(status):
    """Set bot status (running, stopped, error)"""
    dashboard_data['bot_status'] = status
    dashboard_data['last_update'] = datetime.now().isoformat()


def update_prices(sol_price, btc_price):
    """Update current prices"""
    dashboard_data['current_price'] = sol_price
    dashboard_data['btc_price'] = btc_price


def set_market_regime(regime):
    """Set current market regime"""
    dashboard_data['market_regime'] = regime


def add_error(error_msg):
    """Add an error to the log"""
    dashboard_data['errors'].append({
        'message': error_msg,
        'timestamp': datetime.now().isoformat()
    })
    # Keep only last 100 errors
    if len(dashboard_data['errors']) > 100:
        dashboard_data['errors'] = dashboard_data['errors'][-100:]
