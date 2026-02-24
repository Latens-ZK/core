/**
 * deploy.mjs — Deploy Latens contracts to Starknet Sepolia
 *
 * Prerequisites:
 *   cd contracts/scripts && npm install
 *
 * Usage:
 *   node deploy.mjs
 *
 * Required .env (at repo root):
 *   STARKNET_PRIVATE_KEY=0x...
 *   STARKNET_ACCOUNT_ADDRESS=0x...
 *   STARKNET_RPC_URL=https://starknet-sepolia.public.blastapi.io  (default)
 *
 * Steps:
 *   1. Declare + deploy StateRootRegistry  (admin = deployer account)
 *   2. Declare + deploy BalanceVerifier    (registry = step-1 address)
 *   3. Call update_root with the demo snapshot Merkle root
 *   4. Declare + deploy DaoGate            (verifier = step-2 address, threshold = 1 BTC)
 *   5. Write all addresses back to root .env and frontend/.env.local
 */

import { RpcProvider, Account, hash } from 'starknet';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..', '..');
dotenv.config({ path: path.join(ROOT, '.env') });

// ─── Demo constants ───────────────────────────────────────────────────────────
// Merkle root is deterministic — produced by backend/scripts/seed_demo.py
const DEMO_MERKLE_ROOT  = '0x63667a469595c9063746e61290a8929ac9c152e9b0e7d1f76dd792b48d92b03';
const DEMO_BLOCK_HEIGHT = '800000';
// DAO membership threshold: 1 BTC = 100_000_000 satoshis
const DEMO_DAO_THRESHOLD = '100000000';

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function waitAndLog(provider, txHash, label) {
  process.stdout.write(`  Waiting for ${label} (${txHash.slice(0, 12)}…) `);
  const receipt = await provider.waitForTransaction(txHash);
  const status = receipt.finality_status ?? receipt.execution_status ?? 'confirmed';
  console.log(`→ ${status}`);
  return receipt;
}

async function declareOrSkip(account, provider, sierra, casm, name) {
  console.log(`\n  Declaring ${name}…`);
  try {
    const res = await account.declare({ contract: sierra, casm });
    await waitAndLog(provider, res.transaction_hash, `declare ${name}`);
    console.log(`  Class hash: ${res.class_hash}`);
    return res.class_hash;
  } catch (err) {
    const msg = err?.message ?? '';
    if (
      msg.includes('ClassAlreadyDeclared') ||
      msg.includes('already declared') ||
      msg.includes('DuplicateTx')
    ) {
      const classHash = hash.computeSierraContractClassHash(sierra);
      console.log(`  Already declared. Class hash: ${classHash}`);
      return classHash;
    }
    throw err;
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const privateKey    = process.env.STARKNET_PRIVATE_KEY;
  const accountAddress = process.env.STARKNET_ACCOUNT_ADDRESS;
  const rpcUrl        = process.env.STARKNET_RPC_URL || 'https://starknet-sepolia.public.blastapi.io';

  if (!privateKey || !accountAddress || privateKey === '0x...' || accountAddress === '0x...') {
    console.error('\nERROR: Missing credentials in .env\n');
    console.error('Set these in the repo root .env file:');
    console.error('  STARKNET_PRIVATE_KEY=0x<your-private-key>');
    console.error('  STARKNET_ACCOUNT_ADDRESS=0x<your-account-address>\n');
    console.error('How to get a Starknet Sepolia account:');
    console.error('  1. Install Argent X or Braavos browser wallet');
    console.error('  2. Switch to Starknet Sepolia testnet');
    console.error('  3. Deploy the account (small STRK/ETH required)');
    console.error('  4. Get testnet tokens from https://faucet.starknet.io');
    console.error('  5. Export private key from wallet settings');
    process.exit(1);
  }

  console.log('='.repeat(60));
  console.log('Latens — Contract Deployment to Starknet Sepolia');
  console.log('='.repeat(60));
  console.log(`RPC:     ${rpcUrl}`);
  console.log(`Account: ${accountAddress}`);

  const provider = new RpcProvider({ nodeUrl: rpcUrl });
  const account  = new Account(provider, accountAddress, privateKey);

  // ── Artifacts ────────────────────────────────────────────────────────────
  const artifactsDir = path.join(ROOT, 'contracts', 'target', 'dev');
  if (!fs.existsSync(artifactsDir)) {
    console.error(`\nERROR: Compiled artifacts not found at ${artifactsDir}`);
    console.error('Run:  cd contracts && scarb build');
    process.exit(1);
  }

  const load = name => JSON.parse(
    fs.readFileSync(path.join(artifactsDir, name), 'utf8')
  );

  const registrySierra = load('latens_contracts_StateRootRegistry.contract_class.json');
  const registryCasm   = load('latens_contracts_StateRootRegistry.compiled_contract_class.json');
  const verifierSierra = load('latens_contracts_BalanceVerifier.contract_class.json');
  const verifierCasm   = load('latens_contracts_BalanceVerifier.compiled_contract_class.json');
  const daoSierra      = load('latens_contracts_DaoGate.contract_class.json');
  const daoCasm        = load('latens_contracts_DaoGate.compiled_contract_class.json');

  // ── Step 1: StateRootRegistry ─────────────────────────────────────────────
  console.log('\n[1/5] StateRootRegistry');
  const registryClassHash = await declareOrSkip(account, provider, registrySierra, registryCasm, 'StateRootRegistry');

  console.log('  Deploying…');
  const deployReg = await account.deployContract({
    classHash: registryClassHash,
    constructorCalldata: [accountAddress], // admin = deployer
  });
  await waitAndLog(provider, deployReg.transaction_hash, 'deploy StateRootRegistry');
  const registryAddress = deployReg.contract_address;
  console.log(`  Address: ${registryAddress}`);

  // ── Step 2: BalanceVerifier ───────────────────────────────────────────────
  console.log('\n[2/5] BalanceVerifier');
  const verifierClassHash = await declareOrSkip(account, provider, verifierSierra, verifierCasm, 'BalanceVerifier');

  console.log('  Deploying…');
  const deployVer = await account.deployContract({
    classHash: verifierClassHash,
    constructorCalldata: [registryAddress],
  });
  await waitAndLog(provider, deployVer.transaction_hash, 'deploy BalanceVerifier');
  const verifierAddress = deployVer.contract_address;
  console.log(`  Address: ${verifierAddress}`);

  // ── Step 3: Register demo Merkle root ─────────────────────────────────────
  console.log('\n[3/5] Registering demo Merkle root…');
  console.log(`  Root:   ${DEMO_MERKLE_ROOT}`);
  console.log(`  Height: ${DEMO_BLOCK_HEIGHT}`);

  const updateTx = await account.execute([{
    contractAddress: registryAddress,
    entrypoint: 'update_root',
    calldata: [DEMO_MERKLE_ROOT, DEMO_BLOCK_HEIGHT],
  }]);
  await waitAndLog(provider, updateTx.transaction_hash, 'update_root');
  console.log(`  Root registered! TX: ${updateTx.transaction_hash}`);

  // ── Step 4: DaoGate ───────────────────────────────────────────────────────
  console.log(`\n[4/5] DaoGate  (threshold: ${DEMO_DAO_THRESHOLD} sats = 1 BTC)`);
  const daoClassHash = await declareOrSkip(account, provider, daoSierra, daoCasm, 'DaoGate');

  console.log('  Deploying…');
  const deployDao = await account.deployContract({
    classHash: daoClassHash,
    constructorCalldata: [verifierAddress, DEMO_DAO_THRESHOLD],
  });
  await waitAndLog(provider, deployDao.transaction_hash, 'deploy DaoGate');
  const daoAddress = deployDao.contract_address;
  console.log(`  Address: ${daoAddress}`);

  // ── Step 5: Persist addresses ─────────────────────────────────────────────
  console.log('\n[5/5] Updating .env…');
  const envPath = path.join(ROOT, '.env');
  let envContent = fs.readFileSync(envPath, 'utf8');

  const replacements = {
    STATE_ROOT_REGISTRY_ADDRESS: registryAddress,
    BALANCE_VERIFIER_ADDRESS:    verifierAddress,
    DAO_GATE_ADDRESS:            daoAddress,
    NEXT_PUBLIC_VERIFIER_ADDRESS: verifierAddress,
    NEXT_PUBLIC_REGISTRY_ADDRESS: registryAddress,
  };

  for (const [key, value] of Object.entries(replacements)) {
    const re = new RegExp(`${key}=.*`);
    if (re.test(envContent)) {
      envContent = envContent.replace(re, `${key}=${value}`);
    } else {
      envContent += `\n${key}=${value}`;
    }
  }
  fs.writeFileSync(envPath, envContent);
  console.log('  .env updated.');

  // Also write to frontend/.env.local
  const frontendEnv = path.join(ROOT, 'frontend', '.env.local');
  const frontendEnvContent = [
    `NEXT_PUBLIC_API_URL=${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'}`,
    `NEXT_PUBLIC_VERIFIER_ADDRESS=${verifierAddress}`,
    `NEXT_PUBLIC_REGISTRY_ADDRESS=${registryAddress}`,
  ].join('\n') + '\n';
  fs.writeFileSync(frontendEnv, frontendEnvContent);
  console.log('  frontend/.env.local updated.');

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log('\n' + '='.repeat(60));
  console.log('DEPLOYMENT COMPLETE ✓');
  console.log('='.repeat(60));
  console.log(`STATE_ROOT_REGISTRY_ADDRESS = ${registryAddress}`);
  console.log(`BALANCE_VERIFIER_ADDRESS    = ${verifierAddress}`);
  console.log(`DAO_GATE_ADDRESS            = ${daoAddress}`);
  console.log(`\nMerkle root registered:   ${DEMO_MERKLE_ROOT}`);
  console.log(`At block height:          ${DEMO_BLOCK_HEIGHT}`);
  console.log(`DAO membership threshold: 1 BTC (${DEMO_DAO_THRESHOLD} satoshis)`);
  console.log('\nNext: run  node verify_demo.mjs  to test on-chain proof verification.');
  console.log('='.repeat(60));
}

main().catch(err => {
  console.error('\nDeployment failed:', err?.message ?? err);
  process.exit(1);
});
