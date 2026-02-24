"""
Poseidon hash implementation for Starknet compatibility.
Uses starknet-py official implementation — no fallback.
"""
from typing import List
import logging

logger = logging.getLogger(__name__)

# Guard: fail loudly if starknet-py is not available
try:
    from starknet_py.hash.poseidon import poseidon_hash, poseidon_hash_many
except ImportError as e:
    raise ImportError(
        "starknet-py is required for Poseidon hashing. "
        "Install it with: pip install starknet-py==0.20.0"
    ) from e


class PoseidonHash:
    """Poseidon hash utilities compatible with Starknet Cairo contracts."""

    # Starknet field prime
    PRIME = 2**251 + 17 * 2**192 + 1

    @staticmethod
    def hash(x: int, y: int) -> int:
        """
        Compute Poseidon(x, y) — matches Cairo PoseidonTrait::new().update(x).update(y).finalize().

        Args:
            x: First field element (int)
            y: Second field element (int)

        Returns:
            Poseidon hash as int
        """
        return poseidon_hash(x, y)

    @staticmethod
    def hash_many(inputs: List[int]) -> int:
        """
        Compute Poseidon hash of a list of field elements.

        Args:
            inputs: List of integers (field elements)

        Returns:
            Hash output
        """
        return poseidon_hash_many(inputs)

    @staticmethod
    def hash_bytes(data: bytes) -> int:
        """
        Hash bytes by reducing to field element first.

        Args:
            data: Input bytes

        Returns:
            Hash output
        """
        val = int.from_bytes(data, 'big')
        return val % PoseidonHash.PRIME

    @staticmethod
    def hash_address_balance(address_hash: int, balance: int) -> int:
        """
        Compute leaf hash: Poseidon(address_hash, balance).
        Matches Cairo: PoseidonTrait::new().update(address_hash).update(balance.into()).finalize()
        """
        return PoseidonHash.hash(address_hash, balance)

    @staticmethod
    def hash_commitment(address_hash: int, salt: int) -> int:
        """
        Compute commitment: Poseidon(address_hash, salt).
        Matches Cairo: PoseidonTrait::new().update(address_hash).update(salt).finalize()
        """
        return PoseidonHash.hash(address_hash, salt)
