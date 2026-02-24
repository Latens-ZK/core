import pytest
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.crypto.merkle_tree import MerkleTree
from src.crypto.poseidon import PoseidonHash

def test_merkle_tree_construction():
    # Arrange
    leaves = [1, 2, 3, 4]
    """
    Tree structure:
        Root
       /    \
      H12   H34
     /  \   /  \
    1    2 3    4
    """
    
    # Act
    tree = MerkleTree(leaves)
    
    # Assert
    # Level 1
    h12 = PoseidonHash.hash(1, 2)
    h34 = PoseidonHash.hash(3, 4)
    # Root
    root = PoseidonHash.hash(h12, h34)
    
    assert tree.root == root

def test_merkle_proof_verification():
    # Arrange
    leaves = [10, 20, 30, 40, 50]
    tree = MerkleTree(leaves)
    root = tree.root
    
    # Act & Assert for each leaf
    for i, leaf in enumerate(leaves):
        proof = tree.get_proof(i)
        is_valid = tree.verify_proof(leaf, proof, root)
        assert is_valid, f"Proof for leaf {i} failed"

def test_invalid_proof():
    leaves = [1, 2, 3, 4]
    tree = MerkleTree(leaves)
    proof = tree.get_proof(0)
    
    # Tamper with proof value
    proof[0]['value'] += 1
    
    is_valid = tree.verify_proof(leaves[0], proof, tree.root)
    assert not is_valid
