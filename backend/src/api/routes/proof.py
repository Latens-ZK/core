"""
Proof generation endpoints.

Privacy model (post-refactor):
  - The backend NEVER receives a raw Bitcoin address.
  - The frontend computes: address_hash, commitment = Poseidon(address_hash, salt),
    and the full Merkle witness client-side.
  - The backend receives only: commitment (felt252) + threshold.
  - The backend looks up the snapshot row by commitment hash (pre-indexed),
    assembles Starknet calldata, and returns it.
  - Rate limiting is commitment-hash based, NOT IP-based.
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator
from typing import Optional, List, Any

from ...circuit.proof_generator import ProofGenerator
from ...crypto.poseidon import PoseidonHash
from ..limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Request / Response Models ─────────────────────────────────────────────────

class ProofRequest(BaseModel):
    """
    Privacy-first proof request.

    The client (browser) is responsible for:
      1. Getting the user's Bitcoin address (never sent here).
      2. Computing address_hash = SHA256(address) % PRIME locally.
      3. Generating a random salt.
      4. Computing commitment = Poseidon(address_hash, salt) locally.
      5. Looking up their Merkle witness from the snapshot (via /api/snapshot/witness).
      6. Sending only commitment + threshold here.
    """
    commitment: str   # felt252 hex string: Poseidon(address_hash, salt)
    threshold: int = 0  # minimum balance in satoshis; 0 = prove existence only
    block_height: Optional[int] = None  # pin to a specific snapshot height

    @field_validator('commitment')
    @classmethod
    def validate_commitment(cls, v: str) -> str:
        v = v.strip()
        hex_val = v.lstrip('0x')
        try:
            parsed = int(hex_val, 16)
        except ValueError:
            raise ValueError("commitment must be a valid hex felt252")
        # Must be within Starknet field prime
        PRIME = 2**251 + 17 * 2**192 + 1
        if parsed >= PRIME:
            raise ValueError("commitment exceeds felt252 field prime")
        return v

    @field_validator('threshold')
    @classmethod
    def validate_threshold(cls, v: int) -> int:
        if v < 0:
            raise ValueError("threshold must be >= 0")
        return v


class MerklePathElementResponse(BaseModel):
    value: int
    direction: bool


class ProofResponse(BaseModel):
    # Calldata fields (no address ever returned)
    commitment: str        # hex string (echoed back)
    snapshot_root: str     # hex string
    threshold: int
    block_height: int
    merkle_path: List[MerklePathElementResponse]

    # Pre-encoded Starknet ABI calldata for BalanceVerifier.verify_proof()
    # The client still needs to supply address_hash, salt, balance in the
    # actual on-chain call — these are NOT sent here; the client holds them.
    # starknet_calldata here encodes only the Merkle path + root for reference.
    starknet_calldata: List[str]   # decimal felt252 strings

    # Diagnostic
    proof: str
    public_signals: List[Any]
    verified_locally: bool


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=ProofResponse)
@limiter.limit("3/hour")
async def generate_proof(request: Request, req: ProofRequest):
    """
    Assemble ZK proof calldata given a commitment hash.

    The backend never sees or stores a raw Bitcoin address.
    The commitment is used to locate the prover's record in the snapshot.

    Rate limit: 3 proof requests per commitment per hour.
    """
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot, AddressBalance
    import json

    # Expose commitment to the rate-limiter key function via request.state.
    # The limiter reads this in limiter.py::_get_commitment_from_request().
    request.state.commitment_key = req.commitment

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

        # 2. Lookup record by commitment hash.
        #    The snapshot indexer stores commitment when it processes an address;
        #    if the commitment column is not yet populated (legacy rows), the
        #    caller must use the /api/snapshot/witness endpoint instead.
        addr_balance = db.query(AddressBalance).filter(
            AddressBalance.snapshot_id == snapshot.id,
            AddressBalance.commitment == req.commitment
        ).first()

        if not addr_balance:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Commitment '{req.commitment}' not found in snapshot at block "
                    f"{snapshot.block_height}. "
                    "Ensure the client computed commitment = Poseidon(address_hash, salt) "
                    "using the same snapshot's address_hash."
                )
            )

        # 3. Check threshold early (fast-fail before circuit logic)
        if req.threshold > 0 and addr_balance.balance < req.threshold:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Balance {addr_balance.balance} satoshis is below "
                    f"threshold {req.threshold}"
                )
            )

        # 4. Parse Merkle path
        if not addr_balance.merkle_path or addr_balance.merkle_path in ('{}', '[]', ''):
            raise HTTPException(
                status_code=500,
                detail="Merkle path not available for this commitment. Re-generate snapshot."
            )

        raw_path = json.loads(addr_balance.merkle_path)
        if not isinstance(raw_path, list):
            raise HTTPException(status_code=500, detail="Merkle path data is corrupt.")

        # 5. Reconstruct address_hash and commitment ints from stored values
        commitment_int = int(req.commitment.lstrip('0x'), 16)
        addr_hash = int(addr_balance.address_hash, 16)
        snapshot_root = int(snapshot.merkle_root, 16)

        # 6. Run circuit logic (Python simulation / pre-flight check).
        #    Note: salt is NOT available here (privacy guarantee).
        #    We verify only Merkle inclusion + threshold; commitment was
        #    already matched by the DB lookup above.
        proof_gen = ProofGenerator()

        # Minimal circuit check: Merkle path + threshold (no re-check commitment).
        result = proof_gen.generate_proof_no_salt(
            address_hash=addr_hash,
            balance=addr_balance.balance,
            merkle_path=raw_path,
            snapshot_root=snapshot_root,
            commitment=commitment_int,
            threshold=req.threshold
        )

        # 7. Build Merkle path response
        merkle_path_response = [
            MerklePathElementResponse(value=el['value'], direction=el['direction'])
            for el in raw_path
        ]

        # 8. Pre-encode Starknet ABI calldata for the Merkle path portion only.
        #    The client must prepend address_hash, salt, balance from their local state.
        calldata_ints = [
            addr_balance.balance,
            len(raw_path),
        ]
        for element in raw_path:
            calldata_ints.append(element['value'])
            calldata_ints.append(1 if element['direction'] else 0)
        calldata_ints.append(commitment_int)
        calldata_ints.append(req.threshold)

        starknet_calldata = [str(v) for v in calldata_ints]

        return ProofResponse(
            commitment=req.commitment,
            snapshot_root=hex(snapshot_root),
            threshold=req.threshold,
            block_height=snapshot.block_height,
            merkle_path=merkle_path_response,
            starknet_calldata=starknet_calldata,
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
