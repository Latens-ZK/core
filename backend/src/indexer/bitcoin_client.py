"""
Bitcoin client — multi-provider UTXO data fetching.

Provider priority (configurable via BTC_API_PROVIDER env var):
  1. xverse    — Xverse wallet REST API (P2 integration goal)
  2. blockstream — Blockstream esplora API (default fallback)
  3. mempool   — mempool.space (second fallback)

Switch:
  BTC_API_PROVIDER=xverse      → use Xverse first
  BTC_API_PROVIDER=blockstream → use Blockstream (default)
  BTC_API_PROVIDER=mempool     → use mempool.space

Auto-fallback: if the preferred provider fails, the client will
automatically retry with the next provider in the list.
"""
import os
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

# ─── Provider Backends ────────────────────────────────────────────────────────

class _BlockstreamProvider:
    """Blockstream esplora public API (default)."""
    BASE = "https://blockstream.info/api"

    def fetch_latest_block_height(self, session: requests.Session) -> int:
        r = session.get(f"{self.BASE}/blocks/tip/height", timeout=30)
        r.raise_for_status()
        return int(r.text.strip())

    def fetch_block_hash(self, height: int, session: requests.Session) -> str:
        r = session.get(f"{self.BASE}/block-height/{height}", timeout=30)
        r.raise_for_status()
        return r.text.strip()

    def fetch_block(self, block_hash: str, session: requests.Session) -> Dict:
        r = session.get(f"{self.BASE}/block/{block_hash}", timeout=30)
        r.raise_for_status()
        return r.json()

    def fetch_address_utxos(self, address: str, session: requests.Session) -> List[Dict]:
        """Returns list of {value, status: {confirmed, block_height}}."""
        r = session.get(f"{self.BASE}/address/{address}/utxo", timeout=30)
        r.raise_for_status()
        return r.json()


class _MempoolProvider:
    """mempool.space API — same Esplora-compatible schema as Blockstream."""
    BASE = "https://mempool.space/api"

    def fetch_latest_block_height(self, session: requests.Session) -> int:
        r = session.get(f"{self.BASE}/blocks/tip/height", timeout=30)
        r.raise_for_status()
        return int(r.text.strip())

    def fetch_block_hash(self, height: int, session: requests.Session) -> str:
        r = session.get(f"{self.BASE}/block-height/{height}", timeout=30)
        r.raise_for_status()
        return r.text.strip()

    def fetch_block(self, block_hash: str, session: requests.Session) -> Dict:
        r = session.get(f"{self.BASE}/block/{block_hash}", timeout=30)
        r.raise_for_status()
        return r.json()

    def fetch_address_utxos(self, address: str, session: requests.Session) -> List[Dict]:
        r = session.get(f"{self.BASE}/address/{address}/utxo", timeout=30)
        r.raise_for_status()
        return r.json()


class _XverseProvider:
    """
    Xverse wallet REST API (P2 integration goal — PRD §3.4).

    Xverse API reference:
      https://docs.xverse.app/api/reference/

    UTXO endpoint:
      GET https://api.xverse.app/v1/address/{address}/utxo
      Response: { total_utxos: int, utxos: [{txid, vout, value, block_height, ...}] }

    NOTE: The Xverse endpoint returns address- and network-specific data.
    Auto-detected from address prefix (mainnet/testnet).

    Normalizes to Blockstream-compatible format for uniform downstream processing.
    """
    MAINNET_BASE = "https://api.xverse.app/v1"
    TESTNET_BASE = "https://api-testnet.xverse.app/v1"

    def _base(self, address: str) -> str:
        # Testnet addresses start with m, n, tb1, 2
        if address.startswith(('m', 'n', 'tb1', '2')):
            return self.TESTNET_BASE
        return self.MAINNET_BASE

    def fetch_latest_block_height(self, session: requests.Session) -> int:
        # Xverse doesn't expose a direct tip-height endpoint; fall back to Blockstream
        logger.info("Xverse: no tip-height endpoint — falling back to Blockstream for chain tip.")
        return _BlockstreamProvider().fetch_latest_block_height(session)

    def fetch_block_hash(self, height: int, session: requests.Session) -> str:
        return _BlockstreamProvider().fetch_block_hash(height, session)

    def fetch_block(self, block_hash: str, session: requests.Session) -> Dict:
        return _BlockstreamProvider().fetch_block(block_hash, session)

    def fetch_address_utxos(self, address: str, session: requests.Session) -> List[Dict]:
        """
        Fetch UTXOs for an address from Xverse API.

        Normalizes Xverse response to Blockstream-compatible format:
          {
            "value": int,          # satoshis
            "status": {
              "confirmed": bool,
              "block_height": int
            }
          }
        """
        base = self._base(address)
        r = session.get(f"{base}/address/{address}/utxo", timeout=30)

        if r.status_code == 404:
            # Xverse returns 404 for addresses with no UTXO history — treat as empty
            logger.debug(f"Xverse: address {address} has no UTXOs (404)")
            return []

        r.raise_for_status()
        data = r.json()

        # Xverse response: {"total_utxos": N, "utxos": [...]}
        raw_utxos = data.get("utxos", []) if isinstance(data, dict) else data

        normalized = []
        for utxo in raw_utxos:
            block_height = utxo.get("block_height") or utxo.get("status", {}).get("block_height", 0)
            confirmed = bool(block_height and block_height > 0)
            normalized.append({
                "txid": utxo.get("txid", ""),
                "vout": utxo.get("vout", 0),
                "value": utxo.get("value", 0),
                "status": {
                    "confirmed": confirmed,
                    "block_height": block_height or 0,
                },
            })

        return normalized


# ─── Provider registry ────────────────────────────────────────────────────────

_PROVIDERS = {
    "blockstream": _BlockstreamProvider,
    "mempool": _MempoolProvider,
    "xverse": _XverseProvider,
}

_FALLBACK_ORDER = ["xverse", "blockstream", "mempool"]


# ─── Main client ─────────────────────────────────────────────────────────────

class BitcoinClient:
    """
    Multi-provider Bitcoin data client.

    Provider selected via BTC_API_PROVIDER env var (default: blockstream).
    Falls back to other providers on failure.

    Example:
        BTC_API_PROVIDER=xverse python -m backend.src.indexer.bitcoin_client
    """

    def __init__(self, preferred_provider: Optional[str] = None):
        chosen = (
            preferred_provider
            or os.getenv("BTC_API_PROVIDER", "blockstream")
        ).lower()

        if chosen not in _PROVIDERS:
            logger.warning(f"Unknown BTC_API_PROVIDER '{chosen}'. Defaulting to 'blockstream'.")
            chosen = "blockstream"

        self._preferred = chosen
        self._provider_order: List[str] = [chosen] + [
            p for p in _FALLBACK_ORDER if p != chosen
        ]
        self.session = requests.Session()

        logger.info(f"BitcoinClient: primary provider = '{chosen}' | fallback order = {self._provider_order}")

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_provider(self, name: str):
        return _PROVIDERS[name]()

    def _with_fallback(self, method_name: str, *args, **kwargs):
        """
        Call method_name on the preferred provider; fall back to others on failure.
        """
        last_error: Optional[Exception] = None
        for provider_name in self._provider_order:
            provider = self._get_provider(provider_name)
            if not hasattr(provider, method_name):
                continue
            try:
                result = getattr(provider, method_name)(*args, session=self.session, **kwargs)
                if provider_name != self._preferred:
                    logger.info(f"[fallback] {provider_name}.{method_name} succeeded.")
                return result
            except Exception as exc:
                logger.warning(f"{provider_name}.{method_name} failed: {exc}")
                last_error = exc
                time.sleep(1)

        raise RuntimeError(
            f"All providers failed for {method_name}: {last_error}"
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_latest_block_height(self) -> int:
        """Return the current blockchain tip height."""
        return self._with_fallback("fetch_latest_block_height")

    def fetch_block_hash(self, height: int) -> str:
        """Fetch block hash at given height."""
        return self._with_fallback("fetch_block_hash", height)

    def fetch_block(self, block_hash: str) -> Dict:
        """Fetch block metadata by hash."""
        return self._with_fallback("fetch_block", block_hash)

    def fetch_address_utxos(self, address: str) -> List[Dict]:
        """
        Fetch all UTXOs for address.
        Returns Blockstream-schema dicts: {value, status: {confirmed, block_height}}.
        """
        return self._with_fallback("fetch_address_utxos", address)

    def get_address_balance(self, address: str) -> int:
        """
        Get total confirmed balance for address in satoshis (at chain tip).
        """
        utxos = self.fetch_address_utxos(address)
        return sum(
            utxo['value']
            for utxo in utxos
            if utxo.get('status', {}).get('confirmed', False)
        )

    def fetch_utxos_at_height(
        self,
        block_height: int,
        addresses: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Fetch confirmed balances as of `block_height` for the given addresses.

        For each address: sum only UTXOs confirmed at or before `block_height`.

        Args:
            block_height: Target block height (inclusive).
            addresses: Bitcoin addresses to query. Defaults to demo list.

        Returns:
            Dict mapping address → confirmed balance in satoshis.
            Addresses with zero balance at target height are omitted.
        """
        if addresses is None:
            logger.info("No address list supplied — using default demo addresses.")
            addresses = _DEMO_ADDRESSES

        logger.info(
            f"Fetching balances for {len(addresses)} addresses at height {block_height} "
            f"via '{self._preferred}'"
        )
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

    # ── Esplora-compatible helpers (kept for backward compat) ──────────────────

    def fetch_block_txids(self, block_hash: str) -> List[str]:
        """Fetch transaction IDs in a block (Blockstream/mempool only)."""
        r = self.session.get(
            f"https://blockstream.info/api/block/{block_hash}/txids", timeout=30
        )
        r.raise_for_status()
        return r.json()

    def fetch_transaction(self, txid: str) -> Dict:
        """Fetch transaction data (Blockstream only)."""
        r = self.session.get(
            f"https://blockstream.info/api/tx/{txid}", timeout=30
        )
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    provider = sys.argv[1] if len(sys.argv) > 1 else "blockstream"
    client = BitcoinClient(preferred_provider=provider)

    tip = client.fetch_latest_block_height()
    print(f"Chain tip: {tip}")

    block_hash = client.fetch_block_hash(tip)
    print(f"Tip block hash: {block_hash}")

    # UTXO balance for genesis coinbase
    balance = client.get_address_balance("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    print(f"Genesis coinbase balance: {balance:,} sat")
