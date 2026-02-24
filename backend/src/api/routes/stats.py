"""
General statistics endpoints.
"""
from fastapi import APIRouter
from ...database import SessionLocal
from ...models.snapshot import Snapshot, AddressBalance
from sqlalchemy import func

router = APIRouter()

@router.get("/")
async def get_stats():
    """
    Get global protocol statistics.
    """
    db = SessionLocal()
    try:
        total_snapshots = db.query(Snapshot).count()
        latest_snapshot = db.query(Snapshot).order_by(Snapshot.block_height.desc()).first()
        
        # Calculate total BTC secured (sum of all snapshots' total_balance is wrong, 
        # we want the sum of balances in the LATEST snapshot or max?)
        # Let's show "Total Value Indexed" from the latest snapshot.
        
        tvl = 0
        latest_height = 0
        if latest_snapshot:
            tvl = latest_snapshot.total_balance
            latest_height = latest_snapshot.block_height
            
        return {
            "total_snapshots": total_snapshots,
            "latest_block_height": latest_height,
            "total_btc_indexed": tvl,
            "protocol_status": "Operational"
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()
