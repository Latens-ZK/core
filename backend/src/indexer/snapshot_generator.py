"""
Snapshot generator for creating Merkle tree snapshots from Bitcoin data.
Includes on-chain root registration via Starknet.
"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .bitcoin_client import BitcoinClient, _DEMO_ADDRESSES
from .balance_aggregator import BalanceAggregator

logger = logging.getLogger(__name__)


class SnapshotGenerator:
    """Generates snapshots of Bitcoin state and registers Merkle roots on Starknet."""

    def __init__(self, db_session=None):
        self.bitcoin_client = BitcoinClient()
        self.balance_aggregator = BalanceAggregator(
            min_balance_satoshis=int(os.getenv("MIN_BALANCE_SATOSHIS", "1000000"))
        )
        self.db = db_session

        # Addresses monitored for snapshot inclusion.
        # Override via MONITORED_ADDRESSES env var (comma-separated).
        env_addrs = os.getenv("MONITORED_ADDRESSES", "")
        self.monitored_addresses: List[str] = (
            [a.strip() for a in env_addrs.split(",") if a.strip()]
            if env_addrs
            else list(_DEMO_ADDRESSES)
        )

    def generate_snapshot(self, block_height: int) -> Dict:
        """
        Generate a snapshot for a specific block height.
        1. Fetches Bitcoin data
        2. Builds Merkle tree
        3. Persists to DB
        4. Registers root on Starknet

        Args:
            block_height: Bitcoin block height

        Returns:
            Snapshot metadata dict
        """
        start_time = time.time()
        logger.info(f"Starting snapshot for block {block_height}")

        # 1. Fetch block metadata
        block_hash = self.bitcoin_client.fetch_block_hash(block_height)
        block_data = self.bitcoin_client.fetch_block(block_hash)
        timestamp = block_data.get('timestamp', int(time.time()))

        # 2. Fetch balances for monitored addresses at target height
        raw_balances = self.bitcoin_client.fetch_utxos_at_height(
            block_height, addresses=self.monitored_addresses
        )

        # 3. Validate, filter, sort
        self.balance_aggregator.validate_balances(raw_balances)
        filtered = self.balance_aggregator.aggregate_balances(raw_balances)
        sorted_balances = self.balance_aggregator.sort_addresses_deterministic(filtered)

        if not sorted_balances:
            raise ValueError(f"No eligible addresses found at block {block_height}")

        # 4. Build Merkle Tree
        from ..crypto.merkle_tree import MerkleTree
        from ..crypto.poseidon import PoseidonHash
        from ..crypto.address_utils import AddressUtils

        logger.info(f"Building Merkle tree over {len(sorted_balances)} addresses...")

        leaves = []
        addr_to_index: Dict[str, int] = {}

        for idx, (addr, bal) in enumerate(sorted_balances):
            addr_hash = AddressUtils.get_address_hash(addr)
            leaf_hash = PoseidonHash.hash_address_balance(addr_hash, bal)
            leaves.append(leaf_hash)
            addr_to_index[addr] = idx

        tree = MerkleTree(leaves)
        merkle_root = hex(tree.root)

        # 5. Pre-generate Merkle paths for all addresses
        logger.info("Generating Merkle paths for all addresses...")
        merkle_paths_data: Dict[str, list] = {}
        for addr, idx in addr_to_index.items():
            merkle_paths_data[addr] = tree.get_proof(idx)
            # Validate each proof immediately
            addr_hash = AddressUtils.get_address_hash(addr)
            bal = dict(sorted_balances)[addr]
            leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
            if not tree.verify_proof(leaf, merkle_paths_data[addr], tree.root):
                raise ValueError(f"Proof self-check failed for address {addr}")

        stats = self.balance_aggregator.get_statistics(filtered)
        generation_time = time.time() - start_time

        snapshot = {
            'block_height': block_height,
            'block_hash': block_hash,
            'merkle_root': merkle_root,
            'timestamp': timestamp,
            'generated_at': datetime.now().isoformat(),
            'total_addresses': stats['total_addresses'],
            'total_balance': stats['total_balance'],
            'generation_time': generation_time,
        }

        # 6. Export deterministic JSON snapshot
        self._export_json(snapshot, sorted_balances)

        # 7. Persist to DB
        self.persist_snapshot(snapshot, sorted_balances, merkle_paths_data)

        # 8. Register root on Starknet
        try:
            self.register_root_on_chain(tree.root, block_height)
        except Exception as e:
            logger.error(f"On-chain registration failed: {e}. Snapshot is in DB but not registered on Starknet.")

        logger.info(f"Snapshot complete in {generation_time:.1f}s: {snapshot}")
        return snapshot

    def _export_json(self, snapshot: Dict, sorted_balances: list) -> Path:
        """
        Write snapshot + sorted balances to output/snapshot_{block_height}.json.

        The file is deterministic: same block_height always produces the same
        byte-identical output (addresses sorted by address_hash ascending).
        """
        output_dir = Path(os.getenv("SNAPSHOT_OUTPUT_DIR", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"snapshot_{snapshot['block_height']}.json"

        payload = {
            **snapshot,
            "balances": [
                {"address": addr, "balance": bal}
                for addr, bal in sorted_balances
            ],
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)

        logger.info(f"Snapshot JSON exported to {json_path}")
        return json_path

    def register_root_on_chain(self, merkle_root: int, block_height: int):
        """
        Call StateRootRegistry.update_root() on Starknet Sepolia.
        Requires STARKNET_PRIVATE_KEY, STARKNET_ACCOUNT_ADDRESS, STATE_ROOT_REGISTRY_ADDRESS in env.
        """
        import asyncio
        asyncio.run(self._async_register_root(merkle_root, block_height))

    async def _async_register_root(self, merkle_root: int, block_height: int):
        private_key = os.getenv("STARKNET_PRIVATE_KEY")
        account_address = os.getenv("STARKNET_ACCOUNT_ADDRESS")
        registry_address = os.getenv("STATE_ROOT_REGISTRY_ADDRESS")

        if not all([private_key, account_address, registry_address]):
            logger.warning(
                "Skipping on-chain registration: set STARKNET_PRIVATE_KEY, "
                "STARKNET_ACCOUNT_ADDRESS, STATE_ROOT_REGISTRY_ADDRESS in .env"
            )
            return

        try:
            from starknet_py.net.full_node_client import FullNodeClient
            from starknet_py.net.account.account import Account
            from starknet_py.net.signer.stark_curve_signer import KeyPair
            from starknet_py.contract import Contract
            from starknet_py.net.models.chains import StarknetChainId
        except ImportError:
            logger.error(
                "starknet-py is not installed. "
                "Install it on Python ≤3.12 with: pip install starknet-py==0.29.0"
            )
            return

        node_url = os.getenv("STARKNET_RPC_URL", "https://starknet-sepolia.public.blastapi.io")
        client = FullNodeClient(node_url=node_url)

        key_pair = KeyPair.from_private_key(int(private_key, 16))
        account = Account(
            client=client,
            address=int(account_address, 16),
            key_pair=key_pair,
            chain=StarknetChainId.SEPOLIA,
        )

        # Load ABI from compiled artifacts
        import json
        from pathlib import Path
        abi_path = Path(__file__).parent.parent.parent.parent / "contracts" / "target" / "dev"
        abi_file = abi_path / "latens_contracts_StateRootRegistry.contract_class.json"

        if not abi_file.exists():
            logger.warning(f"Contract ABI not found at {abi_file}. Run 'scarb build' in contracts/.")
            return

        with open(abi_file) as f:
            contract_data = json.load(f)

        contract = Contract(
            address=int(registry_address, 16),
            abi=contract_data.get("abi", []),
            provider=account,
        )

        logger.info(f"Registering root {hex(merkle_root)} at height {block_height} on Starknet...")
        invocation = await contract.functions["update_root"].invoke(
            new_root=merkle_root,
            height=block_height,
            max_fee=int(1e16)
        )
        await invocation.wait_for_acceptance()
        logger.info(f"Root registered! Tx: {hex(invocation.hash)}")

    def persist_snapshot(self, snapshot_data: Dict, balances: list, merkle_paths: Dict):
        """Persist snapshot and all address balances to the database."""
        from ..database import SessionLocal
        from ..models.snapshot import Snapshot, AddressBalance
        from ..crypto.address_utils import AddressUtils
        import json

        logger.info("Persisting snapshot to database...")
        db = SessionLocal()
        try:
            existing = db.query(Snapshot).filter(
                Snapshot.block_height == snapshot_data['block_height']
            ).first()
            if existing:
                logger.info(f"Snapshot at height {snapshot_data['block_height']} already exists.")
                return

            db_snapshot = Snapshot(
                block_height=snapshot_data['block_height'],
                block_hash=snapshot_data['block_hash'],
                merkle_root=snapshot_data['merkle_root'],
                total_addresses=snapshot_data['total_addresses'],
                total_balance=snapshot_data['total_balance'],
                timestamp=snapshot_data['timestamp'],
                status='complete',
            )
            db.add(db_snapshot)
            db.commit()
            db.refresh(db_snapshot)

            logger.info(f"Inserting {len(balances)} address balances...")
            items = []
            for addr, bal in balances:
                addr_hash = AddressUtils.get_address_hash(addr)

                if addr not in merkle_paths:
                    raise ValueError(f"Missing Merkle path for address {addr}")

                path_json = json.dumps(merkle_paths[addr])

                items.append(AddressBalance(
                    snapshot_id=db_snapshot.id,
                    address=addr,
                    address_hash=hex(addr_hash),
                    balance=bal,
                    merkle_path=path_json,
                ))

            db.bulk_save_objects(items)
            db.commit()
            logger.info("Snapshot persistence complete.")

        except Exception as e:
            logger.error(f"Database error: {e}")
            db.rollback()
            raise
        finally:
            db.close()
