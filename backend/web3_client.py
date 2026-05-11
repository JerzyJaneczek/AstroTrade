import json
from pathlib import Path
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from backend.config import RPC_URL

BASE_DIR = Path(__file__).parent.parent
ABIS_DIR = BASE_DIR / "abis"

_w3: Web3 | None = None


def get_w3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(RPC_URL))
        _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if not _w3.is_connected():
            raise ConnectionError(f"Cannot connect to node at {RPC_URL}. Is `npx hardhat node` running?")
    return _w3


def load_abi(contract_name: str) -> list:
    path = ABIS_DIR / f"{contract_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"ABI not found: {path}. Run deploy.py first.")
    with open(path) as f:
        return json.load(f)


def get_contract(address: str, contract_name: str):
    w3 = get_w3()
    abi = load_abi(contract_name)
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def send_tx(fn, sender_address: str, private_key: str) -> dict:
    w3 = get_w3()
    sender = Web3.to_checksum_address(sender_address)
    nonce = w3.eth.get_transaction_count(sender)
    tx = fn.build_transaction({
        "from": sender,
        "nonce": nonce,
        "gas": 3_000_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt
