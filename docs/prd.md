# PRD — Latens: Zero-Knowledge Bitcoin State Verification on Starknet

**Version:** 1.1
**Status:** MVP Build
**Stack:** Cairo 1 · Starknet Sepolia · Python/Rust Indexer · Next.js Frontend

---

## 1. Problem Statement

Bitcoin address queries on public explorers (Mempool.space, Blockstream, etc.) leak user intent — the querier's IP, identity, and interest are exposed. There is no privacy-preserving way to prove:

- "I own ≥ X BTC" without revealing the address
- "My address is not blacklisted" without identifying yourself

**Latens** solves this by anchoring a Bitcoin balance snapshot as a Merkle root on Starknet, then allowing users to generate ZK proofs of balance inclusion — no address revealed on-chain.

---

## 2. MVP Scope

### In Scope

| # | Feature |
|---|---------|
| 1 | Bitcoin UTXO data ingestion via Blockstream API |
| 2 | Address balance aggregation at fixed block height |
| 3 | Deterministic Merkle tree with Poseidon hashing |
| 4 | ZK proof of balance inclusion (exact balance) |
| 5 | ZK proof of threshold satisfaction (balance ≥ X BTC) |
| 6 | Cairo on-chain State Root Registry |
| 7 | Cairo on-chain Proof Verifier |
| 8 | Minimal Next.js demo UI with Starknet wallet integration |

### Out of Scope (V1)

- Full Bitcoin consensus validation
- Wallet / key management
- Cross-chain bridging
- Real-time block syncing
- Watchlists / alerting
- Compliance set proofs (stretch goal)

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        OFF-CHAIN LAYER                          │
│                                                                 │
│  Blockstream API ──► Indexer ──► Snapshot Generator             │
│                                       │                         │
│                                  Merkle Tree                    │
│                                  (Poseidon)                     │
│                                       │                         │
│                               ZK Proof Generator               │
│                                       │                         │
└───────────────────────────────────────┼─────────────────────────┘
                                        │
                         REST API + proof blob
                                        │
┌───────────────────────────────────────▼─────────────────────────┐
│                         FRONTEND (Next.js)                      │
│  - Address input         - Salt generation                      │
│  - Commitment hash       - Proof display                        │
│  - Wallet connect        - Starknet tx submit                   │
└───────────────────────────────────────┬─────────────────────────┘
                                        │
                              Starknet Sepolia
                                        │
┌───────────────────────────────────────▼─────────────────────────┐
│                       ON-CHAIN LAYER (Cairo)                    │
│                                                                 │
│   StateRootRegistry          ProofVerifier                      │
│   ├─ current_root            ├─ verify_balance_proof()          │
│   ├─ block_height            └─ verify_threshold_proof()        │
│   └─ update_root()                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Requirements

---

### 4.1 Bitcoin Indexer

**Language:** Python (preferred for speed) or Rust
**Data Source:** Blockstream API — `https://blockstream.info/api/`

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| IDX-01 | Accept a target `block_height` as input parameter |
| IDX-02 | Fetch all UTXOs confirmed at or before `block_height` |
| IDX-03 | Aggregate satoshi balances per address: `Map<address_hash → u64>` |
| IDX-04 | Filter out addresses with `balance == 0` |
| IDX-05 | (Optional) Filter out addresses with `balance < 1,000,000 satoshis` (0.01 BTC) to bound dataset size |
| IDX-06 | Output a deterministic JSON snapshot file |
| IDX-07 | Snapshot must be reproducible: same block → same output always |

#### Output Schema

```json
{
  "block_height": 880000,
  "timestamp": 1700000000,
  "total_addresses": 42000,
  "balances": [
    {
      "address": "bc1q...",
      "address_hash": "0x1a2b...",
      "satoshis": 150000000
    }
  ]
}
```

#### Non-Functional Requirements

- Snapshot generation must complete in < 5 minutes for filtered dataset
- Must log errors for unreachable blocks or API rate limits
- Must not mutate snapshot after generation (immutable artifact)

---

### 4.2 Merkle Tree Builder

**Language:** Same as indexer (Python/Rust)
**Hash Function:** Poseidon (Starknet-native, ZK-friendly)

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| MRK-01 | Sort address entries lexicographically by `address_hash` before tree construction |
| MRK-02 | Compute each leaf as: `leaf = Poseidon(address_hash ∥ balance_as_felt252)` |
| MRK-03 | Build a binary Merkle tree over all leaves |
| MRK-04 | Pad tree to next power of 2 with zero-leaves if needed |
| MRK-05 | Output: `merkle_root` as `felt252` |
| MRK-06 | Store per-address Merkle paths for proof generation |
| MRK-07 | Merkle path must include: sibling hashes + left/right position per level |

#### Merkle Path Schema

```json
{
  "address_hash": "0x1a2b...",
  "balance": 150000000,
  "leaf_index": 7,
  "path": [
    { "sibling": "0xabc...", "position": "right" },
    { "sibling": "0xdef...", "position": "left" }
  ]
}
```

#### Non-Functional Requirements

- Poseidon implementation must match Starknet's Poseidon parameter set exactly
- Tree depth must be logged for circuit parameter configuration

---

### 4.3 ZK Proof Generator

**Framework:** Cairo native proof system (STARK-based, runs off-chain then verified on-chain)
**Alternative:** Garaga verifier library for SNARK integration if needed

#### Circuit: `balance_inclusion_proof`

**Private Witness (never leaves prover):**

```
address_hash   : felt252
salt           : felt252
balance        : u64
merkle_path[]  : [(sibling: felt252, position: u8)]
```

**Public Inputs (visible on-chain):**

```
snapshot_root  : felt252
commitment     : felt252
threshold      : u64   (0 = no threshold check)
```

**Constraints (all must hold):**

| # | Constraint |
|---|-----------|
| C-01 | `Poseidon(address_hash ∥ salt) == commitment` |
| C-02 | `ComputeMerkleRoot(address_hash, balance, merkle_path) == snapshot_root` |
| C-03 | If `threshold > 0`: `balance >= threshold` |

**Output:**

```
proof_blob     : bytes
public_signals : { snapshot_root, commitment, threshold }
```

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| PRF-01 | Proof generation must complete in < 10 seconds |
| PRF-02 | Invalid balance (threshold not met) must fail at circuit level, not return false proof |
| PRF-03 | Address not in snapshot must return `Error: address_not_indexed` |
| PRF-04 | Proof must be serializable to JSON for frontend transport |
| PRF-05 | Proof must be verifiable by the on-chain Cairo verifier |

---

### 4.4 Backend API Server

**Language:** Python (FastAPI) or Rust (Axum)

#### Endpoints

##### `POST /generate-proof`

Request:
```json
{
  "address": "bc1q...",
  "threshold_satoshis": 100000000,
  "commitment": "0x..."
}
```

Response (success):
```json
{
  "proof": "0x...",
  "public_signals": {
    "snapshot_root": "0x...",
    "commitment": "0x...",
    "threshold": 100000000
  },
  "block_height": 880000
}
```

Response (error):
```json
{
  "error": "address_not_indexed | threshold_not_met | snapshot_unavailable",
  "message": "Human-readable description"
}
```

##### `GET /snapshot/current`

Response:
```json
{
  "block_height": 880000,
  "merkle_root": "0x...",
  "total_addresses": 42000,
  "timestamp": 1700000000
}
```

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| API-01 | Validate Bitcoin address format (Base58 / Bech32) before processing |
| API-02 | Never log or persist plaintext addresses beyond request lifetime |
| API-03 | Rate limit: max 10 proof requests/minute per IP |
| API-04 | Return structured error codes (not raw exceptions) |
| API-05 | Serve current snapshot metadata at all times |

---

### 4.5 Cairo Smart Contracts

**Language:** Cairo 1
**Network:** Starknet Sepolia testnet
**Deployment:** Via Starknet Foundry (`sncast`)

---

#### Contract 1: `StateRootRegistry`

**Storage:**

```cairo
#[storage]
struct Storage {
    current_root: felt252,
    block_height: u64,
    updated_at: u64,
    admin: ContractAddress,
}
```

**Functions:**

```cairo
// Admin only — updates the on-chain snapshot root
fn update_root(
    ref self: ContractState,
    new_root: felt252,
    block_height: u64
);

// Public read
fn get_root(self: @ContractState) -> (felt252, u64);

// Admin transfer
fn transfer_admin(ref self: ContractState, new_admin: ContractAddress);
```

**Events:**

```cairo
#[event]
enum Event {
    RootUpdated: RootUpdated,
}

struct RootUpdated {
    new_root: felt252,
    block_height: u64,
    updated_at: u64,
}
```

**Functional Requirements:**

| ID | Requirement |
|----|-------------|
| REG-01 | Only admin address can call `update_root` |
| REG-02 | `update_root` must reject if `block_height` is not greater than current |
| REG-03 | `get_root` must be callable by any address with no gas (view function) |
| REG-04 | Emit `RootUpdated` event on every successful update |

---

#### Contract 2: `BalanceProofVerifier`

**Dependencies:** References `StateRootRegistry` for root validation.

**Functions:**

```cairo
fn verify_balance_proof(
    ref self: ContractState,
    proof: Array<felt252>,
    snapshot_root: felt252,
    commitment: felt252,
    threshold: u64,
) -> bool;
```

**Verification Logic:**

1. Assert `snapshot_root == StateRootRegistry::get_root()`
2. Run embedded STARK verifier on `proof` with `(snapshot_root, commitment, threshold)` as public inputs
3. If valid → emit `ProofVerified` event → return `true`
4. If invalid → revert with `INVALID_PROOF` error

**Events:**

```cairo
struct ProofVerified {
    commitment: felt252,
    threshold: u64,
    block_height: u64,
    verifier: ContractAddress,
}
```

**Functional Requirements:**

| ID | Requirement |
|----|-------------|
| VER-01 | Reject proof if `snapshot_root` does not match registry |
| VER-02 | Reject any proof with mismatched public inputs |
| VER-03 | Emit `ProofVerified` on success — include `commitment` and `threshold` |
| VER-04 | Never store or emit the user's address or balance |
| VER-05 | Function must be callable by any EOA (no access restriction) |

---

### 4.6 Frontend (Next.js)

**Framework:** Next.js 14+ (App Router)
**Wallet:** `starknet-react` + Argent / Braavos

#### Pages / Components

| Component | Responsibility |
|-----------|---------------|
| `AddressInput` | BTC address entry + local format validation |
| `SaltGenerator` | Generate 32-byte random salt in-browser (not persisted) |
| `CommitmentDisplay` | Show `Poseidon(address_hash ∥ salt)` result |
| `ThresholdInput` | Optional BTC threshold input (in BTC, convert to satoshis) |
| `ProofRequest` | POST to backend, display loading / error states |
| `WalletConnect` | Connect Argent/Braavos wallet |
| `ProofSubmit` | Serialize proof, call `verify_balance_proof` on-chain |
| `ResultDisplay` | Show verification result + block height + Starknet tx hash |

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| UI-01 | Validate BTC address format client-side before any network call |
| UI-02 | Salt must be generated fresh per session using `crypto.getRandomValues()` |
| UI-03 | Salt must never be persisted to `localStorage` or cookies |
| UI-04 | Commitment must be computed client-side using JS Poseidon implementation |
| UI-05 | Display current snapshot block height and merkle root from `/snapshot/current` |
| UI-06 | Show meaningful error states: `address_not_indexed`, `threshold_not_met`, `snapshot_mismatch` |
| UI-07 | Show Starknet transaction hash as proof of on-chain verification |
| UI-08 | Show: "Address never sent on-chain" messaging clearly |

---

## 5. Data Flow (End-to-End)

```
1. [Client]  User enters BTC address + optional threshold
2. [Client]  Generate salt = crypto.getRandomValues(32 bytes)
3. [Client]  address_hash = Poseidon(address_bytes)
4. [Client]  commitment = Poseidon(address_hash || salt)
5. [Client]  POST /generate-proof { address, commitment, threshold }

6. [Backend] Validate address format
7. [Backend] Compute address_hash
8. [Backend] Lookup balance in snapshot DB
9. [Backend] Retrieve merkle_path for address_hash
10. [Backend] Run ZK circuit with private inputs
11. [Backend] Return { proof, public_signals }

12. [Client]  Display proof received
13. [Client]  User connects Starknet wallet
14. [Client]  Call BalanceProofVerifier.verify_balance_proof(proof, root, commitment, threshold)

15. [Contract] Assert root matches StateRootRegistry
16. [Contract] Run STARK verifier
17. [Contract] Emit ProofVerified event
18. [Contract] Return true

19. [Client]  Display: ✔ Valid | Block H | Threshold: ≥ X BTC
```

---

## 6. Data Privacy Guarantees

| Layer | Knows | Does NOT Know |
|-------|-------|---------------|
| Client | address, salt, balance (if returned) | nothing hidden from self |
| Backend (MVP) | address, balance | salt (only client knows) |
| On-Chain | proof, root, commitment, threshold | address, balance, UTXOs |
| Public / Chain explorer | commitment, threshold, tx hash | address, balance, identity |

**MVP trust note:** Backend sees the plaintext address in Model A. This is acceptable for hackathon. Production hardening moves to commitment-only model via TEE or client-side proof generation.

---

## 7. Error States

| Error Code | Trigger | User Message |
|------------|---------|--------------|
| `address_not_indexed` | Address balance = 0 or below filter threshold | "Address not included in current snapshot." |
| `threshold_not_met` | balance < threshold in circuit | "Threshold not satisfied. Proof cannot be generated." |
| `snapshot_mismatch` | Proof root ≠ contract root | "Snapshot outdated. Please regenerate your proof." |
| `invalid_proof` | Verifier rejects proof | "Proof verification failed. Transaction reverted." |
| `address_invalid` | Bad BTC address format | "Invalid Bitcoin address format." |
| `snapshot_unavailable` | No snapshot loaded | "System snapshot not available. Try again later." |

---

## 8. Security Requirements

| ID | Requirement |
|----|-------------|
| SEC-01 | Merkle tree ordering must be deterministic and canonical (lexicographic by address_hash) |
| SEC-02 | No duplicate leaves allowed in Merkle tree |
| SEC-03 | Salt must be ≥ 32 bytes, cryptographically random |
| SEC-04 | Admin key for `StateRootRegistry` must use a hardware wallet or multisig for production |
| SEC-05 | Proof verifier must not allow replay: commitment binds address+salt uniquely |
| SEC-06 | Balance encoded as `u64` — must validate no overflow during Poseidon input packing |
| SEC-07 | Snapshot JSON must be hash-verified before loading into proof generator |
| SEC-08 | Backend must sanitize all inputs before passing to proof circuit |

---

## 9. Performance Targets

| Operation | Target |
|-----------|--------|
| Snapshot generation (filtered, ~1M addresses) | < 5 minutes |
| Merkle tree construction | < 60 seconds |
| ZK proof generation | < 10 seconds |
| On-chain verification gas | < 0.01 ETH equivalent on Starknet |
| Frontend proof request e2e | < 15 seconds total |

---

## 10. Build Milestones & Acceptance Criteria

### Phase 1 — Indexer + Snapshot

- [ ] Connect to Blockstream API, fetch UTXOs at fixed block height
- [ ] Aggregate balances per address
- [ ] Apply balance filter (≥ 0.01 BTC)
- [ ] Output deterministic JSON snapshot
- **Done when:** Same block_height run twice → byte-identical snapshot output

### Phase 2 — Merkle Tree

- [ ] Implement Poseidon hash matching Starknet's parameters
- [ ] Sort addresses by hash, build binary tree
- [ ] Compute and output `merkle_root`
- [ ] Store per-address merkle paths
- **Done when:** Merkle root is reproducible and path verification passes offline

### Phase 3 — ZK Circuit

- [ ] Implement Cairo circuit with constraints C-01, C-02, C-03
- [ ] Generate proof for valid address + balance
- [ ] Confirm invalid threshold fails at circuit, not verifier
- [ ] Confirm address-not-in-tree fails at merkle constraint
- **Done when:** Valid proof verifies, invalid proof rejects — both deterministic

### Phase 4 — Cairo Contracts

- [ ] Deploy `StateRootRegistry` to Starknet Sepolia
- [ ] Deploy `BalanceProofVerifier` to Starknet Sepolia
- [ ] Call `update_root` with real snapshot root
- [ ] Call `verify_balance_proof` with valid proof → returns true
- [ ] Call `verify_balance_proof` with tampered proof → reverts
- **Done when:** Both positive and negative cases pass on Sepolia

### Phase 5 — Backend API

- [ ] Implement `/generate-proof` endpoint
- [ ] Implement `/snapshot/current` endpoint
- [ ] Validate address, load snapshot, run proof, return result
- **Done when:** Curl test with real BTC address returns verifiable proof blob

### Phase 6 — Frontend Demo

- [ ] Address input + salt generation + commitment display
- [ ] Proof request flow with loading states
- [ ] Wallet connect + on-chain submit
- [ ] Result display with tx hash
- **Done when:** Full e2e demo runs without manual intervention

---

## 11. Definition of Done (MVP)

- [ ] Snapshot Merkle root is live on Starknet Sepolia
- [ ] Valid ZK proof verifies successfully on-chain → `ProofVerified` event emitted
- [ ] Invalid / tampered proof is rejected
- [ ] No plaintext Bitcoin address appears on-chain at any point
- [ ] Demo uses real Bitcoin block height (not synthetic data)
- [ ] Frontend shows: address hidden, threshold verified, tx hash visible

---

## 12. Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Blockstream API rate limits block snapshot generation | High | Cache responses; use a local Bitcoin node as fallback |
| Poseidon implementation mismatch between off-chain and Cairo | High | Use Starknet's official Poseidon constants; write cross-validation test |
| ZK proof generation > 10 sec | High | Limit dataset to addresses ≥ 0.01 BTC; profile circuit depth |
| Merkle tree too large for memory | Medium | Stream-build tree; use depth-first construction |
| Starknet Sepolia outage during demo | Medium | Pre-record a verified tx as fallback; cache the result |
| Frontend Poseidon JS lib diverges from Cairo | Medium | Write shared test vectors; verify commitment matches off-chain |
| Admin key compromise for root update | Low (MVP) | Use test key for hackathon; document production multisig path |

---

## 13. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Bitcoin data | Blockstream REST API |
| Indexer | Python 3.11+ (or Rust) |
| Merkle / Poseidon | Python `poseidon-hash` or custom with Starknet params |
| ZK circuit | Cairo (native STARK proof) |
| Proof generation | Cairo runner (off-chain) |
| Backend API | FastAPI (Python) or Axum (Rust) |
| Smart contracts | Cairo 1, Starknet Foundry |
| Contract deployment | `sncast` CLI, Starknet Sepolia |
| Frontend | Next.js 14, `starknet-react`, TailwindCSS |
| Wallet | Argent X / Braavos |

---

## 14. Stretch Goals (Post-MVP)

| Goal | Description |
|------|-------------|
| Non-association proof | Prove address is NOT in a blacklist set |
| Recursive proof | Prove correctness of snapshot generation itself |
| Clean UTXO proof | Prove no interaction with flagged transaction |
| DAO gating | Smart contract checks threshold proof → mints membership NFT |
| Commitment-only backend | Backend never sees plaintext address (TEE or client-side proving) |
