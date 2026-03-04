# Privacy Model

> What each party learns — and what they provably cannot learn — at every stage
> of the Latens proof lifecycle.

---

## The Fundamental Claim

A Starknet contract can confirm "this Starknet address controls a Bitcoin wallet with
≥ X BTC" without learning: which Bitcoin wallet, the exact balance, any UTXO,
any transaction history, or any link between the Starknet identity and the Bitcoin identity.

The on-chain record is `{commitment, threshold, snapshot_height, timestamp}`.
The Bitcoin address is structurally absent — not redacted, not encrypted, **absent**.

---

## Information Layer Analysis

### Layer 0 — The Prover's Machine (Client)

**Knows:**
- Bitcoin address (entered by user)
- Salt (generated locally, 32 bytes, session memory only)
- Balance (returned by backend in proof response — MVP only; S3 avoids this)
- Merkle path (returned by backend)
- Commitment = `Poseidon(address_hash, salt)`

**Cannot be inferred from what the client reveals to anyone:**
- The client sends `{address, salt_hex, threshold}` to the backend (MVP model)
- This reveals the address to the backend — acknowledged and documented as the MVP trust assumption
- The commitment is also sent to the backend but reveals nothing about the address without the salt; and the backend already has the address, making the commitment binding but not additional leakage

---

### Layer 1 — Backend (Proof Server)

**MVP model — what the backend receives:**

```
POST /api/proof/generate {
    address: "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    salt_hex: "deadbeef...deadbeef",
    threshold: 100000000
}
```

**Knows:**
- Bitcoin address (from request body)
- Balance (from snapshot database, looked up by address)
- Merkle path (from snapshot database)
- Timestamp and IP of the request

**Does NOT know:**
- Which Starknet account will submit the proof
- Any historical addresses the user has queried
- The full UTXO breakdown (only the aggregated balance at snapshot height is stored)

**MVP trust note:** The backend is a semi-trusted party. A rigorous ZK system should not require trust at this layer. The architecture is explicitly designed so this trust assumption is isolated and replaceable.

**Production model:**

The `/api/snapshot/witness/{address}` endpoint decouples witness retrieval from proof generation. In S3:
1. Frontend fetches Merkle witness (address → path, balance) — server learns address was queried
2. Frontend runs WASM prover locally with `(address, salt, balance, path)` — server sees nothing
3. Frontend submits STARK proof calldata to Starknet — server is removed from the loop entirely

In S3, the backend is reduced to a **data availability layer** (Merkle witnesses), not a prover. The only residual leakage is that the backend knows the address was queried — equivalent to searching a block explorer, but with the proof itself generated privately.

---

### Layer 2 — Starknet (On-Chain)

**Calldata submitted to `BalanceVerifier.verify_proof()`:**
```
[address_hash, salt, balance, merkle_path_len, ...path_elements, commitment, threshold]
```

**Transaction calldata is public.** Anyone reading the chain can see:
- `address_hash` — a deterministic scalar encoding of the Bitcoin address. This is NOT the raw address, but given the encoding (`address_bytes_as_int % P`), it is **reversible if you know the address**: an observer who suspects a specific address can check. It is not reversible by brute-force over all Bitcoin addresses (≈50M) in polynomial time if the prover keeps the address secret.

> **Critical note on calldata privacy:** In the MVP, `address_hash` appears in calldata and is therefore public on-chain. This is a privacy limitation: a party who already knows or suspects the Bitcoin address can confirm it. Full ZK production would move proof generation client-side and submit only `{commitment, proof_blob, threshold}` as calldata — address_hash would be a private witness never appearing on-chain.

**What the chain records:**

From `ProofVerified` event:
```
{
  commitment: felt252,         // Poseidon(address_hash, salt) — no preimage known to observers
  threshold: u64,              // The declared minimum balance
  snapshot_height: u64,        // Which Bitcoin snapshot was used
  timestamp: u64               // Starknet block timestamp
}
```

**Cannot be inferred from the event:**
- Bitcoin address (commitment provides no information about address without the salt)
- Exact balance (only that balance ≥ threshold)
- UTXO composition
- Transaction history
- Starknet→Bitcoin identity link (the Starknet address that submitted the proof is known; its link to the Bitcoin address is the commitment, which is unlinkable without the salt)

---

### Layer 3 — Chain Explorer / Public Observer

Sees: everything in Layer 2.

Cannot see: address_hash is visible in calldata (see note above); commitment preimage is not inferable; balance is private beyond the threshold floor.

---

## Privacy Comparison: Latens vs. Alternatives

| Approach | What the verifier learns | Privacy level |
|---|---|---|
| "Just check my address on Etherscan" | Full address, full balance, full history | None |
| Bridge BTC to wrapped BTC | Bridge operator links BTC→EVM address | Low |
| zkBridge (existing solutions) | Source chain address visible in proof | Medium |
| **Latens (MVP)** | **Backend: address. On-chain: commitment only** | **Medium-High** |
| **Latens (S3 full ZK)** | **No party learns address from proof** | **Maximum** |

---

## Commitment Scheme and Unlinkability

The commitment `c = Poseidon(address_hash, salt)` has the following unlinkability property:

Given commitments `c1` and `c2` from two separate proof sessions for the **same Bitcoin address** with different salts:
- `c1 = Poseidon(h_addr, salt_1)`
- `c2 = Poseidon(h_addr, salt_2)`

An external observer cannot determine whether `c1` and `c2` share the same `h_addr` without knowing at least one of the salts. This means the same Bitcoin address can generate multiple proofs across time, and they appear **unlinkable** to any observer who doesn't have the salt.

This is critical for DAO memberships: a user who joins two DAOs at different times produces two `MemberAdded` events with different `commitment` values and different `nullifier_hash` values. No on-chain observer can determine these events came from the same Bitcoin wallet.

---

## Salt Management

The salt is the linchpin of the privacy model.

| Property | Implementation |
|---|---|
| Generation | `crypto.getRandomValues(new Uint8Array(32))` — browser CSPRNG |
| Entropy | 256 bits — collision probability ≈ 2^{-128} |
| Storage | Session memory only — never `localStorage`, never `sessionStorage` |
| Transport | Included in proof request (MVP — necessary for commitment derivation by backend) |
| On-chain | Appears in calldata (MVP limitation — see Layer 2 note) |
| S3 model | Never leaves browser |

The fact that salt appears in MVP calldata means an observer can verify that `Poseidon(address_hash, salt) == commitment` — but since `address_hash` is also in the calldata, this reveals nothing additional. The privacy boundary is the address-to-hash step, not the commitment step.

---

## What "Zero-Knowledge" Means Here

In the strict cryptographic sense, the MVP is **not** a zero-knowledge proof system. It is a **provably correct** statement generation system where:
- Correctness: The backend verifies the three constraints in Python before generating calldata. If the constraints don't hold, no calldata is produced.
- Soundness: The on-chain Cairo verifier independently rechecks all three constraints. A malicious backend cannot produce calldata that passes on-chain if the actual Bitcoin constraint isn't satisfied.
- Zero-knowledge: NOT achieved in MVP. The calldata reveals `address_hash`, `salt`, and `balance`. A true ZK proof would replace this calldata with a STARK proof blob that encodes the same facts without revealing the witnesses.

The system does achieve **strong practical privacy** for the on-chain record — the `ProofVerified` event contains no address information. The privacy limitation is at the calldata layer, which is solvable with client-side proving.

---

## Related Documentation

- [Security Model](./security.md) — Threat surface, mitigations, known limitations
- [Architecture](./architecture.md) — Layer overview and production hardening path
- [Cryptographic Specification](./crypto-spec.md) — Commitment scheme formal properties
