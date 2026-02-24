# Latens Demo Guide

This guide walks through the demonstration of Latens for the hackathon.

## Prerequisites

1. **Backend Running**:
   ```bash
   cd backend
   # Ensure venv is active and dependencies installed
   uvicorn src.api.main:app --reload
   ```

2. **Frontend Running**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Starknet Wallet**: Argent X or Braavos installed in browser (Testnet).

## Demo Script

### SCENE 1: The Privacy Problem (1 min)

1. Open [mempool.space](https://mempool.space).
2. "Everything on Bitcoin is public. If I know your address, I know your balance."
3. "But what if I want to prove I'm a whale to a DAO, completely anonymously?"

### SCENE 2: Latens Intro (1 min)

1. Open **Latens** at `http://localhost:3000`.
2. "Latens is a ZK verification layer. It snapshots Bitcoin state and lets you prove facts about your holdings without revealing them."

### SCENE 3: Generating a Proof (2 mins)

1. Enter a Bitcoin Address: `bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh` (or any valid address).
2. Enter Threshold: `100000000` (1 BTC).
3. Click **Generate Proof**.
4. Explain what's happening:
   - "My browser generates a random salt."
   - "We hash Address + Salt = Commitment."
   - "The backend proves: I know an Address inside the Merkle Tree with Balance > 1 BTC, and it matches this Commitment."

### SCENE 4: On-Chain Verification (2 mins)

1. Proof appears (Green Box).
2. Click **Verify on Starknet**.
3. Wallet popup appears. Approve transaction.
4. "The Starknet contract verifies the ZK proof. It sees the Commitment and the Proof, but NEVER the address."
5. Show success message.

### SCENE 5: The "Why" (1 min)

1. "We just bridged Bitcoin reputation to Starknet."
2. "Use cases: DAO Gating, lending credit scores, anonymous airdrops."

## Phase 4: Starknet Contract Deployment

Deploy the contracts once, then use them forever.

### One-Time Setup

```bash
# 1. Fill in your Starknet Sepolia credentials in .env:
#    STARKNET_PRIVATE_KEY=0x<your-private-key>
#    STARKNET_ACCOUNT_ADDRESS=0x<your-account-address>
#
#    Get a free account + STRK tokens:
#    → Install Argent X or Braavos wallet
#    → Switch to Sepolia testnet
#    → Faucet: https://faucet.starknet.io

# 2. Install deploy script dependencies (one time):
cd contracts/scripts && npm install

# 3. Deploy both contracts + register demo Merkle root:
node deploy.mjs

# 4. Verify on-chain proofs (positive + negative cases):
node verify_demo.mjs
```

**deploy.mjs** does:
1. Declares + deploys `StateRootRegistry` (admin = your account)
2. Declares + deploys `BalanceVerifier` (registry address passed in constructor)
3. Calls `update_root` with the demo snapshot Merkle root at block 800,000
4. Writes contract addresses back to `.env` and `frontend/.env.local`

**verify_demo.mjs** does:
1. **POSITIVE**: sends valid proof for `1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ` → tx succeeds
2. **NEGATIVE**: sends tampered proof (wrong balance) → tx reverts

Both tests passing = Phase 4 done criterion met.

## Troubleshooting

- **"Snapshot not found"**: Ensure backend snapshot generator ran. Trigger via `POST /api/snapshot/generate`.
- **"Balance below threshold"**: Use a smaller threshold or a whale address.
- **Wallet Connection**: Ensure you are on Starknet Sepolia Testnet.
