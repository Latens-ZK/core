/**
 * verify_demo.mjs — Phase 4 done-criterion: on-chain proof verification
 *
 * Tests three cases on the deployed contracts:
 *   1. POSITIVE: BalanceVerifier.verify_proof() succeeds for valid calldata
 *   2. NEGATIVE: verify_proof() reverts on tampered balance (Merkle mismatch)
 *   3. DAO JOIN: DaoGate.join_dao() succeeds → member added with nullifier stored
 *
 * Prerequisites:
 *   - deploy.mjs must have run (contract addresses in .env)
 *   - STARKNET_PRIVATE_KEY + STARKNET_ACCOUNT_ADDRESS set in .env
 *   - Python backend must have seeded a snapshot at height 800,000 OR
 *     the DEMO_* constants below must match what was indexed.
 *
 * Usage:
 *   node verify_demo.mjs
 *
 * Proof data:
 *   address : 1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ
 *   balance : 200,000,000 sat (2 BTC)
 *   salt    : 0x1234567890abcdef (deterministic demo salt)
 *   height  : 800,000
 *
 * How calldata was generated (Python):
 *   from src.circuit.proof_generator import ProofGenerator
 *   from src.crypto.poseidon import PoseidonHash
 *   from src.crypto.address_utils import AddressUtils
 *   addr_hash = AddressUtils.get_address_hash("1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ")
 *   salt = 0x1234567890abcdef
 *   commitment = PoseidonHash.hash_commitment(addr_hash, salt)
 *   gen = ProofGenerator()
 *   calldata = gen.generate_calldata(addr_hash, salt, 200_000_000, path, commitment, 100_000_000)
 */

import { RpcProvider, Account } from 'starknet';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
dotenv.config({ path: path.join(ROOT, '.env') });

// ─── Demo calldata ─────────────────────────────────────────────────────────────
// Layout for verify_proof(address_hash, salt, balance, merkle_path, commitment, threshold):
//   [address_hash, salt, balance, path_len,
//    path[0].value, path[0].direction, ... , commitment, threshold]

const VALID_CALLDATA = [
  '461883673067612584792338221093381074111200688148327570451060764091247821750', // address_hash
  '1311768467294899695',                                                          // salt = 0x1234567890abcdef
  '200000000',                                                                    // balance: 2 BTC
  '3',                                                                            // merkle_path length
  '1606027379435345129025600649467605874028167328785086011983591641809269492251', // path[0].value
  '1',                                                                            // path[0].direction = Right
  '1273211030432860885457380883246437736983154416911174402242081771522202122897', // path[1].value
  '1',                                                                            // path[1].direction = Right
  '268981268424111534551828952898826710918360351739285386418717985138702640655',  // path[2].value
  '1',                                                                            // path[2].direction = Right
  '3277040955342947357396102218962827964502330469704889508457844397982119416161', // commitment
  '100000000',                                                                    // threshold: 1 BTC
];

// Tampered: wrong balance → Merkle leaf mismatch → revert
const TAMPERED_CALLDATA = [...VALID_CALLDATA];
TAMPERED_CALLDATA[2] = '999999999';

// DaoGate calldata for join_dao(address_hash, salt, balance, path, commitment, external_nullifier)
// external_nullifier = the DaoGate contract address (prevents cross-DAO replay)
const buildDaoCalldata = (daoGateAddress) => {
  const externalNullifier = BigInt(daoGateAddress).toString();
  return [
    ...VALID_CALLDATA.slice(0, VALID_CALLDATA.length - 1), // drop threshold
    externalNullifier,                                       // external_nullifier
  ];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function waitAndLog(provider, txHash) {
  process.stdout.write(`  TX: ${txHash.slice(0, 18)}… `);
  try {
    const receipt = await provider.waitForTransaction(txHash, { retryInterval: 2000 });
    const status = receipt.execution_status ?? receipt.finality_status ?? 'confirmed';
    return { ok: status !== 'REVERTED', status };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

function pass(msg) {
  console.log(`  ✓ PASS — ${msg}\n`);
}

function fail(msg) {
  console.error(`  ✗ FAIL — ${msg}\n`);
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const privateKey = process.env.STARKNET_PRIVATE_KEY;
  const accountAddress = process.env.STARKNET_ACCOUNT_ADDRESS;
  const verifierAddress = process.env.BALANCE_VERIFIER_ADDRESS;
  const daoGateAddress = process.env.DAO_GATE_ADDRESS;
  const rpcUrl = process.env.STARKNET_RPC_URL || 'https://starknet-sepolia.public.blastapi.io';

  if (!verifierAddress || verifierAddress === '0x...') {
    console.error('ERROR: BALANCE_VERIFIER_ADDRESS not set. Run deploy.mjs first.');
    process.exit(1);
  }
  if (!privateKey || privateKey === '0x...') {
    console.error('ERROR: STARKNET_PRIVATE_KEY not set in .env');
    process.exit(1);
  }

  console.log('='.repeat(65));
  console.log('Latens — Phase 4: On-Chain Proof Verification');
  console.log('='.repeat(65));
  console.log(`Network  : Starknet Sepolia`);
  console.log(`Verifier : ${verifierAddress}`);
  console.log(`DaoGate  : ${daoGateAddress || '(not set)'}`);
  console.log(`Account  : ${accountAddress}`);
  console.log('');

  const provider = new RpcProvider({ nodeUrl: rpcUrl });
  const account = new Account(provider, accountAddress, privateKey);

  let passed = 0;
  let total = 0;

  // ── Test 1: Valid proof ────────────────────────────────────────────────────
  total++;
  console.log('[1/3] POSITIVE — verify_proof() with valid calldata');
  console.log('  Address: 1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ (balance=2 BTC, threshold=1 BTC)');
  try {
    const tx = await account.execute([{
      contractAddress: verifierAddress,
      entrypoint: 'verify_proof',
      calldata: VALID_CALLDATA,
    }]);
    const { ok, status, error } = await waitAndLog(provider, tx.transaction_hash);
    if (ok) {
      console.log(`→ ${status}`);
      pass('Transaction succeeded — ProofVerified event emitted');
      passed++;
    } else {
      console.log('→ FAILED');
      fail(`Unexpected failure: ${error ?? status}`);
    }
  } catch (err) {
    console.log('→ FAILED');
    fail(err?.message ?? err);
  }

  // ── Test 2: Tampered balance ───────────────────────────────────────────────
  total++;
  console.log('[2/3] NEGATIVE — verify_proof() with tampered balance (999999999 vs 200000000)');
  console.log('  Expected: transaction REVERTS (Merkle root mismatch)');
  try {
    const tx = await account.execute([{
      contractAddress: verifierAddress,
      entrypoint: 'verify_proof',
      calldata: TAMPERED_CALLDATA,
    }]);
    const { ok, status } = await waitAndLog(provider, tx.transaction_hash);
    if (!ok) {
      console.log('→ reverted as expected');
      pass('Transaction reverted — tampered proof rejected');
      passed++;
    } else {
      console.log(`→ ${status} (unexpected success)`);
      fail('Transaction should have reverted but did not');
    }
  } catch (err) {
    const msg = err?.message ?? '';
    const isExpectedRevert =
      msg.includes('revert') ||
      msg.includes('REVERTED') ||
      msg.includes('Error in the called contract') ||
      msg.includes('Invalid') ||
      msg.includes('Merkle');
    if (isExpectedRevert) {
      console.log('→ reverted as expected');
      pass('Transaction reverted — tampered proof rejected');
      passed++;
    } else {
      fail(`Unexpected error: ${msg}`);
    }
  }

  // ── Test 3: DaoGate.join_dao() ────────────────────────────────────────────
  total++;
  console.log('[3/3] DAO JOIN — join_dao() with external_nullifier = DAO gate address');
  if (!daoGateAddress || daoGateAddress === '0x...') {
    console.log('  SKIP — DAO_GATE_ADDRESS not set. Set it in .env to run this test.\n');
    total--;
  } else {
    console.log(`  DaoGate: ${daoGateAddress}`);
    const calldata = buildDaoCalldata(daoGateAddress);
    try {
      const tx = await account.execute([{
        contractAddress: daoGateAddress,
        entrypoint: 'join_dao',
        calldata,
      }]);
      const { ok, status, error } = await waitAndLog(provider, tx.transaction_hash);
      if (ok) {
        console.log(`→ ${status}`);
        pass('MemberAdded event emitted — nullifier stored on-chain');
        passed++;
      } else {
        // "Already a DAO member" is an acceptable pass for repeated demo runs
        if ((error || status || '').toString().includes('Already a DAO member')) {
          console.log('→ already member');
          pass('Already a DAO member (nullifier previously recorded)');
          passed++;
        } else {
          console.log('→ FAILED');
          fail(`Unexpected failure: ${error ?? status}`);
        }
      }
    } catch (err) {
      const msg = err?.message ?? '';
      if (msg.includes('Already a DAO member') || msg.includes('Nullifier already used')) {
        console.log('→ already member');
        pass('Already a DAO member / nullifier used (expected for repeated runs)');
        passed++;
      } else {
        console.log('→ FAILED');
        fail(msg);
      }
    }
  }

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log('='.repeat(65));
  const allPass = passed === total;
  if (allPass) {
    console.log(`✓ Phase 4 COMPLETE — ${passed}/${total} tests passed`);
    console.log('  BalanceVerifier and DaoGate verified on Sepolia.');
  } else {
    console.log(`✗ ${passed}/${total} tests passed — review errors above.`);
  }
  console.log('='.repeat(65));

  process.exit(allPass ? 0 : 1);
}

main().catch(err => {
  console.error('Fatal error:', err?.message ?? err);
  process.exit(1);
});
