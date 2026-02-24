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

## Troubleshooting

- **"Snapshot not found"**: Ensure backend snapshot generator ran. Trigger via `POST /api/snapshot/generate`.
- **"Balance below threshold"**: Use a smaller threshold or a whale address.
- **Wallet Connection**: Ensure you are on Starknet Sepolia Testnet.
