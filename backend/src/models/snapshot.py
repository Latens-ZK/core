"""
Database models for Latens.
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, index=True)
    block_height = Column(Integer, unique=True, index=True)
    block_hash = Column(String, index=True)
    merkle_root = Column(String)
    total_addresses = Column(Integer)
    total_balance = Column(BigInteger)
    timestamp = Column(Integer)           # Bitcoin block timestamp (unix)
    status = Column(String, default='complete')  # pending | building | complete | failed
    created_at = Column(DateTime, default=datetime.utcnow)

    balances = relationship("AddressBalance", back_populates="snapshot")


class AddressBalance(Base):
    __tablename__ = "address_balances"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), index=True)
    address = Column(String, index=True)
    address_hash = Column(String)         # Hex string of Poseidon(sha256(address))
    balance = Column(BigInteger)          # Satoshis
    merkle_path = Column(Text)            # JSON: [{"value": int, "direction": bool}]

    snapshot = relationship("Snapshot", back_populates="balances")
