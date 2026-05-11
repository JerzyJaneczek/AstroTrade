import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")

# Hardhat default accounts (well-known test keys — never use in production)
HARDHAT_ACCOUNTS = [
    {
        "address": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "private_key": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    },
    {
        "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "private_key": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    },
    {
        "address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "private_key": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    },
    {
        "address": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
        "private_key": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    },
    {
        "address": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
        "private_key": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926b",
    },
]

DEPLOYER = HARDHAT_ACCOUNTS[0]

_addresses_file = BASE_DIR / "addresses.json"


def load_addresses() -> dict:
    if not _addresses_file.exists():
        raise FileNotFoundError(
            "addresses.json not found. Run `poetry run python backend/deploy.py` first."
        )
    with open(_addresses_file) as f:
        return json.load(f)
