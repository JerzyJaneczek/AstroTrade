from fastapi import APIRouter, HTTPException
from web3 import Web3

from backend.config import load_addresses
from backend.web3_client import get_contract, get_w3

router = APIRouter(tags=["Chain"])


# Events to capture per contract: { contract_name: [event_name, ...] }
WATCHED_EVENTS = {
    "AgentFactory":      ["AgentDeployed"],
    "AgentMarketplace":  ["TokensListed", "TokensBought", "ListingCancelled",
                          "ProtocolFeeUpdated", "FeeRecipientUpdated"],
    "RiskManager":       ["RiskProfileSet", "AgentHalted", "AgentResumed"],
    "PerformanceOracle": ["SnapshotPushed", "ReporterUpdated"],
}

# Events on per-agent contracts — fetched via AgentFactory registry
VAULT_EVENTS  = ["Deposited", "WithdrawalRequested", "WithdrawalExecuted",
                 "TradeExecuted", "ProfitsSettled", "ExecutorUpdated"]


@router.get("/api/chain/logs")
def get_chain_logs():
    try:
        addresses = load_addresses()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    w3   = get_w3()
    logs = []

    # Infrastructure contracts
    for contract_name, event_names in WATCHED_EVENTS.items():
        contract = get_contract(addresses[contract_name], contract_name)
        for event_name in event_names:
            try:
                event_obj = getattr(contract.events, event_name)
                entries   = event_obj().get_logs(from_block=0)
                for e in entries:
                    logs.append(_format_log(e, contract_name, event_name, w3))
            except Exception:
                pass

    # Per-agent vault events (fetched for each deployed agent)
    factory = get_contract(addresses["AgentFactory"], "AgentFactory")
    count   = factory.functions.getAgentCount().call()
    for i in range(count):
        rec        = factory.functions.getAgent(i).call()
        agent_name = rec[0]
        vault_addr = rec[3]
        vault      = get_contract(vault_addr, "AgentVault")
        for event_name in VAULT_EVENTS:
            try:
                event_obj = getattr(vault.events, event_name)
                entries   = event_obj().get_logs(from_block=0)
                for e in entries:
                    label = f"AgentVault ({agent_name})"
                    logs.append(_format_log(e, label, event_name, w3))
            except Exception:
                pass

    logs.sort(key=lambda x: (x["block_number"], x["tx_index"]), reverse=True)
    return logs


def _format_log(entry, contract_name: str, event_name: str, w3) -> dict:
    args = dict(entry["args"])
    # Convert bytes/HexBytes to hex strings so they serialise cleanly
    clean_args = {}
    for k, v in args.items():
        if isinstance(v, (bytes, bytearray)):
            clean_args[k] = "0x" + v.hex()
        else:
            clean_args[k] = v

    return {
        "block_number": entry["blockNumber"],
        "tx_hash":      "0x" + entry["transactionHash"].hex(),
        "tx_index":     entry["transactionIndex"],
        "contract":     contract_name,
        "event":        event_name,
        "args":         clean_args,
    }


@router.get("/api/chain/state")
def get_chain_state():
    try:
        addresses = load_addresses()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    w3 = get_w3()
    block = w3.eth.get_block("latest")

    factory    = get_contract(addresses["AgentFactory"],      "AgentFactory")
    oracle     = get_contract(addresses["PerformanceOracle"], "PerformanceOracle")
    risk_mgr   = get_contract(addresses["RiskManager"],       "RiskManager")
    marketplace = get_contract(addresses["AgentMarketplace"], "AgentMarketplace")
    usdc       = get_contract(addresses["MockUSDC"],          "MockUSDC")

    # ── Agents ────────────────────────────────────────────────────────────────
    count = factory.functions.getAgentCount().call()
    agents = []
    for i in range(count):
        rec = factory.functions.getAgent(i).call()
        name, strategy_hash, token_addr, vault_addr, trader = rec

        token = get_contract(token_addr, "AgentToken")
        vault = get_contract(vault_addr, "AgentVault")

        total_supply        = token.functions.totalSupply().call()
        vault_token_holding = token.functions.balanceOf(vault_addr).call()
        circulating         = total_supply - vault_token_holding
        global_ppt          = token.functions.globalProfitPerToken().call()

        aum              = vault.functions.getAUM().call()
        last_settled_aum = vault.functions.lastSettledAUM().call()
        executor         = vault.functions.executor().call()
        mgmt_fee         = vault.functions.mgmtFeeBps().call()
        perf_fee         = vault.functions.perfFeeBps().call()
        min_investment   = vault.functions.minInvestment().call()

        rp      = risk_mgr.functions.profiles(vault_addr).call()
        halted  = risk_mgr.functions.isHalted(vault_addr).call()
        hwm     = risk_mgr.functions.highWaterMark(vault_addr).call()

        perf = None
        try:
            snap = oracle.functions.getLatest(vault_addr).call()
            perf = {
                "nav_per_token":        snap[0],
                "total_aum":            snap[1],
                "cumulative_return_bps": snap[2],
                "win_rate_bps":         snap[3],
                "sharpe_ratio":         snap[4],
                "timestamp":            snap[5],
            }
        except Exception:
            pass

        agents.append({
            "index":           i,
            "name":            name,
            "strategy_hash":   "0x" + strategy_hash.hex(),
            "token_address":   token_addr,
            "vault_address":   vault_addr,
            "trader":          trader,
            "token": {
                "total_supply":           total_supply,
                "vault_holding":          vault_token_holding,
                "circulating_supply":     circulating,
                "global_profit_per_token": global_ppt,
            },
            "vault": {
                "aum_usdc":          aum,
                "last_settled_aum":  last_settled_aum,
                "executor":          executor,
                "mgmt_fee_bps":      mgmt_fee,
                "perf_fee_bps":      perf_fee,
                "min_investment":    min_investment,
            },
            "risk": {
                "max_drawdown_pct":  rp[0],
                "max_position_pct":  rp[1],
                "trailing_stop_pct": rp[2],
                "trader":            rp[3],
                "halted":            halted,
                "high_water_mark":   hwm,
            },
            "performance": perf,
        })

    # ── Account balances ──────────────────────────────────────────────────────
    accounts = []
    for idx, acct in enumerate(HARDHAT_ACCOUNTS):
        addr = Web3.to_checksum_address(acct["address"])
        eth_bal  = w3.eth.get_balance(addr)
        usdc_bal = usdc.functions.balanceOf(addr).call()

        holdings = []
        for ag in agents:
            tok = get_contract(ag["token_address"], "AgentToken")
            bal     = tok.functions.balanceOf(addr).call()
            pending = tok.functions.pendingProfits(addr).call()
            holdings.append({
                "agent_name":      ag["name"],
                "token_address":   ag["token_address"],
                "balance":         bal,
                "pending_profits": pending,
            })

        accounts.append({
            "index":          idx,
            "address":        addr,
            "eth_balance":    eth_bal,
            "usdc_balance":   usdc_bal,
            "token_holdings": holdings,
        })

    # ── Marketplace listings ──────────────────────────────────────────────────
    mp_count = marketplace.functions.getListingCount().call()
    listings = []
    for i in range(mp_count):
        l = marketplace.functions.listings(i).call()
        listings.append({
            "id":              i,
            "seller":          l[0],
            "agent_token":     l[1],
            "amount":          l[2],
            "price_per_token": l[3],
            "active":          l[4],
        })

    return {
        "block_number": block["number"],
        "block_timestamp": block["timestamp"],
        "contracts": {
            "AgentFactory":       addresses["AgentFactory"],
            "AgentMarketplace":   addresses["AgentMarketplace"],
            "RiskManager":        addresses["RiskManager"],
            "PerformanceOracle":  addresses["PerformanceOracle"],
            "MockUSDC":           addresses["MockUSDC"],
        },
        "agents":               agents,
        "accounts":             accounts,
        "marketplace_listings": listings,
    }
