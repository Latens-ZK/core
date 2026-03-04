# Execution Flow

> End-to-end trace of every state transition and network call in the Latens system.
> Execution order is strict — each phase depends on the prior completing successfully.

---

## Phase 0: Snapshot Bootstrap (Admin, One-Time per Block Height)

```
1.  Admin selects Bitcoin block height H (e.g., 800,000)

2.  POST /api/snapshot/generate { "block_height": H }

3.  Backend: BitcoinClient.fetch_utxos(H)
    → calls Blockstream API: GET /api/block/{hash}/txs
    → aggregates satoshi balances per address
    → filters: remove zero-balance addresses

4.  Backend: MerkleTree.build(balances)
    → sort addresses ascending by address_hash = address_bytes_as_int % P
    → compute leaf[i] = Poseidon(address_hash[i], balance[i])
    → pad to next power of 2 with zero-leaves
    → compute tree bottom-up: parent = Poseidon(left, right)
    → store per-address merkle_path

5.  Backend: persist to SQLite
    → Snapshot: { block_height, merkle_root, total_addresses, timestamp }
    → AddressBalance: { address_hash, balance, merkle_path_json }

6.  Admin: call StateRootRegistry.update_root(merkle_root, H)
    → Contract checks: caller == admin ✓
    → Contract checks: H > current_block_height ✓
    → Writes: current_root, block_height, root_history[H], updated_at
    → Emits: RootUpdated { block_height: H, merkle_root, updated_at }

CHECKPOINT: Root is live on-chain. Any proof referencing this root can be verified.
```

---

## Phase 1: Client-Side Commitment Generation

**Runs entirely in the browser. No network calls.**

```
1.  User enters Bitcoin address
    → Validate: Base58 checksum (P2PKH/P2SH) or Bech32 (native SegWit)
    → Reject on format error — no request sent

2.  User sets optional threshold (e.g., 1.0 BTC → 100,000,000 satoshis)

3.  Browser generates salt:
    salt = crypto.getRandomValues(new Uint8Array(32))
    → 256 bits of entropy
    → stored in React state only — never localStorage/sessionStorage

4.  Commitment calculated client-side:
    address_hash = address_utf8_bytes_as_int % P
    commitment = Poseidon_pair(address_hash, salt)
    → displayed to user (hex)
    → this is what binds the proof to a specific address, without revealing it
```

---

## Phase 2: Proof Request (Client → Backend)

```
5.  POST /api/proof/generate {
        "address":    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        "salt_hex":   "deadbeef...deadbeef",   ← 64 hex chars
        "threshold":  100000000
    }

6.  Backend validation:
    → Check address format (bitcoin-address library)
    → If malformed → HTTP 422

7.  Backend lookup:
    address_hash = address_utf8_bytes_as_int % P
    record = DB.query(AddressBalance).filter(address_hash == computed)
    → If not found → HTTP 404 { "error": "address_not_indexed" }

8.  Backend: threshold pre-check
    → If record.balance < threshold → HTTP 400 { "error": "threshold_not_met" }

9.  Backend: commitment derivation
    client_commitment = Poseidon_pair(address_hash, salt_from_request)

10. Backend: circuit verification (off-chain simulation)
    ProofGenerator.generate_proof_no_salt(
        address_hash, balance, merkle_path, snapshot_root,
        commitment=client_commitment, threshold
    )
    → Verifies: balance >= threshold
    → Verifies: recompute_root(Poseidon(address_hash, balance), path) == snapshot_root
    → If either fails → returns error (internal consistency check)

11. Backend: calldata encoding
    ProofGenerator.generate_calldata(address_hash, salt, balance, merkle_path,
                                     commitment, threshold)
    → [address_hash, salt, balance, len(path), path[0].value, path[0].dir, ..., commitment, threshold]

12. Response:
    {
      "proof": "LATENS_PROOF_v1:...",
      "public_signals": { snapshot_root, commitment, threshold },
      "block_height": H,
      "starknet_calldata": [...],
      "verified_locally": true
    }
```

---

## Phase 3: On-Chain Verification (Client → Starknet)

```
13. User connects Starknet wallet (Argent X / Braavos)
    → get-starknet wallet provider
    → network must be Starknet Sepolia

14. Frontend constructs transaction:
    account.execute({
        contractAddress: VERIFIER_ADDRESS,
        entrypoint: 'verify_proof',
        calldata: starknet_calldata   ← direct from step 12
    })

15. Wallet prompts user to sign → user approves

16. Transaction submitted to Starknet sequencer

17. BalanceVerifier.verify_proof() executes:

    a. Calls StateRootRegistry.get_latest_snapshot()
       → Returns (snapshot_root, snapshot_height, updated_at)

    b. Asserts snapshot_root != 0
       → If zero: revert 'No root registered yet'

    c. Calls StateRootRegistry.is_root_valid(snapshot_height)
       → age = latest_height - snapshot_height
       → Asserts age <= 1008
       → If expired: revert 'Root expired'

    d. C-01: hades_permutation(address_hash, salt, 2)[0] == commitment
       → If mismatch: revert 'Invalid commitment'

    e. C-03: if threshold > 0: balance >= threshold
       → If fails: revert 'Balance below threshold'

    f. C-02: leaf = hades_permutation(address_hash, balance, 2)[0]
             computed_root = compute_merkle_root(leaf, merkle_path)
             assert computed_root == snapshot_root
       → If mismatch: revert 'Invalid Merkle proof'

    g. Emits: ProofVerified { commitment, threshold, snapshot_height, timestamp }

    h. Returns: true

18. Transaction confirmed → frontend receives tx_hash

19. Frontend displays:
    ✔ Valid | Block 800,000 | ≥ 1 BTC | Tx: 0x...
    [View on Starkscan ↗]
```

---

## Phase 4: DAO Membership (Optional, via DaoGate)

```
20. If caller wants DAO membership instead of one-time verification:
    Replace step 14 with DaoGate.join_dao() call

21. DaoGate.join_dao() executes:

    a. Assert !members[caller]
       → If already member: revert 'Already a DAO member'

    b. nullifier_hash = hades_permutation(salt, external_nullifier, 2)[0]
       (external_nullifier = DaoGate contract address as felt252)

    c. Assert !used_nullifiers[nullifier_hash]
       → If reused: revert 'Nullifier already used'

    d. verifier.verify_proof(..., threshold=min_threshold)
       → All constraints from steps 17a-h apply
       → If any fail: revert (cascades from BalanceVerifier)

    e. used_nullifiers[nullifier_hash] = true
    f. members[caller] = true
    g. member_count += 1
    h. Emits: MemberAdded { member, commitment, nullifier_hash, timestamp }

22. Membership is permanent — is_member(caller) returns true for all future calls
```

---

## Failure Paths

| Where | Condition | Revert / Response |
|---|---|---|
| Client (format) | Bad Bitcoin address | No request sent; UI error |
| Backend | Address not in snapshot | HTTP 404 `address_not_indexed` |
| Backend | Balance < threshold | HTTP 400 `threshold_not_met` |
| Backend | No snapshot in DB | HTTP 503 `snapshot_unavailable` |
| Contract | snapshot_root == 0 | Revert `'No root registered yet'` |
| Contract | Root too old | Revert `'Root expired'` |
| Contract | Commitment mismatch | Revert `'Invalid commitment'` |
| Contract | Threshold not met | Revert `'Balance below threshold'` |
| Contract | Bad Merkle path | Revert `'Invalid Merkle proof'` |
| DaoGate | Already member | Revert `'Already a DAO member'` |
| DaoGate | Nullifier reused | Revert `'Nullifier already used'` |

---

## State Diagram

```
[No snapshot]
     │
     │ POST /api/snapshot/generate
     ▼
[Snapshot in DB]
     │
     │ Admin: StateRootRegistry.update_root()
     ▼
[Root registered on-chain]  ←──── loops on new snapshot updates
     │
     │ User: POST /api/proof/generate
     ▼
[Calldata available]
     │
     │ Wallet: BalanceVerifier.verify_proof()
     ▼
[ProofVerified event on-chain]
     │                              ┌────────────────────────────┐
     │ (optional)                   │ DaoGate.join_dao()         │
     └──────────────────────────────→ MemberAdded event on-chain │
                                    └────────────────────────────┘
```

---

## Related Documentation

- [Architecture](./architecture.md) — System layer overview
- [API Reference](./api.md) — Endpoint details for steps 5–12
- [Contract Reference](./contracts.md) — Revert conditions for steps 17–22
- [Cryptographic Specification](./crypto-spec.md) — Hash functions used in every Poseidon call
