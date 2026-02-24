"""
Comprehensive backend tests: crypto, API integration, and Merkle tree.
Run: pytest backend/tests/ -v
"""
import pytest
import json
from fastapi.testclient import TestClient


# ─── Merkle Tree Tests ─────────────────────────────────────────────────────────

class TestMerkleTree:
    def test_basic_build(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        leaves = [1, 2, 3, 4]
        tree = MerkleTree(leaves)
        assert tree.root is not None
        assert tree.root != 0

    def test_single_leaf(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        tree = MerkleTree([42])
        assert tree.root == 42

    def test_proof_valid(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        leaves = [10, 20, 30, 40, 50]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            proof = tree.get_proof(i)
            assert tree.verify_proof(leaf, proof, tree.root), f"Proof failed for leaf {i}"

    def test_proof_invalid(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        tree = MerkleTree([1, 2, 3, 4])
        proof = tree.get_proof(0)
        assert not tree.verify_proof(999, proof, tree.root)

    def test_direction_is_bool(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        tree = MerkleTree([1, 2, 3, 4])
        proof = tree.get_proof(1)
        for el in proof:
            assert isinstance(el['direction'], bool), "direction must be bool, not string"

    def test_odd_leaf_count(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        leaves = [1, 2, 3]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            proof = tree.get_proof(i)
            assert tree.verify_proof(leaf, proof, tree.root)

    def test_proof_deterministic(self):
        from backend.src.crypto.merkle_tree import MerkleTree
        leaves = [100, 200, 300]
        t1 = MerkleTree(leaves)
        t2 = MerkleTree(leaves)
        assert t1.root == t2.root


# ─── Poseidon Tests ────────────────────────────────────────────────────────────

class TestPoseidon:
    def test_import_succeeds(self):
        """Ensure starknet-py Poseidon is available (no mock fallback)."""
        from backend.src.crypto.poseidon import PoseidonHash
        # Just ensure it imports without error
        assert PoseidonHash is not None

    def test_hash_deterministic(self):
        from backend.src.crypto.poseidon import PoseidonHash
        h1 = PoseidonHash.hash(1, 2)
        h2 = PoseidonHash.hash(1, 2)
        assert h1 == h2

    def test_hash_asymmetric(self):
        from backend.src.crypto.poseidon import PoseidonHash
        assert PoseidonHash.hash(1, 2) != PoseidonHash.hash(2, 1)

    def test_commitment_matches_hash(self):
        from backend.src.crypto.poseidon import PoseidonHash
        addr_hash = 12345678
        salt = 99999999
        c1 = PoseidonHash.hash_commitment(addr_hash, salt)
        c2 = PoseidonHash.hash(addr_hash, salt)
        assert c1 == c2


# ─── Address Utils Tests ───────────────────────────────────────────────────────

class TestAddressUtils:
    def test_valid_bech32(self):
        from backend.src.crypto.address_utils import AddressUtils
        assert AddressUtils.validate_address("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")

    def test_valid_p2pkh(self):
        from backend.src.crypto.address_utils import AddressUtils
        assert AddressUtils.validate_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")

    def test_valid_p2sh(self):
        from backend.src.crypto.address_utils import AddressUtils
        assert AddressUtils.validate_address("34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo")

    def test_invalid_address(self):
        from backend.src.crypto.address_utils import AddressUtils
        assert not AddressUtils.validate_address("not-an-address")
        assert not AddressUtils.validate_address("")
        assert not AddressUtils.validate_address("aaa")

    def test_hash_is_felt(self):
        from backend.src.crypto.address_utils import AddressUtils
        PRIME = 2**251 + 17 * 2**192 + 1
        h = AddressUtils.get_address_hash("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        assert 0 < h < PRIME

    def test_hash_deterministic(self):
        from backend.src.crypto.address_utils import AddressUtils
        addr = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        assert AddressUtils.get_address_hash(addr) == AddressUtils.get_address_hash(addr)


# ─── API Integration Tests ─────────────────────────────────────────────────────

@pytest.fixture
def client():
    """FastAPI test client with a fresh in-memory database."""
    import os
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"

    from backend.src.api.main import app
    from backend.src.models.snapshot import Base
    from backend.src.database import engine
    Base.metadata.create_all(bind=engine)

    return TestClient(app)


@pytest.fixture
def seeded_client(client):
    """Client with a seeded demo snapshot."""
    from backend.src.database import SessionLocal
    from backend.src.models.snapshot import Snapshot, AddressBalance
    from backend.src.crypto.merkle_tree import MerkleTree
    from backend.src.crypto.poseidon import PoseidonHash
    from backend.src.crypto.address_utils import AddressUtils
    import json

    demo_addrs = {
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": 7_500_000_000,
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": 252_597_000_000,
    }
    sorted_items = sorted(demo_addrs.items())
    leaves = [PoseidonHash.hash_address_balance(AddressUtils.get_address_hash(a), b) for a, b in sorted_items]
    tree = MerkleTree(leaves)

    db = SessionLocal()
    snap = Snapshot(
        block_height=800_000, block_hash="abc123", merkle_root=hex(tree.root),
        total_addresses=2, total_balance=sum(demo_addrs.values()),
        timestamp=1690168218, status='complete'
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)

    for idx, (addr, bal) in enumerate(sorted_items):
        addr_hash = AddressUtils.get_address_hash(addr)
        proof = tree.get_proof(idx)
        leaf = PoseidonHash.hash_address_balance(addr_hash, bal)
        assert tree.verify_proof(leaf, proof, tree.root)
        db.add(AddressBalance(
            snapshot_id=snap.id, address=addr,
            address_hash=hex(addr_hash), balance=bal,
            merkle_path=json.dumps(proof)
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

    def test_by_height(self, seeded_client):
        r = seeded_client.get("/api/snapshot/800000")
        assert r.status_code == 200

    def test_by_height_not_found(self, client):
        r = client.get("/api/snapshot/999999")
        assert r.status_code == 404


class TestProofAPI:
    def test_invalid_address_rejected(self, seeded_client):
        r = seeded_client.post("/api/proof/generate", json={
            "address": "not-valid",
            "salt_hex": "abcd1234",
            "threshold": 0,
        })
        assert r.status_code == 422  # Pydantic validation error

    def test_address_not_in_snapshot(self, seeded_client):
        r = seeded_client.post("/api/proof/generate", json={
            "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "salt_hex": "deadbeef",
            "threshold": 0,
        })
        assert r.status_code == 404

    def test_successful_proof(self, seeded_client):
        r = seeded_client.post("/api/proof/generate", json={
            "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "salt_hex": "deadbeefdeadbeef",
            "threshold": 0,
        })
        assert r.status_code == 200
        data = r.json()
        # All calldata fields present
        assert "address_hash" in data
        assert "salt" in data
        assert "balance" in data
        assert "merkle_path" in data
        assert "snapshot_root" in data
        assert "commitment" in data
        assert "threshold" in data
        assert "block_height" in data
        assert data["balance"] == 7_500_000_000
        assert data["block_height"] == 800_000
        assert data["verified_locally"] is True

    def test_threshold_too_high(self, seeded_client):
        r = seeded_client.post("/api/proof/generate", json={
            "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "salt_hex": "deadbeef",
            "threshold": 999_999_999_999,  # 9999 BTC, way above balance
        })
        assert r.status_code == 400

    def test_negative_threshold_rejected(self, seeded_client):
        r = seeded_client.post("/api/proof/generate", json={
            "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            "salt_hex": "deadbeef",
            "threshold": -1,
        })
        assert r.status_code == 422
