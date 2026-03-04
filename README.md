# Latens

**Zero-Knowledge Bitcoin State Verification on Starknet**

Latens lets you prove Bitcoin solvency without ever revealing your address. A privacy-preserving ZK layer that bridges Bitcoin reputation to Starknet.

> *"I own ≥ 1 BTC"* — proven on-chain, address never seen.

**In-depth docs:** [Architecture](docs/architecture.md) · [Crypto Spec](docs/crypto-spec.md) · [Contracts](docs/contracts.md) · [API](docs/api.md) · [Security](docs/security.md) · [Privacy](docs/privacy.md) · [Integration Guide](docs/integration.md)

---

## How It Works

| Step | What happens |
|------|-------------|
| 1 | Latens snapshots the Bitcoin UTXO set at a fixed block height |
| 2 | Balances are committed into a [Poseidon Merkle tree](docs/crypto-spec.md) |
| 3 | The Merkle root is registered on Starknet via [`StateRootRegistry`](docs/contracts.md#staterootregistry) |
| 4 | You generate a ZK proof binding your address + a random salt to a commitment |
| 5 | [`BalanceVerifier`](docs/contracts.md#balanceverifier) checks the proof against the registry root — on-chain, trustless |
| 6 | [`DaoGate`](docs/contracts.md#daogate) optionally gates DAO membership behind your proof |

Privacy model: Your Bitcoin address is **never posted on-chain** at any point. The chain only sees `commitment = Poseidon(address_hash || salt)`. See the [full privacy analysis](docs/privacy.md) and [end-to-end execution flow](docs/flow.md).

---

## Quick Start

### Option A — Docker (one command)

```bash
cp .env.example .env          # fill in Starknet credentials if deploying
docker-compose up --build
```

- **Frontend** → http://localhost:3000
- **Backend API** → http://localhost:8000/docs

The backend automatically seeds 8 demo Bitcoin whale addresses (block 800000) on first startup.

### Option B — Demo script (manual stack)

```bash
chmod +x scripts/start_demo.sh
./scripts/start_demo.sh
```

Then open a second terminal and run the frontend:

```bash
cd frontend && npm run dev     # → http://localhost:3000
```

### Option C — Manual setup

**Prerequisites:** Python 3.11+, Node.js 18+

```bash
# Backend
cd backend
python -m venv venv
# Windows: venv\Scripts\activate  |  Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# Seed demo data (8 Bitcoin whale addresses at block 800000)
python scripts/seed_demo.py

# Start API server
uvicorn src.api.main:app --reload
# → http://localhost:8000/docs

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## Project Structure

```
latens/
├── backend/
│   ├── src/
│   │   ├── indexer/         # Bitcoin UTXO fetching (Blockstream API)
│   │   ├── crypto/          # Poseidon hash, Merkle tree builder
│   │   ├── circuit/         # ZK proof generator (Python simulation)
│   │   ├── api/             # FastAPI routes + rate limiting
│   │   └── models/          # SQLAlchemy ORM (Snapshot, AddressBalance)
│   ├── scripts/
│   │   ├── seed_demo.py     # Seed 8 demo whale addresses into DB
│   │   └── test_e2e_flow.py # End-to-end API smoke test
│   └── tests/               # 58 pytest tests
│
├── contracts/               # Cairo 1 smart contracts (Scarb 2.9.2)
│   ├── src/
│   │   ├── state_root_registry.cairo  # Stores Bitcoin Merkle roots on Starknet
│   │   ├── balance_verifier.cairo     # Verifies ZK balance inclusion proofs
│   │   └── dao_gate.cairo             # DAO membership behind balance proof
│   ├── scripts/
│   │   ├── deploy.mjs       # Deploy all 3 contracts to Sepolia (starknet.js)
│   │   └── verify_demo.mjs  # Run positive + negative proof tests on Sepolia
│   └── tests/               # 14 Cairo tests (scarb cairo-test)
│
├── frontend/                # Next.js 14 (static export)
│   └── src/
│       ├── app/             # App router
│       ├── components/      # ProofGenerator, WalletConnect, MerkleVisualizer, …
│       └── lib/crypto.ts    # Browser-side Poseidon + salt generation
│
├── scripts/
│   └── start_demo.sh        # One-command demo bootstrap
├── Makefile                 # make demo | test | docker
├── docker-compose.yml
└── .env.example
```

---

## API Reference

### Health

```
GET /health
→ { "status": "healthy" }
```

### Snapshot

```
GET /api/snapshot/latest
GET /api/snapshot/current     ← alias for /latest
GET /api/snapshot/{height}
GET /api/snapshot/status/{height}
POST /api/snapshot/generate   { "block_height": 800000 }
```

### Proof

```bash
POST /api/proof/generate

curl -X POST http://localhost:8000/api/proof/generate \
  -H "Content-Type: application/json" \
  -d '{
    "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "salt_hex": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "threshold": 0
  }'
```

Response includes `starknet_calldata` — pass directly to `BalanceVerifier.verify_proof()`.

Rate limit: 10 requests/minute per IP.

### Stats

```
GET /api/stats
```

---

## Smart Contracts

Full interface specs, storage layouts, and event schemas: [Contract Reference](docs/contracts.md)

| Contract | Address (Sepolia) | Purpose |
|----------|-------------------|---------|
| `StateRootRegistry` | deploy to get | Stores Bitcoin snapshot Merkle roots |
| `BalanceVerifier` | deploy to get | Verifies ZK balance inclusion proofs |
| `DaoGate` | deploy to get | DAO membership behind ≥ 1 BTC proof |

### Deploy to Starknet Sepolia

```bash
# 1. Get a Sepolia wallet (Argent X or Braavos → Sepolia testnet)
#    Faucet: https://faucet.starknet.io

# 2. Fill credentials in .env:
#    STARKNET_PRIVATE_KEY=0x...
#    STARKNET_ACCOUNT_ADDRESS=0x...

# 3. Build contracts
cd contracts && scarb build

# 4. Deploy all 3 contracts + register demo root
cd scripts && npm install && node deploy.mjs

# 5. Test on-chain verification (positive + negative cases)
node verify_demo.mjs
```

`deploy.mjs` automatically updates `.env` and `frontend/.env.local` with the deployed addresses.

---

## Testing

```bash
# Backend Python tests (58 tests)
cd backend
venv/Scripts/python -m pytest tests/ -v        # Windows
# venv/bin/python -m pytest tests/ -v          # Mac/Linux

# Cairo contract tests (14 tests)
cd contracts
scarb cairo-test

# Quick API smoke test (requires backend running)
cd backend && python scripts/test_e2e_flow.py

# All via Makefile
make test
```

---

## Privacy Model

See the [full privacy model](docs/privacy.md) for information-theoretic analysis of each layer, the calldata privacy caveat, and the production ZK path. See the [security model](docs/security.md) for threat analysis and known limitations.

| Layer | Sees | Never sees |
|-------|------|------------|
| Client | address, salt, balance | — |
| Backend (MVP) | address (for UTXO lookup) | salt |
| On-chain (Starknet) | commitment, threshold, Merkle root | address, balance |
| Chain explorer | commitment, tx hash | address, balance, identity |

**On-chain guarantee:** The verifier confirms that *someone* knows an address inside the Merkle tree with the correct balance, without learning *which* address or *what* balance. The `ProofVerified` event contains only `{commitment, threshold, snapshot_height, timestamp}`.

---

## Use Cases

1. **DAO Gating** — Prove ≥ X BTC to access a DAO, no address revealed
2. **Anonymous Lending** — Bitcoin credit score without KYC
3. **Airdrop Eligibility** — Target whale wallets without a public list
4. **Cross-Chain Reputation** — Port Bitcoin history to Starknet ecosystem

See the [integration guide](docs/integration.md) for Cairo code snippets, threshold tiers, and composable use case patterns.

---

## Demo Addresses

These addresses are pre-seeded in the demo database (block 800000):

| Label | Address |
|-------|---------|
| Whale-1 (Genesis block) | `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` |
| Whale-2 | `34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo` |
| Whale-3 | `1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Bitcoin data | Blockstream REST API |
| Indexer + API | Python 3.12, FastAPI, SQLAlchemy |
| Poseidon / Merkle | Pure Python (matches Starknet params exactly) |
| ZK circuit | Python simulation + Cairo on-chain verification |
| Smart contracts | Cairo 1, Scarb 2.9.2, Starknet Sepolia |
| Deploy scripts | starknet.js v5.29.0 (Node.js) |
| Frontend | Next.js 14 static export, TypeScript, TailwindCSS |
| Wallet | `get-starknet` + Argent X / Braavos |
| Container | Docker, docker-compose |

---

## License

MIT
