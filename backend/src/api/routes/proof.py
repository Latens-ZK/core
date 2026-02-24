"""
Proof generation endpoints.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from typing import Optional, List, Any

from ...circuit.proof_generator import ProofGenerator
from ...crypto.poseidon import PoseidonHash
from ...crypto.address_utils import AddressUtils

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Request / Response Models ─────────────────────────────────────────────────

class ProofRequest(BaseModel):
    address: str
    salt_hex: str       # 32 bytes as hex string (no 0x prefix)
    threshold: int = 0  # in satoshis, 0 = prove existence only
    block_height: Optional[int] = None

    @validator('address')
    def validate_address(cls, v):
        if not AddressUtils.validate_address(v):
            raise ValueError(f"Invalid Bitcoin address: {v}")
        return v.strip()

    @validator('salt_hex')
    def validate_salt(cls, v):
        v = v.strip().lstrip('0x')
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("salt_hex must be a valid hex string")
        return v

    @validator('threshold')
    def validate_threshold(cls, v):
        if v < 0:
            raise ValueError("threshold must be >= 0")
        return v


class MerklePathElementResponse(BaseModel):
    value: int
    direction: bool


class ProofResponse(BaseModel):
    # Full calldata for the Starknet contract call
    address_hash: str      # hex string
    salt: str              # hex string (echoed back from request)
    balance: int           # satoshis
    merkle_path: List[MerklePathElementResponse]
    snapshot_root: str     # hex string
    commitment: str        # hex string
    threshold: int
    block_height: int

    # Legacy / diagnostic
    proof: str
    public_signals: List[Any]
    verified_locally: bool


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=ProofResponse)
async def generate_proof(req: ProofRequest):
    """
    Generate ZK proof calldata for a Bitcoin address balance.

    Returns all fields needed to call BalanceVerifier.verify_proof() on Starknet.
    """
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot, AddressBalance
    import json

    db = SessionLocal()
    try:
        # 1. Find snapshot
        query = db.query(Snapshot).filter(Snapshot.status == 'complete')
        if req.block_height:
            query = query.filter(Snapshot.block_height == req.block_height)
        else:
            query = query.order_by(Snapshot.block_height.desc())

        snapshot = query.first()
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail="No complete snapshot found. Trigger snapshot generation first."
            )

        # 2. Lookup address in snapshot
        addr_balance = db.query(AddressBalance).filter(
            AddressBalance.snapshot_id == snapshot.id,
            AddressBalance.address == req.address
        ).first()

        if not addr_balance:
            raise HTTPException(
                status_code=404,
                detail=f"Address '{req.address}' not found in snapshot at block {snapshot.block_height}"
            )

        # 3. Check threshold early
        if req.threshold > 0 and addr_balance.balance < req.threshold:
            raise HTTPException(
                status_code=400,
                detail=f"Balance {addr_balance.balance} satoshis is below threshold {req.threshold}"
            )

        # 4. Parse Merkle path
        if not addr_balance.merkle_path or addr_balance.merkle_path in ('{}', '[]', ''):
            raise HTTPException(
                status_code=500,
                detail="Merkle path not available for this address. Re-generate snapshot."
            )

        raw_path = json.loads(addr_balance.merkle_path)
        if not isinstance(raw_path, list):
            raise HTTPException(status_code=500, detail="Merkle path data is corrupt.")

        # 5. Compute commitment
        salt = int(req.salt_hex, 16)
        addr_hash = int(addr_balance.address_hash, 16)
        commitment = PoseidonHash.hash_commitment(addr_hash, salt)
        snapshot_root = int(snapshot.merkle_root, 16)

        # 6. Run circuit logic (Python simulation / pre-flight check)
        proof_gen = ProofGenerator()
        result = proof_gen.generate_proof(
            address_hash=addr_hash,
            salt=salt,
            balance=addr_balance.balance,
            merkle_path=raw_path,
            snapshot_root=snapshot_root,
            commitment=commitment,
            threshold=req.threshold
        )

        # 7. Build full calldata response
        merkle_path_response = [
            MerklePathElementResponse(value=el['value'], direction=el['direction'])
            for el in raw_path
        ]

        return ProofResponse(
            # Calldata fields
            address_hash=hex(addr_hash),
            salt=hex(salt),
            balance=addr_balance.balance,
            merkle_path=merkle_path_response,
            snapshot_root=hex(snapshot_root),
            commitment=hex(commitment),
            threshold=req.threshold,
            block_height=snapshot.block_height,
            # Diagnostic
            proof=result['proof'],
            public_signals=result['public_signals'],
            verified_locally=result['verified'],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Proof generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
