"""
Snapshot witness endpoints.

These endpoints allow the client (browser) to:
  1. GET /api/snapshot/witness/{commitment}
     Look up the Merkle path for a pre-registered commitment.
     Returns path + snapshot_root so the client can self-verify before
     submitting the on-chain transaction.

  2. POST /api/snapshot/witness/register
     Register a commitment against an address_hash in the latest snapshot.
     This is the privacy-safe alternative to the old proof/generate:
       - Client sends commitment = Poseidon(address_hash, salt) + address_hash
       - Backend finds the AddressBalance row by address_hash, writes commitment
       - From now on the proof route can look up by commitment (not by address)

  Privacy model:
    - address_hash is NOT the raw address (it's SHA-256(address) % PRIME)
    - salt never reaches the backend
    - The raw Bitcoin address never touches the network
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional, List

logger = logging.getLogger(__name__)
router = APIRouter()

PRIME = 2**251 + 17 * 2**192 + 1


# ─── Models ────────────────────────────────────────────────────────────────────

class WitnessRegisterRequest(BaseModel):
    """
    Register a commitment for a given address_hash in a snapshot.

    The client computes:
      address_hash = SHA256(address) % PRIME        (encodeAddressAsFelt252)
      commitment   = Poseidon(address_hash, salt)   (computeCommitment)

    Only address_hash and commitment are sent — salt and raw address stay local.
    """
    address_hash: str   # hex felt252
    commitment: str     # hex felt252
    block_height: Optional[int] = None  # None = latest complete snapshot

    @field_validator('address_hash', 'commitment')
    @classmethod
    def validate_felt252(cls, v: str) -> str:
        v = v.strip()
        try:
            val = int(v.lstrip('0x'), 16)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid hex felt252")
        if val >= PRIME:
            raise ValueError("Value exceeds felt252 field prime")
        return v


class WitnessRegisterResponse(BaseModel):
    commitment: str
    address_hash: str
    balance: int         # satoshis
    block_height: int
    snapshot_root: str
    merkle_path: list
    registered: bool     # True = newly written; False = was already set


class WitnessResponse(BaseModel):
    commitment: str
    address_hash: str
    balance: int
    block_height: int
    snapshot_root: str
    merkle_path: list


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=WitnessRegisterResponse)
async def register_commitment(req: WitnessRegisterRequest):
    """
    Client-side commitment registration (privacy-preserving).

    Flow:
      1. Client computes address_hash = SHA256(address) % PRIME locally.
      2. Client generates a random salt locally.
      3. Client computes commitment = Poseidon(address_hash, salt) locally.
      4. Client calls this endpoint with address_hash + commitment.
      5. Backend finds the matching AddressBalance row by address_hash.
      6. Backend writes the commitment to that row.
      7. From now on, /api/proof/generate can look up by commitment.

    Rate limit: not throttled here — the commitment-hash rate limiter on
    /proof/generate is the primary defense.
    """
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot, AddressBalance
    import json

    db = SessionLocal()
    try:
        # Find snapshot
        query = db.query(Snapshot).filter(Snapshot.status == 'complete')
        if req.block_height:
            query = query.filter(Snapshot.block_height == req.block_height)
        else:
            query = query.order_by(Snapshot.block_height.desc())

        snapshot = query.first()
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail="No complete snapshot found."
            )

        # Find AddressBalance by address_hash
        row = db.query(AddressBalance).filter(
            AddressBalance.snapshot_id == snapshot.id,
            AddressBalance.address_hash == req.address_hash,
        ).first()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"address_hash '{req.address_hash}' not found in snapshot "
                    f"at block {snapshot.block_height}. "
                    "Ensure the address is included in the UTXO snapshot."
                )
            )

        already_set = row.commitment is not None

        # Write commitment (idempotent if same value)
        if row.commitment and row.commitment != req.commitment:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A different commitment is already registered for this address_hash. "
                    "Each address can only have one active commitment per snapshot. "
                    "If you want to reset, contact the admin or use a different snapshot."
                )
            )

        if not already_set:
            row.commitment = req.commitment
            db.commit()

        merkle_path = json.loads(row.merkle_path) if row.merkle_path else []

        return WitnessRegisterResponse(
            commitment=req.commitment,
            address_hash=req.address_hash,
            balance=row.balance,
            block_height=snapshot.block_height,
            snapshot_root=snapshot.merkle_root,
            merkle_path=merkle_path,
            registered=not already_set,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Witness registration error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/{commitment}", response_model=WitnessResponse)
async def get_witness(commitment: str, block_height: Optional[int] = None):
    """
    Look up Merkle path + root for an already-registered commitment.

    Used by the frontend after registration to build the full proof witness.
    Returns the same data as /register but without writing anything.
    """
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot, AddressBalance
    import json

    db = SessionLocal()
    try:
        query = db.query(Snapshot).filter(Snapshot.status == 'complete')
        if block_height:
            query = query.filter(Snapshot.block_height == block_height)
        else:
            query = query.order_by(Snapshot.block_height.desc())

        snapshot = query.first()
        if not snapshot:
            raise HTTPException(status_code=404, detail="No complete snapshot found.")

        row = db.query(AddressBalance).filter(
            AddressBalance.snapshot_id == snapshot.id,
            AddressBalance.commitment == commitment,
        ).first()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Commitment '{commitment}' not found. "
                    "Call POST /api/snapshot/witness/register first."
                )
            )

        merkle_path = json.loads(row.merkle_path) if row.merkle_path else []

        return WitnessResponse(
            commitment=commitment,
            address_hash=row.address_hash,
            balance=row.balance,
            block_height=snapshot.block_height,
            snapshot_root=snapshot.merkle_root,
            merkle_path=merkle_path,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Witness lookup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
