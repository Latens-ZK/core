"""
Bitcoin client for fetching blockchain data from Blockstream API.
"""
import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BitcoinClient:
    """Client for interacting with Bitcoin blockchain via Blockstream API."""
    
    def __init__(self, api_url: str = "https://blockstream.info/api"):
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        
    def fetch_block_hash(self, height: int) -> str:
        """
        Fetch block hash at given height.
        
        Args:
            height: Block height
            
        Returns:
            Block hash as hex string
        """
        url = f"{self.api_url}/block-height/{height}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.text.strip()
    
    def fetch_block(self, block_hash: str) -> Dict:
        """
        Fetch block data by hash.
        
        Args:
            block_hash: Block hash
            
        Returns:
            Block data dictionary
        """
        url = f"{self.api_url}/block/{block_hash}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def fetch_block_txids(self, block_hash: str) -> List[str]:
        """
        Fetch all transaction IDs in a block.
        
        Args:
            block_hash: Block hash
            
        Returns:
            List of transaction IDs
        """
        url = f"{self.api_url}/block/{block_hash}/txids"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def fetch_transaction(self, txid: str) -> Dict:
        """
        Fetch transaction data.
        
        Args:
            txid: Transaction ID
            
        Returns:
            Transaction data dictionary
        """
        url = f"{self.api_url}/tx/{txid}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def fetch_address_utxos(self, address: str) -> List[Dict]:
        """
        Fetch UTXOs for a specific address.
        
        Args:
            address: Bitcoin address
            
        Returns:
            List of UTXO dictionaries
        """
        url = f"{self.api_url}/address/{address}/utxo"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_address_balance(self, address: str) -> int:
        """
        Get total balance for an address in satoshis.
        
        Args:
            address: Bitcoin address
            
        Returns:
            Balance in satoshis
        """
        utxos = self.fetch_address_utxos(address)
        return sum(utxo['value'] for utxo in utxos)
    
    def fetch_utxos_at_height(self, block_height: int, max_blocks: int = 1) -> Dict[str, int]:
        """
        Fetch all UTXOs at a specific block height.
        This is a simplified version for MVP - in production, you'd need
        to maintain a full UTXO set or use a Bitcoin node.
        
        Args:
            block_height: Target block height
            max_blocks: Number of recent blocks to scan (for demo purposes)
            
        Returns:
            Dictionary mapping address to balance in satoshis
        """
        logger.info(f"Fetching UTXOs at block height {block_height}")
        
        address_balances: Dict[str, int] = {}
        
        # For MVP: This is a simplified approach
        # In production, you'd need to:
        # 1. Maintain full UTXO set from genesis
        # 2. Or use a Bitcoin node with txindex
        # 3. Or use a dedicated indexer like Electrs
        
        for height in range(block_height - max_blocks + 1, block_height + 1):
            try:
                block_hash = self.fetch_block_hash(height)
                txids = self.fetch_block_txids(block_hash)
                
                logger.info(f"Processing block {height} with {len(txids)} transactions")
                
                for txid in txids:
                    tx = self.fetch_transaction(txid)
                    
                    # Process outputs
                    for vout in tx.get('vout', []):
                        if 'scriptpubkey_address' in vout:
                            address = vout['scriptpubkey_address']
                            value = vout['value']
                            
                            if address not in address_balances:
                                address_balances[address] = 0
                            address_balances[address] += value
                            
            except Exception as e:
                logger.error(f"Error processing block {height}: {e}")
                continue
        
        return address_balances


if __name__ == "__main__":
    # Test the client
    logging.basicConfig(level=logging.INFO)
    
    client = BitcoinClient()
    
    # Test fetching latest block
    try:
        latest_height = 800000  # Example height
        block_hash = client.fetch_block_hash(latest_height)
        print(f"Block hash at height {latest_height}: {block_hash}")
        
        block = client.fetch_block(block_hash)
        print(f"Block timestamp: {block.get('timestamp')}")
        print(f"Number of transactions: {block.get('tx_count')}")
        
    except Exception as e:
        print(f"Error: {e}")
