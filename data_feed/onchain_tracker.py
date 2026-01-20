"""
On-Chain Intelligence Tracker (Phase 3.1 Elite)

Monitors Solana blockchain for whale movements and exchange flows.
Uses Helius API for transaction data.

Features:
- Large transfer detection (>10k SOL)
- Exchange flow classification (TO/FROM exchange)
- Net flow aggregation over time windows
- Caching to respect API rate limits
- Graceful degradation without API key

Data signals:
- Net inflow TO exchanges = Bearish (whales preparing to sell)
- Net outflow FROM exchanges = Bullish (whales accumulating)
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import time

logger = logging.getLogger(__name__)


class FlowDirection(Enum):
    """Classification of transfer direction"""
    TO_EXCHANGE = "to_exchange"        # Bearish signal - preparing to sell
    FROM_EXCHANGE = "from_exchange"    # Bullish signal - accumulating
    WALLET_TO_WALLET = "wallet_to_wallet"  # Neutral
    INTERNAL_EXCHANGE = "internal"     # Exchange to exchange - ignore
    UNKNOWN = "unknown"


@dataclass
class WhaleTransfer:
    """Represents a single large SOL transfer"""
    timestamp: datetime
    signature: str
    from_address: str
    to_address: str
    amount_sol: float
    direction: FlowDirection
    exchange_name: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'signature': self.signature[:16] + '...',
            'from': self.from_address[:8] + '...',
            'to': self.to_address[:8] + '...',
            'amount_sol': self.amount_sol,
            'direction': self.direction.value,
            'exchange': self.exchange_name
        }


class OnchainTracker:
    """
    On-chain intelligence tracker for Solana.
    
    Uses Helius API to monitor:
    - Large SOL transfers (whale movements)
    - Exchange inflows/outflows
    - Net flow aggregation for trading signals
    
    Requires HELIUS_API_KEY in environment or config.
    """
    
    # Known exchange wallet addresses (curated list)
    # Format: address -> exchange name
    EXCHANGE_WALLETS = {
        # Binance
        '5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9': 'Binance',
        'AC5RDfQFmDS1deWZos921JfqscXdByf4BKHs5ACWjtW2': 'Binance',
        '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM': 'Binance',
        
        # OKX
        '5VCwKtCXgCJ6kit5FybXjvriW3xELsFDhYrPSqtJNmcD': 'OKX',
        'JCNCMFXo5M5qwUPg2Utu1u6YWp3MbygxqBsBeXXJfrw': 'OKX',
        
        # Coinbase
        'H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS': 'Coinbase',
        'GJRs4FwHtemZ5ZE9x3FNvJ8TMwitKTh21yxdRPqn7npE': 'Coinbase',
        
        # Kraken
        'FWznbcNXWQuHTawe9RxvQ2LdCENssh12dsznf4RiouN5': 'Kraken',
        
        # Bybit
        'BmFdpraQhkiDQE6SnfG5omcA1VwzqfXrwtNYBwWTymy6': 'Bybit',
        
        # KuCoin
        'BQcdHdAQW1hczDbBi9hiegXAR7A98Q9jx3X3iBBBDiq4': 'KuCoin',
        
        # Gate.io
        'u6PJ8DtQuPFnfmwHbGFULQ4u4EgjDiyYKjVEsynXq2w': 'Gate.io',
        
        # Huobi/HTX
        '88xTWZMeKfiTgbfEmPLdsUCQcZinwUfk25EBQZ21XMAZ': 'HTX',
    }
    
    def __init__(self):
        self.name = "OnchainTracker"
        
        # API setup - try environment first, then config
        self.api_key = os.getenv('HELIUS_API_KEY', '')
        if not self.api_key:
            try:
                import config
                self.api_key = getattr(config, 'HELIUS_API_KEY', '')
            except:
                pass
        
        self.base_url = "https://api.helius.xyz/v0"
        
        # Cache for rate limiting (Helius free tier: 100k credits/day)
        self.last_fetch_time: Optional[datetime] = None
        self.cache_duration_seconds = 300  # 5 minutes
        self.cached_transfers: List[WhaleTransfer] = []
        
        # Transfer history for aggregation
        self.transfer_history: List[WhaleTransfer] = []
        self.max_history = 200
        
        # Current analysis state
        self.last_analysis: Optional[Dict] = None
        
        # Status tracking
        self.api_available = bool(self.api_key)
        self.last_api_error: Optional[str] = None
        
        if not self.api_key:
            logger.warning(f"⚠️  {self.name}: No HELIUS_API_KEY - running in DEGRADED mode (neutral signals)")
        else:
            logger.info(f"✅ {self.name}: Initialized with Helius API")
    
    def _is_exchange_wallet(self, address: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an address is a known exchange wallet.
        
        Returns:
            (is_exchange: bool, exchange_name: Optional[str])
        """
        if address in self.EXCHANGE_WALLETS:
            return True, self.EXCHANGE_WALLETS[address]
        return False, None
    
    def _classify_transfer(self, from_addr: str, to_addr: str) -> Tuple[FlowDirection, Optional[str]]:
        """
        Classify a transfer based on source and destination addresses.
        
        Returns:
            (direction: FlowDirection, exchange_name: Optional[str])
        """
        from_is_exchange, from_name = self._is_exchange_wallet(from_addr)
        to_is_exchange, to_name = self._is_exchange_wallet(to_addr)
        
        if to_is_exchange and not from_is_exchange:
            # Wallet -> Exchange = BEARISH (depositing to sell)
            return FlowDirection.TO_EXCHANGE, to_name
        
        elif from_is_exchange and not to_is_exchange:
            # Exchange -> Wallet = BULLISH (withdrawing to hold)
            return FlowDirection.FROM_EXCHANGE, from_name
        
        elif from_is_exchange and to_is_exchange:
            # Exchange -> Exchange = Internal, ignore
            return FlowDirection.INTERNAL_EXCHANGE, None
        
        else:
            # Wallet -> Wallet = Neutral
            return FlowDirection.WALLET_TO_WALLET, None
    
    def _fetch_from_helius(self, min_sol: float = 10000) -> List[WhaleTransfer]:
        """
        Fetch recent large transfers from Helius API.
        
        Uses the enhanced transactions API to get parsed transfer data.
        
        Args:
            min_sol: Minimum SOL amount to consider
            
        Returns:
            List of WhaleTransfer objects
        """
        transfers = []
        
        if not self.api_key:
            return transfers
        
        try:
            import requests
            
            # Helius enhanced transactions endpoint for native SOL transfers
            # We'll query recent transactions and filter for large transfers
            url = f"{self.base_url}/addresses/So11111111111111111111111111111111111111112/transactions"
            
            params = {
                'api-key': self.api_key,
                'limit': 100,
                'type': 'TRANSFER'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                self.last_api_error = None
                
                for tx in data:
                    try:
                        # Parse Helius enhanced transaction format
                        # Native transfers are in nativeTransfers array
                        native_transfers = tx.get('nativeTransfers', [])
                        
                        for nt in native_transfers:
                            amount_lamports = nt.get('amount', 0)
                            amount_sol = amount_lamports / 1e9  # Convert lamports to SOL
                            
                            if amount_sol >= min_sol:
                                from_addr = nt.get('fromUserAccount', '')
                                to_addr = nt.get('toUserAccount', '')
                                
                                if from_addr and to_addr:
                                    direction, exchange = self._classify_transfer(from_addr, to_addr)
                                    
                                    # Only track exchange-related transfers
                                    if direction in [FlowDirection.TO_EXCHANGE, FlowDirection.FROM_EXCHANGE]:
                                        timestamp = tx.get('timestamp', 0)
                                        if timestamp:
                                            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                                        else:
                                            dt = datetime.now(timezone.utc)
                                        
                                        transfer = WhaleTransfer(
                                            timestamp=dt,
                                            signature=tx.get('signature', ''),
                                            from_address=from_addr,
                                            to_address=to_addr,
                                            amount_sol=amount_sol,
                                            direction=direction,
                                            exchange_name=exchange
                                        )
                                        transfers.append(transfer)
                    except Exception as e:
                        logger.debug(f"{self.name}: Error parsing tx: {e}")
                        continue
                
                logger.info(f"📊 {self.name}: Fetched {len(transfers)} whale transfers from Helius")
                
            elif response.status_code == 429:
                self.last_api_error = "Rate limited"
                logger.warning(f"⚠️  {self.name}: Helius rate limited, using cached data")
                
            else:
                self.last_api_error = f"HTTP {response.status_code}"
                logger.warning(f"⚠️  {self.name}: Helius returned {response.status_code}")
                
        except requests.exceptions.Timeout:
            self.last_api_error = "Timeout"
            logger.warning(f"⚠️  {self.name}: Helius API timeout")
            
        except Exception as e:
            self.last_api_error = str(e)
            logger.error(f"❌ {self.name}: Error fetching from Helius: {e}")
        
        return transfers
    
    def fetch_recent_transfers(self, min_sol: float = None) -> List[WhaleTransfer]:
        """
        Fetch recent large SOL transfers with caching.
        
        Args:
            min_sol: Minimum SOL amount (default from config)
            
        Returns:
            List of WhaleTransfer objects
        """
        import config
        
        if min_sol is None:
            min_sol = getattr(config, 'WHALE_TRANSFER_THRESHOLD', 10000)
        
        now = datetime.now(timezone.utc)
        
        # Check cache validity
        if (self.last_fetch_time and self.cached_transfers and
            (now - self.last_fetch_time).total_seconds() < self.cache_duration_seconds):
            logger.debug(f"{self.name}: Using cached data ({len(self.cached_transfers)} transfers)")
            return self.cached_transfers
        
        # Fetch fresh data
        transfers = self._fetch_from_helius(min_sol)
        
        # Update cache
        if transfers:  # Only update cache if we got data
            self.last_fetch_time = now
            self.cached_transfers = transfers
            
            # Add to history (dedupe by signature)
            existing_sigs = {t.signature for t in self.transfer_history}
            for t in transfers:
                if t.signature not in existing_sigs:
                    self.transfer_history.append(t)
            
            # Trim history
            if len(self.transfer_history) > self.max_history:
                self.transfer_history = self.transfer_history[-self.max_history:]
        
        return self.cached_transfers
    
    def analyze_flow(self, hours: int = 4) -> Dict:
        """
        Analyze net exchange flow over a time period.
        
        Aggregates transfers to determine overall whale positioning.
        
        Args:
            hours: Lookback period in hours
            
        Returns:
            Dict with comprehensive flow analysis
        """
        import config
        
        result = {
            'period_hours': hours,
            'to_exchange_count': 0,
            'from_exchange_count': 0,
            'to_exchange_sol': 0.0,
            'from_exchange_sol': 0.0,
            'net_flow_sol': 0.0,  # Positive = inflow (bearish), Negative = outflow (bullish)
            'bias': 'neutral',
            'confidence': 'low',
            'score_adjustment_long': 0,
            'score_adjustment_short': 0,
            'exchanges_involved': set(),
            'largest_transfer': None,
            'api_available': self.api_available,
            'last_error': self.last_api_error
        }
        
        # Fetch latest transfers (will use cache if valid)
        self.fetch_recent_transfers()
        
        # Filter by time window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = [t for t in self.transfer_history if t.timestamp > cutoff]
        
        # Aggregate flows
        largest_amount = 0
        for transfer in recent:
            if transfer.direction == FlowDirection.TO_EXCHANGE:
                result['to_exchange_count'] += 1
                result['to_exchange_sol'] += transfer.amount_sol
                if transfer.exchange_name:
                    result['exchanges_involved'].add(transfer.exchange_name)
                    
            elif transfer.direction == FlowDirection.FROM_EXCHANGE:
                result['from_exchange_count'] += 1
                result['from_exchange_sol'] += transfer.amount_sol
                if transfer.exchange_name:
                    result['exchanges_involved'].add(transfer.exchange_name)
            
            if transfer.amount_sol > largest_amount:
                largest_amount = transfer.amount_sol
                result['largest_transfer'] = transfer.to_dict()
        
        # Convert set to list for JSON serialization
        result['exchanges_involved'] = list(result['exchanges_involved'])
        
        # Calculate net flow
        result['net_flow_sol'] = result['to_exchange_sol'] - result['from_exchange_sol']
        
        # Determine bias and score adjustments
        threshold = getattr(config, 'WHALE_FLOW_THRESHOLD', 50000)
        
        # Get score values from config
        HIGH_PENALTY = getattr(config, 'WHALE_HIGH_FLOW_PENALTY', 20)
        MED_PENALTY = getattr(config, 'WHALE_MED_FLOW_PENALTY', 10)
        HIGH_BOOST = getattr(config, 'WHALE_HIGH_FLOW_BOOST', 15)
        MED_BOOST = getattr(config, 'WHALE_MED_FLOW_BOOST', 7)
        
        if result['net_flow_sol'] > threshold * 2:
            # Strong net inflow = VERY BEARISH
            result['bias'] = 'bearish'
            result['confidence'] = 'high'
            result['score_adjustment_long'] = -HIGH_PENALTY
            result['score_adjustment_short'] = HIGH_BOOST
            
        elif result['net_flow_sol'] > threshold:
            # Moderate net inflow = BEARISH
            result['bias'] = 'bearish'
            result['confidence'] = 'medium'
            result['score_adjustment_long'] = -MED_PENALTY
            result['score_adjustment_short'] = MED_BOOST
            
        elif result['net_flow_sol'] < -threshold * 2:
            # Strong net outflow = VERY BULLISH
            result['bias'] = 'bullish'
            result['confidence'] = 'high'
            result['score_adjustment_long'] = HIGH_BOOST
            result['score_adjustment_short'] = -HIGH_PENALTY
            
        elif result['net_flow_sol'] < -threshold:
            # Moderate net outflow = BULLISH
            result['bias'] = 'bullish'
            result['confidence'] = 'medium'
            result['score_adjustment_long'] = MED_BOOST
            result['score_adjustment_short'] = -MED_PENALTY
        
        self.last_analysis = result
        return result
    
    def get_status(self) -> Dict:
        """
        Get current whale/flow status for dashboard display.
        
        Returns:
            Dict with status information
        """
        if not self.last_analysis:
            self.analyze_flow(hours=4)
        
        a = self.last_analysis or {}
        
        bias_emoji = {
            'bullish': '🐋📈',
            'bearish': '🐋📉',
            'neutral': '🐋➡️'
        }
        
        net_flow = a.get('net_flow_sol', 0)
        bias = a.get('bias', 'neutral')
        
        # Format flow nicely
        if abs(net_flow) >= 1000000:
            flow_str = f"{net_flow/1000000:+.1f}M SOL"
        elif abs(net_flow) >= 1000:
            flow_str = f"{net_flow/1000:+.1f}k SOL"
        else:
            flow_str = f"{net_flow:+,.0f} SOL"
        
        return {
            'enabled': self.api_available,
            'degraded_mode': not self.api_available,
            'bias': bias,
            'emoji': bias_emoji.get(bias, '❓'),
            'net_flow_sol': net_flow,
            'net_flow_display': flow_str,
            'to_exchange_sol': a.get('to_exchange_sol', 0),
            'from_exchange_sol': a.get('from_exchange_sol', 0),
            'confidence': a.get('confidence', 'low'),
            'transfer_count': a.get('to_exchange_count', 0) + a.get('from_exchange_count', 0),
            'exchanges': a.get('exchanges_involved', []),
            'score_long': a.get('score_adjustment_long', 0),
            'score_short': a.get('score_adjustment_short', 0),
            'last_error': a.get('last_error'),
            'message': f"{bias_emoji.get(bias, '')} Whales {bias.upper()} | {flow_str}"
        }


# Module-level convenience function
def get_whale_bias() -> str:
    """Quick check for current whale bias."""
    tracker = OnchainTracker()
    analysis = tracker.analyze_flow(hours=4)
    return analysis['bias']
