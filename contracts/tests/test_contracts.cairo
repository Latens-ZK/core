use starknet::ContractAddress;

// ─── Contract Tests for Latens ─────────────────────────────────────────────────
// Run: snforge test

mod tests {
    use latens_contracts::state_root_registry::{StateRootRegistry, IStateRootRegistryDispatcher, IStateRootRegistryDispatcherTrait};
    use latens_contracts::balance_verifier::{BalanceVerifier, IBalanceVerifierDispatcher, IBalanceVerifierDispatcherTrait, MerklePathElement};
    use starknet::testing::{set_caller_address, PopLogTrait};
    use starknet::{contract_address_const, get_contract_address};
    use core::array::ArrayTrait;

    fn deploy_registry(admin: ContractAddress) -> IStateRootRegistryDispatcher {
        let mut calldata = array![admin.into()];
        let (addr, _) = starknet::syscalls::deploy_syscall(
            StateRootRegistry::TEST_CLASS_HASH.try_into().unwrap(),
            0,
            calldata.span(),
            false
        ).unwrap();
        IStateRootRegistryDispatcher { contract_address: addr }
    }

    fn deploy_verifier(registry: ContractAddress) -> IBalanceVerifierDispatcher {
        let mut calldata = array![registry.into()];
        let (addr, _) = starknet::syscalls::deploy_syscall(
            BalanceVerifier::TEST_CLASS_HASH.try_into().unwrap(),
            0,
            calldata.span(),
            false
        ).unwrap();
        IBalanceVerifierDispatcher { contract_address: addr }
    }

    // ─── Registry Tests ──────────────────────────────────────────────────────

    #[test]
    fn test_registry_update_root() {
        let admin = contract_address_const::<0x123>();
        set_caller_address(admin);
        let registry = deploy_registry(admin);

        registry.update_root(42_felt252, 800000_u64);
        assert(registry.get_root() == 42_felt252, 'Root should be 42');
    }

    #[test]
    fn test_registry_root_history() {
        let admin = contract_address_const::<0x123>();
        set_caller_address(admin);
        let registry = deploy_registry(admin);

        registry.update_root(100_felt252, 800000_u64);
        registry.update_root(200_felt252, 800001_u64);

        // Latest root
        assert(registry.get_root() == 200_felt252, 'Latest root should be 200');

        // Historical lookup
        assert(registry.get_root_at_height(800000_u64) == 100_felt252, 'Historical root mismatch');
        assert(registry.get_root_at_height(800001_u64) == 200_felt252, 'Root at 800001 mismatch');
    }

    #[test]
    #[should_panic(expected: ('Unauthorized: admin only', ))]
    fn test_registry_unauthorized() {
        let admin = contract_address_const::<0x123>();
        let attacker = contract_address_const::<0x456>();
        set_caller_address(admin);
        let registry = deploy_registry(admin);

        set_caller_address(attacker);
        registry.update_root(999_felt252, 800000_u64);
    }

    #[test]
    fn test_registry_emits_event() {
        let admin = contract_address_const::<0x123>();
        set_caller_address(admin);
        let registry = deploy_registry(admin);
        registry.update_root(77_felt252, 800000_u64);
        // Event emitting: verify via logs (snforge captures them)
        let mut logs = starknet::testing::get_events();
        assert(logs.len() == 1_u32, 'Should emit 1 event');
    }

    // ─── Verifier Tests ───────────────────────────────────────────────────────

    #[test]
    fn test_verifier_rejects_zero_root() {
        let admin = contract_address_const::<0x123>();
        set_caller_address(admin);
        let registry = deploy_registry(admin);
        let verifier = deploy_verifier(registry.contract_address);

        // No root set — should panic with 'No root registered yet'
        let result = std::panic::catch_unwind(|| {
            verifier.verify_proof(1, 2, 100, array![], 3, 50);
        });
        assert(result.is_err(), 'Should fail with no root');
    }

    #[test]
    fn test_verifier_has_registry() {
        let admin = contract_address_const::<0x123>();
        set_caller_address(admin);
        let registry = deploy_registry(admin);
        let verifier = deploy_verifier(registry.contract_address);
        assert(verifier.get_registry() == registry.contract_address, 'Registry mismatch');
    }
}
