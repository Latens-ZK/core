use core::array::ArrayTrait;
use core::hash::HashStateTrait;
use core::poseidon::PoseidonTrait;

#[derive(Drop, Serde)]
struct MerklePathElement {
    value: felt252,
    direction: bool, 
}

#[derive(Drop, Serde)]
struct PrivateInputs {
    address_hash: felt252,
    salt: felt252,
    balance: u64,
    merkle_path: Array<MerklePathElement>,
}

#[derive(Drop, Serde)]
struct PublicInputs {
    snapshot_root: felt252,
    commitment: felt252,
    threshold: u64,
}

fn main(private_inputs: PrivateInputs, public_inputs: PublicInputs) {
    // 1. Verify commitment verification
    // poseidon(address_hash, salt) == commitment
    let calculated_commitment = PoseidonTrait::new()
        .update(private_inputs.address_hash)
        .update(private_inputs.salt)
        .finalize();
        
    assert(calculated_commitment == public_inputs.commitment, 'Invalid commitment');

    // 2. Verify threshold
    if public_inputs.threshold > 0 {
        assert(private_inputs.balance >= public_inputs.threshold, 'Balance below threshold');
    }

    // 3. Verify Merkle Proof
    // Leaf = Poseidon(address_hash, balance)
    let leaf_hash = PoseidonTrait::new()
        .update(private_inputs.address_hash)
        .update(private_inputs.balance.into())
        .finalize();
        
    let calculated_root = compute_merkle_root(leaf_hash, private_inputs.merkle_path);
    
    assert(calculated_root == public_inputs.snapshot_root, 'Invalid Merkle proof');
}

fn compute_merkle_root(leaf: felt252, mut path: Array<MerklePathElement>) -> felt252 {
    let mut current_hash = leaf;
    
    loop {
        match path.pop_front() {
            Option::Some(element) => {
                let sibling = element.value;
                
                if !element.direction {
                    // Sibling is left
                    current_hash = PoseidonTrait::new()
                        .update(sibling)
                        .update(current_hash)
                        .finalize();
                } else {
                    // Sibling is right
                    current_hash = PoseidonTrait::new()
                        .update(current_hash)
                        .update(sibling)
                        .finalize();
                }
            },
            Option::None => {
                break;
            }
        };
    };
    
    current_hash
}
