/**
 * Latens — Client-side cryptography library.
 *
 * Privacy guarantee: The raw Bitcoin address NEVER leaves the browser.
 * All address processing happens locally in this file.
 *
 * Exports:
 *   generateSalt()                          — cryptographically random 32-byte salt
 *   encodeAddressAsFelt252(address)         — canonical hash160 → felt252 encoding
 *   computeCommitment(addressHash, salt)    — Poseidon(address_hash, salt)
 *   computeMerkleWitness(commitment, tree)  — full Merkle path from local tree
 *   generateNoirProof(witness)              — ZK proof stub (Barretenberg WASM)
 *   buildStarknetCalldata(proof, witness)   — assemble on-chain calldata
 *
 * Encoding spec (felt252 address encoding):
 *   address_hash = SHA-256(UTF-8(bitcoin_address)) mod PRIME
 *
 *   Rationale: SHA-256 is available in all browsers via @noble/hashes,
 *   produces a 32-byte value, and the modular reduction ensures the result
 *   fits in a felt252 field element. This matches the backend's
 *   AddressUtils.get_address_hash() in address_utils.py.
 *
 *   Alternative (hash160): For P2PKH/P2SH addresses, decoding the Base58Check
 *   payload gives the RIPEMD-160(SHA-256(pubkey)) hash directly (20 bytes = 160 bits),
 *   which fits cleanly as a felt252. This is cheaper in Cairo but requires
 *   address-format-specific decoding. SHA-256(address_string) % PRIME is the
 *   canonical spec used in this sprint for uniformity across all address types.
 */

import { hash } from 'starknet';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex as toHex } from '@noble/hashes/utils';

// ─── Constants ────────────────────────────────────────────────────────────────

/** Starknet field prime: 2^251 + 17·2^192 + 1 */
const PRIME = 2n ** 251n + 17n * 2n ** 192n + 1n;

// ─── Types ────────────────────────────────────────────────────────────────────

/** One element of a Merkle inclusion proof (mirrors Cairo MerklePathElement). */
export interface MerklePathElement {
    /** Sibling node value as decimal string (felt252). */
    value: string;
    /**
     * Direction semantics (matches Python MerkleTree + Cairo):
     *   false → sibling is LEFT  → hash(sibling, current)
     *   true  → sibling is RIGHT → hash(current, sibling)
     */
    direction: boolean;
}

/** Full witness for one address in the Merkle tree. */
export interface MerkleWitness {
    addressHash: string;   // hex felt252
    salt: string;          // hex felt252
    commitment: string;    // hex felt252 = Poseidon(addressHash, salt)
    balance: bigint;       // satoshis
    merkleRoot: string;    // hex felt252
    merklePath: MerklePathElement[];
    threshold: bigint;     // satoshis
}

/** Noir ZK proof (Barretenberg output). */
export interface NoirProof {
    proof: Uint8Array;
    publicInputs: string[];
}

/** Result of buildStarknetCalldata(). */
export interface StarknetCalldata {
    /** Calldata for BalanceVerifier.verify_proof() — pass to account.execute(). */
    verifyProof: string[];
    /** Calldata for DaoGate.join_dao() — includes external_nullifier. */
    joinDao: (externalNullifier: string) => string[];
}

// Simple Merkle tree node structure for client-side tree
export interface MerkleTreeNode {
    hash: string;        // hex felt252
    left?: MerkleTreeNode;
    right?: MerkleTreeNode;
    address?: string;    // only on leaves
    balance?: bigint;
}

// ─── Core Primitives ──────────────────────────────────────────────────────────

/** Generate a cryptographically random 32-byte salt as a hex string. */
export const generateSalt = (): string => {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return '0x' + toHex(array);
};

/**
 * Canonical felt252 address encoding.
 *
 * Spec: SHA-256(UTF-8(bitcoin_address)) mod PRIME
 *
 * Matches: backend/src/crypto/address_utils.py::AddressUtils.get_address_hash()
 * Matches: Cairo hades_permutation input (address_hash parameter)
 *
 * @param address Bitcoin address string (any format: P2PKH, P2SH, Bech32, Bech32m)
 * @returns Hex felt252 string (0x-prefixed)
 */
export const encodeAddressAsFelt252 = (address: string): string => {
    const hashBytes = sha256(new TextEncoder().encode(address));
    const hex = toHex(hashBytes);
    const bigVal = BigInt(`0x${hex}`);
    const fieldVal = bigVal % PRIME;
    return '0x' + fieldVal.toString(16);
};

/**
 * @deprecated Use encodeAddressAsFelt252 — same implementation, clearer name.
 */
export const normalizeAddress = encodeAddressAsFelt252;

/**
 * Compute commitment = Poseidon(addressHash, salt).
 * Uses starknet.js hash.computePoseidonHash which calls hades_permutation(x, y, 2)[0].
 * Matches Python PoseidonHash.hash_commitment() and Cairo hades_permutation(x, y, 2).s0.
 */
export const computeCommitment = (addressHash: string, saltHex: string): string => {
    return hash.computePoseidonHash(addressHash, saltHex);
};

/**
 * Compute a Poseidon leaf hash for a (addressHash, balance) pair.
 * This is the leaf value inserted into the Merkle tree.
 * Matches Cairo: hades_permutation(address_hash, balance.into(), 2).s0
 */
export const computeLeafHash = (addressHash: string, balance: bigint): string => {
    return hash.computePoseidonHash(addressHash, '0x' + balance.toString(16));
};

// ─── Merkle Witness Computation ───────────────────────────────────────────────

/**
 * Compute the Merkle path (witness) for a given commitment in a locally-held tree.
 *
 * The tree is a flat array of { address, balance } objects. This function:
 *   1. Computes address_hash = encodeAddressAsFelt252(address) for each entry.
 *   2. Builds a Poseidon Merkle tree bottom-up.
 *   3. Locates the target commitment's address in the tree.
 *   4. Returns the sibling path from leaf to root.
 *
 * @param address     The prover's Bitcoin address (stays in browser).
 * @param salt        The prover's random salt (stays in browser).
 * @param balanceList Array of { address: string, balance: bigint } from the snapshot.
 * @param threshold   Minimum balance in satoshis.
 * @returns           MerkleWitness with path, root, and commitment.
 * @throws            Error if address is not found in the balance list.
 */
export const computeMerkleWitness = (
    address: string,
    salt: string,
    balanceList: Array<{ address: string; balance: bigint }>,
    threshold: bigint = 0n,
): MerkleWitness => {
    if (balanceList.length === 0) {
        throw new Error('Balance list is empty — cannot build Merkle tree');
    }

    // 1. Compute address hashes and leaf hashes
    const addressHash = encodeAddressAsFelt252(address);
    const leaves = balanceList.map(entry => ({
        address: entry.address,
        addressHash: encodeAddressAsFelt252(entry.address),
        balance: entry.balance,
        leafHash: computeLeafHash(encodeAddressAsFelt252(entry.address), entry.balance),
    }));

    // 2. Find the target leaf index
    const targetIndex = leaves.findIndex(l => l.address === address);
    if (targetIndex === -1) {
        throw new Error(
            `Address '${address}' not found in the provided balance list. ` +
            'Ensure you are using the correct snapshot.'
        );
    }

    // 3. Build the Merkle tree bottom-up using Poseidon pair hashes
    let level: string[] = leaves.map(l => l.leafHash);
    const paths: Array<MerklePathElement[]> = leaves.map(() => []);

    while (level.length > 1) {
        const nextLevel: string[] = [];
        const halfLen = Math.ceil(level.length / 2);

        for (let i = 0; i < halfLen; i++) {
            const leftIdx = 2 * i;
            const rightIdx = 2 * i + 1;

            const left = level[leftIdx];
            // Duplicate last node if odd number of nodes (standard padding)
            const right = rightIdx < level.length ? level[rightIdx] : level[leftIdx];

            const parentHash = hash.computePoseidonHash(left, right);
            nextLevel.push(parentHash);

            // Update sibling info for all leaves in this subtree
            for (let leafIdx = 0; leafIdx < leaves.length; leafIdx++) {
                // Track which subtree this leaf belongs to at this level
                const subtreeRoot = Math.floor(leafIdx / Math.pow(2, paths[leafIdx].length));
                if (Math.floor(subtreeRoot / 2) === i) {
                    const isLeftChild = subtreeRoot % 2 === 0;
                    if (isLeftChild) {
                        // This leaf is in the left subtree; sibling is RIGHT
                        paths[leafIdx].push({ value: right, direction: true });
                    } else {
                        // This leaf is in the right subtree; sibling is LEFT
                        paths[leafIdx].push({ value: left, direction: false });
                    }
                }
            }
        }

        level = nextLevel;
    }

    const merkleRoot = level[0];
    const merklePath = paths[targetIndex];
    const commitment = computeCommitment(addressHash, salt);
    const balance = leaves[targetIndex].balance;

    return {
        addressHash,
        salt,
        commitment,
        balance,
        merkleRoot,
        merklePath,
        threshold,
    };
};

// ─── ZK Proof Generation (Barretenberg WASM stub) ─────────────────────────────

/**
 * Generate a Noir/Barretenberg ZK proof client-side.
 *
 * STATUS: Stub implementation for Sprint S1.
 * Real implementation (S2) will:
 *   1. Load @aztec/bb.js (Barretenberg WASM bundle)
 *   2. Instantiate the circuit from circuit.nr compiled .json
 *   3. Execute: await bb.prove(witness, circuit)
 *   4. Return the proof bytes + public inputs
 *
 * The stub returns a deterministic placeholder proof so the frontend
 * UI and Starknet calldata assembly can be developed/tested in parallel.
 *
 * @param witness The MerkleWitness produced by computeMerkleWitness().
 * @returns       NoirProof with proof bytes and public inputs.
 */
export const generateNoirProof = async (witness: MerkleWitness): Promise<NoirProof> => {
    // TODO (S2): Replace with real Barretenberg WASM invocation:
    //
    // import { Barretenberg, RawBuffer } from '@aztec/bb.js';
    // const bb = await Barretenberg.new();
    // const circuitJson = await fetch('/circuit.json').then(r => r.json());
    // const { proof, publicInputs } = await bb.proveUltraPlonk(circuitJson, witnessMap);
    // return { proof, publicInputs };

    console.warn(
        '[Latens] generateNoirProof: using stub proof — real Barretenberg WASM not yet integrated.\n' +
        'Set NEXT_PUBLIC_USE_REAL_PROVER=true and provide @aztec/bb.js to enable real proofs.'
    );

    // Stub: encode the public inputs as the "proof"
    const encoder = new TextEncoder();
    const stubProof = encoder.encode(
        `LATENS_STUB_v1:commitment=${witness.commitment}:root=${witness.merkleRoot}`
    );

    return {
        proof: stubProof,
        publicInputs: [
            witness.merkleRoot,
            witness.commitment,
            witness.threshold.toString(),
        ],
    };
};

// ─── Starknet Calldata Assembly ───────────────────────────────────────────────

/**
 * Assemble Starknet calldata for BalanceVerifier.verify_proof() and
 * DaoGate.join_dao() from a local witness.
 *
 * The client holds address_hash, salt, balance — these are included in
 * the calldata so the on-chain contract can verify the commitment.
 * No raw Bitcoin address ever appears on-chain or in backend logs.
 *
 * @param witness   Local MerkleWitness.
 * @returns         StarknetCalldata with calldata builders.
 */
export const buildStarknetCalldata = (witness: MerkleWitness): StarknetCalldata => {
    // Serialize merkle path: [len, value0, direction0, value1, direction1, ...]
    const pathCalldata: string[] = [witness.merklePath.length.toString()];
    for (const el of witness.merklePath) {
        pathCalldata.push(BigInt(el.value).toString());
        pathCalldata.push(el.direction ? '1' : '0');
    }

    // verify_proof(address_hash, salt, balance, merkle_path, commitment, threshold)
    const verifyProof: string[] = [
        BigInt(witness.addressHash).toString(),
        BigInt(witness.salt).toString(),
        witness.balance.toString(),
        ...pathCalldata,
        BigInt(witness.commitment).toString(),
        witness.threshold.toString(),
    ];

    // join_dao(address_hash, salt, balance, merkle_path, commitment, external_nullifier)
    const joinDao = (externalNullifier: string): string[] => [
        BigInt(witness.addressHash).toString(),
        BigInt(witness.salt).toString(),
        witness.balance.toString(),
        ...pathCalldata,
        BigInt(witness.commitment).toString(),
        BigInt(externalNullifier).toString(),
    ];

    return { verifyProof, joinDao };
};
