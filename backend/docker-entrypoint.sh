#!/bin/sh
set -e

echo "==> Latens backend starting..."

# Seed demo data if the database is empty
python - <<'PYEOF'
import os, sys
sys.path.insert(0, '/app')
os.environ.setdefault('DATABASE_URL', 'sqlite:////app/data/latens.db')

from src.database import engine
from src.models.snapshot import Base, Snapshot
from sqlalchemy.orm import Session

Base.metadata.create_all(bind=engine)

with Session(engine) as db:
    count = db.query(Snapshot).count()

if count == 0:
    print("==> No snapshots found — seeding demo data...")
    import subprocess
    result = subprocess.run(
        ['python', 'scripts/seed_demo.py'],
        cwd='/app',
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("SEED ERROR:", result.stderr)
        sys.exit(1)
    print(result.stdout)
    print("==> Demo data seeded (block 800000, 8 whale addresses).")
else:
    print(f"==> Found {count} snapshot(s) — skipping seed.")
PYEOF

echo "==> Starting uvicorn..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
