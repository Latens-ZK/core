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
from .routes import proof, snapshot, stats
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
    version="1.0.0",
)

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

app.include_router(proof.router,     prefix="/api/proof",    tags=["Proof"])
app.include_router(snapshot.router,  prefix="/api/snapshot", tags=["Snapshots"])
app.include_router(stats.router,     prefix="/api/stats",    tags=["Statistics"])


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Latens API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Health check endpoint for Docker healthcheck."""
    return {"status": "healthy"}
