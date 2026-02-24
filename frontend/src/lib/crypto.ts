import { hash, num } from 'starknet';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex as toHex } from '@noble/hashes/utils';

// Starknet Prime (for reference)
const PRIME = 2n ** 251n + 17n * 2n ** 192n + 1n;

export const generateSalt = (): string => {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return '0x' + toHex(array);
};

export const normalizeAddress = (address: string): string => {
    // Matches backend: int.from_bytes(sha256(address.encode()).digest(), 'big') % PRIME
    const hashBytes = sha256(new TextEncoder().encode(address));
    const hex = toHex(hashBytes);
    const bigVal = BigInt(`0x${hex}`);
    const fieldVal = bigVal % PRIME;
    return '0x' + fieldVal.toString(16);
};

export const computeCommitment = (addressHash: string, saltHex: string): string => {
    // Poseidon PAIR hash: hades_permutation(addressHash, salt, 2)[0]
    // Matches backend PoseidonHash.hash_commitment() and Cairo hades_permutation(x, y, 2).
    // NOTE: computePoseidonHash(a, b) is the 2-input pair hash — NOT the sponge.
    return hash.computePoseidonHash(addressHash, saltHex);
};
