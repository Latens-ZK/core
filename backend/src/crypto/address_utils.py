"""
Bitcoin address utilities with proper validation.
Uses python-bitcoinlib for format validation where available.
"""
import hashlib
import logging

logger = logging.getLogger(__name__)

# Starknet field prime
PRIME = 2**251 + 17 * 2**192 + 1


class AddressUtils:
    """Utilities for processing Bitcoin addresses."""

    @staticmethod
    def get_address_hash(address: str) -> int:
        """
        Convert Bitcoin address to a single Starknet field element (felt252).

        Strategy: SHA256(utf8(address)) % PRIME
        This is documented as the canonical address representation for Latens.

        Args:
            address: Bitcoin address string

        Returns:
            Integer < PRIME for use in Cairo
        """
        h = hashlib.sha256(address.encode('utf-8')).digest()
        val = int.from_bytes(h, 'big')
        return val % PRIME

    @staticmethod
    def validate_address(address: str) -> bool:
        """
        Validate Bitcoin address format.
        Supports: Legacy (P2PKH '1...'), P2SH ('3...'), Bech32 ('bc1q...'), Bech32m ('bc1p...').

        Args:
            address: Address string

        Returns:
            True if valid, False otherwise
        """
        if not address or not isinstance(address, str):
            return False

        address = address.strip()

        # Try using python-bitcoinlib for proper validation
        try:
            import bitcoin.base58
            import bitcoin.bech32

            if address.startswith(('1', '3')):
                # Legacy / P2SH — Base58Check
                try:
                    decoded = bitcoin.base58.decode(address)
                    return len(decoded) == 25  # version byte + 20-byte hash + 4-byte checksum
                except Exception:
                    return False
            elif address.lower().startswith('bc1'):
                # Bech32 / Bech32m
                hrp, data = bitcoin.bech32.decode(address)
                return hrp == 'bc' and data is not None
            else:
                return False

        except ImportError:
            # Fallback: regex-style length + prefix check
            logger.warning("python-bitcoinlib not available, using basic address validation")
            return AddressUtils._validate_basic(address)

    @staticmethod
    def _validate_basic(address: str) -> bool:
        """Basic prefix + length validation fallback."""
        if len(address) < 26 or len(address) > 90:
            return False
        if not address.startswith(('1', '3', 'bc1')):
            return False
        # Check character set (Base58 or Bech32)
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        bech32_chars = set('qpzry9x8gf2tvdw0s3jn54khce6mua7l')
        if address.lower().startswith('bc1'):
            return all(c in bech32_chars for c in address[3:].lower())
        else:
            return all(c in base58_chars for c in address)


if __name__ == "__main__":
    test_addrs = [
        "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",  # valid Bech32
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",             # Satoshi genesis
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",             # P2SH
        "not-an-address",                                  # invalid
    ]
    for addr in test_addrs:
        valid = AddressUtils.validate_address(addr)
        h = AddressUtils.get_address_hash(addr) if valid else None
        print(f"{'✓' if valid else '✗'} {addr[:30]:32} hash={hex(h)[:16] if h else 'N/A'}")
