from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from web3 import Web3

from backend.config import load_addresses
from backend.web3_client import get_contract, send_tx, get_w3

router = APIRouter(tags=["Investor"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_agent_list() -> list[dict]:
    addresses = load_addresses()
    factory = get_contract(addresses["AgentFactory"], "AgentFactory")
    oracle = get_contract(addresses["PerformanceOracle"], "PerformanceOracle")

    count = factory.functions.getAgentCount().call()
    agents = []
    for i in range(count):
        record = factory.functions.getAgent(i).call()
        name, strategy_hash, token_addr, vault_addr, trader = record

        vault = get_contract(vault_addr, "AgentVault")
        aum = vault.functions.getAUM().call()

        perf = None
        try:
            snap = oracle.functions.getLatest(vault_addr).call()
            perf = {
                "nav_per_token": snap[0],
                "total_aum": snap[1],
                "cumulative_return_bps": snap[2],
                "win_rate_bps": snap[3],
                "sharpe_ratio": snap[4],
                "timestamp": snap[5],
            }
        except Exception:
            pass  # No snapshots yet — oracle reverts

        agents.append({
            "index": i,
            "name": name,
            "strategy_hash": "0x" + strategy_hash.hex(),
            "token_address": token_addr,
            "vault_address": vault_addr,
            "trader": trader,
            "aum_usdc": aum,
            "performance": perf,
        })
    return agents


# ── Agents ────────────────────────────────────────────────────────────────────

@router.get("/api/investor/agents")
def list_agents():
    return _get_agent_list()


# ── Portfolio ─────────────────────────────────────────────────────────────────

@router.get("/api/investor/portfolio")
def get_portfolio(address: str):
    addresses = load_addresses()
    factory = get_contract(addresses["AgentFactory"], "AgentFactory")
    count = factory.functions.getAgentCount().call()
    holder = Web3.to_checksum_address(address)

    holdings = []
    for i in range(count):
        record = factory.functions.getAgent(i).call()
        name, _strategy_hash, token_addr, vault_addr, _trader = record
        token = get_contract(token_addr, "AgentToken")
        balance = token.functions.balanceOf(holder).call()
        if balance > 0:
            pending = token.functions.pendingProfits(holder).call()
            holdings.append({
                "agent_index": i,
                "name": name,
                "token_address": token_addr,
                "vault_address": vault_addr,
                "balance": balance,
                "pending_profits_usdc": pending,
            })
    return holdings


# ── Deposit ───────────────────────────────────────────────────────────────────

class DepositRequest(BaseModel):
    vault_address: str
    usdc_amount: int        # In USDC micro-units (6 decimals, e.g. 1_000_000 = 1 USDC)
    investor_address: str
    private_key: str


@router.post("/api/investor/deposit")
def deposit(req: DepositRequest):
    addresses = load_addresses()
    usdc = get_contract(addresses["MockUSDC"], "MockUSDC")
    vault = get_contract(req.vault_address, "AgentVault")

    vault_cs = Web3.to_checksum_address(req.vault_address)

    # Approve vault to spend USDC
    try:
        send_tx(
            usdc.functions.approve(vault_cs, req.usdc_amount),
            req.investor_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"USDC approve failed: {e}")

    # Deposit into vault
    try:
        token_before = _token_balance(vault, req.investor_address)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read token balance before deposit: {e}")

    try:
        receipt = send_tx(
            vault.functions.deposit(req.usdc_amount),
            req.investor_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"deposit failed: {e}")

    try:
        token_after = _token_balance(vault, req.investor_address)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read token balance after deposit: {e}")

    return {
        "tx_hash": "0x" + "0x" + receipt["transactionHash"].hex(),
        "usdc_deposited": req.usdc_amount,
        "tokens_received": token_after - token_before,
    }


def _token_balance(vault_contract, investor_address: str) -> int:
    token_addr = vault_contract.functions.agentToken().call()
    w3 = get_w3()
    token_addr = Web3.to_checksum_address(token_addr)
    token = get_contract(token_addr, "AgentToken")
    return token.functions.balanceOf(Web3.to_checksum_address(investor_address)).call()


# ── Withdrawal ────────────────────────────────────────────────────────────────

class WithdrawalRequest(BaseModel):
    vault_address: str
    investor_address: str
    private_key: str


@router.post("/api/investor/request-withdrawal")
def request_withdrawal(req: WithdrawalRequest):
    vault = get_contract(req.vault_address, "AgentVault")
    try:
        receipt = send_tx(
            vault.functions.requestWithdrawal(),
            req.investor_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"requestWithdrawal failed: {e}")
    cooldown_secs = vault.functions.COOLDOWN().call()
    return {
        "tx_hash": "0x" + receipt["transactionHash"].hex(),
        "message": f"Withdrawal cooldown started. Execute after {cooldown_secs // 3600}h.",
    }


@router.post("/api/investor/execute-withdrawal")
def execute_withdrawal(req: WithdrawalRequest):
    addresses = load_addresses()
    vault = get_contract(req.vault_address, "AgentVault")
    token_addr = vault.functions.agentToken().call()
    token = get_contract(token_addr, "AgentToken")

    # Investor must approve vault to pull their tokens back
    try:
        token_balance = token.functions.balanceOf(
            Web3.to_checksum_address(req.investor_address)
        ).call()
        send_tx(
            token.functions.approve(
                Web3.to_checksum_address(req.vault_address), token_balance
            ),
            req.investor_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token approve failed: {e}")

    try:
        receipt = send_tx(
            vault.functions.executeWithdrawal(),
            req.investor_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"executeWithdrawal failed: {e}")

    return {"tx_hash": "0x" + receipt["transactionHash"].hex()}


# ── Marketplace ───────────────────────────────────────────────────────────────

class ListRequest(BaseModel):
    agent_token_address: str
    amount: int             # Agent token amount (18 decimals)
    price_per_token: int    # USDC per token (6 decimals per 1e18 tokens)
    seller_address: str
    private_key: str


@router.post("/api/marketplace/list")
def list_tokens(req: ListRequest):
    addresses = load_addresses()
    mp_addr = addresses["AgentMarketplace"]
    token = get_contract(req.agent_token_address, "AgentToken")
    marketplace = get_contract(mp_addr, "AgentMarketplace")

    # Approve marketplace to pull tokens
    try:
        send_tx(
            token.functions.approve(Web3.to_checksum_address(mp_addr), req.amount),
            req.seller_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token approve failed: {e}")

    try:
        receipt = send_tx(
            marketplace.functions.listTokens(
                Web3.to_checksum_address(req.agent_token_address),
                req.amount,
                req.price_per_token,
            ),
            req.seller_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"listTokens failed: {e}")

    logs = marketplace.events.TokensListed().process_receipt(receipt)
    listing_id = logs[0]["args"]["listingId"] if logs else None
    return {"tx_hash": "0x" + receipt["transactionHash"].hex(), "listing_id": listing_id}


class BuyRequest(BaseModel):
    listing_id: int
    amount: int             # Agent token amount to buy (18 decimals)
    buyer_address: str
    private_key: str


@router.post("/api/marketplace/buy")
def buy_tokens(req: BuyRequest):
    addresses = load_addresses()
    mp_addr = addresses["AgentMarketplace"]
    usdc = get_contract(addresses["MockUSDC"], "MockUSDC")
    marketplace = get_contract(mp_addr, "AgentMarketplace")

    listing = marketplace.functions.listings(req.listing_id).call()
    price_per_token = listing[3]  # pricePerToken
    total_cost = (req.amount * price_per_token) // 10**18

    # Approve USDC to marketplace (cost + fee buffer)
    fee_bps = marketplace.functions.feeBps().call()
    total_with_fee = total_cost + (total_cost * fee_bps) // 10000

    try:
        send_tx(
            usdc.functions.approve(Web3.to_checksum_address(mp_addr), total_with_fee),
            req.buyer_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"USDC approve failed: {e}")

    try:
        receipt = send_tx(
            marketplace.functions.buyTokens(req.listing_id, req.amount),
            req.buyer_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"buyTokens failed: {e}")

    return {"tx_hash": "0x" + receipt["transactionHash"].hex(), "usdc_spent": total_cost}


class CancelRequest(BaseModel):
    listing_id: int
    seller_address: str
    private_key: str


@router.post("/api/marketplace/cancel")
def cancel_listing(req: CancelRequest):
    addresses = load_addresses()
    marketplace = get_contract(addresses["AgentMarketplace"], "AgentMarketplace")
    try:
        receipt = send_tx(
            marketplace.functions.cancelListing(req.listing_id),
            req.seller_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"cancelListing failed: {e}")
    return {"tx_hash": "0x" + receipt["transactionHash"].hex()}


@router.get("/api/marketplace/listings")
def get_listings():
    addresses = load_addresses()
    marketplace = get_contract(addresses["AgentMarketplace"], "AgentMarketplace")
    count = marketplace.functions.getListingCount().call()
    result = []
    for i in range(count):
        l = marketplace.functions.listings(i).call()
        result.append({
            "listing_id": i,
            "seller": l[0],
            "agent_token": l[1],
            "amount": l[2],
            "price_per_token": l[3],
            "active": l[4],
        })
    return result
