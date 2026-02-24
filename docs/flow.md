dinesh alright — now we go full systems-level detail.
This is the **execution-grade User Flow Spec** you give engineers.

Built on Starknet
Bitcoin data source: Blockstream API or self-hosted node [https://blockstream.info/api/](https://blockstream.info/api/)

---

# LATENS — FULL USER FLOW SPEC (DETAILED)

---

# 0. Actors

### 1. End User

Wants to privately verify BTC balance or ownership.

### 2. Latens Backend

Indexer + Merkle builder + Proof generator.

### 3. Starknet Verifier Contract

Final authority for proof validity.

---

# 1. SYSTEM STATE BEFORE ANY USER INTERACTION

This is critical.

## 1.1 Snapshot Generation Flow (Precondition)

### Trigger

Cron job or manual admin trigger.

### Steps

1. Select Bitcoin block height `H`.
2. Fetch all UTXOs at height `H`.
3. Aggregate balances per address.
4. Filter:

   * Remove zero balances.
5. Deterministic ordering:

   * Lexicographically sorted by address hash.
6. Construct Merkle tree:

   * Leaf = Poseidon(address_hash || balance)
7. Compute:

   * `snapshot_root`
   * `total_addresses`
   * `timestamp`

### Persisted Data (Backend DB)

```
{
  block_height: H,
  snapshot_root: felt252,
  total_addresses: N,
  address_balances: Map<address_hash, balance>,
  merkle_paths: Map<address_hash, proof_path>
}
```

---

## 1.2 Root Publication (On-Chain)

Admin calls:

```
update_root(snapshot_root, block_height)
```

Contract stores:

```
current_root
block_height
updated_at
```

From this moment:
All proofs must reference `current_root`.

---

# 2. USER FLOW A — PRIVATE BALANCE LOOKUP (FULL TRACE)

---

## Phase 1 — Client-Side Commitment

### Step 1 — User Inputs BTC Address

Input format validated:

* Base58 or Bech32
* Length check
* Checksum verification

No network call yet.

---

### Step 2 — Local Salt Generation

Browser generates:

```
salt = random(32 bytes)
```

Stored in memory (NOT localStorage).

---

### Step 3 — Address Normalization

Convert address to canonical representation:

* Convert to scriptPubKey
* Hash to 32-byte value

Reason:
Different address encodings should map consistently.

---

### Step 4 — Commitment Calculation

```
address_hash = Poseidon(address_bytes)
commitment = Poseidon(address_hash || salt)
```

Now:

* Raw address still private
* Commitment safe to transmit

---

## Phase 2 — Backend Query

### Step 5 — Send Request

Payload sent:

```
POST /generate-proof

{
  commitment,
  optional_threshold
}
```

Backend does NOT receive plaintext address in ideal model.
(For MVP it may, but spec assumes privacy-first architecture.)

---

## Phase 3 — Proof Preparation (Backend Internal)

This is where most complexity lives.

---

### Step 6 — Address Lookup

Backend must reconstruct address_hash.

Two models:

### Model A (MVP Simpler)

Frontend also sends plaintext address securely.
Backend hashes and finds balance.

### Model B (Stronger Privacy)

Backend maintains mapping:
commitment → precomputed address_hash
(using private secure channel or TEE)

For hackathon → Model A acceptable.

---

### Step 7 — Fetch Balance

Lookup:

```
balance = address_balances[address_hash]
```

If not found:
Return error: “Address not in snapshot.”

---

### Step 8 — Retrieve Merkle Path

```
merkle_path = merkle_paths[address_hash]
```

Includes:

* sibling hashes
* left/right positions

---

## Phase 4 — ZK Proof Generation

---

### Circuit Private Inputs

```
address_hash
salt
balance
merkle_path[]
```

---

### Circuit Public Inputs

```
snapshot_root
threshold (optional)
commitment
```

---

### Circuit Constraints (Exact)

1. `Poseidon(address_hash || salt) == commitment`
2. `ComputeMerkleRoot(address_hash, balance, merkle_path) == snapshot_root`
3. If threshold provided:

   ```
   balance >= threshold
   ```

No balance output.

---

### Output

```
proof_blob
public_signals
```

Returned to frontend.

---

## Phase 5 — On-Chain Verification

---

### Step 9 — User Connects Wallet

Wallet:

* Argent
* Braavos
* Any Starknet wallet

Gas paid by user.

---

### Step 10 — Submit Proof

Call:

```
verify_balance_proof(
    proof,
    snapshot_root,
    threshold,
    commitment
)
```

---

## Phase 6 — Contract Logic

Verifier executes:

1. Validate proof using embedded verifier.
2. Check:

   ```
   snapshot_root == stored_root
   ```
3. If valid:

   * Emit event
   * Return true

Else:

* Revert or return false

---

## Phase 7 — Final UI State

If success:

```
✔ Valid Proof
Block Height: H
Threshold: ≥ 1 BTC
```

No address revealed.
No balance revealed.

---

# 3. USER FLOW B — “I Own ≥ X BTC” (THRESHOLD MODE)

This is the stronger use case.

Only difference:

* Threshold must be public input.
* Circuit includes inequality constraint.
* Balance itself never leaves private witness.

---

## Important Edge Case

User has 0.8 BTC but tries ≥1 BTC.

Circuit fails at constraint stage.
Proof generation fails.
User sees:

```
Threshold not satisfied.
```

No chain interaction.

---

# 4. FAILURE STATES (DETAILED)

---

## A. Snapshot Mismatch

User generates proof for root R1.
Contract root = R2.

Verification fails.

UI response:
“Snapshot outdated. Regenerate proof.”

---

## B. Malformed Proof

Verifier rejects.

Gas spent.
Transaction reverts.

---

## C. Address Not Indexed

If below balance filter threshold:

* Address excluded from snapshot
* Proof impossible

UI message:
“Address not included in current privacy set.”

---

# 5. DATA PRIVACY SURFACE ANALYSIS

Let’s audit leakage.

---

## At Client

Knows:

* address
* salt
* balance (only if backend returns it — ideally don’t)

---

## Backend

Knows (MVP):

* address
* balance

Future hardened model:

* Backend only sees commitment

---

## On-Chain

Sees:

* proof
* snapshot_root
* threshold
* commitment

Cannot infer:

* address
* balance
* UTXOs

---

# 6. STATE TRANSITION DIAGRAM (SIMPLIFIED)

```
User Input
   ↓
Local Hashing
   ↓
Commitment Sent
   ↓
Balance Lookup
   ↓
Merkle Path Retrieved
   ↓
ZK Proof Generated
   ↓
Proof Submitted On-Chain
   ↓
Verification Event
```

---

# 7. DAO GATING FLOW (DETAILED)

---

## Step 1 — DAO Contract Requires

```
require(verify_threshold_proof(proof))
```

---

## Step 2 — User Generates ≥ X BTC Proof

Same as earlier flow.

---

## Step 3 — DAO Mints Role

If true:

```
mintMembershipNFT(msg.sender)
```

No BTC identity link.

This enables:

* Anonymous capital gating
* Cross-chain reputation
* BTC-backed governance

---

# 8. PERFORMANCE EXPECTATIONS

* Proof generation: < 10 sec
* Merkle tree size: optimized via filtering
* Verification cost: low due to Cairo-native proof system

Reference:
Starknet uses STARK proofs, optimized for verification efficiency
[https://docs.starknet.io/](https://docs.starknet.io/)

---

# 9. SECURITY REVIEW CHECKLIST

Before demo:

* Deterministic Merkle ordering
* No duplicate leaves
* Salt length ≥ 32 bytes
* Threshold logic correctly enforced
* Root immutability enforced

---

# 10. Critical Design Opinion

dinesh real talk:

Balance lookup is cool.
Threshold proof is impressive.
But the killer feature is:

> Prove non-interaction with blacklisted sets.

That’s institution-grade.

That would make this more interesting than explorers like
Mempool.space
[https://mempool.space/docs](https://mempool.space/docs)

Because they observe — you prove.

---

If you want next level:

* I can design the exact Merkle leaf structure
* Or write the full Cairo contract interface spec
* Or simulate attack vectors like a red team

This is getting serious now.
