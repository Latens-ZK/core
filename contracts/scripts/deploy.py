"""
Deploy Latens contracts to Starknet Sepolia.
Uses starknet-py FullNodeClient (compatible with starknet-py 0.20+).
"""
import asyncio
import os
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


async def deploy():
    from starknet_py.net.full_node_client import FullNodeClient
    from starknet_py.net.account.account import Account
    from starknet_py.net.signer.stark_curve_signer import KeyPair
    from starknet_py.contract import Contract
    from starknet_py.net.models.chains import StarknetChainId
    from starknet_py.net.udc_deployer.deployer import Deployer

    private_key = os.getenv("STARKNET_PRIVATE_KEY")
    account_address = os.getenv("STARKNET_ACCOUNT_ADDRESS")

    if not private_key or not account_address:
        print("ERROR: Set STARKNET_PRIVATE_KEY and STARKNET_ACCOUNT_ADDRESS in .env")
        sys.exit(1)

    node_url = os.getenv("STARKNET_RPC_URL", "https://starknet-sepolia.public.blastapi.io")
    print(f"Connecting to Starknet Sepolia via {node_url}...")

    client = FullNodeClient(node_url=node_url)
    key_pair = KeyPair.from_private_key(int(private_key, 16))
    account = Account(
        client=client,
        address=int(account_address, 16),
        key_pair=key_pair,
        chain=StarknetChainId.SEPOLIA,
    )

    # Compiled artifacts path (run `scarb build` in contracts/ first)
    artifacts_dir = Path(__file__).parent.parent / "target" / "dev"
    if not artifacts_dir.exists():
        print(f"ERROR: Compiled artifacts not found at {artifacts_dir}")
        print("Run `scarb build` in the contracts/ directory first.")
        sys.exit(1)

    # ─── Deploy StateRootRegistry ──────────────────────────────────────────────
    print("\n[1/2] Deploying StateRootRegistry...")

    registry_class_file = artifacts_dir / "latens_contracts_StateRootRegistry.contract_class.json"
    registry_casm_file = artifacts_dir / "latens_contracts_StateRootRegistry.compiled_contract_class.json"

    with open(registry_class_file) as f:
        registry_class = json.load(f)
    with open(registry_casm_file) as f:
        registry_casm = json.load(f)

    declare_result = await Contract.declare_v3(
        account=account,
        compiled_contract=json.dumps(registry_class),
        compiled_contract_casm=json.dumps(registry_casm),
        auto_estimate=True,
    )
    await declare_result.wait_for_acceptance()
    print(f"  Declared StateRootRegistry: class_hash={hex(declare_result.class_hash)}")

    deploy_result = await declare_result.deploy_v1(
        constructor_args=[int(account_address, 16)],  # admin = deployer
        auto_estimate=True,
    )
    await deploy_result.wait_for_acceptance()
    registry_address = hex(deploy_result.deployed_contract.address)
    print(f"  Deployed StateRootRegistry: {registry_address}")

    # ─── Deploy BalanceVerifier ────────────────────────────────────────────────
    print("\n[2/2] Deploying BalanceVerifier...")

    verifier_class_file = artifacts_dir / "latens_contracts_BalanceVerifier.contract_class.json"
    verifier_casm_file = artifacts_dir / "latens_contracts_BalanceVerifier.compiled_contract_class.json"

    with open(verifier_class_file) as f:
        verifier_class = json.load(f)
    with open(verifier_casm_file) as f:
        verifier_casm = json.load(f)

    declare_result2 = await Contract.declare_v3(
        account=account,
        compiled_contract=json.dumps(verifier_class),
        compiled_contract_casm=json.dumps(verifier_casm),
        auto_estimate=True,
    )
    await declare_result2.wait_for_acceptance()
    print(f"  Declared BalanceVerifier: class_hash={hex(declare_result2.class_hash)}")

    deploy_result2 = await declare_result2.deploy_v1(
        constructor_args=[int(registry_address, 16)],  # ← pass registry address to verifier
        auto_estimate=True,
    )
    await deploy_result2.wait_for_acceptance()
    verifier_address = hex(deploy_result2.deployed_contract.address)
    print(f"  Deployed BalanceVerifier: {verifier_address}")

    # ─── Output ───────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("DEPLOYMENT COMPLETE")
    print("="*60)
    print(f"STATE_ROOT_REGISTRY_ADDRESS={registry_address}")
    print(f"BALANCE_VERIFIER_ADDRESS={verifier_address}")
    print("\nAdd these to your .env file and frontend/.env.local:")
    print(f"NEXT_PUBLIC_VERIFIER_ADDRESS={verifier_address}")
    print(f"NEXT_PUBLIC_REGISTRY_ADDRESS={registry_address}")
    print("="*60)

    # Auto-write to .env if it exists
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, 'a') as f:
            f.write(f"\n# Deployed {__import__('datetime').datetime.now().isoformat()}\n")
            f.write(f"STATE_ROOT_REGISTRY_ADDRESS={registry_address}\n")
            f.write(f"BALANCE_VERIFIER_ADDRESS={verifier_address}\n")
        print(f"\nAddresses appended to {env_path}")

    return registry_address, verifier_address


if __name__ == "__main__":
    asyncio.run(deploy())
