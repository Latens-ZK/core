# Cryptographic Specification

> The correctness of Latens is entirely reducible to two properties: (1) Poseidon is
> Cairo-compatible, and (2) the Merkle construction is deterministic. This document
> specifies both precisely enough to reproduce the system from scratch.

---

## 1. Field and Hash Parameters

**Stark prime:**
```
P = 2^251 + 17·2^192 + 1
  = 3618502788666131213697322783095070105623107215331596699973092056135872020481
```

All arithmetic is performed mod `P`. Every `felt252` in Cairo is an element of `F_P`.

**Hades permutation parameters (Poseidon-P3):**

| Parameter | Value | Meaning |
|---|---|---|
| `t` | 3 | State width (3 field elements) |
| `RF` | 8 | Full rounds (4 pre-partial + 4 post-partial) |
| `RP` | 83 | Partial rounds |
| `alpha` | 3 | S-box exponent (x³ mod P) |

Round constants: 107 values sourced from `poseidon-py 0.1.5` (starkware-libs/poseidon-py, MIT). Stored in `backend/src/crypto/poseidon.py` as `_RC[0..106]`.

**MDS matrix** (implicit in `_mix3`):
```python
def _mix3(s0, s1, s2):
    t = (s0 + s1 + s2) % P
    return (t + 2*s0) % P, (t - 2*s1) % P, (t - 3*s2) % P
```

This is equivalent to Cairo's internal MDS for state size 3.

---

## 2. Pair Hash (the fundamental building block)

```
Poseidon_pair(x, y) := hades_permutation(x, y, 2)[0]
```

Concretely:
- Initial state: `[s0, s1, s2] = [x, y, 2]`
- Apply 91 Hades rounds
- Return `s0`

**Python:**
```python
def poseidon_hash(x: int, y: int) -> int:
    s0, _, _ = _hades_permutation(x % P, y % P, 2)
    return s0
```

**Cairo:**
```cairo
use core::poseidon::hades_permutation;
let (result, _, _) = hades_permutation(x, y, 2);
```

These are **byte-identical** on the same inputs. The test vectors in `backend/src/circuit/test_vectors.py` verify this cross-compatibility with a set of known (input → output) pairs derived from Starknet's official Poseidon implementation.

---

## 3. Address Encoding

Bitcoin addresses are converted to `felt252` via:

```python
# 1. Encode address as UTF-8 bytes
raw = address.encode('utf-8')

# 2. Interpret bytes as big-endian integer
addr_int = int.from_bytes(raw, 'big')

# 3. Reduce mod P  
address_hash = addr_int % P
```

This encoding is deterministic and injective within the Bitcoin address namespace (all valid addresses are shorter than the 32-byte field element). `P1eP5QGefi2DMPTfTL5SLmv7DivfNa` → same `felt252` on every run, every machine.

> **Note:** The encoding does not distinguish between P2PKH, P2SH, and bech32 address formats at the hash level. Two different address strings for the same scriptPubKey would produce different `address_hash` values. This is intentional: the snapshot indexes addresses as strings, not scripts.

---

## 4. Merkle Leaf Construction

```
leaf[i] = Poseidon_pair(address_hash[i], balance[i])
```

where `balance[i]` is satoshis as a non-negative integer, directly cast to `felt252`.

Balance range: `0 ≤ balance ≤ 21,000,000 × 10^8 = 2.1 × 10^15` satoshis.

Field prime: `P ≈ 3.6 × 10^75`.

No overflow is possible — all Bitcoin balances fit comfortably in `felt252`.

---

## 5. Merkle Tree Construction

### Leaf ordering

Leaves are sorted **ascending by `address_hash`**, establishing a canonical ordering:
```
addresses.sort(key=lambda a: address_to_felt252(a))
```

This sort is deterministic across all implementations. Same block height → identical leaf sequence → identical root.

### Tree structure

Binary heap, 1-indexed. For `N` leaves:
1. Pad to `n = 2^⌈log₂(N)⌉` with zero-leaves `leaf = 0`
2. Tree has `2n` nodes: `tree[n..2n-1]` are leaves, `tree[1..n-1]` are internal nodes
3. Internal nodes: `tree[i] = Poseidon_pair(tree[2i], tree[2i+1])`
4. `root = tree[1]`

### Merkle path format

For leaf at index `i` (0-indexed among leaves):
```
path = [
  { "value": sibling_hash, "direction": bool },
  ...
]
```

**Direction encoding:**
- `direction = false` → sibling is the **left** child → compute `Poseidon_pair(sibling, current)`
- `direction = true` → sibling is the **right** child → compute `Poseidon_pair(current, sibling)`

This encoding is mirrored in `BalanceVerifier.compute_merkle_root`:
```cairo
let (next, _, _) = if !el.direction {
    hades_permutation(sibling, current, 2)  // sibling LEFT
} else {
    hades_permutation(current, sibling, 2)  // sibling RIGHT
};
```

---

## 6. Circuit Constraints

The three invariants verified both off-chain (in `proof_generator.py`) and on-chain (in `balance_verifier.cairo`):

### C-01: Commitment Binding

```
Poseidon_pair(address_hash, salt) == commitment
```

Proves the prover knows the preimage of the commitment. Prevents commitment substitution attacks.

### C-02: Merkle Inclusion

```
recompute_root(Poseidon_pair(address_hash, balance), merkle_path) == snapshot_root
```

Proves the `(address_hash, balance)` pair is a genuine leaf in the registered snapshot. The root is fetched from `StateRootRegistry` on-chain — it cannot be forged.

### C-03: Threshold Satisfaction

```
if threshold > 0: balance >= threshold
```

The `balance` here is the private witness — the same value used in C-02. This means the threshold proof is **tight**: you cannot claim a higher balance to satisfy the threshold while using a different balance for the Merkle proof, because both feed from the same `balance` variable.

---

## 7. Commitment Scheme Properties

The commitment `c = Poseidon(h_addr, salt)` satisfies:

| Property | Achieved? | Reasoning |
|---|---|---|
| **Hiding** | Yes (computationally) | Poseidon is a one-way permutation; without knowing `salt`, `c` reveals no information about `h_addr` |
| **Binding** | Yes (computationally) | Finding `(h', salt')` such that `Poseidon(h', salt') == c` with `h' ≠ h_addr` requires breaking Poseidon |
| **Uniqueness** | Probabilistic | 32-byte salt → collision probability ≈ 2^{-128} per pair |

The salt must be generated with `crypto.getRandomValues(new Uint8Array(32))` — browser CSPRNG, not `Math.random()`.

---

## 8. Nullifier Scheme

```
nullifier_hash = Poseidon_pair(salt, external_nullifier)
```

`external_nullifier` = the `DaoGate` contract address, cast to `felt252`.

**Double-spend prevention:**  
The same `salt` used in the proof's commitment binds to a specific `nullifier_hash`. If the same Bitcoin address tries to re-join with a new salt, they generate a fresh commitment and fresh nullifier — but this costs them a new proof and the new nullifier is not yet in the map. The binding here is per-salt, not per-address: **one salt = one DAO membership**, regardless of which address generated it.

**Cross-DAO isolation:**  
`external_nullifier` encodes which DAO the proof is for. Reusing the same `(address_hash, salt)` pair in a different `DaoGate` produces a different `nullifier_hash` and thus doesn't conflict — but both memberships are bounded to distinct DAOs. A single proof blob cannot be replayed across DAO contracts.

---

## 9. Test Vectors

Cross-compatibility between Python and Cairo is validated in `backend/src/circuit/test_vectors.py`.

Example canonical vectors:

| Input (x, y) | Expected `Poseidon_pair(x, y)` |
|---|---|
| `(0, 0)` | Known constant from starknet-py reference |
| `(1, 2)` | Known constant from starknet-py reference |
| `(2^128, 2^64)` | Known constant validated against Cairo unit tests |

The Cairo unit tests (`contracts/tests/test_contracts.cairo`) verify the same vectors using `hades_permutation` directly, confirming the round-trip.

---

## Related Documentation

- [System Architecture](./architecture.md) — Component map, layer overview
- [Contract Reference](./contracts.md) — Cairo storage, interfaces, event schemas
- [Security Model](./security.md) — Attack surfaces and mitigations
