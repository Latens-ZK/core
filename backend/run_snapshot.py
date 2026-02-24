"""
CLI runner for generating a Bitcoin state snapshot.

Usage
-----
    # Snapshot at latest block height:
    python run_snapshot.py

    # Snapshot at a specific block height:
    python run_snapshot.py --height 800000

    # Use a custom set of addresses (comma-separated):
    python run_snapshot.py --height 800000 --addresses "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa,34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"

Environment
-----------
    Reads .env from the project root automatically.
    Optional vars: MIN_BALANCE_SATOSHIS, SNAPSHOT_OUTPUT_DIR, MONITORED_ADDRESSES,
                   STARKNET_PRIVATE_KEY, STARKNET_ACCOUNT_ADDRESS, STATE_ROOT_REGISTRY_ADDRESS
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# ── Resolve project root so `src.*` imports work from any cwd ──────────────────
_HERE = Path(__file__).parent          # backend/
sys.path.insert(0, str(_HERE))         # so `import src.xxx` resolves

# Load .env before any src imports
from dotenv import load_dotenv
load_dotenv(_HERE / ".env")
load_dotenv(_HERE.parent / ".env")     # also try repo root .env

from src.indexer.bitcoin_client import BitcoinClient
from src.indexer.snapshot_generator import SnapshotGenerator
from src.database import engine
from src.models.snapshot import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_snapshot")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a Latens Bitcoin state snapshot")
    p.add_argument(
        "--height", type=int, default=None,
        help="Bitcoin block height to snapshot. Defaults to current chain tip.",
    )
    p.add_argument(
        "--addresses", type=str, default=None,
        help="Comma-separated list of Bitcoin addresses to include (overrides MONITORED_ADDRESSES env var).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Ensure DB tables exist
    logger.info("Initialising database tables...")
    Base.metadata.create_all(bind=engine)

    # Resolve block height
    if args.height is not None:
        block_height = args.height
    else:
        logger.info("Fetching latest block height from Blockstream API...")
        client = BitcoinClient()
        block_height = client.fetch_latest_block_height()

    logger.info(f"Target block height: {block_height:,}")

    # Build generator (pass addresses via env or CLI flag)
    if args.addresses:
        os.environ["MONITORED_ADDRESSES"] = args.addresses

    gen = SnapshotGenerator()

    if args.addresses:
        addrs = [a.strip() for a in args.addresses.split(",") if a.strip()]
        logger.info(f"Using {len(addrs)} addresses from --addresses flag")

    logger.info(f"Monitoring {len(gen.monitored_addresses)} address(es)")

    # Generate snapshot
    snapshot = gen.generate_snapshot(block_height)

    # Print summary
    output_dir = os.getenv("SNAPSHOT_OUTPUT_DIR", "output")
    json_path = Path(output_dir) / f"snapshot_{block_height}.json"

    print()
    print("=" * 60)
    print("  Latens Snapshot Complete")
    print("=" * 60)
    print(f"  Block height  : {snapshot['block_height']:,}")
    print(f"  Block hash    : {snapshot['block_hash']}")
    print(f"  Merkle root   : {snapshot['merkle_root']}")
    print(f"  Addresses     : {snapshot['total_addresses']:,}")
    print(f"  Total balance : {snapshot['total_balance']:,} sat  ({snapshot['total_balance'] / 1e8:.8f} BTC)")
    print(f"  Generated at  : {snapshot['generated_at']}")
    print(f"  Time taken    : {snapshot['generation_time']:.2f}s")
    if json_path.exists():
        print(f"  JSON output   : {json_path.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
