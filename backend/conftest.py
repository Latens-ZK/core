"""
Root conftest for backend test suite.

Sets up sys.path and patches the SQLAlchemy engine to use a shared
in-memory SQLite database (via StaticPool) so all connections see the
same tables and data within a test run.
"""
import os
import sys
from pathlib import Path

# ── Path setup: make `from src.xxx import` work ───────────────────────────────
_BACKEND_DIR = Path(__file__).parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Set env vars before any src.* imports so database.py picks them up
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

# ── Patch src.database to use a StaticPool engine ────────────────────────────
# With sqlite:///:memory: each new connection normally gets an empty DB.
# StaticPool forces all connections to share the same in-memory connection,
# so Base.metadata.create_all() and SessionLocal() see the same tables.
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TEST_SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=_TEST_ENGINE)

import src.database as _db_module  # noqa: E402 — intentional late import
_db_module.engine = _TEST_ENGINE
_db_module.SessionLocal = _TEST_SESSION_LOCAL
