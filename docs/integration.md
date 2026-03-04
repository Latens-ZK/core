# Integrating with Latens

> A practical guide for DeFi protocols and DAO tooling that want to integrate
> Bitcoin balance proofs as a credentialing primitive.

---

## What Latens Provides

One composable primitive: **provable Bitcoin balance ownership, privacy-preserving, verifiable on Starknet.**

The verification result is a boolean with an event — not a token, not a credential NFT by default. The truth sits in `BalanceVerifier.verify_proof() → bool` and the `ProofVerified` event. What you build on top of it is up to you.

---

## Integration Paths

### Path A: Minimal — Call BalanceVerifier Directly

Your contract calls `BalanceVerifier.verify_proof()` inline and acts on the result.

```cairo
use latens_contracts::balance_verifier::{
    IBalanceVerifierDispatcher, IBalanceVerifierDispatcherTrait, MerklePathElement
};

#[starknet::contract]
mod YourProtocol {
    #[storage]
    struct Storage {
        verifier: ContractAddress,
    }

    fn gate_action(
        ref self: ContractState,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        threshold_satoshis: u64,
    ) {
        let verifier = IBalanceVerifierDispatcher {
            contract_address: self.verifier.read()
        };

        // Reverts if proof invalid → no state change
        let verified = verifier.verify_proof(
            address_hash, salt, balance, merkle_path, commitment, threshold_satoshis
        );
        assert(verified, 'BTC balance proof required');

        // Your logic here — caller has proven BTC ownership
        self._do_privileged_action(get_caller_address());
    }
}
```

**When to use:** One-time actions (airdrop claims, single-use access tokens).

**Replay prevention:** You must implement your own nullifier or usage tracking if the action should only be claimable once.

---

### Path B: Delegate to DaoGate

Deploy your own `DaoGate` with a threshold appropriate for your use case. Other contracts check `DaoGate.is_member()`.

```cairo
// Any address that has called join_dao() with a valid ≥ 1 BTC proof
// is permanently in the member set
let is_whale = dao_gate.is_member(get_caller_address());
assert(is_whale, 'DAO: BTC whale required');
```

**When to use:** Persistent membership (DAOs, governance, tiered access).

**DaoGate constructor parameters:**
```
verifier: ContractAddress  → address of deployed BalanceVerifier
threshold: u64             → minimum satoshis required (100_000_000 = 1 BTC)
```

**Threshold tiers for reference:**

| Use Case | Threshold (satoshis) |
|---|---|
| Any BTC holder | `1` (or `0` for no check) |
| Micro-whale (≥ 0.1 BTC) | `10_000_000` |
| Whale (≥ 1 BTC) | `100_000_000` |
| Major holder (≥ 10 BTC) | `1_000_000_000` |
| Institutional (≥ 100 BTC) | `10_000_000_000` |

---

### Path C: Historical Snapshot Proofs

Use `verify_proof_at_height` to accept proofs against a specific historical Bitcoin snapshot — not just the latest registered root.

```cairo
verifier.verify_proof_at_height(
    address_hash, salt, balance, merkle_path,
    commitment, threshold,
    800000  // specific Bitcoin block height
);
```

**Use case:** Eligibility snapshots — "prove you held ≥ 1 BTC on the day of the event (block 800,000)." Even after the latest root has been updated to a newer height, users can still prove their historical state if the historical root is still within the `MAX_ROOT_AGE` window.

---

## Frontend Integration

The frontend only needs to:
1. Call `POST /api/proof/generate` with `{address, salt_hex, threshold}`
2. Receive `starknet_calldata` in the response
3. Submit calldata to the appropriate contract function

Using `starknet-react`:

```typescript
import { useAccount, useContract } from '@starknet-react/core';
import { BALANCE_VERIFIER_ABI } from './abis';

const { account } = useAccount();
const { contract } = useContract({
    abi: BALANCE_VERIFIER_ABI,
    address: process.env.NEXT_PUBLIC_VERIFIER_ADDRESS,
});

async function submitProof(calldata: string[]) {
    const tx = await contract.invoke('verify_proof', calldata);
    await account.waitForTransaction(tx.transaction_hash);
    return tx.transaction_hash;
}
```

The `starknet_calldata` array from the API response is already encoded in the Starknet ABI format:

```
[address_hash, salt, balance, path_len, path[0].value, path[0].dir, ..., commitment, threshold]
```

---

## Composable Use Cases

### Anonymous Lending (Credit Score from BTC)

```
User proves ≥ 5 BTC → Lending protocol grants collateral-free loan up to X
```

1. User calls `BalanceVerifier.verify_proof()` in the lending contract's collateral check
2. Lending contract records: `commitments[caller] = commitment` (for future proof of same wallet)
3. Loan terms are based on threshold tier, not exact balance

**Privacy:** Lender learns floor balance (≥ 5 BTC), nothing else. Exact balance, address, UTXO composition — all private.

---

### Tiered Airdrop Eligibility

```
Block 800,000 snapshot: 
  ≥ 0.1 BTC → Tier A  (1000 tokens)
  ≥ 1 BTC   → Tier B  (5000 tokens)
  ≥ 10 BTC  → Tier C  (25000 tokens)
```

Each tier is a separate `DaoGate` (or a single contract that calls `verify_proof` with different thresholds). Users generate a proof for the highest tier they qualify for and claim once. Historical root (`verify_proof_at_height`) ensures the snapshot is fixed regardless of when users claim.

---

### Cross-Chain Reputation Bridge

```
User proves BTC history → receives on-chain attestation on Starknet
```

An attestation registry stores `{starknet_address → commitment → threshold}`. Other protocols query the registry instead of running their own verification. The registry operator gets `ProofVerified` events and mints soulbound attestation tokens (ERC721 non-transferable variant).

---

### Compliance Set Exclusion (Stretch)

```
Prove your address is NOT in a OFAC/sanctioned set
```

Requires a separate Merkle tree over the sanctioned set (sparse Merkle tree with 1 for included, 0 for not). A non-membership proof shows the leaf at the address's position is 0. This is the "killer feature" noted in the original design doc — institution-grade compliance without doxing.

**Status:** Architectural design complete; not yet implemented. Tracked as a stretch goal.

---

## Event Indexing

Listen for `ProofVerified` on `BalanceVerifier` to build off-chain indexes:

```
Event: ProofVerified {
    commitment: felt252,       // Indexed — query by commitment
    threshold: u64,
    snapshot_height: u64,
    timestamp: u64
}
```

Starknet event indexers (Apibara, Starkscan) can stream these events. Build a reputation score by counting how many times a commitment has verified, across how many thresholds.

---

## Deployed Addresses (Starknet Sepolia)

> Run `node contracts/scripts/deploy.mjs` to get live addresses.
> The deploy script writes them to `.env` and `frontend/.env.local` automatically.

| Contract | Address |
|---|---|
| `StateRootRegistry` | See `.env` after deployment |
| `BalanceVerifier` | See `.env` after deployment |
| `DaoGate` (1 BTC gate) | See `.env` after deployment |

---

## Related Documentation

- [Contract Reference](./contracts.md) — Full ABI, storage layout, revert conditions
- [API Reference](./api.md) — Calldata generation endpoint
- [Security Model](./security.md) — Replay prevention, nullifier design
- [Privacy Model](./privacy.md) — What the verifier contract does and doesn't reveal
