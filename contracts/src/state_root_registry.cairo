use starknet::ContractAddress;

#[starknet::interface]
pub trait IStateRootRegistry<TContractState> {
    fn update_root(ref self: TContractState, new_root: felt252, height: u64);
    fn get_root(self: @TContractState) -> felt252;
    fn get_root_at_height(self: @TContractState, height: u64) -> felt252;
    fn get_latest_snapshot(self: @TContractState) -> (felt252, u64, u64);
    fn get_admin(self: @TContractState) -> ContractAddress;
}

#[starknet::contract]
pub mod StateRootRegistry {
    use starknet::{ContractAddress, get_caller_address, get_block_timestamp};

    #[storage]
    struct Storage {
        current_root: felt252,
        block_height: u64,
        updated_at: u64,
        admin: ContractAddress,
        // History: mapping block_height -> merkle_root
        root_history: starknet::storage::Map<u64, felt252>,
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

            // Store in history map
            self.root_history.write(height, new_root);

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
    }
}
