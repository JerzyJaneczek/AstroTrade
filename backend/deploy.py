"""
Deploy all AstroTrade contracts to a local Hardhat node.

Usage:
    poetry run python backend/deploy.py

Prerequisites:
    npx hardhat node   (running in a separate terminal)
    npx hardhat compile
"""

import json
import shutil
from pathlib import Path
from web3 import Web3

BASE_DIR = Path(__file__).parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts" / "contracts"
ABIS_DIR = BASE_DIR / "abis"
ADDRESSES_FILE = BASE_DIR / "addresses.json"

RPC_URL = "http://127.0.0.1:8545"

# Hardhat default account #0
DEPLOYER_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

# Test accounts that receive minted USDC
TEST_ACCOUNTS = [
    "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
    "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
]

INITIAL_USDC = 1_000_000 * 10**6  # 1,000,000 USDC each


def load_artifact(contract_path: str, contract_name: str) -> dict:
    path = ARTIFACTS_DIR / contract_path / f"{contract_name}.json"
    with open(path) as f:
        return json.load(f)


def copy_abis():
    ABIS_DIR.mkdir(exist_ok=True)
    for artifact_file in ARTIFACTS_DIR.rglob("*.json"):
        if artifact_file.name.endswith(".dbg.json"):
            continue
        artifact = json.loads(artifact_file.read_text())
        if "abi" not in artifact:
            continue
        dest = ABIS_DIR / f"{artifact_file.stem}.json"
        dest.write_text(json.dumps(artifact["abi"], indent=2))
    print(f"  ABIs copied to {ABIS_DIR}/")


def deploy_contract(w3: Web3, artifact: dict, constructor_args: list, deployer: str, key: str) -> str:
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    nonce = w3.eth.get_transaction_count(deployer)
    tx = contract.constructor(*constructor_args).build_transaction({
        "from": deployer,
        "nonce": nonce,
        "gas": 5_000_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key=key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.contractAddress


def call_fn(w3: Web3, fn, sender: str, key: str):
    nonce = w3.eth.get_transaction_count(sender)
    tx = fn.build_transaction({
        "from": sender,
        "nonce": nonce,
        "gas": 3_000_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key=key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)


def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    assert w3.is_connected(), "Cannot connect to Hardhat node. Run `npx hardhat node` first."
    deployer = Web3.to_checksum_address(DEPLOYER_ADDRESS)
    print(f"Deployer: {deployer}")
    print(f"Balance:  {w3.from_wei(w3.eth.get_balance(deployer), 'ether')} ETH\n")

    # Copy ABIs from artifacts
    print("Copying ABIs...")
    copy_abis()

    # 1. MockUSDC
    print("Deploying MockUSDC...")
    usdc_artifact = load_artifact("mocks/MockUSDC.sol", "MockUSDC")
    usdc_addr = deploy_contract(w3, usdc_artifact, [], deployer, DEPLOYER_KEY)
    print(f"  MockUSDC:            {usdc_addr}")

    usdc = w3.eth.contract(address=usdc_addr, abi=usdc_artifact["abi"])

    # Mint USDC to deployer + test accounts
    for account in [deployer] + [Web3.to_checksum_address(a) for a in TEST_ACCOUNTS]:
        call_fn(w3, usdc.functions.mint(account, INITIAL_USDC), deployer, DEPLOYER_KEY)
    print(f"  Minted {INITIAL_USDC // 10**6:,} USDC to {1 + len(TEST_ACCOUNTS)} accounts")

    # 2. RiskManager
    print("Deploying RiskManager...")
    rm_artifact = load_artifact("RiskManager.sol", "RiskManager")
    rm_addr = deploy_contract(w3, rm_artifact, [], deployer, DEPLOYER_KEY)
    print(f"  RiskManager:         {rm_addr}")

    # 3. PerformanceOracle
    print("Deploying PerformanceOracle...")
    oracle_artifact = load_artifact("PerformanceOracle.sol", "PerformanceOracle")
    oracle_addr = deploy_contract(w3, oracle_artifact, [], deployer, DEPLOYER_KEY)
    print(f"  PerformanceOracle:   {oracle_addr}")

    oracle = w3.eth.contract(address=oracle_addr, abi=oracle_artifact["abi"])
    call_fn(w3, oracle.functions.setReporter(deployer), deployer, DEPLOYER_KEY)
    print(f"  Reporter set to deployer")

    # 4. AgentMarketplace
    print("Deploying AgentMarketplace...")
    mp_artifact = load_artifact("AgentMarketplace.sol", "AgentMarketplace")
    mp_addr = deploy_contract(w3, mp_artifact, [usdc_addr, 50, deployer], deployer, DEPLOYER_KEY)
    print(f"  AgentMarketplace:    {mp_addr}")

    # 5. AgentFactory
    print("Deploying AgentFactory...")
    factory_artifact = load_artifact("AgentFactory.sol", "AgentFactory")
    factory_addr = deploy_contract(w3, factory_artifact, [rm_addr, oracle_addr, usdc_addr], deployer, DEPLOYER_KEY)
    print(f"  AgentFactory:        {factory_addr}")

    # Save all addresses
    addresses = {
        "MockUSDC": usdc_addr,
        "RiskManager": rm_addr,
        "PerformanceOracle": oracle_addr,
        "AgentMarketplace": mp_addr,
        "AgentFactory": factory_addr,
    }
    ADDRESSES_FILE.write_text(json.dumps(addresses, indent=2))
    print(f"\nAddresses saved to {ADDRESSES_FILE}")
    print("\nDeployment complete. Start the API with:")
    print("  poetry run uvicorn backend.main:app --reload")


if __name__ == "__main__":
    main()
