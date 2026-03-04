# Security Model

> A rigorous analysis of the trust assumptions, threat surface, and known limitations
> of the Latens MVP. Written for engineers and auditors who need to understand what
> the system actually guarantees — and what it doesn't.

---

## Trust Hierarchy

```
Full trust required from user:
  ├─ Starknet consensus (L1 security ultimately from Ethereum)
  ├─ Cairo verifier correctness (formally verifiable; contract is open source)
  └─ Poseidon hash function security (used by Starknet itself; well-studied)

Partial trust (MVP):
  └─ Latens backend  ← sees plaintext Bitcoin address for UTXO lookup

No trust required from user:
  ├─ On-chain verifier (trustless, fully deterministic)
  ├─ Commitment scheme (address_hash + salt never leave prover in production model)
  └─ Merkle root (published on-chain, independent of backend post-publication)
```

The MVP's critical trust assumption is the backend database. The backend knows which address was looked up. This is explicitly flagged in the codebase as the production hardening target.

---

## Threat Model

### T-01: Fake Merkle Root

**Attack:** Attacker with admin key publishes a malicious `snapshot_root` that includes fake balances — for example, inserting `0x0000...0001 → 2.1M BTC`.

**Mitigation:**
- `StateRootRegistry.update_root()` is admin-only
- The admin is a single account for the MVP (test key; documented as requiring multisig for production)
- The Merkle root itself can be independently verified: anyone can download the Bitcoin UTXO set at block `H` and recompute the root from scratch, checking it matches the on-chain value
- **Root reproducibility** is a first-class design goal: same block height → byte-identical snapshot → identical root

**Residual risk (MVP):** Admin key compromise. Mitigated in production via contract upgrade to multisig/DAO-controlled admin.

---

### T-02: Proof Replay

**Attack:** Alice generates a valid proof. She submits it once to `BalanceVerifier`. She then tries to submit the same proof again (to `DaoGate` or elsewhere).

**Mitigation (DaoGate):**
- `nullifier_hash = Poseidon(salt, external_nullifier)` is stored in `used_nullifiers` on first use
- Subsequent submissions with the same salt revert with `'Nullifier already used'`
- Cross-DAO replay: different `external_nullifier` → different `nullifier_hash` → no collision

**Mitigation (BalanceVerifier):**
- `BalanceVerifier` itself does **not** store nullifiers — it's a stateless verifier
- Replay prevention is the responsibility of the consuming contract (`DaoGate` implements it; custom integrators must implement their own)
- This is explicitly documented in the contract interface

---

### T-03: Commitment Substitution

**Attack:** Prover sends `commitment = Poseidon(h_evil, salt)` but claims `commitment = Poseidon(h_real, salt)` in the calldata, hoping to prove membership for an address they don't own.

**Mitigation:**
- C-01 is enforced on-chain: `hades_permutation(address_hash, salt, 2)[0] == commitment`
- If `address_hash` in the calldata doesn't match the preimage of `commitment`, the assertion reverts
- Finding a second preimage requires breaking Poseidon — computationally infeasible

---

### T-04: Merkle Path Forgery

**Attack:** Attacker has an address with 0.5 BTC but wants to satisfy a 1 BTC threshold. They craft a fake Merkle path claiming their leaf has balance 2 BTC.

**Mitigation:**
- The leaf is `Poseidon(address_hash, balance)` — forging the balance changes the leaf hash
- A fake path would have to hash to the registered `snapshot_root`
- Finding such a path requires a second preimage on Poseidon for the root, which is infeasible
- Furthermore, C-03 uses the **same `balance` variable** as C-02's leaf construction — you can't claim different balances for the threshold check vs. the Merkle proof

---

### T-05: Snapshot Staleness

**Attack:** User generates a proof when they hold 5 BTC. They transfer the BTC out. A week later, they re-submit the old proof claiming they still hold 5 BTC.

**Mitigation:**
- `MAX_ROOT_AGE = 1008` blocks ≈ 1 week
- After this window, `is_root_valid()` returns false
- `BalanceVerifier` asserts this before accepting any proof → 'Root expired'
- Admin must publish fresh snapshot roots at least weekly for the system to remain live

**Residual risk:** Within the TTL window, an address that went to ~0 BTC can still generate a valid proof against the snapshot where it held BTC. This is an **inherent property of snapshot-based systems** — not a bug. Applications with tighter freshness requirements should use shorter `MAX_ROOT_AGE` or request a new snapshot.

---

### T-06: Backend Address Leakage (MVP Specific)

**Attack:** The backend API is compromised. The attacker extracts the access log, which contains Bitcoin addresses submitted for proof generation.

**Mitigation (MVP):**
- The backend does not log plaintext addresses beyond the request lifetime (per `API-02` requirement)
- Address is used only to compute `address_hash` and look up balance; it's not stored in the `proof` output

**Mitigation (Production):**
- The `/api/snapshot/witness/{address}` endpoint exists explicitly to support client-side proving models where the address never reaches the backend
- In S3, the frontend downloads the Merkle witness (which only reveals that *some* address in the snapshot was queried, not which one) and proves locally using a WASM circuit

---

### T-07: Salt Entropy Failure

**Attack:** The frontend generates a weak salt — for example, using `Math.random()` instead of `crypto.getRandomValues()`. An attacker brute-forces the salt space to deanonymize the commitment.

**Mitigation:**
- Salt generation uses `crypto.getRandomValues(new Uint8Array(32))` — 256 bits of entropy
- Salt is never persisted to `localStorage` or cookies (per `UI-03`)
- A commitment `c = Poseidon(h_addr, salt)` with 256-bit salt has collision resistance ≈ 2^{128} (birthday bound)

**Residual risk:** If a user reuses the same salt across multiple proofs (by re-entering it manually), the nullifier system doesn't help because the same nullifier is already used. Users must generate a fresh salt for each proof session.

---

### T-08: Merkle Tree Ordering Ambiguity

**Attack:** An off-chain operator constructs a Merkle tree with a different leaf order, producing a different root. They upload this to the registry. A user generates a proof against the canonical tree but the on-chain root is for the non-canonical tree — verification fails.

**Mitigation:**
- Leaf ordering is canonically defined: **ascending sort by `address_hash`**
- The sort key is `address_bytes_as_int % P` — deterministic for any Python/Cairo implementation using identical encoding
- Test vectors validate root reproducibility

---

## Known Limitations

### L-01: Trusted Prover (MVP)

The MVP is a **trusted prover** model: the backend verifies circuit logic in Python and returns calldata. There is no cryptographic ZK proof in the strict sense — the backend is trusted to not fabricate witnesses.

**What this means:**
- A malicious backend *could* return valid-looking calldata for an address that doesn't satisfy the threshold
- The on-chain verifier would accept it, because the verifier checks **calldata consistency**, not backend honesty

**Production resolution:** Client-side Noir + Barretenberg WASM prover. The prover runs in the browser; the backend only serves the Merkle witness. The on-chain verifier switches to Garaga SNARK verification, which is cryptographically sound.

---

### L-02: Full Bitcoin Consensus Not Validated

The indexer trusts Blockstream API for UTXO data. It does not validate block headers, PoW, or transaction scripts. A compromised Blockstream API could serve incorrect UTXO data.

**Production resolution:** Run a local `bitcoind` or `electrs` node. Verify block headers via SPV. Compute UTXO set locally.

---

### L-03: Single Admin Key

`StateRootRegistry` admin is a single account. If the key is lost or compromised, root updates are unavailable (lost) or malicious (compromised).

**Production resolution:** Replace admin with a multisig (`2-of-3` minimum) or a governance contract that requires a timelock and community vote for root updates.

---

### L-04: No Non-Membership Proofs

The current version cannot prove "address X is NOT in a blacklist set." This requires a different Merkle accumulator (e.g., sparse Merkle tree with presence/absence bits) or a separate CRS.

**Production extension:** Sparse Merkle tree with explicit zero-leaves for non-members. Proofs of non-membership then follow the same inclusion path structure with a zero-leaf termination check.

---

## Security Properties Summary

| Property | MVP | Production |
|---|---|---|
| On-chain root integrity | ✅ Admin-controlled, monotonic height | ✅ Multisig admin |
| Commitment hiding | ✅ Poseidon one-wayness | ✅ Same |
| Merkle forgery resistance | ✅ Poseidon second-preimage resistance | ✅ Same |
| Threshold binding | ✅ Same balance in C-02 and C-03 | ✅ Same |
| Replay prevention | ✅ Nullifier map (DaoGate) | ✅ Same + cross-DAO |
| Root staleness | ✅ MAX_ROOT_AGE = 1008 blocks | ✅ Configurable TTL |
| Backend privacy | ❌ Trusted prover (backend sees address) | ✅ Client-side WASM proving |
| Proof soundness | ❌ Python simulation (no ZK) | ✅ Noir STARK + Garaga |
| Admin key security | ❌ Single key (test) | ✅ Multisig + timelock |
| Data sourcing | ❌ Trusts Blockstream | ✅ Local Bitcoin node |

---

## Related Documentation

- [Privacy Model](./privacy.md) — Information-theoretic analysis of what each layer learns
- [Cryptographic Specification](./crypto-spec.md) — Hash parameters and formal constraints
- [Contract Reference](./contracts.md) — Storage layout and revert conditions
