#!/usr/bin/env python3
"""
System Diagnostic Check
Comprehensive check of all system components

Usage:
    python system_diagnostic.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logging
from data_feed import OKXClient, MarketDataFeed
from filters import FilterManager
from strategy import StrategyManager
from risk import RiskManager
from execution import OrderManager, PositionTracker
from model_learning import DataCollector
import config

setup_logging()
import logging
logger = logging.getLogger(__name__)

def check_component(name, func):
    """Helper to check components"""
    try:
        result = func()
        if result:
            print(f"   ✅ {name}: OK")
        else:
            print(f"   ⚠️  {name}: Warning")
        return result
    except Exception as e:
        print(f"   ❌ {name}: FAILED - {e}")
        return False

def run_diagnostic():
    """Run comprehensive system diagnostic"""
    
    print("\n" + "="*80)
    print("🚀 SYSTEM DIAGNOSTIC CHECK")
    print("="*80)
    
    results = {}
    
    # 1. Configuration Check
    print("\n1️⃣  Configuration Check...")
    results['config'] = True
    print(f"   Trading Symbol: {config.TRADING_SYMBOL}")
    print(f"   Mode: {'SIMULATED' if config.OKX_SIMULATED else 'LIVE'}")
    print(f"   Max Daily Trades: {config.MAX_DAILY_TRADES}")
    print(f"   Risk Per Trade: {config.MAX_RISK_PER_TRADE*100}%")
    print(f"   Position Size: {config.POSITION_SIZE_PCT*100}%")
    
    # 2. API Credentials
    print("\n2️⃣  OKX API Credentials...")
    client = OKXClient()
    api_ok = bool(client.api_key and client.secret_key and client.passphrase)
    print(f"   API Key: {'✅ Set' if client.api_key else '❌ Missing'}")
    print(f"   Secret Key: {'✅ Set' if client.secret_key else '❌ Missing'}")
    print(f"   Passphrase: {'✅ Set' if client.passphrase else '❌ Missing'}")
    print(f"   Domain: {client.base_url}")
    results['api_creds'] = api_ok
    
    # 3. API Connectivity
    print("\n3️⃣  OKX API Connectivity...")
    try:
        ticker = client.get_ticker(config.TRADING_SYMBOL)
        if ticker:
            print(f"   ✅ Connected - Price: ${ticker.get('last', 'N/A')}")
            results['api_connect'] = True
        else:
            print(f"   ❌ Connection failed")
            results['api_connect'] = False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['api_connect'] = False
    
    # 4. Account Balance
    print("\n4️⃣  Account Balance...")
    try:
        balance = client.get_account_balance()
        if balance:
            # Balance is a list, extract first account's equity
            if isinstance(balance, list) and len(balance) > 0:
                account = balance[0]
                details = account.get('details', [])
                if details:
                    total_eq = details[0].get('eq', '0')
                    print(f"   ✅ Balance check OK - Total Equity: ${total_eq}")
                else:
                    total_eq = account.get('totalEq', 'N/A')
                    print(f"   ✅ Balance check OK - Total Equity: ${total_eq}")
            else:
                total_eq = balance.get('totalEq', 'N/A') if isinstance(balance, dict) else 'N/A'
                print(f"   ✅ Balance check OK - Total Equity: ${total_eq}")
            results['balance'] = True
        else:
            print(f"   ⚠️  Could not fetch balance")
            results['balance'] = False
    except Exception as e:
        print(f"   ⚠️  Balance check error: {e}")
        results['balance'] = False
    
    # 5. Component Initialization
    print("\n5️⃣  Component Initialization...")
    
    components = {
        'MarketDataFeed': lambda: MarketDataFeed(client),
        'FilterManager': lambda: FilterManager(),
        'StrategyManager': lambda: StrategyManager(),
        'RiskManager': lambda: RiskManager(client),
        'OrderManager': lambda: OrderManager(client),
        'PositionTracker': lambda: PositionTracker(client),
        'DataCollector': lambda: DataCollector()
    }
    
    initialized = {}
    for name, init_func in components.items():
        try:
            obj = init_func()
            initialized[name] = obj
            print(f"   ✅ {name}: Initialized")
        except Exception as e:
            print(f"   ❌ {name}: Failed - {e}")
            initialized[name] = None
    
    results['components'] = all(initialized.values())
    
    # 6. Market Data Fetch
    print("\n6️⃣  Market Data Fetch Test...")
    if initialized.get('MarketDataFeed'):
        try:
            market_data = initialized['MarketDataFeed']
            timeframes = [config.LTF_TIMEFRAME, config.MTF_TIMEFRAME, config.HTF_TIMEFRAME]
            market_state = market_data.get_market_state(
                config.TRADING_SYMBOL,
                timeframes
            )
            if market_state:
                price = market_state.get('current_price', 0)
                print(f"   ✅ Market data OK - Current Price: ${price:.2f}")
                print(f"   ✅ Timeframes available: {list(market_state.get('timeframes', {}).keys())}")
                results['market_data'] = True
            else:
                print(f"   ⚠️  Market data fetch returned None")
                results['market_data'] = False
        except Exception as e:
            print(f"   ❌ Market data error: {e}")
            results['market_data'] = False
    else:
        results['market_data'] = False
    
    # 7. Strategy Signal Generation
    print("\n7️⃣  Strategy Signal Generation...")
    if initialized.get('StrategyManager') and initialized.get('MarketDataFeed'):
        try:
            market_data = initialized['MarketDataFeed']
            strategy = initialized['StrategyManager']
            timeframes = [config.LTF_TIMEFRAME, config.MTF_TIMEFRAME, config.HTF_TIMEFRAME]
            market_state = market_data.get_market_state(
                config.TRADING_SYMBOL,
                timeframes
            )
            if market_state:
                signal = strategy.analyze_market(market_state)
                if signal:
                    print(f"   ✅ Signal generated: {signal.get('strategy')} - {signal.get('direction')}")
                else:
                    print(f"   ✅ Strategies working (no signal currently - this is normal)")
                results['strategies'] = True
            else:
                results['strategies'] = False
        except Exception as e:
            print(f"   ⚠️  Strategy test error: {e}")
            results['strategies'] = False
    else:
        results['strategies'] = False
    
    # 8. Filter System
    print("\n8️⃣  Filter System...")
    if initialized.get('FilterManager'):
        try:
            filters = initialized['FilterManager']
            stats = filters.get_filter_statistics()
            print(f"   ✅ Filters initialized")
            print(f"   ✅ Total checks: {stats.get('total_checks', 0)}")
            print(f"   ✅ Pass rate: {stats.get('pass_rate', 0)*100:.1f}%")
            results['filters'] = True
        except Exception as e:
            print(f"   ⚠️  Filter check error: {e}")
            results['filters'] = False
    else:
        results['filters'] = False
    
    # 9. Risk Management
    print("\n9️⃣  Risk Management...")
    if initialized.get('RiskManager'):
        try:
            risk = initialized['RiskManager']
            can_trade, reason = risk.check_can_trade(0)
            print(f"   ✅ Risk manager initialized")
            print(f"   ✅ Can trade: {can_trade} ({reason})")
            if risk.emergency_shutdown:
                print(f"   ⚠️  Emergency shutdown active: {risk.shutdown_reason}")
            else:
                print(f"   ✅ No emergency shutdown")
            results['risk'] = True
        except Exception as e:
            print(f"   ⚠️  Risk check error: {e}")
            results['risk'] = False
    else:
        results['risk'] = False
    
    # 10. AI Systems
    print("\n🔟 AI Systems...")
    try:
        hybrid_enabled = getattr(config, 'HYBRID_AI_ENABLED', True)
        print(f"   Hybrid AI Enabled: {hybrid_enabled}")
        
        try:
            from agents.enhanced_autonomous_system import EnhancedAutonomousTradeSystem
            print(f"   ✅ Hybrid AI available")
            results['ai'] = True
        except ImportError:
            print(f"   ⚠️  Hybrid AI not available")
            try:
                from agents.claude_autonomous_system import AutonomousTradeSystem
                print(f"   ✅ Claude AI available")
                results['ai'] = True
            except ImportError:
                print(f"   ⚠️  No AI systems available")
                results['ai'] = False
    except Exception as e:
        print(f"   ⚠️  AI check error: {e}")
        results['ai'] = False
    
    # Summary
    print("\n" + "="*80)
    print("📊 DIAGNOSTIC SUMMARY")
    print("="*80)
    
    all_critical = [
        results.get('api_creds'),
        results.get('api_connect'),
        results.get('components'),
        results.get('market_data'),
        results.get('risk')
    ]
    
    if all(all_critical):
        print("\n✅ ALL CRITICAL SYSTEMS: OPERATIONAL")
        print("\n📋 System Status:")
        print(f"   ✅ Ready for live trading: {'YES' if not config.OKX_SIMULATED else 'SIMULATED MODE'}")
        print(f"   ✅ All components initialized")
        print(f"   ✅ API connectivity OK")
        print(f"   ✅ Market data fetching OK")
        print(f"   ✅ Risk management active")
        
        if results.get('strategies'):
            print(f"   ✅ Strategies operational")
        if results.get('filters'):
            print(f"   ✅ Filters operational")
        if results.get('ai'):
            print(f"   ✅ AI systems available")
        
        print("\n💡 System is ready to trade!")
        print("   Run: python main.py")
        
    else:
        print("\n⚠️  ISSUES DETECTED")
        print("\nFailed checks:")
        if not results.get('api_creds'):
            print("   ❌ API credentials missing")
        if not results.get('api_connect'):
            print("   ❌ API connection failed")
        if not results.get('components'):
            print("   ❌ Component initialization failed")
        if not results.get('market_data'):
            print("   ❌ Market data fetch failed")
        if not results.get('risk'):
            print("   ❌ Risk management check failed")
    
    print("\n" + "="*80)
    return all(all_critical)

if __name__ == '__main__':
    try:
        success = run_diagnostic()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
