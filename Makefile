# ────────────────────────────────────────────────────────────────────────────
# Latens — Developer Makefile
# Usage: make <target>
# ────────────────────────────────────────────────────────────────────────────

# Detect OS for venv binary path
ifeq ($(OS),Windows_NT)
  PYTHON := backend/venv/Scripts/python
  ACTIVATE := backend/venv/Scripts/activate
else
  PYTHON := backend/venv/bin/python
  ACTIVATE := backend/venv/bin/activate
endif

.PHONY: help install demo seed test test-backend test-contracts docker clean

## Show this help
help:
	@echo ""
	@echo "  Latens Developer Commands"
	@echo "  ─────────────────────────────────────────────"
	@echo "  make install       Install backend Python deps"
	@echo "  make seed          Seed demo DB (8 whale addresses, block 800000)"
	@echo "  make demo          Seed + start backend API (http://localhost:8000)"
	@echo "  make test          Run all backend tests (58 pytest tests)"
	@echo "  make test-backend  Run backend tests only"
	@echo "  make docker        Build and start full stack via Docker"
	@echo "  make clean         Remove compiled caches and local DB"
	@echo ""

## Install Python virtualenv + dependencies
install:
	cd backend && python -m venv venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r backend/requirements.txt
	@echo "Done. Activate with: source $(ACTIVATE)"

## Seed the demo SQLite database
seed:
	cd backend && $(abspath $(PYTHON)) scripts/seed_demo.py

## Seed demo data then start the backend API server
demo: seed
	@echo ""
	@echo "  Backend starting at http://localhost:8000"
	@echo "  API docs:          http://localhost:8000/docs"
	@echo ""
	@echo "  Quick test commands:"
	@echo "    curl http://localhost:8000/api/snapshot/latest"
	@echo '    curl -X POST http://localhost:8000/api/proof/generate \'
	@echo '      -H "Content-Type: application/json" \'
	@echo '      -d '"'"'{"address":"1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa","salt_hex":"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef","threshold":0}'"'"
	@echo ""
	cd backend && $(abspath $(PYTHON)) -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

## Run backend pytest suite (58 tests)
test-backend:
	cd backend && $(abspath $(PYTHON)) -m pytest tests/ -v

## Run all tests
test: test-backend
	@echo "All tests passed."

## Build and start the full stack with Docker Compose
docker:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example — edit it if needed."; fi
	docker-compose up --build

## Remove Python caches and local DB
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f backend/latens.db
	@echo "Cleaned."
