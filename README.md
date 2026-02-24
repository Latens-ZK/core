# Latens

**Zero-Knowledge Bitcoin State Verification on Starknet**

Latens allows users to privately prove Bitcoin balance ownership or threshold conditions without revealing their address or exact balance on-chain.

## 🎯 Overview

- **Privacy-First**: Prove you own ≥X BTC without revealing your address or exact balance
- **Zero-Knowledge**: Uses ZK proofs verified on Starknet
- **Bitcoin Native**: Works with real Bitcoin blockchain data
- **Trustless**: Cryptographically verifiable proofs
- **Modern UI**: Glassmorphism design with live protocol statistics


## 🏗️ Architecture

```
┌─────────────────┐
│  Bitcoin Chain  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  Indexer        │─────▶│ Merkle Tree  │
│  (Backend)      │      │  Builder     │
└─────────────────┘      └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ ZK Circuit   │
                         │ (Cairo)      │
                         └──────┬───────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         ▼                                             ▼
┌─────────────────┐                          ┌─────────────────┐
│  Frontend       │                          │  Starknet       │
│  (Next.js)      │─────────────────────────▶│  Contracts      │
└─────────────────┘      Submit Proof        └─────────────────┘
```

## 📁 Project Structure

```
latens/
├── backend/              # Python backend service
│   ├── src/
│   │   ├── indexer/     # Bitcoin data fetching
│   │   ├── crypto/      # Merkle tree & Poseidon hash
│   │   ├── circuit/     # Cairo circuit & proof generation
│   │   ├── api/         # FastAPI server
│   │   └── models/      # Database models
│   ├── tests/
│   └── requirements.txt
├── contracts/           # Cairo smart contracts
│   ├── src/
│   │   ├── state_root_registry.cairo
│   │   └── proof_verifier.cairo
│   ├── tests/
│   └── Scarb.toml
├── frontend/            # Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   └── package.json
└── docs/                # Documentation
    ├── prd.md
    └── flow.md
```

## 🚀 Quick Start

### Option A: Docker (Recommended)

Run the full stack (Frontend + Backend + DB) with one command:

```bash
docker-compose up --build
```
- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Option B: Manual Setup

#### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- [Scarb](https://docs.swmansion.com/scarb/docs/install.html) (for contracts)
- Starknet wallet (Argent/Braavos)

#### 2. Backend Setup
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate | Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.main:app --reload
```

#### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

#### 4. Smart Contracts
```bash
cd contracts
scarb build
# Deploy to Testnet (requires .env vars)
python scripts/deploy.py
```

## 🔧 Usage

### Generate a Snapshot

```bash
cd backend
python -m src.scripts.generate_snapshot --block-height 800000
```

### Start the API Server

```bash
cd backend
uvicorn src.api.main:app --reload
```

### Access the Demo

Open browser to `http://localhost:3000/demo`

## 🎮 Demo Flow

1. **Enter Bitcoin Address**: Input your BTC address locally
2. **Generate Proof**: Client-side commitment + backend proof generation
3. **Connect Wallet**: Connect Starknet wallet (Argent/Braavos)
4. **Submit Proof**: Verify on-chain without revealing address
5. **View Result**: See verification status

## 🔐 Privacy Guarantees

- ✅ Bitcoin address never appears on-chain
- ✅ Exact balance remains private
- ✅ Only threshold satisfaction is proven
- ✅ Salt prevents correlation attacks

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest tests/ -v

# Contract tests
cd contracts
scarb test

# Frontend tests
cd frontend
npm test
```

## 📚 Documentation

- [PRD](./docs/prd.md) - Product Requirements Document
- [Flow](./docs/flow.md) - Detailed User Flow Specification
- [Implementation Plan](./docs/implementation_plan.md) - Technical Implementation Guide

## 🛠️ Technology Stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **ZK Circuits**: Cairo
- **Smart Contracts**: Cairo on Starknet
- **Frontend**: Next.js, TypeScript, TailwindCSS
- **Cryptography**: Poseidon hash, Merkle trees

## 🎯 Use Cases

1. **Private Balance Verification**: Prove ownership without revealing amount
2. **Threshold Gating**: Access DAOs/services with ≥X BTC requirement
3. **Anonymous Reputation**: Build cross-chain reputation from Bitcoin holdings
4. **Compliance Proofs**: Prove non-interaction with blacklisted addresses

## 📄 License

MIT

## 🤝 Contributing

This is a hackathon project. Contributions welcome!

## 🔗 Resources

- [Starknet Docs](https://docs.starknet.io/)
- [Blockstream API](https://blockstream.info/api/)
- [Cairo Book](https://book.cairo-lang.org/)
