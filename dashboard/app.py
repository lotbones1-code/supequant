"""
SupeQuant Trading Dashboard
Real-time monitoring of trades, balance, and bot status
"""

from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import json
import os
import threading

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
        """Get open positions"""
        return jsonify({
            'positions': dashboard_data['open_positions']
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
