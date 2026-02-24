use starknet::ContractAddress;

// ─── Interface for the Registry ───────────────────────────────────────────────
#[starknet::interface]
pub trait IStateRootRegistryDispatch<TContractState> {
    fn get_root(self: @TContractState) -> felt252;
    fn get_root_at_height(self: @TContractState, height: u64) -> felt252;
}

// ─── Structs ──────────────────────────────────────────────────────────────────
/// One element of a Merkle inclusion proof.
///
/// `direction` semantics (matches Python MerkleTree):
///   false → sibling is LEFT  (current node is the right child)  → hash(sibling, current)
///   true  → sibling is RIGHT (current node is the left child)   → hash(current, sibling)
#[derive(Drop, Serde, Copy)]
pub struct MerklePathElement {
    value: felt252,
    direction: bool,
}

// ─── Interface ────────────────────────────────────────────────────────────────
#[starknet::interface]
pub trait IBalanceVerifier<TContractState> {
    /// Verify against the LATEST on-chain root.
    fn verify_proof(
        ref self: TContractState,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        threshold: u64,
    ) -> bool;

    /// Verify against a specific historical root.
    fn verify_proof_at_height(
        ref self: TContractState,
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

// ─── Contract ─────────────────────────────────────────────────────────────────
#[starknet::contract]
pub mod BalanceVerifier {
    use super::{
        MerklePathElement,
        IStateRootRegistryDispatchDispatcher,
        IStateRootRegistryDispatchDispatcherTrait,
    };
    use starknet::{ContractAddress, get_block_timestamp};
    use core::poseidon::hades_permutation;

    #[storage]
    struct Storage {
        registry_address: ContractAddress,
    }

    // ─── Events ───────────────────────────────────────────────────────────────
    #[event]
    #[derive(Drop, starknet::Event)]
    enum Event {
        ProofVerified: ProofVerified,
    }

    #[derive(Drop, starknet::Event)]
    struct ProofVerified {
        #[key]
        commitment: felt252,
        threshold: u64,
        timestamp: u64,
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    #[constructor]
    fn constructor(ref self: ContractState, registry: ContractAddress) {
        self.registry_address.write(registry);
    }

    // ─── External ─────────────────────────────────────────────────────────────
    #[abi(embed_v0)]
    impl BalanceVerifierImpl of super::IBalanceVerifier<ContractState> {
        /// Verify against the LATEST on-chain root.
        fn verify_proof(
            ref self: ContractState,
            address_hash: felt252,
            salt: felt252,
            balance: u64,
            merkle_path: Array<MerklePathElement>,
            commitment: felt252,
            threshold: u64,
        ) -> bool {
            let registry = IStateRootRegistryDispatchDispatcher {
                contract_address: self.registry_address.read()
            };
            let snapshot_root = registry.get_root();
            assert(snapshot_root != 0, 'No root registered yet');

            _verify(
                ref self,
                address_hash, salt, balance,
                merkle_path, commitment, threshold,
                snapshot_root,
            )
        }

        /// Verify against a specific historical root.
        fn verify_proof_at_height(
            ref self: ContractState,
            address_hash: felt252,
            salt: felt252,
            balance: u64,
            merkle_path: Array<MerklePathElement>,
            commitment: felt252,
            threshold: u64,
            block_height: u64,
        ) -> bool {
            let registry = IStateRootRegistryDispatchDispatcher {
                contract_address: self.registry_address.read()
            };
            let snapshot_root = registry.get_root_at_height(block_height);
            assert(snapshot_root != 0, 'No root at this height');

            _verify(
                ref self,
                address_hash, salt, balance,
                merkle_path, commitment, threshold,
                snapshot_root,
            )
        }

        fn get_registry(self: @ContractState) -> ContractAddress {
            self.registry_address.read()
        }
    }

    // ─── Internal ─────────────────────────────────────────────────────────────

    /// Core verification logic.
    ///
    /// Poseidon PAIR hash used throughout:
    ///   pair_hash(x, y) = hades_permutation(x, y, 2).s0
    ///
    /// This matches Python `PoseidonHash.hash(x, y)` = `_hades_permutation(x, y, 2)[0]`
    /// and starknet-py `poseidon_hash(x, y)` = `hades_permutation(x, y, 2)[0]`.
    fn _verify(
        ref self: ContractState,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        threshold: u64,
        snapshot_root: felt252,
    ) -> bool {
        // ── C-01: commitment = Poseidon(address_hash, salt) ──────────────────
        let (calc_commitment, _, _) = hades_permutation(address_hash, salt, 2);
        assert(calc_commitment == commitment, 'Invalid commitment');

        // ── C-03: balance >= threshold (if set) ──────────────────────────────
        if threshold > 0 {
            assert(balance >= threshold, 'Balance below threshold');
        }

        // ── C-02: Merkle root = recompute(leaf, path) ────────────────────────
        //   leaf = Poseidon(address_hash, balance_as_felt252)
        let (leaf_hash, _, _) = hades_permutation(address_hash, balance.into(), 2);
        let calculated_root = compute_merkle_root(leaf_hash, merkle_path);
        assert(calculated_root == snapshot_root, 'Invalid Merkle proof');

        // ── Emit ProofVerified ───────────────────────────────────────────────
        self.emit(ProofVerified {
            commitment,
            threshold,
            timestamp: get_block_timestamp(),
        });

        true
    }

    /// Recompute Merkle root from leaf + proof path.
    ///
    /// direction semantics (mirrors Python MerkleTree.verify_proof):
    ///   false → sibling is LEFT  → hash(sibling, current)
    ///   true  → sibling is RIGHT → hash(current, sibling)
    fn compute_merkle_root(leaf: felt252, mut path: Array<MerklePathElement>) -> felt252 {
        let mut current = leaf;

        loop {
            match path.pop_front() {
                Option::Some(el) => {
                    let sibling = el.value;
                    let (next, _, _) = if !el.direction {
                        // sibling is LEFT → hash(sibling, current)
                        hades_permutation(sibling, current, 2)
                    } else {
                        // sibling is RIGHT → hash(current, sibling)
                        hades_permutation(current, sibling, 2)
                    };
                    current = next;
                },
                Option::None => { break; },
            };
        };

        current
    }
}
