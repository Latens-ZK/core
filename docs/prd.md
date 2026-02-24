alright dinesh, here’s a **Claude Code – Plan Mode optimized PRD**
(clean, execution-focused, no fluff)

---

# PRD — Latens (Claude Code Plan Mode)

## 1. Objective

Build an MVP of **Latens**:
A zero-knowledge Bitcoin state verification layer deployed on Starknet using Cairo contracts.

Deliverables:

* Bitcoin state snapshot → Merkle root
* ZK balance / ownership proof
* On-chain verifier contract
* Working demo with real Bitcoin data

Reference:

* Starknet Docs: [https://docs.starknet.io/](https://docs.starknet.io/)

---

## 2. Scope (Strict MVP)

### In Scope

1. Bitcoin block ingestion (light indexer)
2. UTXO → address balance computation
3. Merkle tree over balances
4. ZK inclusion proof for:

   * Exact balance
   * ≥ X BTC threshold
5. Cairo verifier contract
6. Minimal UI demo

### Out of Scope

* Full Bitcoin consensus validation
* Wallet functionality
* Cross-chain bridging
* Real-time syncing
* Watchlists
* Compliance sets

---

## 3. System Architecture

### A. Off-Chain Layer

#### 1. Bitcoin Data Source

Options:

* Self-hosted Bitcoin node
* Blockstream API (dev mode)
  [https://blockstream.info/api/](https://blockstream.info/api/)

Goal:

* Fetch blocks
* Extract UTXOs
* Compute address balances

---

#### 2. Snapshot Generator

Input:

* Block height H

Output:

* JSON snapshot:

  ```
  {
    block_height,
    merkle_root,
    total_addresses,
    timestamp
  }
  ```

Logic:

* Map<Address → Balance>
* Filter: balance > 0
* Sort deterministically
* Build Merkle tree

Hash function:

* Poseidon (ZK friendly)

---

#### 3. ZK Circuit

Circuit Inputs (private):

* address
* salt
* balance

Public Inputs:

* merkle_root
* threshold (optional)

Constraints:

* Hash(address || salt)
* Verify Merkle inclusion
* Assert balance ≥ threshold

Output:

* proof
* public signals

Framework Options:

* Cairo native proof
* Or external (e.g., Stark-friendly circuit)

---

### B. On-Chain Layer (Starknet)

Deployed Contract Components:

#### 1. State Root Registry

Stores:

```
current_merkle_root
block_height
```

Functions:

* update_root(proof)
* get_root()

Access control:

* Admin only (MVP)
* Future → proof-of-correct-snapshot

---

#### 2. Proof Verifier

Function:

```
verify_balance_proof(proof, public_inputs) -> bool
```

Requirements:

* Valid ZK proof
* Merkle root matches registry

If valid:

* Emit event
* Return true

---

## 4. User Flow (MVP)

### Private Balance Proof

1. User enters BTC address locally
2. Frontend:

   * Generates random salt
   * Hashes address || salt
3. Backend:

   * Finds balance
   * Generates ZK proof
4. User submits proof to Starknet
5. Contract verifies
6. Boolean result displayed

Privacy:

* Address never sent on-chain
* Salt prevents rainbow correlation

---

## 5. Technical Stack

### Backend

* Rust or Python indexer
* Bitcoin RPC
* Merkle tree builder
* Proof generator

### ZK

* Cairo proof system (preferred)
* Poseidon hashing

### Smart Contracts

* Cairo 1
* Starknet testnet deployment

### Frontend

* Next.js minimal UI
* Starknet wallet integration

---

## 6. Data Structures

### Address Balance Map

```
Map<String address, u64 satoshis>
```

### Merkle Leaf

```
hash(address_hash || balance)
```

### Snapshot Metadata

```
struct Snapshot {
    block_height: u64,
    merkle_root: felt252,
}
```

---

## 7. Security Model

Trust Assumptions:

* Bitcoin consensus correctness
* Starknet verifier correctness

Attack Vectors:

* Malicious snapshot generation
* Incorrect indexing
* Balance overflow

Mitigations:

* Deterministic snapshot build
* Open-source indexer
* Public reproducibility

---

## 8. Performance Constraints

Target:

* Snapshot generation < 5 min
* Proof generation < 10 sec
* On-chain verification < reasonable gas

Limit:

* Only include addresses ≥ 0.01 BTC (optional optimization)

Reason:
Bitcoin UTXO set ~80–100GB
Source: [https://bitcoin.org/en/full-node](https://bitcoin.org/en/full-node)

---

## 9. Milestones (Claude Plan Mode Breakdown)

### Phase 1 — Indexing

* Connect to Bitcoin RPC
* Extract balances at fixed height
* Output deterministic JSON

### Phase 2 — Merkleization

* Implement Poseidon hash
* Build Merkle tree
* Output root

### Phase 3 — ZK Circuit

* Implement inclusion proof
* Implement ≥ threshold constraint
* Generate test proofs

### Phase 4 — Starknet Contract

* Deploy registry
* Deploy verifier
* Integrate proof verification

### Phase 5 — Demo UI

* Local proof generation
* Submit to Starknet
* Display verified result

---

## 10. Demo Narrative

1. “This is mempool.space — it sees your queries.”
   Mempool.space

2. “Latens hides what you’re querying.”

3. Generate private ≥1 BTC proof

4. Verify live on Starknet

5. Explain:

   * No address revealed
   * Only validity proven

---

## 11. Definition of Done

* Snapshot root stored on Starknet
* Valid proof verifies successfully
* Invalid proof fails
* No plaintext address on-chain
* Live demo using real Bitcoin block height

---

## 12. Risk Register

| Risk                         | Severity | Mitigation            |
| ---------------------------- | -------- | --------------------- |
| Proof generation too slow    | High     | Limit dataset         |
| Merkle tree too large        | Medium   | Balance threshold     |
| Starknet verifier complexity | Medium   | Use standard verifier |

---

## 13. Stretch Goals

* Recursive proof for snapshot correctness
* Non-association proofs
* Clean UTXO proofs
* DAO gating integration

---

If you want, next I can:

* Break this into **Claude Code task prompts**
* Or write a **dev execution checklist**
* Or design the exact Cairo contract structure

This is hackathon-viable if you keep it tight, dinesh.
