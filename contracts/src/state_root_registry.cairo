use starknet::ContractAddress;

/// Maximum age of a Merkle root before it is considered expired.
/// 1008 blocks ≈ 1 week at 10-minute Bitcoin block times.
/// BalanceVerifier rejects proofs referencing roots older than this.
const MAX_ROOT_AGE: u64 = 1008;

#[starknet::interface]
pub trait IStateRootRegistry<TContractState> {
    fn update_root(ref self: TContractState, new_root: felt252, height: u64);
    fn get_root(self: @TContractState) -> felt252;
    fn get_root_at_height(self: @TContractState, height: u64) -> felt252;
    fn get_latest_snapshot(self: @TContractState) -> (felt252, u64, u64);
    fn get_admin(self: @TContractState) -> ContractAddress;
    /// Returns true if the root stored at `snapshot_height` is still within
    /// MAX_ROOT_AGE blocks of the current latest registered height.
    /// Returns false if the root is missing (zero) or too old.
    fn is_root_valid(self: @TContractState, snapshot_height: u64) -> bool;
    /// Returns the MAX_ROOT_AGE constant (1008 blocks).
    fn get_max_root_age(self: @TContractState) -> u64;
}

#[starknet::contract]
pub mod StateRootRegistry {
    use starknet::{ContractAddress, get_caller_address, get_block_timestamp};
    use super::MAX_ROOT_AGE;

    #[storage]
    struct Storage {
        current_root: felt252,
        block_height: u64,
        updated_at: u64,
        admin: ContractAddress,
        // History: mapping block_height -> merkle_root
        root_history: starknet::storage::Map<u64, felt252>,
        // Snapshot block_height -> snapshot timestamp (for future TTL extensions)
        height_to_timestamp: starknet::storage::Map<u64, u64>,
    }

    // ─── Events ───────────────────────────────────────────────────────────────
    #[event]
    #[derive(Drop, starknet::Event)]
    enum Event {
        RootUpdated: RootUpdated,
    }

    #[derive(Drop, starknet::Event)]
    struct RootUpdated {
        #[key]
        block_height: u64,
        merkle_root: felt252,
        updated_at: u64,
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    #[constructor]
    fn constructor(ref self: ContractState, admin_address: ContractAddress) {
        self.admin.write(admin_address);
    }

    // ─── External ─────────────────────────────────────────────────────────────
    #[abi(embed_v0)]
    impl StateRootRegistryImpl of super::IStateRootRegistry<ContractState> {
        fn update_root(ref self: ContractState, new_root: felt252, height: u64) {
            let caller = get_caller_address();
            let admin = self.admin.read();
            assert(caller == admin, 'Unauthorized: admin only');

            // REG-02: block height must strictly increase
            let current_height = self.block_height.read();
            assert(height > current_height, 'Height must be greater');

            let ts = get_block_timestamp();

            self.current_root.write(new_root);
            self.block_height.write(height);
            self.updated_at.write(ts);

            // Store in history maps
            self.root_history.write(height, new_root);
            self.height_to_timestamp.write(height, ts);

            // Emit event
            self.emit(RootUpdated { block_height: height, merkle_root: new_root, updated_at: ts });
        }

        fn get_root(self: @ContractState) -> felt252 {
            self.current_root.read()
        }

        fn get_root_at_height(self: @ContractState, height: u64) -> felt252 {
            self.root_history.read(height)
        }

        fn get_latest_snapshot(self: @ContractState) -> (felt252, u64, u64) {
            (
                self.current_root.read(),
                self.block_height.read(),
                self.updated_at.read()
            )
        }

        fn get_admin(self: @ContractState) -> ContractAddress {
            self.admin.read()
        }

        /// Check whether a snapshot root at `snapshot_height` is still within
        /// the validity window relative to the latest registered root height.
        ///
        /// Validity condition:
        ///   root_at(snapshot_height) != 0
        ///   AND latest_height - snapshot_height <= MAX_ROOT_AGE
        ///
        /// BalanceVerifier calls this before accepting any proof.
        fn is_root_valid(self: @ContractState, snapshot_height: u64) -> bool {
            // Root must exist at that height
            let root = self.root_history.read(snapshot_height);
            if root == 0 {
                return false;
            }

            let latest_height = self.block_height.read();

            // snapshot_height cannot be in the future
            if snapshot_height > latest_height {
                return false;
            }

            // Age check: latest_height - snapshot_height <= MAX_ROOT_AGE
            let age = latest_height - snapshot_height;
            age <= MAX_ROOT_AGE
        }

        fn get_max_root_age(self: @ContractState) -> u64 {
            MAX_ROOT_AGE
        }
    }
}
