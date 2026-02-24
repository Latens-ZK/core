# Latens Demo Guide

This guide walks through the full demonstration of Latens for the hackathon.

---

## Prerequisites

**Terminal A — Backend:**
```bash
./scripts/start_demo.sh
# OR manually:
cd backend && python scripts/seed_demo.py
cd backend && uvicorn src.api.main:app --reload
```

**Terminal B — Frontend:**
```bash
cd frontend && npm run dev
# → http://localhost:3000
```

**Browser wallet:** Argent X or Braavos installed, switched to **Starknet Sepolia** testnet.

---

## Demo Script (7 minutes)

### SCENE 1 — The Privacy Problem (1 min)

1. Open [mempool.space](https://mempool.space) and search for `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa`.
2. _"Everything on Bitcoin is public. If I know your address, I know your balance, your transaction history — everything."_
3. _"But what if you want to prove you're a whale to join a DAO, get a loan, or claim an airdrop — completely anonymously?"_

---

### SCENE 2 — Latens Introduction (1 min)

1. Open **Latens** at `http://localhost:3000`.
2. _"Latens is a ZK verification layer. It takes a snapshot of the Bitcoin UTXO set, builds a Poseidon Merkle tree of all balances, and anchors the root on Starknet."_
3. Point to the **StateRadar** widget showing the live block height and Merkle root.
4. _"The root is immutable, on-chain. Anyone can verify against it."_

---

### SCENE 3 — Generating a ZK Proof (2 mins)

1. Click **Whale-1** demo badge → address fills in.
2. Set threshold to `1` BTC.
3. Click **Generate Cryptographic Evidence**.
4. While loading, explain:
   - _"The browser generates a random 32-byte salt."_
   - _"commitment = Poseidon(address\_hash || salt) — this is what goes on-chain."_
   - _"The backend computes: does this address exist in the Merkle tree with balance ≥ 1 BTC? It returns a ZK proof."_
5. Proof appears — point to the **Merkle Visualizer** showing the inclusion path.
6. Click the **Binary inspector icon** → show the raw `starknet_calldata` array.
   - _"This is the exact calldata passed to the Starknet contract. No address. No balance. Just a commitment and a proof path."_

---

### SCENE 4 — On-Chain Verification (2 mins)

1. Click **Transmit to Starknet**.
2. If wallet not connected, the modal opens automatically → connect and approve.
3. _"The Starknet BalanceVerifier contract checks: (1) commitment matches, (2) Merkle path leads to the registered root, (3) balance ≥ threshold. All in Cairo."_
4. Transaction confirms → **tx hash panel appears**.
5. Click **View on Starkscan** → show the `ProofVerified` event on Sepolia.
   - _"Commitment is on-chain. The Bitcoin address is nowhere."_

---

### SCENE 5 — DAO Gating Use Case (1 min)

1. _"Now imagine this DAO contract:"_
   ```
   DaoGate.join_dao(proof) → if balance ≥ 1 BTC → grant membership
   ```
2. _"You proved membership to a DAO without revealing which wallet you own. No KYC. No doxing. Pure cryptography."_
3. _"Use cases: DAOs, anonymous lending, airdrop eligibility, cross-chain reputation."_

---

## Phase 4: Starknet Contract Deployment

Deploy the contracts once — run forever.

### One-Time Setup

```bash
# 1. Fill in your Starknet Sepolia credentials in .env:
#    STARKNET_PRIVATE_KEY=0x<your-private-key>
#    STARKNET_ACCOUNT_ADDRESS=0x<your-account-address>
#
#    How to get credentials:
#    → Install Argent X or Braavos wallet
#    → Switch to Sepolia testnet
#    → Faucet: https://faucet.starknet.io
#    → Export private key from wallet settings

# 2. Build contracts (requires Scarb 2.9.2)
cd contracts && scarb build

# 3. Install deploy script dependencies (one time)
cd contracts/scripts && npm install

# 4. Deploy all 3 contracts + register demo Merkle root
node deploy.mjs

# 5. Verify on-chain (positive + negative cases)
node verify_demo.mjs
```

**deploy.mjs** does:
1. Declares + deploys `StateRootRegistry` (admin = your account)
2. Declares + deploys `BalanceVerifier` (registry = step-1 address)
3. Calls `update_root` with demo Merkle root at block 800,000
4. Declares + deploys `DaoGate` (verifier = step-2 address, threshold = 1 BTC)
5. Writes all addresses back to `.env` and `frontend/.env.local`

**verify_demo.mjs** does:
1. **POSITIVE**: sends valid proof for `1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ` → tx succeeds
2. **NEGATIVE**: sends tampered proof (wrong balance) → tx reverts

Both tests passing = deployment criterion met.

---

## Quick API Test (no wallet needed)

```bash
# Get the latest snapshot
curl http://localhost:8000/api/snapshot/latest | python -m json.tool

# Generate a ZK proof (replace salt with any 64-char hex)
curl -s -X POST http://localhost:8000/api/proof/generate \
  -H "Content-Type: application/json" \
  -d '{
    "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "salt_hex": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "threshold": 0
  }' | python -m json.tool

# Check verified_locally == true in the response
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `"No snapshot found"` | Run `python scripts/seed_demo.py` in `backend/` |
| `"Balance below threshold"` | Use a smaller threshold or pick Whale-1/Whale-2 |
| Wallet popup doesn't appear | Ensure Argent X / Braavos is installed and on Sepolia testnet |
| `"Verifier contract not deployed"` | Run `node deploy.mjs` and set `NEXT_PUBLIC_VERIFIER_ADDRESS` |
| Docker frontend build fails | Ensure `.env` exists (copy from `.env.example`) before building |
