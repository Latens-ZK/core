"""
Balance aggregator for processing Bitcoin UTXOs.
"""
from typing import Dict, List, Tuple
import logging
from collections import defaultdict

from ..crypto.address_utils import AddressUtils

logger = logging.getLogger(__name__)


class BalanceAggregator:
    """Aggregates UTXO data into address balances."""
    
    def __init__(self, min_balance_satoshis: int = 1_000_000):
        """
        Initialize aggregator.
        
        Args:
            min_balance_satoshis: Minimum balance to include (default 0.01 BTC)
        """
        self.min_balance = min_balance_satoshis
        
    def aggregate_balances(self, address_balances: Dict[str, int]) -> Dict[str, int]:
        """
        Aggregate and filter balances.
        
        Args:
            address_balances: Raw address to balance mapping
            
        Returns:
            Filtered and sorted address balances
        """
        logger.info(f"Aggregating balances for {len(address_balances)} addresses")
        
        # Filter zero balances and below minimum
        filtered = {
            addr: balance 
            for addr, balance in address_balances.items() 
            if balance >= self.min_balance
        }
        
        logger.info(f"After filtering: {len(filtered)} addresses with balance >= {self.min_balance} satoshis")
        
        return filtered
    
    def sort_addresses_deterministic(self, address_balances: Dict[str, int]) -> List[Tuple[str, int]]:
        """
        Sort addresses deterministically by ascending address_hash (SHA-256 mod P as int).

        Per PRD requirement MRK-01: leaf nodes MUST be ordered by ascending
        address_hash so that Merkle tree construction is reproducible across
        runs and environments.

        Args:
            address_balances: Address to balance mapping

        Returns:
            List of (address, balance) tuples sorted by address_hash ascending
        """
        sorted_items = sorted(
            address_balances.items(),
            key=lambda x: AddressUtils.get_address_hash(x[0]),
        )
        logger.info(f"Sorted {len(sorted_items)} addresses by address_hash (deterministic)")
        return sorted_items
    
    def validate_balances(self, address_balances: Dict[str, int]) -> bool:
        """
        Validate balance data for correctness.
        
        Args:
            address_balances: Address to balance mapping
            
        Returns:
            True if valid, raises exception otherwise
        """
        # Check for negative balances
        negative = [addr for addr, bal in address_balances.items() if bal < 0]
        if negative:
            raise ValueError(f"Found {len(negative)} addresses with negative balances")
        
        # Check for duplicate addresses (should not happen with dict)
        if len(address_balances) != len(set(address_balances.keys())):
            raise ValueError("Duplicate addresses found")
        
        # Check for overflow (Bitcoin max supply is 21M BTC = 2.1e15 satoshis)
        MAX_SATOSHIS = 21_000_000 * 100_000_000
        overflow = [addr for addr, bal in address_balances.items() if bal > MAX_SATOSHIS]
        if overflow:
            raise ValueError(f"Found {len(overflow)} addresses with impossible balances")
        
        logger.info("Balance validation passed")
        return True
    
    def get_statistics(self, address_balances: Dict[str, int]) -> Dict:
        """
        Get statistics about the balance distribution.
        
        Args:
            address_balances: Address to balance mapping
            
        Returns:
            Statistics dictionary
        """
        if not address_balances:
            return {
                'total_addresses': 0,
                'total_balance': 0,
                'min_balance': 0,
                'max_balance': 0,
                'avg_balance': 0
            }
        
        balances = list(address_balances.values())
        total_balance = sum(balances)
        
        stats = {
            'total_addresses': len(address_balances),
            'total_balance': total_balance,
            'total_btc': total_balance / 100_000_000,
            'min_balance': min(balances),
            'max_balance': max(balances),
            'avg_balance': total_balance // len(balances),
            'median_balance': sorted(balances)[len(balances) // 2]
        }
        
        logger.info(f"Statistics: {stats}")
        return stats


if __name__ == "__main__":
    # Test the aggregator
    logging.basicConfig(level=logging.INFO)
    
    # Sample data
    test_balances = {
        'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh': 150_000_000,  # 1.5 BTC
        'bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4': 50_000_000,   # 0.5 BTC
        '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa': 500_000,              # 0.005 BTC (below min)
        'bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3': 1_000_000_000  # 10 BTC
    }
    
    aggregator = BalanceAggregator(min_balance_satoshis=1_000_000)
    
    # Validate
    aggregator.validate_balances(test_balances)
    
    # Filter
    filtered = aggregator.aggregate_balances(test_balances)
    print(f"\nFiltered addresses: {len(filtered)}")
    
    # Sort
    sorted_balances = aggregator.sort_addresses_deterministic(filtered)
    print("\nSorted addresses:")
    for addr, balance in sorted_balances:
        print(f"  {addr[:20]}... : {balance / 100_000_000:.8f} BTC")
    
    # Statistics
    stats = aggregator.get_statistics(filtered)
    print(f"\nStatistics:")
    print(f"  Total addresses: {stats['total_addresses']}")
    print(f"  Total BTC: {stats['total_btc']:.8f}")
    print(f"  Average balance: {stats['avg_balance'] / 100_000_000:.8f} BTC")
