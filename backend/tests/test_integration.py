"""
Comprehensive backend tests: crypto, API integration, and Merkle tree.

Run from backend/ directory:
    pytest tests/ -v

Or from repo root:
    pytest backend/tests/ -v
"""
import json
import os
import pytest
from fastapi.testclient import TestClient


# ─── Merkle Tree Tests ─────────────────────────────────────────────────────────

class TestMerkleTree:
    def test_basic_build(self):
        from src.crypto.merkle_tree import MerkleTree
        leaves = [1, 2, 3, 4]
        tree = MerkleTree(leaves)
        assert tree.root is not None
        assert tree.root != 0

    def test_single_leaf(self):
        from src.crypto.merkle_tree import MerkleTree
        tree = MerkleTree([42])
        assert tree.root == 42

    def test_proof_valid(self):
        from src.crypto.merkle_tree import MerkleTree
        leaves = [10, 20, 30, 40, 50]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            proof = tree.get_proof(i)
            assert tree.verify_proof(leaf, proof, tree.root), f"Proof failed for leaf {i}"

    def test_proof_invalid(self):
        from src.crypto.merkle_tree import MerkleTree
        tree = MerkleTree([1, 2, 3, 4])
        proof = tree.get_proof(0)
        assert not tree.verify_proof(999, proof, tree.root)

    def test_direction_is_bool(self):
        from src.crypto.merkle_tree import MerkleTree
        tree = MerkleTree([1, 2, 3, 4])
        proof = tree.get_proof(1)
        for el in proof:
            assert isinstance(el['direction'], bool), "direction must be bool, not string"

    def test_odd_leaf_count(self):
        from src.crypto.merkle_tree import MerkleTree
        leaves = [1, 2, 3]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            proof = tree.get_proof(i)
            assert tree.verify_proof(leaf, proof, tree.root)

    def test_proof_deterministic(self):
        from src.crypto.merkle_tree import MerkleTree
        leaves = [100, 200, 300]
        t1 = MerkleTree(leaves)
        t2 = MerkleTree(leaves)
        assert t1.root == t2.root


# ─── Poseidon Tests ────────────────────────────────────────────────────────────

class TestPoseidon:
    def test_import_succeeds(self):
        from src.crypto.poseidon import PoseidonHash
        assert PoseidonHash is not None

    def test_hash_deterministic(self):
        from src.crypto.poseidon import PoseidonHash
        h1 = PoseidonHash.hash(1, 2)
        h2 = PoseidonHash.hash(1, 2)
        assert h1 == h2

    def test_hash_asymmetric(self):
        from src.crypto.poseidon import PoseidonHash
        assert PoseidonHash.hash(1, 2) != PoseidonHash.hash(2, 1)

    def test_commitment_matches_hash(self):
        from src.crypto.poseidon import PoseidonHash
        addr_hash = 12345678
        salt = 99999999
        c1 = PoseidonHash.hash_commitment(addr_hash, salt)
        c2 = PoseidonHash.hash(addr_hash, salt)
        assert c1 == c2

    def test_known_permutation_vector(self):
        """Verified against poseidon-py 0.1.5 C library: permutation_3([0,0,0])."""
        from src.crypto.poseidon import _hades_permutation
        s0, s1, s2 = _hades_permutation(0, 0, 0)
        # s0 matches RES_P3_0 from poseidon-py test.c (standard field)
        assert s0 == 0x79e8d1e78258000a28fc9d49e233bc6852357968577b1e386550ed6a9086133
        assert s1 == 0x3840d003d0f3f96dbb796ff6aa6a63be5b5404b91ccaabca256154cbb6fb984
        assert s2 == 0x1eb39da3f7d3b04142d0ac83d9da00c9325a61fb2ef326e50b70eaa8a3c7cc7


# ─── Address Utils Tests ───────────────────────────────────────────────────────

class TestAddressUtils:
    def test_valid_bech32(self):
        from src.crypto.address_utils import AddressUtils
        assert AddressUtils.validate_address("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")

    def test_valid_p2pkh(self):
        from src.crypto.address_utils import AddressUtils
        assert AddressUtils.validate_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")

    def test_valid_p2sh(self):
        from src.crypto.address_utils import AddressUtils
        assert AddressUtils.validate_address("34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo")

    def test_invalid_address(self):
        from src.crypto.address_utils import AddressUtils
        assert not AddressUtils.validate_address("not-an-address")
        assert not AddressUtils.validate_address("")
        assert not AddressUtils.validate_address("aaa")

    def test_hash_is_felt(self):
        from src.crypto.address_utils import AddressUtils
        PRIME = 2**251 + 17 * 2**192 + 1
        h = AddressUtils.get_address_hash("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        assert 0 < h < PRIME

    def test_hash_deterministic(self):
        from src.crypto.address_utils import AddressUtils
        addr = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        assert AddressUtils.get_address_hash(addr) == AddressUtils.get_address_hash(addr)


# ─── Sort-order Tests ──────────────────────────────────────────────────────────

class TestSortOrder:
    def test_sort_by_address_hash_not_string(self):
        """MRK-01: addresses sorted by address_hash int, not lexicographic string."""
        from src.indexer.balance_aggregator import BalanceAggregator
        from src.crypto.address_utils import AddressUtils

        balances = {
            "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,
            "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": 252_597_000_000,
            "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh": 150_000_000_000,
        }

        agg = BalanceAggregator()
        sorted_items = agg.sort_addresses_deterministic(balances)
        sorted_addrs = [a for a, _ in sorted_items]

        # Verify hashes are in ascending order
        hashes = [AddressUtils.get_address_hash(a) for a in sorted_addrs]
        assert hashes == sorted(hashes), "Addresses must be sorted by ascending address_hash"

    def test_sort_is_deterministic(self):
        """Same input always produces same output order."""
        from src.indexer.balance_aggregator import BalanceAggregator

        balances = {
            "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,
            "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": 252_597_000_000,
        }
        agg = BalanceAggregator()
        r1 = agg.sort_addresses_deterministic(balances)
        r2 = agg.sort_addresses_deterministic(balances)
        assert r1 == r2


# ─── Snapshot Determinism Test ─────────────────────────────────────────────────

class TestSnapshotDeterminism:
    """Phase 1 done criterion: same block_height run twice → byte-identical output."""

    def _build_snapshot_json(self, balances: dict) -> str:
        """Build the snapshot JSON payload as it would be written to disk."""
        from src.crypto.merkle_tree import MerkleTree
        from src.crypto.poseidon import PoseidonHash
        from src.crypto.address_utils import AddressUtils
        from src.indexer.balance_aggregator import BalanceAggregator
        import json

        agg = BalanceAggregator()
        sorted_items = agg.sort_addresses_deterministic(balances)

        leaves = []
        for addr, bal in sorted_items:
            addr_hash = AddressUtils.get_address_hash(addr)
            leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
            leaves.append(leaf)

        tree = MerkleTree(leaves)

        payload = {
            "block_height": 800_000,
            "merkle_root": hex(tree.root),
            "balances": [{"address": a, "balance": b} for a, b in sorted_items],
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    def test_same_input_identical_output(self):
        balances = {
            "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,
            "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": 252_597_000_000,
            "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh": 150_000_000_000,
        }
        out1 = self._build_snapshot_json(balances)
        out2 = self._build_snapshot_json(balances)
        assert out1 == out2, "Snapshot output must be byte-identical across runs"

    def test_merkle_root_stable(self):
        """Merkle root must not change when inputs are the same."""
        from src.crypto.merkle_tree import MerkleTree
        from src.crypto.poseidon import PoseidonHash
        from src.crypto.address_utils import AddressUtils
        from src.indexer.balance_aggregator import BalanceAggregator

        balances = {
            "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,
            "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": 252_597_000_000,
        }
        agg = BalanceAggregator()

        def get_root(b):
            items = agg.sort_addresses_deterministic(b)
            leaves = [
                PoseidonHash.hash_address_balance(AddressUtils.get_address_hash(a), bal)
                for a, bal in items
            ]
            return MerkleTree(leaves).root

        assert get_root(balances) == get_root(balances)


# ─── API Integration Tests ─────────────────────────────────────────────────────

@pytest.fixture
def client():
    """FastAPI test client with a fresh (dropped+recreated) in-memory database."""
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"

    from src.api.main import app
    from src.models.snapshot import Base
    from src.database import engine

    # Drop all tables then recreate to guarantee clean state per test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    return TestClient(app)


@pytest.fixture
def seeded_client(client):
    """Client with a seeded demo snapshot (2 addresses)."""
    from src.database import SessionLocal
    from src.models.snapshot import Snapshot, AddressBalance
    from src.crypto.merkle_tree import MerkleTree
    from src.crypto.poseidon import PoseidonHash
    from src.crypto.address_utils import AddressUtils
    from src.indexer.balance_aggregator import BalanceAggregator

    demo_addrs = {
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": 252_597_000_000,
    }
    # Sort by address_hash per PRD MRK-01
    agg = BalanceAggregator()
    sorted_items = agg.sort_addresses_deterministic(demo_addrs)
    leaves = [
        PoseidonHash.hash_address_balance(AddressUtils.get_address_hash(a), b)
        for a, b in sorted_items
    ]
    tree = MerkleTree(leaves)

    db = SessionLocal()
    snap = Snapshot(
        block_height=800_000, block_hash="abc123", merkle_root=hex(tree.root),
        total_addresses=2, total_balance=sum(demo_addrs.values()),
        timestamp=1690168218, status='complete',
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)

    for idx, (addr, bal) in enumerate(sorted_items):
        addr_hash = AddressUtils.get_address_hash(addr)
        proof = tree.get_proof(idx)
        leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
        assert tree.verify_proof(leaf, proof, tree.root)
        # Use a fixed test salt to produce a deterministic commitment
        test_salt = 0xdeadbeef
        commitment_int = PoseidonHash.hash_commitment(addr_hash, test_salt)
        db.add(AddressBalance(
            snapshot_id=snap.id, address=addr,
            address_hash=hex(addr_hash), balance=bal,
            merkle_path=json.dumps(proof),
            commitment=hex(commitment_int),
        ))
    db.commit()
    db.close()
    return client


class TestAPIHealth:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_stats(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_snapshots" in data
        assert "total_btc_indexed" in data


class TestSnapshotAPI:
    def test_latest_no_snapshot(self, client):
        r = client.get("/api/snapshot/latest")
        assert r.status_code == 404

    def test_latest_with_snapshot(self, seeded_client):
        r = seeded_client.get("/api/snapshot/latest")
        assert r.status_code == 200
        data = r.json()
        assert data["block_height"] == 800_000
        assert data["status"] == "complete"
        assert "merkle_root" in data

    def test_current_alias(self, seeded_client):
        """/snapshot/current is an alias for /snapshot/latest (PRD §4.4)."""
        latest = seeded_client.get("/api/snapshot/latest").json()
        current = seeded_client.get("/api/snapshot/current").json()
        assert current["block_height"] == latest["block_height"]
        assert current["merkle_root"] == latest["merkle_root"]

    def test_by_height(self, seeded_client):
        r = seeded_client.get("/api/snapshot/800000")
        assert r.status_code == 200

    def test_by_height_not_found(self, client):
        r = client.get("/api/snapshot/999999")
        assert r.status_code == 404


class TestProofAPI:
    """
    Proof API tests — updated for the privacy-first model.

    The new /api/proof/generate endpoint accepts:
      - commitment (felt252 hex): Poseidon(address_hash, salt) — computed client-side
      - threshold (int): minimum balance in satoshis

    The backend never receives a raw Bitcoin address.
    Tests use the commitment seeded by seeded_client (test salt = 0xdeadbeef).
    """

    def _commitment_for(self, address: str) -> str:
        """Compute the test commitment (matching seeded_client test_salt=0xdeadbeef)."""
        from src.crypto.poseidon import PoseidonHash
        from src.crypto.address_utils import AddressUtils
        addr_hash = AddressUtils.get_address_hash(address)
        commitment_int = PoseidonHash.hash_commitment(addr_hash, 0xdeadbeef)
        return hex(commitment_int)

    def test_invalid_commitment_rejected(self, seeded_client):
        """Non-hex commitment should return 422."""
        r = seeded_client.post("/api/proof/generate", json={
            "commitment": "not-a-hex",
            "threshold": 0,
        })
        assert r.status_code == 422

    def test_commitment_not_in_snapshot(self, seeded_client):
        """Unknown commitment returns 404 (privacy-safe: no address info leaked)."""
        r = seeded_client.post("/api/proof/generate", json={
            "commitment": "0xdeadbeefdeadbeef",
            "threshold": 0,
        })
        assert r.status_code == 404

    def test_successful_proof(self, seeded_client):
        """Valid commitment returns proof calldata; no address in response."""
        commitment = self._commitment_for("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        r = seeded_client.post("/api/proof/generate", json={
            "commitment": commitment,
            "threshold": 0,
        })
        assert r.status_code == 200
        data = r.json()
        # Verify response fields
        assert "commitment" in data
        assert "snapshot_root" in data
        assert "threshold" in data
        assert "block_height" in data
        assert "merkle_path" in data
        assert "starknet_calldata" in data
        assert "verified_locally" in data
        # Privacy: no raw address in response
        assert "address" not in data
        assert "salt" not in data
        # Data correctness
        assert isinstance(data["starknet_calldata"], list)
        assert data["block_height"] == 800_000
        assert data["verified_locally"] is True
        assert data["commitment"] == commitment

    def test_threshold_too_high(self, seeded_client):
        """Commitment exists but balance < threshold → 400."""
        commitment = self._commitment_for("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        r = seeded_client.post("/api/proof/generate", json={
            "commitment": commitment,
            "threshold": 999_999_999_999,
        })
        assert r.status_code == 400

    def test_negative_threshold_rejected(self, seeded_client):
        """Negative threshold → 422 Pydantic validation error."""
        commitment = self._commitment_for("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        r = seeded_client.post("/api/proof/generate", json={
            "commitment": commitment,
            "threshold": -1,
        })
        assert r.status_code == 422
