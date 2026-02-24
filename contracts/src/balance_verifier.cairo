use starknet::ContractAddress;

// ─── Interface for the Registry ───────────────────────────────────────────────
#[starknet::interface]
trait IStateRootRegistryDispatch<TContractState> {
    fn get_root(self: @TContractState) -> felt252;
    fn get_root_at_height(self: @TContractState, height: u64) -> felt252;
}

// ─── Structs ──────────────────────────────────────────────────────────────────
#[derive(Drop, Serde)]
struct MerklePathElement {
    value: felt252,
    direction: bool, // false = sibling is left, true = sibling is right
}

// ─── Interface ────────────────────────────────────────────────────────────────
#[starknet::interface]
trait IBalanceVerifier<TContractState> {
    fn verify_proof(
        ref self: TContractState,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        threshold: u64,
    ) -> bool;

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
mod BalanceVerifier {
    use super::{MerklePathElement, IStateRootRegistryDispatchDispatcher, IStateRootRegistryDispatchDispatcherTrait};
    use starknet::{ContractAddress, get_block_timestamp};
    use core::poseidon::PoseidonTrait;
    use core::hash::{HashStateTrait, HashStateExTrait};

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
    #[external(v0)]
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
            // Fetch root from registry — this is the trust anchor
            let registry = IStateRootRegistryDispatchDispatcher {
                contract_address: self.registry_address.read()
            };
            let snapshot_root = registry.get_root();
            assert(snapshot_root != 0, 'No root registered yet');

            _verify(ref self, address_hash, salt, balance, merkle_path, commitment, threshold, snapshot_root)
        }

        /// Verify against a specific historical root (for older snapshots).
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

            _verify(ref self, address_hash, salt, balance, merkle_path, commitment, threshold, snapshot_root)
        }

        fn get_registry(self: @ContractState) -> ContractAddress {
            self.registry_address.read()
        }
    }

    // ─── Internal ─────────────────────────────────────────────────────────────
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
        // 1. Verify commitment: Poseidon(address_hash, salt) == commitment
        let calculated_commitment = PoseidonTrait::new()
            .update(address_hash)
            .update(salt)
            .finalize();
        assert(calculated_commitment == commitment, 'Invalid commitment');

        // 2. Verify threshold
        if threshold > 0 {
            assert(balance >= threshold, 'Balance below threshold');
        }

        // 3. Reconstruct Merkle leaf: Poseidon(address_hash, balance)
        let leaf_hash = PoseidonTrait::new()
            .update(address_hash)
            .update(balance.into())
            .finalize();

        // 4. Traverse Merkle path to root
        let calculated_root = compute_merkle_root(leaf_hash, merkle_path);
        assert(calculated_root == snapshot_root, 'Invalid Merkle proof');

        // 5. Emit event
        self.emit(ProofVerified {
            commitment,
            threshold,
            timestamp: get_block_timestamp(),
        });

        true
    }

    fn compute_merkle_root(leaf: felt252, mut path: Array<MerklePathElement>) -> felt252 {
        let mut current_hash = leaf;

        loop {
            match path.pop_front() {
                Option::Some(element) => {
                    let sibling = element.value;
                    // direction: false = sibling is left, current goes right
                    //            true  = sibling is right, current goes left
                    if !element.direction {
                        // sibling left, current right
                        current_hash = PoseidonTrait::new()
                            .update(sibling)
                            .update(current_hash)
                            .finalize();
                    } else {
                        // sibling right, current left
                        current_hash = PoseidonTrait::new()
                            .update(current_hash)
                            .update(sibling)
                            .finalize();
                    }
                },
                Option::None => { break; }
            };
        };

        current_hash
    }
}
