"""
Proof generator — Python simulation of the Cairo circuit.
Returns verified calldata for the Starknet BalanceVerifier contract.

Post-refactor notes:
  - The backend no longer receives the raw Bitcoin address or salt.
  - `generate_proof` (legacy, used in tests) still accepts address_hash + salt.
  - `generate_proof_no_salt` is the new production path: verifies only
    Merkle inclusion and threshold; skips the commitment re-derivation since
    the commitment was matched by the DB lookup in proof.py.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ProofGenerator:
    """
    Generates and verifies ZK proof calldata for the BalanceVerifier contract.

    For the hackathon MVP, this is a trusted-prover model:
    - The backend verifies the circuit logic in Python
    - Returns verified calldata for the frontend to submit on-chain
    - True ZK proofs (STARK/SNARK) are the production extension
      (see S2 sprint: Noir circuit + Barretenberg WASM + Garaga verifier)
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
        Verify full circuit logic (commitment + Merkle + threshold) and return calldata.

        Used in tests and legacy code paths where address_hash + salt are known.

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

        return self._build_proof_result(commitment, snapshot_root, merkle_path, threshold)

    def generate_proof_no_salt(
        self,
        address_hash: int,
        balance: int,
        merkle_path: List[Dict],
        snapshot_root: int,
        commitment: int,
        threshold: int,
    ) -> Dict[str, Any]:
        """
        Privacy-safe proof verification: skips commitment re-derivation.

        Used by the production proof route where the backend does NOT have
        the user's salt (salt stays in the browser). The commitment was already
        matched by DB lookup, so we only verify:
          1. balance >= threshold (if threshold > 0)
          2. Merkle inclusion: recompute root from (address_hash, balance) leaf + path

        Args:
            address_hash: Stored field element for the address.
            balance: Satoshis from the snapshot record.
            merkle_path: [{'value': int, 'direction': bool}, ...]
            snapshot_root: Merkle root as int.
            commitment: Poseidon(address_hash, salt) — used only for proof label.
            threshold: Min balance in satoshis.

        Returns:
            Dict with 'proof', 'public_signals', 'verified', 'calldata_ready'
        """
        from ..crypto.poseidon import PoseidonHash
        from ..crypto.merkle_tree import MerkleTree

        # 1. Threshold check
        if threshold > 0 and balance < threshold:
            raise ValueError(
                f"Balance {balance} satoshis is below threshold {threshold}"
            )

        # 2. Merkle inclusion (no salt needed — leaf is address_hash + balance)
        leaf_hash = PoseidonHash.hash_address_balance(address_hash, balance)
        if not MerkleTree.verify_proof_static(leaf_hash, merkle_path, snapshot_root):
            raise ValueError("Merkle proof verification failed")

        return self._build_proof_result(commitment, snapshot_root, merkle_path, threshold)

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
        if not MerkleTree.verify_proof_static(leaf_hash, merkle_path, snapshot_root):
            logger.error("Merkle proof verification failed")
            return False

        return True

    def _build_proof_result(
        self,
        commitment: int,
        snapshot_root: int,
        merkle_path: List[Dict],
        threshold: int,
    ) -> Dict[str, Any]:
        """Build the standardised proof result dict."""
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

    def generate_calldata(
        self,
        address_hash: int,
        salt: int,
        balance: int,
        merkle_path: List[Dict],
        commitment: int,
        threshold: int,
        block_height: Optional[int] = None,
    ) -> List[int]:
        """
        Encode calldata for BalanceVerifier.verify_proof() or verify_proof_at_height().

        Starknet ABI encoding for:
            verify_proof(address_hash, salt, balance, merkle_path, commitment, threshold)
            verify_proof_at_height(..., block_height)  ← if block_height is provided

        MerklePathElement serialises as: [value: felt252, direction: felt252 (0/1)]

        Returns:
            List of ints (felt252 values) to pass as Starknet calldata.
        """
        calldata: List[int] = [
            address_hash,
            salt,
            balance,              # u64 → single felt
            len(merkle_path),     # Array length prefix
        ]

        for element in merkle_path:
            calldata.append(element['value'])
            calldata.append(1 if element['direction'] else 0)

        calldata.append(commitment)
        calldata.append(threshold)  # u64 → single felt

        if block_height is not None:
            calldata.append(block_height)  # for verify_proof_at_height

        return calldata
