"""
Main FastAPI application.
"""
import os
import logging
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from .limiter import limiter
from .routes import proof, snapshot, stats, witness
from ..database import engine
from ..models.snapshot import Base

# Create tables
Base.metadata.create_all(bind=engine)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Latens API",
    description="Zero-Knowledge Bitcoin State Verification on Starknet",
    version="1.1.0",
)

# Rate limiting (API-03: max 10 proof requests/minute per commitment)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — read from env, fallback to localhost for dev
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: /api/snapshot/witness must be registered BEFORE /api/snapshot
# because FastAPI matches prefix routes in order and witness has a deeper prefix.
app.include_router(witness.router,   prefix="/api/snapshot/witness", tags=["Witness"])
app.include_router(proof.router,     prefix="/api/proof",            tags=["Proof"])
app.include_router(snapshot.router,  prefix="/api/snapshot",         tags=["Snapshots"])
app.include_router(stats.router,     prefix="/api/stats",            tags=["Statistics"])


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Latens API",
        "version": "1.1.0",
    }


@app.get("/health")
async def health():
    """Health check endpoint for Docker healthcheck."""
    return {"status": "healthy"}
