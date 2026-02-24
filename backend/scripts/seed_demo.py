"""
Demo data seeding script.
Seeds the database with pre-computed balances for well-known Bitcoin addresses
at a fixed block height, ready for hackathon demo without live API calls.
"""
import sys
import os
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv()

from src.crypto.merkle_tree import MerkleTree
from src.crypto.poseidon import PoseidonHash
from src.crypto.address_utils import AddressUtils
from src.models.snapshot import Base, Snapshot, AddressBalance
from src.database import engine, SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Demo Data ─────────────────────────────────────────────────────────────────
# Well-known Bitcoin addresses with approximate balances at block 800000.
# Balances are in satoshis. These are public on-chain addresses.

DEMO_BLOCK_HEIGHT = 800_000
DEMO_BLOCK_HASH = "00000000000000000002a7c4c1e48d76c5a37902165a270156b7a8d72728a054"
DEMO_BLOCK_TIMESTAMP = 1690168218

DEMO_ADDRESSES = {
    # Satoshi's Genesis Coinbase address
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,         # 75 BTC
    # Binance cold wallet
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo":  252_597_000_000,       # 2525 BTC
    # Demo whale 1 (bc1q Bech32)
    "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh": 150_000_000_000, # 1500 BTC
    # Demo whale 2
    "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el": 5_000_000_000,   # 50 BTC
    # Demo medium holder
    "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ": 200_000_000,             # 2 BTC
    # Demo small holder (above 1 satoshi threshold)
    "1KFHE7w8BhaENAswwryaoccDb6qcT6DbYY": 50_000_000,              # 0.5 BTC
    # Coinbase custody
    "3Kzh9qAqVWQhEsfQz7zEQL1EuSx5tyNLNS": 75_000_000_000,         # 750 BTC
    # Bitfinex hot wallet
    "bc1qazcm763858nkj2dj986etajv6wquslv8uxjj8": 95_000_000_000,   # 950 BTC
}


def seed():
    """Create demo snapshot and register on Starknet if configured."""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Skip if already seeded
        existing = db.query(Snapshot).filter(
            Snapshot.block_height == DEMO_BLOCK_HEIGHT
        ).first()
        if existing:
            logger.info(f"Demo snapshot already exists at block {DEMO_BLOCK_HEIGHT} (status={existing.status}).")
            logger.info(f"Merkle Root: {existing.merkle_root}")
            return existing.merkle_root

        logger.info(f"Seeding {len(DEMO_ADDRESSES)} addresses at block {DEMO_BLOCK_HEIGHT}...")

        # Sort deterministically by address_hash (SHA-256 mod P) per PRD MRK-01
        sorted_items = sorted(
            DEMO_ADDRESSES.items(),
            key=lambda x: AddressUtils.get_address_hash(x[0]),
        )

        # Build leaves
        leaves = []
        addr_data = []
        for addr, bal in sorted_items:
            addr_hash = AddressUtils.get_address_hash(addr)
            leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
            leaves.append(leaf)
            addr_data.append((addr, bal, addr_hash))

        # Build Merkle tree
        tree = MerkleTree(leaves)
        merkle_root = hex(tree.root)
        logger.info(f"Merkle Root: {merkle_root}")

        # Validate all proofs
        for idx, (addr, bal, addr_hash) in enumerate(addr_data):
            proof = tree.get_proof(idx)
            leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
            assert tree.verify_proof(leaf, proof, tree.root), f"Proof self-check failed for {addr}"
        logger.info("All Merkle proofs verified ✓")

        # Persist snapshot
        snapshot = Snapshot(
            block_height=DEMO_BLOCK_HEIGHT,
            block_hash=DEMO_BLOCK_HASH,
            merkle_root=merkle_root,
            total_addresses=len(sorted_items),
            total_balance=sum(b for _, b in sorted_items),
            timestamp=DEMO_BLOCK_TIMESTAMP,
            status='complete',
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        # Persist balances + paths
        items = []
        for idx, (addr, bal, addr_hash) in enumerate(addr_data):
            proof = tree.get_proof(idx)
            items.append(AddressBalance(
                snapshot_id=snapshot.id,
                address=addr,
                address_hash=hex(addr_hash),
                balance=bal,
                merkle_path=json.dumps(proof),
            ))
        db.bulk_save_objects(items)
        db.commit()

        logger.info(f"Seeded {len(items)} addresses. Snapshot ID={snapshot.id}")

        # Register root on Starknet
        registry_address = os.getenv("STATE_ROOT_REGISTRY_ADDRESS")
        if registry_address:
            logger.info("Registering Merkle root on Starknet...")
            import asyncio
            from src.indexer.snapshot_generator import SnapshotGenerator
            gen = SnapshotGenerator()
            asyncio.run(gen._async_register_root(tree.root, DEMO_BLOCK_HEIGHT))
        else:
            logger.warning(
                "STATE_ROOT_REGISTRY_ADDRESS not set — skipping on-chain root registration. "
                "Deploy contracts first and set the env variable."
            )

        return merkle_root

    finally:
        db.close()


if __name__ == "__main__":
    root = seed()
    logger.info(f"\n{'='*60}")
    logger.info(f"Demo seed complete!")
    logger.info(f"Merkle Root: {root}")
    logger.info(f"Block Height: {DEMO_BLOCK_HEIGHT}")
    logger.info(f"\nTry generating a proof for:")
    for addr in list(DEMO_ADDRESSES.keys())[:3]:
        logger.info(f"  {addr}")
    logger.info(f"{'='*60}")
