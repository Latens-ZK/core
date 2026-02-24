"""
Proof generator — Python simulation of the Cairo circuit.
Returns verified calldata for the Starknet BalanceVerifier contract.
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ProofGenerator:
    """
    Generates and verifies ZK proof calldata for the BalanceVerifier contract.

    For the hackathon MVP, this is a trusted-prover model:
    - The backend verifies the circuit logic in Python
    - Returns verified calldata for the frontend to submit on-chain
    - True ZK proofs (STARK/SNARK) are the production extension
    """

    def generate_proof(
        self,
        address_hash: int,
        salt: int,
        balance: int,
        merkle_path: List[Dict],
        snapshot_root: int,
        commitment: int,
        threshold: int,
    ) -> Dict[str, Any]:
        """
        Verify circuit logic and return calldata.

        Args:
            address_hash: SHA256(address) % PRIME
            salt: Random 32-byte value from user browser
            balance: Satoshis
            merkle_path: [{'value': int, 'direction': bool}, ...]
            snapshot_root: Merkle root as int
            commitment: Poseidon(address_hash, salt)
            threshold: Min balance in satoshis

        Returns:
            Dict with 'proof', 'public_signals', 'verified', 'calldata_ready'
        """
        verified = self.verify_circuit_logic(
            address_hash=address_hash,
            salt=salt,
            balance=balance,
            merkle_path=merkle_path,
            snapshot_root=snapshot_root,
            commitment=commitment,
            threshold=threshold,
        )

        if not verified:
            raise ValueError("Circuit logic verification failed — proof would be invalid on-chain")

        # Encode proof as structured calldata identifier
        proof_str = (
            f"LATENS_PROOF_v1:"
            f"commitment={hex(commitment)}:"
            f"root={hex(snapshot_root)}:"
            f"depth={len(merkle_path)}:"
            f"threshold={threshold}"
        )

        return {
            'proof': proof_str,
            'public_signals': [
                hex(snapshot_root),
                hex(commitment),
                threshold,
            ],
            'verified': True,
            'calldata_ready': True,
        }

    def verify_circuit_logic(
        self,
        address_hash: int,
        salt: int,
        balance: int,
        merkle_path: List[Dict],
        snapshot_root: int,
        commitment: int,
        threshold: int,
    ) -> bool:
        """
        Python simulation of the Cairo BalanceVerifier circuit.
        Mirrors the exact logic in contracts/src/balance_verifier.cairo.
        """
        from ..crypto.poseidon import PoseidonHash
        from ..crypto.merkle_tree import MerkleTree

        # 1. Verify commitment: Poseidon(address_hash, salt) == commitment
        expected_commitment = PoseidonHash.hash_commitment(address_hash, salt)
        if expected_commitment != commitment:
            logger.error(f"Commitment mismatch: computed {hex(expected_commitment)} != {hex(commitment)}")
            return False

        # 2. Verify threshold
        if threshold > 0 and balance < threshold:
            logger.error(f"Balance {balance} < threshold {threshold}")
            return False

        # 3. Verify Merkle inclusion
        leaf_hash = PoseidonHash.hash_address_balance(address_hash, balance)
        tree = MerkleTree()
        if not tree.verify_proof(leaf_hash, merkle_path, snapshot_root):
            logger.error("Merkle proof verification failed")
            return False

        return True
