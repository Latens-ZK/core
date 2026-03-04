"""
seed_10k_whales.py — Populate the demo snapshot with realistic whale data.

Generates a synthetic Bitcoin whale snapshot with configurable address count
(default 10,000), builds the Merkle tree, and inserts into the database.
Designed to stress-test the proof route and Merkle visualizer at scale.

Usage (from project root):
    python -m backend.src.indexer.seed_10k_whales [--count 10000] [--height 800001]

Or from backend/ directory:
    python -m src.indexer.seed_10k_whales

Environment:
    DATABASE_URL — SQLite or Postgres connection string (default: sqlite:///latens.db)
"""
import argparse
import hashlib
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

# Allow running as a module from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ─── Realistic whale address pool ─────────────────────────────────────────────
# A representative mix of address types seen in the Bitcoin whale leaderboard.
# Real addresses; balances are synthetic for demo purposes.
KNOWN_WHALES = [
    # Binance cold wallets
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    "3LYJfcfHcvFYTE84nt2bqYx2B7CtEBxMzr",
    "3Cbq7aT1tY8kMxWLbitaG7yT6bPbKChq64",
    # Coinbase cold wallets
    "3Kzh9qAqVWQhEsfQz7zEQL1EuSx5tyNLNS",
    # Genesis / Satoshi era
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "1CounterpartyXXXXXXXXXXXXXXXUWLpVr",
    # Bech32 whale wallets
    "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el",
    "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97",
    # Demo/testnet
    "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ",
    "1KFHE7w8BhaENAswwryaoccDb6qcT6DbYY",
    "bc1qazcm763858nkj2dj986etajv6wquslv8uxjj8",
]

# Realistic distribution:
# ~1% ultra-whales (> 1,000 BTC), ~9% whales (100-1000 BTC), ~90% minnow whales (1-100 BTC)
BTC_DISTRIBUTION = [
    (0.01, (1_000 * 100_000_000, 100_000 * 100_000_000)),  # ultra-whale: 1k-100k BTC
    (0.09, (100 * 100_000_000, 1_000 * 100_000_000)),       # whale: 100-1000 BTC
    (0.90, (1 * 100_000_000, 100 * 100_000_000)),            # minnow-whale: 1-100 BTC
]


def _sample_balance(rng: random.Random) -> int:
    """Sample a realistic whale balance in satoshis."""
    roll = rng.random()
    cumulative = 0.0
    for prob, (lo, hi) in BTC_DISTRIBUTION:
        cumulative += prob
        if roll <= cumulative:
            return rng.randint(lo, hi)
    return rng.randint(1 * 100_000_000, 100 * 100_000_000)


def _synthetic_address(seed: int, fmt: str = "p2pkh") -> str:
    """
    Generate a syntactically valid-looking (but not cryptographically valid)
    Bitcoin address from a seed integer. Used only for demo data.
    """
    # Base58check alphabet
    ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    raw = hashlib.sha256(str(seed).encode()).hexdigest()
    val = int(raw[:20], 16)

    if fmt == "p2pkh":
        # Start with 1, 33 chars total
        chars = ""
        v = val
        while v > 0:
            chars = ALPHABET[v % 58] + chars
            v //= 58
        chars = ("1" + chars.ljust(32, ALPHABET[seed % 58]))[:34]
        return chars

    elif fmt == "p2sh":
        # Start with 3
        chars = ""
        v = val
        while v > 0:
            chars = ALPHABET[v % 58] + chars
            v //= 58
        chars = ("3" + chars.ljust(32, ALPHABET[(seed + 17) % 58]))[:34]
        return chars

    else:
        # bech32 style: bc1q + 38 alphanumeric
        BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        body = "".join(BECH[(val >> (i * 5)) & 31] for i in range(39))
        return f"bc1q{body}"


def seed_snapshot(
    count: int = 10_000,
    block_height: int = 800_001,
    seed: int = 42,
    db_url: str | None = None,
) -> None:
    """
    Build a synthetic snapshot with `count` whale addresses and persist to DB.

    Args:
        count: Number of synthetic addresses.
        block_height: Bitcoin block height to use for the snapshot.
        seed: Random seed for reproducibility.
        db_url: SQLAlchemy connection string. Defaults to DATABASE_URL env var.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Import path resolution
    try:
        from backend.src.models.snapshot import Base, Snapshot, AddressBalance
        from backend.src.crypto.merkle_tree import MerkleTree
        from backend.src.crypto.poseidon import PoseidonHash
        from backend.src.crypto.address_utils import AddressUtils
        from backend.src.indexer.balance_aggregator import BalanceAggregator
    except ImportError:
        from src.models.snapshot import Base, Snapshot, AddressBalance
        from src.crypto.merkle_tree import MerkleTree
        from src.crypto.poseidon import PoseidonHash
        from src.crypto.address_utils import AddressUtils
        from src.indexer.balance_aggregator import BalanceAggregator

    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite:///latens.db")

    logger.info(f"Connecting to: {db_url}")
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Check if snapshot already exists
    existing = db.query(Snapshot).filter(Snapshot.block_height == block_height).first()
    if existing:
        logger.info(f"Snapshot at height {block_height} already exists. Delete it first to re-seed.")
        db.close()
        return

    rng = random.Random(seed)
    t0 = time.time()

    # ── 1. Build address → balance map ─────────────────────────────────────
    logger.info(f"Generating {count} synthetic whale addresses (seed={seed})...")
    address_balances: dict = {}

    # Start with known real whale addresses
    known = list(KNOWN_WHALES)
    rng.shuffle(known)
    for addr in known[:min(len(known), count)]:
        address_balances[addr] = _sample_balance(rng)

    remaining = count - len(address_balances)
    formats = ["p2pkh", "p2sh", "bech32"]
    for i in range(remaining):
        addr_fmt = formats[i % len(formats)]
        addr = _synthetic_address(i + seed * 1_000_000, fmt=addr_fmt)
        address_balances[addr] = _sample_balance(rng)

    # ── 2. Sort deterministically ──────────────────────────────────────────
    logger.info("Sorting addresses by address_hash (deterministic)...")
    agg = BalanceAggregator(min_balance_satoshis=0)
    sorted_items = agg.sort_addresses_deterministic(address_balances)

    # ── 3. Build Merkle tree ───────────────────────────────────────────────
    logger.info(f"Building Poseidon Merkle tree over {len(sorted_items)} leaves...")
    leaves = []
    addr_to_idx: dict = {}
    for idx, (addr, bal) in enumerate(sorted_items):
        addr_hash = AddressUtils.get_address_hash(addr)
        leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
        leaves.append(leaf)
        addr_to_idx[addr] = idx

    tree = MerkleTree(leaves)
    logger.info(f"Merkle root: {hex(tree.root)}")

    # ── 4. Generate paths + verify spot check ─────────────────────────────
    logger.info("Generating Merkle paths (spot-checking 100 proofs)...")
    paths: dict = {}
    for addr, idx in addr_to_idx.items():
        paths[addr] = tree.get_proof(idx)

    spot_check_addrs = rng.sample(list(addr_to_idx.keys()), min(100, len(addr_to_idx)))
    for addr in spot_check_addrs:
        idx = addr_to_idx[addr]
        addr_hash = AddressUtils.get_address_hash(addr)
        bal = address_balances[addr]
        leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
        assert tree.verify_proof(leaf, paths[addr], tree.root), f"Proof check failed for {addr}"
    logger.info("All spot-checks passed ✓")

    total_balance = sum(b for _, b in sorted_items)

    # ── 5. Persist to DB ──────────────────────────────────────────────────
    logger.info("Persisting snapshot to database...")
    snap = Snapshot(
        block_height=block_height,
        block_hash=f"synthetic_{seed}_{block_height}",
        merkle_root=hex(tree.root),
        total_addresses=len(sorted_items),
        total_balance=total_balance,
        timestamp=int(time.time()),
        status="complete",
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)

    logger.info(f"Inserting {len(sorted_items)} AddressBalance rows (batch size 1000)...")
    batch: list = []
    for addr, bal in sorted_items:
        addr_hash = AddressUtils.get_address_hash(addr)
        batch.append(AddressBalance(
            snapshot_id=snap.id,
            address=addr,
            address_hash=hex(addr_hash),
            balance=bal,
            merkle_path=json.dumps(paths[addr]),
            commitment=None,
        ))
        if len(batch) == 1000:
            db.bulk_save_objects(batch)
            db.commit()
            batch = []
            logger.info(f"  Flushed batch (total so far: {snap.id} + {len(sorted_items)}...)")

    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    db.close()
    elapsed = time.time() - t0

    logger.info("=" * 60)
    logger.info(f"Snapshot seeded successfully in {elapsed:.1f}s")
    logger.info(f"  Block height   : {block_height}")
    logger.info(f"  Addresses      : {len(sorted_items):,}")
    logger.info(f"  Total balance  : {total_balance / 100_000_000:.2f} BTC")
    logger.info(f"  Merkle root    : {hex(tree.root)}")
    logger.info("=" * 60)


def main():
    from typing import Optional
    parser = argparse.ArgumentParser(description="Seed synthetic whale snapshot into Latens DB")
    parser.add_argument("--count", type=int, default=10_000, help="Number of addresses (default: 10000)")
    parser.add_argument("--height", type=int, default=800_001, help="Bitcoin block height (default: 800001)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    parser.add_argument("--db", type=str, default=None, help="DATABASE_URL override")
    args = parser.parse_args()

    seed_snapshot(
        count=args.count,
        block_height=args.height,
        seed=args.seed,
        db_url=args.db,
    )


if __name__ == "__main__":
    from typing import Optional
    main()
