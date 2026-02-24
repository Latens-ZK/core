#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# Latens — One-command demo bootstrap
# Usage: ./scripts/start_demo.sh
# ────────────────────────────────────────────────────────────────────────────
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"

# Detect virtualenv Python (Windows git-bash vs Unix)
VENV_WIN="$BACKEND/venv/Scripts/python"
VENV_UNIX="$BACKEND/venv/bin/python"
if [ -f "$VENV_WIN" ]; then
    PYTHON="$VENV_WIN"
elif [ -f "$VENV_UNIX" ]; then
    PYTHON="$VENV_UNIX"
else
    echo "ERROR: virtualenv not found. Run: cd backend && python -m venv venv && pip install -r requirements.txt"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         LATENS — ZK Bitcoin Solvency on Starknet             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Seed demo data ────────────────────────────────────────────────────
echo "[1/3] Seeding demo database..."
cd "$BACKEND" && "$PYTHON" scripts/seed_demo.py
echo "      Done. 8 Bitcoin whale addresses at block 800000."
echo ""

# ── Step 2: Start backend ─────────────────────────────────────────────────────
echo "[2/3] Starting backend API server (port 8000)..."
cd "$BACKEND" && "$PYTHON" -m uvicorn src.api.main:app \
    --host 0.0.0.0 --port 8000 --log-level warning &
BACKEND_PID=$!

# Wait for healthcheck
echo -n "      Waiting for backend"
for i in $(seq 1 15); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo " ✓"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# ── Step 3: Print demo commands ───────────────────────────────────────────────
echo "[3/3] Ready! Copy-paste these commands to test the API:"
echo ""
echo "  ┌─ Get the latest snapshot ────────────────────────────────────┐"
echo "  │  curl http://localhost:8000/api/snapshot/latest              │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
echo "  ┌─ Generate a ZK proof ────────────────────────────────────────┐"
printf '  │  curl -s -X POST http://localhost:8000/api/proof/generate \\\n'
printf '  │    -H "Content-Type: application/json" \\\n'
printf "  │    -d '{\"address\":\"1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa\",\\\n"
printf '  │         "salt_hex":"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",\\\n'
printf '  │         "threshold":0}'"'"' | python -m json.tool\n'
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
echo "  ┌─ Frontend (open a new terminal) ─────────────────────────────┐"
echo "  │  cd frontend && npm run dev   →  http://localhost:3000       │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
echo "  Backend API: http://localhost:8000"
echo "  API docs:    http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."
echo ""

# Keep script alive (backend is in background)
wait $BACKEND_PID
