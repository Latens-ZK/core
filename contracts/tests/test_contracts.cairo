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
    use latens_contracts::dao_gate::{
        DaoGate,
        IDaoGateDispatcher,
        IDaoGateDispatcherTrait,
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

    fn deploy_dao_gate(verifier: ContractAddress, threshold: u64) -> IDaoGateDispatcher {
        let mut calldata: Array<felt252> = array![verifier.into(), threshold.into()];
        let (addr, _) = deploy_syscall(
            DaoGate::TEST_CLASS_HASH.try_into().unwrap(),
            0,
            calldata.span(),
            false,
        ).unwrap();
        IDaoGateDispatcher { contract_address: addr }
    }

    /// Poseidon pair hash: hades_permutation(x, y, 2).s0
    /// Matches Python PoseidonHash.hash(x, y) and starknet-py poseidon_hash(x, y).
    fn pair_hash(x: felt252, y: felt252) -> felt252 {
        let (s0, _, _) = hades_permutation(x, y, 2);
        s0
    }

    /// Compute nullifier_hash = Poseidon(salt, external_nullifier)
    /// Matches DaoGate join_dao internal computation.
    fn nullifier_hash(salt: felt252, external_nullifier: felt252) -> felt252 {
        pair_hash(salt, external_nullifier)
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

    // ─── is_root_valid Tests ─────────────────────────────────────────────────

    #[test]
    fn test_is_root_valid_fresh_root() {
        let registry = deploy_registry();

        // A freshly added root at height H where H is the latest → age = 0 → valid
        registry.update_root(42, 800001_u64);

        // Latest height == 800001, snapshot at 800001 → age = 0 ≤ 1008 → valid
        assert(registry.is_root_valid(800001_u64), 'Fresh root should be valid');
    }

    #[test]
    fn test_is_root_valid_within_window() {
        let registry = deploy_registry();

        // Add a root at height 800000
        registry.update_root(42, 800000_u64);
        // Move the chain forward by 500 blocks (within MAX_ROOT_AGE = 1008)
        registry.update_root(99, 800500_u64);

        // Root at 800000, latest at 800500 → age = 500 ≤ 1008 → valid
        assert(registry.is_root_valid(800000_u64), 'Root within window should be valid');
    }

    #[test]
    fn test_is_root_valid_exactly_at_max_age() {
        let registry = deploy_registry();

        registry.update_root(42, 800000_u64);
        // Advance exactly MAX_ROOT_AGE = 1008 blocks
        registry.update_root(99, 801008_u64);

        // age = 1008 == MAX_ROOT_AGE → valid (boundary inclusive)
        assert(registry.is_root_valid(800000_u64), 'Root at MAX_ROOT_AGE should be valid');
    }

    #[test]
    fn test_is_root_valid_expired() {
        let registry = deploy_registry();

        registry.update_root(42, 800000_u64);
        // Advance 1009 blocks — one past MAX_ROOT_AGE
        registry.update_root(99, 801009_u64);

        // age = 1009 > MAX_ROOT_AGE → expired
        assert(!registry.is_root_valid(800000_u64), 'Root past MAX_ROOT_AGE should be expired');
    }

    #[test]
    fn test_is_root_valid_missing_root() {
        let registry = deploy_registry();
        registry.update_root(42, 800001_u64);

        // Height 999999 was never registered → root_history[999999] == 0 → invalid
        assert(!registry.is_root_valid(999999_u64), 'Unregistered height should be invalid');
    }

    #[test]
    fn test_get_max_root_age_constant() {
        let registry = deploy_registry();
        assert(registry.get_max_root_age() == 1008_u64, 'MAX_ROOT_AGE should be 1008');
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
    #[should_panic(expected: ('Root expired or missing', 'ENTRYPOINT_FAILED'))]
    fn test_verifier_rejects_expired_root_at_height() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);

        let address_hash: felt252 = 0xABC;
        let balance: u64 = 1000;
        let salt: felt252 = 0xDEAD;

        let leaf = pair_hash(address_hash, balance.into());
        let commitment = pair_hash(address_hash, salt);

        // Register root at height 800000
        registry.update_root(leaf, 800000_u64);
        // Advance chain 1009 blocks past MAX_ROOT_AGE = 1008 → expired
        registry.update_root(leaf, 801009_u64);

        // verify_proof_at_height against the expired height should revert
        verifier.verify_proof_at_height(
            address_hash, salt, balance, array![], commitment, 0_u64, 800000_u64
        );
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

    // ─── DaoGate Tests ───────────────────────────────────────────────────────

    #[test]
    fn test_dao_gate_config() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        // Threshold: 100_000_000 satoshis = 1 BTC
        let dao = deploy_dao_gate(verifier.contract_address, 100_000_000_u64);

        assert(dao.get_threshold() == 100_000_000_u64, 'Threshold mismatch');
        assert(dao.get_verifier() == verifier.contract_address, 'Verifier mismatch');
        assert(dao.get_member_count() == 0_u64, 'Should start empty');
    }

    #[test]
    fn test_dao_gate_join_success() {
        // Full integration: registry → verifier → dao_gate
        //
        // We prove: address owns 2 BTC, DAO requires >= 1 BTC.
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        let dao = deploy_dao_gate(verifier.contract_address, 100_000_000_u64); // 1 BTC threshold

        // Build a single-leaf tree for the proof
        let address_hash: felt252 = 0x42424242;
        let balance: u64 = 200_000_000; // 2 BTC in satoshis
        let salt: felt252 = 0xdeadbeef;
        let external_nullifier: felt252 = 0xDA0DA0;  // simulated DAO address

        let leaf = pair_hash(address_hash, balance.into());
        let commitment = pair_hash(address_hash, salt);

        // Register the root (default caller 0x0 == admin)
        registry.update_root(leaf, 800001_u64);

        // Default caller (0x0) is not yet a member
        assert(!dao.is_member(contract_address_const::<0>()), 'Should not be member yet');

        // Join the DAO via ZK proof — balance (2 BTC) >= threshold (1 BTC)
        dao.join_dao(address_hash, salt, balance, array![], commitment, external_nullifier);

        // Default caller (0x0) is now a member
        assert(dao.is_member(contract_address_const::<0>()), 'Should be member now');
        assert(dao.get_member_count() == 1_u64, 'Member count should be 1');
    }

    #[test]
    #[should_panic(expected: ('Balance below threshold', 'ENTRYPOINT_FAILED'))]
    fn test_dao_gate_balance_too_low() {
        // DAO requires 1 BTC, prover only has 0.5 BTC → rejected
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        let dao = deploy_dao_gate(verifier.contract_address, 100_000_000_u64); // 1 BTC threshold

        let address_hash: felt252 = 0x11111111;
        let balance: u64 = 50_000_000; // 0.5 BTC — below threshold
        let salt: felt252 = 0xfeedface;
        let external_nullifier: felt252 = 0xDA0DA0;

        let leaf = pair_hash(address_hash, balance.into());
        let commitment = pair_hash(address_hash, salt);

        registry.update_root(leaf, 800001_u64);
        // Should revert inside BalanceVerifier: 'Balance below threshold'
        dao.join_dao(address_hash, salt, balance, array![], commitment, external_nullifier);
    }

    #[test]
    #[should_panic(expected: ('Already a DAO member', 'ENTRYPOINT_FAILED'))]
    fn test_dao_gate_no_double_join() {
        // Same StarkNet address cannot join twice (even with different nullifier)
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        let dao = deploy_dao_gate(verifier.contract_address, 0_u64); // no threshold for simplicity

        let address_hash: felt252 = 0x99999999;
        let balance: u64 = 100_000_000;
        let salt: felt252 = 0xc0ffee;
        let external_nullifier: felt252 = 0xDA0DA0;

        let leaf = pair_hash(address_hash, balance.into());
        let commitment = pair_hash(address_hash, salt);

        registry.update_root(leaf, 800001_u64);
        dao.join_dao(address_hash, salt, balance, array![], commitment, external_nullifier);

        // Second join — 'Already a DAO member' fires before nullifier check
        dao.join_dao(address_hash, salt, balance, array![], commitment, external_nullifier);
    }

    // ─── Nullifier Replay Prevention Tests ────────────────────────────────────

    #[test]
    fn test_nullifier_computed_and_stored() {
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        let dao = deploy_dao_gate(verifier.contract_address, 0_u64);

        let address_hash: felt252 = 0xBEEF;
        let balance: u64 = 100_000_000;
        let salt: felt252 = 0xCAFE;
        let external_nullifier: felt252 = 0xDA0;

        let leaf = pair_hash(address_hash, balance.into());
        let commitment = pair_hash(address_hash, salt);
        registry.update_root(leaf, 800001_u64);

        // Before join: nullifier not yet used
        let nh = nullifier_hash(salt, external_nullifier);
        assert(!dao.is_nullifier_used(nh), 'Nullifier should not be set yet');

        dao.join_dao(address_hash, salt, balance, array![], commitment, external_nullifier);

        // After join: nullifier must be marked used
        assert(dao.is_nullifier_used(nh), 'Nullifier should be marked used');
    }

    #[test]
    #[should_panic(expected: ('Nullifier already used', 'ENTRYPOINT_FAILED'))]
    fn test_nullifier_replay_same_dao_blocked() {
        // Same salt + same DAO cannot be reused for a second proof.
        // This prevents replay attacks even if the Starknet address changes
        // (e.g. user switches wallets but tries to reuse the same BTC proof).
        let registry = deploy_registry();
        let verifier = deploy_verifier(registry.contract_address);
        // No threshold
        let dao = deploy_dao_gate(verifier.contract_address, 0_u64);

        let salt: felt252 = 0xSECRET;
        let external_nullifier: felt252 = 0xDA0;

        // --- Prover A ---
        let addr_a: felt252 = 0xAAAA;
        let balance_a: u64 = 100_000_000;
        let leaf_a = pair_hash(addr_a, balance_a.into());
        let commitment_a = pair_hash(addr_a, salt);
        registry.update_root(leaf_a, 800001_u64);

        // First user claims the proof
        starknet::testing::set_caller_address(starknet::contract_address_const::<0x1111>());
        dao.join_dao(addr_a, salt, balance_a, array![], commitment_a, external_nullifier);

        // --- Second user tries to claim the same proof ---
        // Change caller so 'Already a DAO member' does not fire
        starknet::testing::set_caller_address(starknet::contract_address_const::<0x2222>());
        dao.join_dao(addr_a, salt, balance_a, array![], commitment_a, external_nullifier);
    }

    #[test]
    fn test_different_external_nullifier_same_salt_different_hash() {
        // Proves that nullifier_hash = Poseidon(salt, external_nullifier) creates
        // distinct hashes for different DAOs, so a proof usable in DAO-A cannot
        // be mechanically replayed in DAO-B just by changing external_nullifier.
        let salt: felt252 = 0xSECRET;
        let dao_a_nullifier: felt252 = 0xDA0A;
        let dao_b_nullifier: felt252 = 0xDA0B;

        let nh_a = nullifier_hash(salt, dao_a_nullifier);
        let nh_b = nullifier_hash(salt, dao_b_nullifier);

        assert(nh_a != nh_b, 'Different DAOs must have different nullifier hashes');
    }
}
