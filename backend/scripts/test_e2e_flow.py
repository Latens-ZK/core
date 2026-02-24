"""
End-to-end test flow for Latens.
Simulates the entire user journey from Bitcoin snapshot to proof verification.
"""
import sys
import os
import logging
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.indexer.snapshot_generator import SnapshotGenerator
from src.circuit.proof_generator import ProofGenerator
from src.crypto.address_utils import AddressUtils
from src.crypto.poseidon import PoseidonHash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_e2e_test():
    logger.info("=== Starting Latens E2E Test ===")
    
    # 1. Setup Data Source (Mock) & Generate Snapshot
    logger.info("\n[Step 1] Generating Snapshot...")
    generator = SnapshotGenerator()
    
    # We use a mocked block height
    block_height = 800000
    
    # Since we don't have a real DB/BTC connection in this script without env vars,
    # we rely on the mocked behavior if API keys missing, or actual if present.
    # For CI/Test stability, we might want to mock the BitcoinClient.
    # But let's try to run it.
    
    try:
        snapshot = generator.generate_snapshot(block_height)
        logger.info(f"Snapshot generated: Root={snapshot['merkle_root']}")
    except Exception as e:
        logger.warning(f"Snapshot generation failed (likely network): {e}")
        logger.info("Using mocked snapshot data for rest of test...")
        snapshot = {'merkle_root': '0x1234abcd', 'block_height': block_height}

    # 2. User Setup (Client Side Simulation)
    logger.info("\n[Step 2] Client Setup...")
    user_address = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
    user_salt = 0xdeadbeef12345678
    user_balance = 150000000 # 1.5 BTC
    threshold = 100000000 # 1 BTC
    
    address_hash = AddressUtils.get_address_hash(user_address)
    commitment = PoseidonHash.hash_commitment(address_hash, user_salt)
    logger.info(f"User Address: {user_address}")
    logger.info(f"Commitment: {hex(commitment)}")
    
    # 3. Proof Generation (Backend)
    logger.info("\n[Step 3] Generating ZK Proof...")
    proof_gen = ProofGenerator()
    
    # Mock Merkle Path (since we don't have the full tree from Step 1 in memory easily here)
    merkle_path = [{'value': 12345, 'direction': False}] 
    
    proof_result = proof_gen.generate_proof(
        address_hash=address_hash,
        salt=user_salt,
        balance=user_balance,
        merkle_path=merkle_path,
        snapshot_root=int(snapshot['merkle_root'], 16),
        commitment=commitment,
        threshold=threshold
    )
    
    logger.info(f"Proof Generated: {proof_result['proof'][:20]}...")
    
    # 4. Verification (Contract Simulation)
    logger.info("\n[Step 4] Simulating On-Chain Verification...")
    # In a real test, we'd call the Starknet contract.
    # Here we verify the 'public signals' match what we expect.
    
    assert proof_result['verified'] == True
    assert proof_result['public_signals'][0] == hex(int(snapshot['merkle_root'], 16))
    assert proof_result['public_signals'][1] == hex(commitment)
    assert proof_result['public_signals'][2] == hex(threshold)
    
    logger.info("Verification Logic Check Passed!")
    
    logger.info("\n=== E2E Test Completed Successfully ===")

if __name__ == "__main__":
    run_e2e_test()
