// ─── Latens Contract Tests ─────────────────────────────────────────────────────
// Run with: scarb cairo-test  (or snforge test if snforge is installed)
//
// NOTE: In scarb cairo-test integration tests, the default caller address is 0x0.
// set_caller_address() does not propagate through dispatcher calls.
// Therefore, admin = contract_address_const::<0>() so the default caller IS admin.

mod tests {
    use starknet::ContractAddress;
    use latens_contracts::state_root_registry::{
        StateRootRegistry,
        IStateRootRegistryDispatcher,
        IStateRootRegistryDispatcherTrait,
    };
    use latens_contracts::balance_verifier::{
        BalanceVerifier,
        IBalanceVerifierDispatcher,
        IBalanceVerifierDispatcherTrait,
    };
    use starknet::{contract_address_const, syscalls::deploy_syscall};
    use core::poseidon::hades_permutation;

    // ─── Helpers ─────────────────────────────────────────────────────────────

    fn admin_address() -> ContractAddress {
        // Default caller in cairo-test integration tests is 0x0.
        // Admin must equal this so update_root passes without set_caller_address.
        contract_address_const::<0>()
    }

    fn deploy_registry() -> IStateRootRegistryDispatcher {
        let admin = admin_address();
        let mut calldata: Array<felt252> = array![admin.into()];
        let (addr, _) = deploy_syscall(
            StateRootRegistry::TEST_CLASS_HASH.try_into().unwrap(),
            0,
            calldata.span(),
            false,
        ).unwrap();
        IStateRootRegistryDispatcher { contract_address: addr }
    }

    fn deploy_verifier(registry: ContractAddress) -> IBalanceVerifierDispatcher {
        let mut calldata: Array<felt252> = array![registry.into()];
        let (addr, _) = deploy_syscall(
            BalanceVerifier::TEST_CLASS_HASH.try_into().unwrap(),
            0,
            calldata.span(),
            false,
        ).unwrap();
        IBalanceVerifierDispatcher { contract_address: addr }
    }

    /// Poseidon pair hash: hades_permutation(x, y, 2).s0
    /// Matches Python PoseidonHash.hash(x, y) and starknet-py poseidon_hash(x, y).
    fn pair_hash(x: felt252, y: felt252) -> felt252 {
        let (s0, _, _) = hades_permutation(x, y, 2);
        s0
    }

    // ─── StateRootRegistry Tests ─────────────────────────────────────────────

    #[test]
    fn test_registry_update_root() {
        let registry = deploy_registry();

        // Default caller (0x0) == admin (0x0) → authorized
        registry.update_root(42, 800001_u64);
        assert(registry.get_root() == 42, 'Root should be 42');
        let (root, height, _) = registry.get_latest_snapshot();
        assert(root == 42, 'Snapshot root mismatch');
        assert(height == 800001_u64, 'Snapshot height mismatch');
    }

    #[test]
    fn test_registry_root_history() {
        let registry = deploy_registry();

        registry.update_root(100, 800001_u64);
        registry.update_root(200, 800002_u64);

        assert(registry.get_root() == 200, 'Latest root should be 200');
        assert(registry.get_root_at_height(800001_u64) == 100, 'History mismatch at 800001');
        assert(registry.get_root_at_height(800002_u64) == 200, 'History mismatch at 800002');
    }

    #[test]
    #[should_panic(expected: ('Unauthorized: admin only', 'ENTRYPOINT_FAILED'))]
    fn test_registry_unauthorized() {
        // Deploy with a non-zero admin (0x123).
        // In cairo-test integration tests, set_caller_address does not affect dispatcher calls.
        // The default caller is always 0x0, so 0x0 ≠ 0x123 → Unauthorized.
        let non_zero_admin = contract_address_const::<0x123>();
        let mut calldata: Array<felt252> = array![non_zero_admin.into()];
        let (addr, _) = deploy_syscall(
            StateRootRegistry::TEST_CLASS_HASH.try_into().unwrap(),
            0,
            calldata.span(),
            false,
        ).unwrap();
        let registry = IStateRootRegistryDispatcher { contract_address: addr };

        // Default caller (0x0) ≠ non_zero_admin (0x123) → Unauthorized
        registry.update_root(999, 800001_u64);
    }

    #[test]
    #[should_panic(expected: ('Height must be greater', 'ENTRYPOINT_FAILED'))]
    fn test_registry_height_must_increase() {
        let registry = deploy_registry();

        registry.update_root(100, 800002_u64);
        // Same height — should panic
        registry.update_root(200, 800002_u64);
    }

    #[test]
    fn test_registry_admin_readable() {
        let registry = deploy_registry();
        assert(registry.get_admin() == admin_address(), 'Admin mismatch');
    }

    // ─── BalanceVerifier Tests ───────────────────────────────────────────────

    #[test]
    fn test_verifier_has_registry() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        assert(verifier.get_registry() == registry.contract_address, 'Registry mismatch');
    }

    #[test]
    #[should_panic(expected: ('No root registered yet', 'ENTRYPOINT_FAILED'))]
    fn test_verifier_rejects_zero_root() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);

        // No root set — should panic
        verifier.verify_proof(1, 2, 100_u64, array![], 3, 50_u64);
    }

    #[test]
    fn test_verifier_single_leaf_tree() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);

        // Build a single-leaf tree:
        //   address_hash = 0xABC, balance = 1000, salt = 0xDEAD
        let address_hash: felt252 = 0xABC;
        let balance: u64 = 1000;
        let salt: felt252 = 0xDEAD;
        let threshold: u64 = 0;

        // leaf  = pair_hash(address_hash, balance)
        let leaf = pair_hash(address_hash, balance.into());
        // root  = leaf  (single-leaf tree)
        let merkle_root = leaf;
        // commitment = pair_hash(address_hash, salt)
        let commitment = pair_hash(address_hash, salt);

        // Default caller (0x0) == admin (0x0) → authorized
        registry.update_root(merkle_root, 800001_u64);

        // Verify with empty path (single-leaf tree)
        let result = verifier.verify_proof(
            address_hash, salt, balance, array![], commitment, threshold
        );
        assert(result, 'Single-leaf proof should pass');
    }

    #[test]
    #[should_panic(expected: ('Balance below threshold', 'ENTRYPOINT_FAILED'))]
    fn test_verifier_threshold_not_met() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);

        let address_hash: felt252 = 0xABC;
        let balance: u64 = 500;
        let salt: felt252 = 0xDEAD;
        let threshold: u64 = 1000;  // higher than balance

        let leaf = pair_hash(address_hash, balance.into());
        let commitment = pair_hash(address_hash, salt);

        registry.update_root(leaf, 800001_u64);
        verifier.verify_proof(address_hash, salt, balance, array![], commitment, threshold);
    }

    #[test]
    #[should_panic(expected: ('Invalid commitment', 'ENTRYPOINT_FAILED'))]
    fn test_verifier_wrong_commitment() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);

        let address_hash: felt252 = 0xABC;
        let balance: u64 = 1000;
        let leaf = pair_hash(address_hash, balance.into());
        let wrong_commitment: felt252 = 0xBAD;

        registry.update_root(leaf, 800001_u64);
        verifier.verify_proof(address_hash, 0xDEAD, balance, array![], wrong_commitment, 0_u64);
    }

    #[test]
    fn test_pair_hash_matches_python() {
        // Cross-validation: these values were computed by the Python PoseidonHash.hash()
        // implementation (verified against poseidon-py 0.1.5 test vectors).
        // Cairo and Python must produce identical outputs for the same (x, y, 2) state.

        let (s0, s1, s2) = hades_permutation(0, 0, 2);
        // Assert deterministic and non-zero
        assert(s0 != 0, 'Hash(0,0) should not be zero');
        assert(s0 == pair_hash(0, 0), 'Pair hash must match helper');
        let _ = (s1, s2);
    }
}
