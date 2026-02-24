"""
Merkle tree implementation using Poseidon hash.
Direction encoding: bool — false = sibling is left, true = sibling is right.
Matches Cairo MerklePathElement { value: felt252, direction: bool }.
"""
from typing import List, Dict, Optional
import logging
from .poseidon import PoseidonHash

logger = logging.getLogger(__name__)


class MerkleTree:
    """Poseidon-hashed Merkle tree for Bitcoin state snapshots."""

    def __init__(self, leaves: List[int] = None):
        """
        Args:
            leaves: List of leaf hashes (integers / felt252 values)
        """
        self.leaves = leaves or []
        self.tree: List[List[int]] = []
        self.root: Optional[int] = None

        if self.leaves:
            self.build(self.leaves)

    def build(self, leaves: List[int]) -> int:
        """Build the Merkle tree from leaves and return the root."""
        if not leaves:
            self.root = 0
            return 0

        self.leaves = leaves
        self.tree = [list(leaves)]

        current_layer = list(leaves)
        while len(current_layer) > 1:
            next_layer = []
            for i in range(0, len(current_layer), 2):
                left = current_layer[i]
                # Duplicate last element if odd count
                right = current_layer[i + 1] if i + 1 < len(current_layer) else left
                node_hash = PoseidonHash.hash(left, right)
                next_layer.append(node_hash)

            self.tree.append(next_layer)
            current_layer = next_layer

        self.root = current_layer[0]
        logger.info(f"Built Merkle tree: {len(leaves)} leaves, root={hex(self.root)}")
        return self.root

    def get_proof(self, leaf_index: int) -> List[Dict]:
        """
        Generate Merkle proof for a leaf.

        Returns:
            List of dicts: [{'value': int, 'direction': bool}, ...]
            direction=False → sibling is LEFT  (current node is the right child)
            direction=True  → sibling is RIGHT (current node is the left child)
        """
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise ValueError(f"Leaf index {leaf_index} out of bounds (tree has {len(self.leaves)} leaves)")

        proof = []
        current_index = leaf_index

        # Traverse up the tree (all layers except root)
        for layer in self.tree[:-1]:
            is_right_child = current_index % 2 == 1

            if is_right_child:
                sibling_index = current_index - 1
            else:
                sibling_index = current_index + 1

            # Handle odd-count layer (last node paired with itself)
            if sibling_index >= len(layer):
                sibling_index = current_index

            sibling_val = layer[sibling_index]

            # direction semantics:
            #   current is right child → sibling is LEFT → direction = False
            #   current is left child  → sibling is RIGHT → direction = True
            direction: bool = not is_right_child  # True when sibling is to the right

            proof.append({
                'value': sibling_val,
                'direction': direction
            })

            current_index //= 2

        return proof

    def verify_proof(self, leaf: int, proof: List[Dict], root: int) -> bool:
        """
        Verify a Merkle proof.

        Args:
            leaf: Leaf hash (int)
            proof: List of {'value': int, 'direction': bool}
            root: Expected Merkle root

        Returns:
            True if proof is valid
        """
        current_hash = leaf

        for item in proof:
            sibling = item['value']
            direction = item['direction']  # bool

            if not direction:
                # Sibling is LEFT → hash(sibling, current)
                current_hash = PoseidonHash.hash(sibling, current_hash)
            else:
                # Sibling is RIGHT → hash(current, sibling)
                current_hash = PoseidonHash.hash(current_hash, sibling)

        return current_hash == root


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    leaves = [1, 2, 3, 4, 5]
    tree = MerkleTree(leaves)
    print(f"Root: {hex(tree.root)}")
    for i, leaf in enumerate(leaves):
        proof = tree.get_proof(i)
        valid = tree.verify_proof(leaf, proof, tree.root)
        assert valid, f"Proof failed for leaf {i}"
        print(f"  Leaf {i}: proof valid ✓")
