"""
Snapshot management endpoints with Pydantic response models.
"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Response Models ───────────────────────────────────────────────────────────

class SnapshotResponse(BaseModel):
    id: int
    block_height: int
    block_hash: Optional[str]
    merkle_root: str
    total_addresses: int
    total_balance: int
    timestamp: int
    status: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True   # ORM → Pydantic


class GenerateRequest(BaseModel):
    block_height: Optional[int] = None   # None = use latest


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/generate", status_code=202)
async def generate_snapshot(req: GenerateRequest, background_tasks: BackgroundTasks):
    """Trigger snapshot generation in background."""
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot

    db = SessionLocal()
    try:
        # Determine block height
        if req.block_height:
            block_height = req.block_height
        else:
            from ...indexer.bitcoin_client import BitcoinClient
            client = BitcoinClient()
            block_height = client.fetch_latest_block_height()

        # Check if already exists
        existing = db.query(Snapshot).filter(
            Snapshot.block_height == block_height
        ).first()
        if existing:
            return {
                "message": f"Snapshot at block {block_height} already exists",
                "block_height": block_height,
                "status": existing.status,
            }

        # Create a pending record so the user can poll status
        pending = Snapshot(
            block_height=block_height,
            block_hash="pending",
            merkle_root="0x0",
            total_addresses=0,
            total_balance=0,
            timestamp=0,
            status='pending',
        )
        db.add(pending)
        db.commit()

    finally:
        db.close()

    background_tasks.add_task(_run_snapshot, block_height)
    return {
        "message": "Snapshot generation started",
        "block_height": block_height,
        "status": "pending",
        "poll": f"/api/snapshot/{block_height}/status",
    }


async def _run_snapshot(block_height: int):
    """Background task wrapper with DB status tracking."""
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot
    from ...indexer.snapshot_generator import SnapshotGenerator

    db = SessionLocal()
    try:
        snapshot = db.query(Snapshot).filter(Snapshot.block_height == block_height).first()
        if snapshot:
            snapshot.status = 'building'
            db.commit()

        gen = SnapshotGenerator()
        gen.generate_snapshot(block_height)

    except Exception as e:
        logger.error(f"Snapshot generation failed for block {block_height}: {e}", exc_info=True)
        db = SessionLocal()
        try:
            snapshot = db.query(Snapshot).filter(Snapshot.block_height == block_height).first()
            if snapshot:
                snapshot.status = 'failed'
                db.commit()
        finally:
            db.close()
    finally:
        db.close()


@router.get("/status/{block_height}")
async def get_snapshot_status(block_height: int):
    """Poll snapshot generation status."""
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot

    db = SessionLocal()
    try:
        snapshot = db.query(Snapshot).filter(Snapshot.block_height == block_height).first()
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"No snapshot found for block {block_height}")
        return {"block_height": block_height, "status": snapshot.status}
    finally:
        db.close()


@router.get("/latest", response_model=SnapshotResponse)
async def get_latest_snapshot():
    """Get the most recent complete snapshot."""
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot

    db = SessionLocal()
    try:
        snapshot = db.query(Snapshot).filter(
            Snapshot.status == 'complete'
        ).order_by(Snapshot.block_height.desc()).first()

        if not snapshot:
            raise HTTPException(status_code=404, detail="No snapshots available yet")

        return snapshot
    finally:
        db.close()


@router.get("/current", response_model=SnapshotResponse)
async def get_current_snapshot():
    """Alias for /latest — returns the most recent complete snapshot (PRD §4.4)."""
    return await get_latest_snapshot()


@router.get("/{block_height}", response_model=SnapshotResponse)
async def get_snapshot(block_height: int):
    """Get snapshot at a specific block height."""
    from ...database import SessionLocal
    from ...models.snapshot import Snapshot

    db = SessionLocal()
    try:
        snapshot = db.query(Snapshot).filter(
            Snapshot.block_height == block_height
        ).first()

        if not snapshot:
            raise HTTPException(status_code=404, detail=f"No snapshot for block {block_height}")

        return snapshot
    finally:
        db.close()
