# Contract Reference

> Three Cairo 1 contracts forming a composable ZK verification stack.
> Deployed on Starknet Sepolia.

---

## Contract Dependency Graph

```
StateRootRegistry
      ▲
      │ (reads root + validity)
BalanceVerifier
      ▲
      │ (delegates verify_proof)
DaoGate
```

Each contract is independently deployable and independently upgradeable. `DaoGate` is optional — `BalanceVerifier` is the core primitive any application can integrate.

---

## StateRootRegistry

**Source:** `contracts/src/state_root_registry.cairo`

Stores the canonical Bitcoin UTXO snapshot Merkle root on-chain. Admin-controlled. Maintains a history of roots by block height.

### Constants

```cairo
const MAX_ROOT_AGE: u64 = 1008;
// ≈ 1 week at 10-minute Bitcoin block intervals
// Roots older than this are treated as expired
```

### Storage Layout

```cairo
struct Storage {
    current_root:       felt252,              // Latest Merkle root
    block_height:       u64,                  // Bitcoin block height of latest snapshot
    updated_at:         u64,                  // Starknet block timestamp of last update
    admin:              ContractAddress,       // Only address that can call update_root
    root_history:       Map<u64, felt252>,    // block_height → merkle_root
    height_to_timestamp: Map<u64, u64>,       // block_height → update timestamp
}
```

### Interface

```cairo
trait IStateRootRegistry<TContractState> {
    // Admin: register a new snapshot root
    fn update_root(ref self, new_root: felt252, height: u64);

    // Read latest root (current_root)
    fn get_root(self: @TContractState) -> felt252;

    // Read root at a specific historical height
    fn get_root_at_height(self: @TContractState, height: u64) -> felt252;

    // Read (root, block_height, updated_at) tuple
    fn get_latest_snapshot(self: @TContractState) -> (felt252, u64, u64);

    // True iff root at `snapshot_height` exists AND age <= MAX_ROOT_AGE
    fn is_root_valid(self: @TContractState, snapshot_height: u64) -> bool;

    // Returns MAX_ROOT_AGE constant (1008)
    fn get_max_root_age(self: @TContractState) -> u64;

    fn get_admin(self: @TContractState) -> ContractAddress;
}
```

### update_root validation

1. `caller == admin` — unauthorized callers revert
2. `height > current_height` — strictly monotonic; prevents rollback to older snapshots

### is_root_valid logic

```cairo
fn is_root_valid(self, snapshot_height: u64) -> bool {
    let root = root_history[snapshot_height];
    if root == 0 { return false; }                        // root doesn't exist
    if snapshot_height > latest_height { return false; }  // future height
    (latest_height - snapshot_height) <= MAX_ROOT_AGE     // age check
}
```

### Events

```cairo
struct RootUpdated {
    #[key] block_height: u64,
    merkle_root: felt252,
    updated_at: u64,
}
```

---

## BalanceVerifier

**Source:** `contracts/src/balance_verifier.cairo`

Verifies the three ZK constraints on-chain using Cairo-native Poseidon. Stateful only through its registry pointer — all verification logic is pure computation.

### Structs

```cairo
struct MerklePathElement {
    value: felt252,      // sibling node hash
    direction: bool,     // false = sibling is LEFT, true = sibling is RIGHT
}
```

### Storage Layout

```cairo
struct Storage {
    registry_address: ContractAddress,  // Points to StateRootRegistry
}
```

### Interface

```cairo
trait IBalanceVerifier<TContractState> {
    // Verify against the LATEST registered root
    fn verify_proof(
        ref self,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        threshold: u64,
    ) -> bool;

    // Verify against a specific historical root
    fn verify_proof_at_height(
        ref self,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        threshold: u64,
        block_height: u64,
    ) -> bool;

    fn get_registry(self: @TContractState) -> ContractAddress;
}
```

### Verification Logic (internal `_verify`)

Executed atomically — any failed assertion reverts the entire call:

```
1. Fetch snapshot_root from StateRootRegistry.get_latest_snapshot()
2. Assert snapshot_root != 0              → 'No root registered yet'
3. Assert registry.is_root_valid(height)  → 'Root expired'

4. C-01: hades_permutation(address_hash, salt, 2)[0] == commitment
         → 'Invalid commitment'

5. C-03: if threshold > 0: balance >= threshold
         → 'Balance below threshold'

6. C-02: leaf = hades_permutation(address_hash, balance, 2)[0]
         computed_root = compute_merkle_root(leaf, merkle_path)
         assert computed_root == snapshot_root
         → 'Invalid Merkle proof'

7. Emit ProofVerified { commitment, threshold, snapshot_height, timestamp }
8. Return true
```

### compute_merkle_root

```cairo
fn compute_merkle_root(leaf: felt252, path: Array<MerklePathElement>) -> felt252 {
    let mut current = leaf;
    for el in path {
        current = match el.direction {
            false => hades_permutation(el.value, current, 2)[0],  // sibling LEFT
            true  => hades_permutation(current, el.value, 2)[0],  // sibling RIGHT
        };
    }
    current
}
```

### Events

```cairo
struct ProofVerified {
    #[key] commitment: felt252,
    threshold: u64,
    snapshot_height: u64,
    timestamp: u64,         // Starknet block timestamp
}
```

Note: `address_hash` and `balance` are **not** emitted. The on-chain record contains only the commitment and the threshold that was satisfied.

### Calldata Encoding

For `verify_proof(address_hash, salt, balance, merkle_path, commitment, threshold)`:

```
[address_hash, salt, balance, len(merkle_path), path[0].value, path[0].direction, ..., commitment, threshold]
```

`MerklePathElement` serialises as two felts: `[value: felt252, direction: felt252 (0 or 1)]`.

Generated by `proof_generator.py::generate_calldata()`.

---

## DaoGate

**Source:** `contracts/src/dao_gate.cairo`

Composes `BalanceVerifier` with nullifier-based replay prevention to gate DAO membership behind a Bitcoin balance proof.

### Storage Layout

```cairo
struct Storage {
    verifier_address: ContractAddress,
    min_threshold: u64,                              // satoshis required to join
    members: Map<ContractAddress, bool>,             // Starknet address → member?
    member_count: u64,
    used_nullifiers: Map<felt252, bool>,             // nullifier_hash → used?
}
```

### Interface

```cairo
trait IDaoGate<TContractState> {
    fn join_dao(
        ref self,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        external_nullifier: felt252,
    );

    fn is_member(self: @TContractState, account: ContractAddress) -> bool;
    fn is_nullifier_used(self: @TContractState, nullifier_hash: felt252) -> bool;
    fn get_member_count(self: @TContractState) -> u64;
    fn get_threshold(self: @TContractState) -> u64;
    fn get_verifier(self: @TContractState) -> ContractAddress;
}
```

### join_dao execution trace

```
1. caller = get_caller_address()
2. Assert !members[caller]                               → 'Already a DAO member'
3. nullifier_hash = hades_permutation(salt, external_nullifier, 2)[0]
4. Assert !used_nullifiers[nullifier_hash]               → 'Nullifier already used'
5. verifier.verify_proof(address_hash, salt, balance, merkle_path,
                         commitment, min_threshold)
   → Reverts if proof invalid (cascades from BalanceVerifier)
6. used_nullifiers[nullifier_hash] = true
7. members[caller] = true
8. member_count += 1
9. Emit MemberAdded { member, commitment, nullifier_hash, timestamp }
```

State writes (steps 6-8) only occur after the external call (step 5) succeeds. If `verify_proof` reverts, no state is written.

### Events

```cairo
struct MemberAdded {
    #[key] member: ContractAddress,      // Starknet address that joined
    commitment: felt252,                 // Bitcoin commitment (not address)
    nullifier_hash: felt252,             // Poseidon(salt, DAO_address)
    timestamp: u64,
}
```

### Constructor parameters

```cairo
fn constructor(verifier: ContractAddress, threshold: u64)
```

`threshold` is set at deploy time and is immutable. Deploy a new `DaoGate` to change the threshold for a new DAO.

---

## Deployment Sequence

```
1. Deploy StateRootRegistry(admin_address)
   → REGISTRY_ADDRESS

2. Deploy BalanceVerifier(registry=REGISTRY_ADDRESS)
   → VERIFIER_ADDRESS

3. Deploy DaoGate(verifier=VERIFIER_ADDRESS, threshold=100_000_000)
   → DAO_ADDRESS

4. Call StateRootRegistry.update_root(merkle_root, block_height)
   → Root is live; proofs can now be verified
```

`contracts/scripts/deploy.mjs` automates this sequence for Starknet Sepolia using `starknet.js` v5.

---

## Testing

**Cairo unit tests** (`contracts/tests/test_contracts.cairo`):
- 14 tests covering: root registration, TTL expiry, valid proof, tampered commitment, tampered Merkle path, threshold enforcement, nullifier replay

**On-chain integration tests** (`contracts/scripts/verify_demo.mjs`):
- Positive: valid proof for demo address → succeeds, `ProofVerified` emitted
- Negative: proof with wrong balance field → transaction reverted

---

## Related Documentation

- [Cryptographic Specification](./crypto-spec.md) — Poseidon params, Merkle construction
- [API Reference](./api.md) — How calldata is generated and returned
- [Security Model](./security.md) — Attack vectors and mitigations
