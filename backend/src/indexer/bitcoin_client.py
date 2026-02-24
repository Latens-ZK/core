"""
Bitcoin client for fetching blockchain data from Blockstream API.
"""
import time
import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Default demo addresses used when no address list is provided
_DEMO_ADDRESSES: List[str] = [
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el",
    "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ",
    "1KFHE7w8BhaENAswwryaoccDb6qcT6DbYY",
    "3Kzh9qAqVWQhEsfQz7zEQL1EuSx5tyNLNS",
    "bc1qazcm763858nkj2dj986etajv6wquslv8uxjj8",
]


class BitcoinClient:
    """Client for interacting with Bitcoin blockchain via Blockstream API."""

    def __init__(self, api_url: str = "https://blockstream.info/api"):
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get(self, url: str, retries: int = 4) -> requests.Response:
        """GET with exponential backoff for rate-limit (HTTP 429) and transient errors."""
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"Rate limited on {url}. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                if attempt == retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(f"Request failed ({exc}). Retrying in {wait}s...")
                time.sleep(wait)
        raise RuntimeError(f"Unreachable: exhausted retries for {url}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_latest_block_height(self) -> int:
        """Return the current blockchain tip height."""
        url = f"{self.api_url}/blocks/tip/height"
        resp = self._get(url)
        return int(resp.text.strip())

    def fetch_block_hash(self, height: int) -> str:
        """
        Fetch block hash at given height.

        Args:
            height: Block height

        Returns:
            Block hash as hex string
        """
        url = f"{self.api_url}/block-height/{height}"
        resp = self._get(url)
        return resp.text.strip()

    def fetch_block(self, block_hash: str) -> Dict:
        """
        Fetch block data by hash.

        Args:
            block_hash: Block hash

        Returns:
            Block data dictionary
        """
        url = f"{self.api_url}/block/{block_hash}"
        resp = self._get(url)
        return resp.json()

    def fetch_block_txids(self, block_hash: str) -> List[str]:
        """
        Fetch all transaction IDs in a block.

        Args:
            block_hash: Block hash

        Returns:
            List of transaction IDs
        """
        url = f"{self.api_url}/block/{block_hash}/txids"
        resp = self._get(url)
        return resp.json()

    def fetch_transaction(self, txid: str) -> Dict:
        """
        Fetch transaction data.

        Args:
            txid: Transaction ID

        Returns:
            Transaction data dictionary
        """
        url = f"{self.api_url}/tx/{txid}"
        resp = self._get(url)
        return resp.json()

    def fetch_address_utxos(self, address: str) -> List[Dict]:
        """
        Fetch all current UTXOs for a specific address.

        Args:
            address: Bitcoin address

        Returns:
            List of UTXO dictionaries (each has 'value', 'status.block_height', etc.)
        """
        url = f"{self.api_url}/address/{address}/utxo"
        resp = self._get(url)
        return resp.json()

    def get_address_balance(self, address: str) -> int:
        """
        Get total confirmed balance for an address in satoshis (at chain tip).

        Args:
            address: Bitcoin address

        Returns:
            Balance in satoshis
        """
        utxos = self.fetch_address_utxos(address)
        return sum(utxo['value'] for utxo in utxos if utxo.get('status', {}).get('confirmed', False))

    def fetch_utxos_at_height(
        self,
        block_height: int,
        addresses: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Fetch confirmed balances as of `block_height` for the given addresses.

        For each address the method calls ``/address/{addr}/utxo`` and sums
        only UTXOs whose ``status.block_height`` is <= ``block_height`` AND
        whose ``status.confirmed`` is True.  UTXOs confirmed after the target
        height are excluded, giving a deterministic balance snapshot.

        Args:
            block_height: Target block height (inclusive).
            addresses: Bitcoin addresses to query.  If omitted the built-in
                       demo address list is used (suitable for testing).

        Returns:
            Dict mapping address -> confirmed balance in satoshis at that height.
            Addresses with zero balance at the target height are omitted.
        """
        if addresses is None:
            logger.info("No address list supplied — using default demo addresses.")
            addresses = _DEMO_ADDRESSES

        logger.info(f"Fetching balances for {len(addresses)} addresses at height {block_height}")
        result: Dict[str, int] = {}

        for address in addresses:
            try:
                utxos = self.fetch_address_utxos(address)
                balance = sum(
                    utxo['value']
                    for utxo in utxos
                    if utxo.get('status', {}).get('confirmed', False)
                    and utxo.get('status', {}).get('block_height', 0) <= block_height
                )
                if balance > 0:
                    result[address] = balance
                    logger.debug(f"{address}: {balance:,} sat")
            except Exception as exc:
                logger.error(f"Failed to fetch UTXOs for {address}: {exc}")

        logger.info(
            f"Collected balances for {len(result)}/{len(addresses)} addresses "
            f"with UTXOs confirmed at height {block_height}"
        )
        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = BitcoinClient()

    tip = client.fetch_latest_block_height()
    print(f"Chain tip: {tip}")

    block_hash = client.fetch_block_hash(tip)
    print(f"Tip block hash: {block_hash}")
