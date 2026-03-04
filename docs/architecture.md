# Latens — System Architecture

> **Bitcoin balance proofs, anchored on Starknet. Address never revealed.**

---

## Motivation

The fundamental tension in DeFi credentialing is this: Bitcoin carries the deepest wealth signal in crypto, but it lives on a fully transparent chain. Any entity that can see your Bitcoin address can reconstruct your entire financial history — UTXOs received, UTXOs spent, probable clustering, exchange interactions.

The obvious workaround — "just move BTC to Starknet and prove there" — destroys the very thing you're trying to prove. The moment you bridge, the bridge becomes an identity link.

Latens takes a different approach: **prove facts about Bitcoin state without moving Bitcoin and without ever revealing a Bitcoin address on any chain.**

The mechanism is a Poseidon Merkle tree over a Bitcoin UTXO snapshot, anchored on Starknet, with on-chain verification of inclusion proofs. The Bitcoin address is a private witness that never leaves the prover's machine.

---

## System Layers

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — DATA SOURCING                                                  │
│                                                                           │
│  Bitcoin canonical chain  →  Blockstream API                             │
│  Deterministic UTXO set at fixed block_height H                          │
│  Address aggregation: Map<address_hash → satoshis>                       │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  (balance snapshot, immutable after H)
┌────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 1 — COMMITMENT STRUCTURE                                           │
│                                                                           │
│  Leaf[i] = Poseidon(address_hash[i], balance[i])                         │
│  Tree = binary Merkle tree, leaves lexicographically sorted by hash      │
│  Root = single felt252 — the canonical commitment to ~N Bitcoin wallets  │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  (root published on-chain)
┌────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 2 — ON-CHAIN ANCHOR (Starknet)                                     │
│                                                                           │
│  StateRootRegistry → stores root + block_height + TTL window             │
│  BalanceVerifier   → verifies Merkle inclusion + threshold constraint    │
│  DaoGate           → gates membership behind a verified proof            │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  (proof generated client-side eventually;
                                 │   MVP: backend-assisted trusted prover)
┌────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 3 — PROOF GENERATION                                               │
│                                                                           │
│  Private witness: address_hash, salt, balance, merkle_path               │
│  Public inputs:   snapshot_root, commitment, threshold                   │
│                                                                           │
│  Constraints verified:                                                   │
│    C-01: Poseidon(address_hash, salt) == commitment                      │
│    C-02: recompute_root(leaf, path) == snapshot_root                     │
│    C-03: balance >= threshold  (if threshold > 0)                        │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  (calldata → wallet → Starknet)
┌────────────────────────────────▼─────────────────────────────────────────┐
│  LAYER 4 — APPLICATION SURFACE                                            │
│                                                                           │
│  DAO membership gating   / Anonymous lending credit score                │
│  Airdrop eligibility set / Cross-chain BTC reputation porting            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Component Map

| Component | Language / Runtime | Role |
|---|---|---|
| `bitcoin_client.py` | Python 3.12 | Fetches UTXO data from Blockstream REST API |
| `poseidon.py` | Pure Python, Starknet-compatible | Hades permutation, exact parameter match with Cairo |
| `merkle_tree.py` | Python | Builds binary Merkle tree; stores per-address paths |
| `proof_generator.py` | Python | Simulates Cairo circuit; produces Starknet calldata |
| FastAPI server | Python, uvicorn | Orchestration: snapshot → witness → calldata → API |
| `StateRootRegistry` | Cairo 1 | Stores Merkle roots on-chain; includes a TTL expiry window |
| `BalanceVerifier` | Cairo 1 | Verifies all 3 constraints using Cairo-native `hades_permutation` |
| `DaoGate` | Cairo 1 | Combines BalanceVerifier with nullifier-based replay prevention |
| Next.js frontend | TypeScript, React | Wallet interface, Merkle visualiser, proof submitter |

---

## Critical Design Decision: Poseidon Everywhere

The entire trust model depends on the off-chain and on-chain Poseidon implementations being **byte-identical**.

Cairo uses `core::poseidon::hades_permutation(x, y, 2)` — its output `s0` is the pair hash.

The Python equivalent (in `backend/src/crypto/poseidon.py`):
```python
def poseidon_hash(x: int, y: int) -> int:
    s0, _, _ = _hades_permutation(x % P, y % P, 2)
    return s0
```

Parameters: `t=3, RF=8, RP=83, alpha=3`, Stark prime `P = 2^251 + 17·2^192 + 1`.

Round constants are sourced from `poseidon-py 0.1.5` (starkware-libs), converted from Montgomery form. This is the only implementation in the stack with no external dependency — it's fully self-contained for auditability.

The same hash function produces:
- Merkle leaves: `Poseidon(address_hash, balance)`
- Commitment: `Poseidon(address_hash, salt)` 
- Nullifier: `Poseidon(salt, external_nullifier)`

All three are verified on-chain in Cairo using the **identical permutation**.

---

## Merkle Tree Construction

```
Sorted leaves (by address_hash, ascending):
  leaf_0 = Poseidon(h_0, b_0)
  leaf_1 = Poseidon(h_1, b_1)
  ...
  leaf_N = Poseidon(h_N, b_N)
  leaf_{N+1..2^ceil(log2(N))} = 0   ← zero-padding to next power of 2

Internal nodes:
  parent = Poseidon(left_child, right_child)

Root = tree[1]  (1-indexed binary heap layout)
```

The lexicographic sort by `address_hash` is **deterministic and canonical**. Same block height → same snapshot → same root. No nonces, timestamps, or ordering ambiguity.

Proof paths store `(sibling_value, direction: bool)` where:
- `direction = false` → sibling is LEFT → `Poseidon(sibling, current)`
- `direction = true` → sibling is RIGHT → `Poseidon(current, sibling)`

This direction encoding is mirrored exactly in `balance_verifier.cairo`'s `compute_merkle_root`.

---

## Privacy Information Flow

```
        ┌──────────┐
        │  Client  │  ← knows: address, salt, balance (from response)
        └────┬─────┘
             │  HTTP POST: {address, salt_hex, threshold}
             ▼
        ┌──────────┐
        │  Backend │  ← knows: address, balance (from DB)
        │          │    does NOT know: salt (stays in browser for future model)
        └────┬─────┘
             │  calldata: {address_hash, salt, balance, merkle_path, commitment, threshold}
             ▼
        ┌────────────┐
        │  Starknet  │  ← knows: commitment, threshold, snapshot_root
        │  Contract  │    CANNOT learn: address, balance, identity
        └────────────┘
```

**What the verifier asserts without learning anything private:**

1. The prover knows an `(address_hash, salt)` pair such that `Poseidon(address_hash, salt) == commitment`
2. That `address_hash` corresponds to a leaf in the Merkle tree at the registered root
3. The balance at that leaf is ≥ the declared threshold

The verifier emits only `{commitment, threshold, snapshot_height, timestamp}` — no address, no balance.

---

## Root TTL and Snapshot Freshness

`StateRootRegistry` enforces a sliding expiry window:

```
MAX_ROOT_AGE = 1008  # ≈ 1 week at 10-minute Bitcoin block intervals
```

`is_root_valid(snapshot_height)` returns false when:
```
latest_registered_height − snapshot_height > MAX_ROOT_AGE
```

`BalanceVerifier` calls this check before accepting any proof. This prevents attackers from re-using proofs against stale roots that may reflect outdated balances — for example, after a large transfer out of a wallet.

---

## Nullifier Design (DaoGate)

Replay prevention in `DaoGate` follows the Semaphore nullifier pattern:

```
nullifier_hash = Poseidon(salt, external_nullifier)
```

where `external_nullifier` is the DAO contract's own address (as `felt252`).

This construction ensures:
1. The **same Bitcoin address can't join the same DAO twice** (same salt → same nullifier)
2. A proof generated for DAO A **cannot be replayed in DAO B** (different `external_nullifier` → different nullifier hash)
3. The nullifier reveals **no information about the underlying address** — it's a Poseidon hash of the user's private salt

---

## Production Hardening Path

The MVP accepts the plaintext Bitcoin address in the proof-generation API for UTXO lookups. The architecture draws a clean line toward full client-side proving:

| Stage | Trust Model | Address visible to backend? |
|---|---|---|
| MVP (current) | Trusted prover (backend) | Yes (for UTXO lookup) |
| S2 (next sprint) | TEE-based proving | No — TLS attestation |
| S3 (full ZK) | Client-side WASM prover | No — address never leaves browser |

S3 replaces `proof_generator.py` with a Noir circuit compiled to WASM, using Barretenberg as the proving backend and Garaga (Starknet) for on-chain SNARK verification. The `BalanceVerifier` interface is unchanged — only the verification logic inside it switches from custom Merkle to Garaga pairing check.

---

## Related Documentation

- [Cryptographic Specification](./crypto-spec.md) — Poseidon parameters, Merkle construction, constraint definitions
- [Contract Reference](./contracts.md) — Cairo interface specs, storage layouts, event schemas
- [API Reference](./api.md) — REST endpoints, request/response schemas, rate limiting
- [Security Model](./security.md) — Threat surface, trust assumptions, known limitations
- [Privacy Model](./privacy.md) — Information-theoretic guarantees per layer
