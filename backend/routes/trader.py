from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from web3 import Web3

from backend.config import load_addresses
from backend.web3_client import get_contract, send_tx

router = APIRouter(prefix="/api/trader", tags=["Trader"])


class CreateAgentRequest(BaseModel):
    name: str
    strategy_description: str       # Plain-English strategy (stored as hash)
    initial_supply: int = 1_000_000  # Tokens minted at creation (18-dec units)
    mgmt_fee_bps: int = 200          # Management fee in basis points (e.g. 200 = 2%)
    perf_fee_bps: int = 2000         # Performance fee in basis points (e.g. 2000 = 20%)
    min_investment: int = 1_000_000  # Minimum deposit in USDC micro-units (default: 1 USDC)
    max_drawdown_pct: int = 20       # RiskManager: max drawdown %
    max_position_pct: int = 10       # RiskManager: max single trade % of AUM
    trailing_stop_pct: int = 5       # RiskManager: trailing stop %
    trader_address: str
    private_key: str


class CreateAgentResponse(BaseModel):
    agent_index: int
    token_address: str
    vault_address: str
    name: str


@router.post("/create-agent", response_model=CreateAgentResponse)
def create_agent(req: CreateAgentRequest):
    addresses = load_addresses()
    factory = get_contract(addresses["AgentFactory"], "AgentFactory")
    risk_manager = get_contract(addresses["RiskManager"], "RiskManager")

    strategy_hash = Web3.keccak(text=req.strategy_description)
    initial_supply_wei = req.initial_supply * 10**18

    try:
        receipt = send_tx(
            factory.functions.deployAgent(
                req.name,
                strategy_hash,
                initial_supply_wei,
                req.mgmt_fee_bps,
                req.perf_fee_bps,
                req.min_investment,
            ),
            req.trader_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"deployAgent failed: {e}")

    # Read the AgentDeployed event to get addresses
    logs = factory.events.AgentDeployed().process_receipt(receipt)
    if not logs:
        raise HTTPException(status_code=500, detail="AgentDeployed event not found in receipt")

    event = logs[0]["args"]
    agent_index = event["index"]
    token_addr = event["tokenAddr"]
    vault_addr = event["vaultAddr"]

    # Set risk profile on behalf of trader
    try:
        send_tx(
            risk_manager.functions.setRiskProfile(
                vault_addr,
                req.max_drawdown_pct,
                req.max_position_pct,
                req.trailing_stop_pct,
            ),
            req.trader_address,
            req.private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"setRiskProfile failed: {e}")

    return CreateAgentResponse(
        agent_index=agent_index,
        token_address=token_addr,
        vault_address=vault_addr,
        name=req.name,
    )
