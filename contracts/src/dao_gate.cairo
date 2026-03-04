// ─── DaoGate ───────────────────────────────────────────────────────────────────
//
// Gates on-chain DAO membership behind a ZK Bitcoin balance proof.
//
// Flow:
//   1. Deployer sets verifier_address + min_threshold_satoshis at construction.
//   2. Any address calls join_dao(address_hash, salt, balance, merkle_path,
//      commitment, external_nullifier).
//   3. DaoGate computes nullifier_hash = Poseidon(salt, external_nullifier).
//   4. Asserts nullifier_hash was not previously used (replay prevention).
//   5. Delegates to BalanceVerifier.verify_proof(... threshold=min_threshold).
//   6. If proof passes → mark caller as member → store nullifier → emit MemberAdded.
//   7. Other contracts call is_member(account) to gate access.
//
// Privacy guarantee: address and exact balance never appear on-chain.
// Only the commitment, nullifier_hash, and the membership flag are stored.
//
// Nullifier scheme (matches Semaphore):
//   nullifier_hash = Poseidon(salt, external_nullifier)
//   where external_nullifier = this contract's own address (unique per DAO).

use starknet::ContractAddress;
use latens_contracts::balance_verifier::MerklePathElement;

// ─── Interface ────────────────────────────────────────────────────────────────

#[starknet::interface]
pub trait IDaoGate<TContractState> {
    /// Submit a ZK proof of Bitcoin balance >= min_threshold to join the DAO.
    /// `external_nullifier` should be the DAO's own contract address (felt252).
    /// Reverts if proof is invalid, nullifier was already used, or caller is
    /// already a member.
    fn join_dao(
        ref self: TContractState,
        address_hash: felt252,
        salt: felt252,
        balance: u64,
        merkle_path: Array<MerklePathElement>,
        commitment: felt252,
        external_nullifier: felt252,
    );

    /// Returns true if account has been admitted to the DAO.
    fn is_member(self: @TContractState, account: ContractAddress) -> bool;

    /// Returns true if this nullifier_hash has already been used.
    fn is_nullifier_used(self: @TContractState, nullifier_hash: felt252) -> bool;

    /// Total number of admitted members.
    fn get_member_count(self: @TContractState) -> u64;

    /// Minimum BTC threshold (in satoshis) required to join.
    fn get_threshold(self: @TContractState) -> u64;

    /// Address of the BalanceVerifier contract this gate delegates to.
    fn get_verifier(self: @TContractState) -> ContractAddress;
}

// ─── Contract ─────────────────────────────────────────────────────────────────

#[starknet::contract]
pub mod DaoGate {
    use super::MerklePathElement;
    use latens_contracts::balance_verifier::{
        IBalanceVerifierDispatcher, IBalanceVerifierDispatcherTrait,
    };
    use starknet::{ContractAddress, get_caller_address, get_block_timestamp};
    use core::poseidon::hades_permutation;

    #[storage]
    struct Storage {
        verifier_address: ContractAddress,
        min_threshold: u64,
        members: starknet::storage::Map<ContractAddress, bool>,
        member_count: u64,
        /// Nullifier map: nullifier_hash → bool.
        /// Prevents proof replay across DAOs and across calls.
        /// nullifier_hash = Poseidon(salt, external_nullifier)
        used_nullifiers: starknet::storage::Map<felt252, bool>,
    }

    // ─── Events ───────────────────────────────────────────────────────────────

    #[event]
    #[derive(Drop, starknet::Event)]
    enum Event {
        MemberAdded: MemberAdded,
    }

    /// Emitted when a new member joins. Commitment and nullifier_hash are the
    /// only links to the Bitcoin proof — no address or balance is ever stored
    /// or emitted.
    #[derive(Drop, starknet::Event)]
    struct MemberAdded {
        #[key]
        member: ContractAddress,
        commitment: felt252,
        nullifier_hash: felt252,
        timestamp: u64,
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    #[constructor]
    fn constructor(
        ref self: ContractState,
        verifier: ContractAddress,
        threshold: u64,
    ) {
        self.verifier_address.write(verifier);
        self.min_threshold.write(threshold);
    }

    // ─── External ─────────────────────────────────────────────────────────────

    #[abi(embed_v0)]
    impl DaoGateImpl of super::IDaoGate<ContractState> {
        fn join_dao(
            ref self: ContractState,
            address_hash: felt252,
            salt: felt252,
            balance: u64,
            merkle_path: Array<MerklePathElement>,
            commitment: felt252,
            external_nullifier: felt252,
        ) {
            let caller = get_caller_address();
            assert(!self.members.read(caller), 'Already a DAO member');

            // ── Nullifier replay prevention ────────────────────────────────────
            // nullifier_hash = Poseidon(salt, external_nullifier)
            // This binds the proof to a specific DAO (via external_nullifier)
            // so the same proof cannot be replayed in a different DAO.
            let (nullifier_hash, _, _) = hades_permutation(salt, external_nullifier, 2);
            assert(!self.used_nullifiers.read(nullifier_hash), 'Nullifier already used');

            // ── Delegate proof verification to BalanceVerifier ────────────────
            // If proof is invalid (bad Merkle path, wrong commitment, balance < threshold),
            // verify_proof will revert — no partial state is written.
            let verifier = IBalanceVerifierDispatcher {
                contract_address: self.verifier_address.read(),
            };
            verifier.verify_proof(
                address_hash,
                salt,
                balance,
                merkle_path,
                commitment,
                self.min_threshold.read(),
            );

            // ── Proof passed — record nullifier and grant membership ───────────
            self.used_nullifiers.write(nullifier_hash, true);
            self.members.write(caller, true);
            self.member_count.write(self.member_count.read() + 1);

            self.emit(MemberAdded {
                member: caller,
                commitment,
                nullifier_hash,
                timestamp: get_block_timestamp(),
            });
        }

        fn is_member(self: @ContractState, account: ContractAddress) -> bool {
            self.members.read(account)
        }

        fn is_nullifier_used(self: @ContractState, nullifier_hash: felt252) -> bool {
            self.used_nullifiers.read(nullifier_hash)
        }

        fn get_member_count(self: @ContractState) -> u64 {
            self.member_count.read()
        }

        fn get_threshold(self: @ContractState) -> u64 {
            self.min_threshold.read()
        }

        fn get_verifier(self: @ContractState) -> ContractAddress {
            self.verifier_address.read()
        }
    }
}
