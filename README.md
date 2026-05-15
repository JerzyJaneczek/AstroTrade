# AstroTrade — No Code Launchpad for Tokenised AI Trading Agents

A platform where traders create AI trading agents from plain English strategies and investors buy/sell tokenised shares in those agents.

Work division can be found in **each what was built table**

---

## What Was Built

**6 Solidity contracts** (Hardhat, OpenZeppelin, Solidity 0.8.24):

| Contract | Description | Who built |
|---|---|---|
| `MockUSDC.sol` | Mintable ERC-20 used as USDC on the local test network | Jerzy |
| `AgentToken.sol` | ERC-20 per agent with a per-token profit accumulator for profit sharing | Jerzy |
| `AgentVault.sol` | Holds USDC deposits (1 USDC = 1 token), enforces withdrawal cooldown, settles profits | Jerzy |
| `AgentFactory.sol` | Deploys Token + Vault pairs on demand and maintains an on-chain registry | Jerzy |
| `RiskManager.sol` | Stores risk profiles per vault, validates trades, supports halt/resume | Hitesh |
| `PerformanceOracle.sol` | Stores NAV and return snapshots pushed by the backend reporter | Hitesh |
| `AgentMarketplace.sol` | Fixed-price secondary market for buying and selling agent tokens | Hitesh |

**Python backend** (FastAPI + web3py, managed by Poetry):

| File | Description | Who built |
|---|---|---|
| `backend/deploy.py` | One-shot deployment script — deploys all contracts and writes `addresses.json` | Jerzy |
| `backend/web3_client.py` | Web3 connection, ABI loader, `send_tx` helper | Hitesh |
| `backend/routes/trader.py` | `POST /api/trader/create-agent` | Hitesh |
| `backend/routes/investor.py` | `GET /api/investor/agents`, deposit, withdrawal, marketplace buy/sell/cancel | Hitesh |

---

## How to Run End-to-End

**Prerequisites:** Node.js, npm, Python 3.12+, Poetry

### 1. Install dependencies

```bash
npm install
poetry install
```

### 2. Compile the contracts

```bash
npx hardhat compile
```

### 3. Start the local blockchain (keep this terminal open)

```bash
npx hardhat node
```

### 4. Deploy contracts (new terminal)

```bash
poetry run python backend/deploy.py
```

This deploys all contracts, mints test USDC to the Hardhat default accounts, and writes `addresses.json`.

### 5. Start the API server (new terminal)

```bash
poetry run uvicorn backend.main:app --reload
```

Interactive API docs available at **http://localhost:8000/docs**

---

### Trader flow — create an agent

```bash
curl -X POST http://localhost:8000/api/trader/create-agent \
  -H "Content-Type: application/json" \
  -d '{
    "name": "BTC RSI Bot",
    "strategy_description": "Buy BTC when RSI < 40 with a 10% trailing stop loss",
    "trader_address": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    "private_key": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
  }'
# Returns: { agent_index, token_address, vault_address, name }
```

### Investor flow — browse agents

```bash
curl http://localhost:8000/api/investor/agents
# Returns list of all agents with AUM and latest performance snapshot
```

### Investor flow — deposit into an agent

```bash
curl -X POST http://localhost:8000/api/investor/deposit \
  -H "Content-Type: application/json" \
  -d '{
    "vault_address": "0xCBd5431cC04031d089c90E7c83288183A6Fe545d",
    "usdc_amount": 1000000,
    "investor_address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "private_key": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
  }'
# Returns: { tx_hash, usdc_deposited, tokens_received }
```

### Investor flow — list and buy tokens on the marketplace

```bash
# List tokens for sale
curl -X POST http://localhost:8000/api/marketplace/list \
  -H "Content-Type: application/json" \
  -d '{
    "agent_token_address": "<token_address>",
    "amount": 500000000000000000000,
    "price_per_token": 1000000,
    "seller_address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "private_key": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
  }'

# Buy from a listing
curl -X POST http://localhost:8000/api/marketplace/buy \
  -H "Content-Type: application/json" \
  -d '{
    "listing_id": 0,
    "amount": 500000000000000000000,
    "buyer_address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    "private_key": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
  }'
```

> **Note:** All private keys above are the well-known Hardhat default test accounts. Never use real private keys here.

---

## Tests

56 tests across 8 files, written with Hardhat + Chai. Run with:

```bash
npm test
```

| File | Tests | What's covered |
|---|---|---|
| `MockUSDC.test.js` | 5 | Decimals, minting, ERC-20 transfer and approve |
| `RiskManager.test.js` | 8 | Profile storage, trade validation, halt/resume access control, high-water mark |
| `PerformanceOracle.test.js` | 8 | Reporter access control, snapshot fields, `getLatest`, `getHistory` range queries |
| `AgentToken.test.js` | 8 | Initial mint, vault-only snapshot, proportional profit math, claim/reset, transfer checkpoint isolation |
| `AgentVault.test.js` | 8 | Deposit scaling, withdrawal cooldown flow, executor/halt guards, profit settlement |
| `AgentFactory.test.js` | 8 | Full deploy pipeline, agent registry, vault-token wiring, symbol derivation |
| `AgentMarketplace.test.js` | 8 | Listing, buy (with fee split), partial buy, cancel, access control |
| `Gas.test.js` | 3 | Gas regression guards for `deployAgent`, `deposit`, and `settleProfits` |

---

## Smart Contract Function Outlines

---

## 1. AgentFactory.sol

| Function | Visibility | Description |
|---|---|---|
| `deployAgent(name, strategyHash, supply, mgmtFee, perfFee, minInvestment)` | external | Deploys a new AgentToken + AgentVault pair and registers them |
| `getAgent(index)` | external view | Returns the token and vault addresses for a given agent index |
| `getAgentCount()` | external view | Returns total number of deployed agents |

---

## 2. AgentToken.sol (ERC-20)

| Function | Visibility | Description |
|---|---|---|
| `transfer(to, amount)` | external | Standard ERC-20 transfer |
| `approve(spender, amount)` | external | Standard ERC-20 approval |
| `claimProfits()` | external | Sends caller their pending profit share in USDC |
| `pendingProfits(holder)` | external view | Returns unclaimed profit balance for a given address |
| `pushProfitSnapshot(amountPerToken)` | external (onlyVault) | Called by the vault to record a new profit distribution |

---

## 3. AgentVault.sol

| Function | Visibility | Description |
|---|---|---|
| `deposit(usdcAmount)` | external | Accepts USDC from investor, mints AgentTokens pro-rata |
| `requestWithdrawal()` | external | Starts the withdrawal cooldown timer for the caller |
| `executeWithdrawal()` | external | Redeems caller's tokens for USDC after cooldown has elapsed |
| `executeTrade(dexRouter, swapCalldata, maxSlippage)` | external (onlyExecutor) | Submits a trade to a DEX on behalf of the agent |
| `settleProfits()` | external | Calculates period profit, deducts fees, pushes snapshot to AgentToken |
| `getAUM()` | external view | Returns total USDC value held in the vault |
| `setExecutor(address)` | external (onlyOwner) | Updates the whitelisted backend executor address |

---

## 4. RiskManager.sol

| Function | Visibility | Description |
|---|---|---|
| `setRiskProfile(vault, maxDrawdown, maxPosition, trailingStop)` | external (onlyTrader) | Sets risk parameters for a given vault at deploy time |
| `validateTrade(vault, tradeSize, currentAUM)` | external view | Reverts if the proposed trade violates any risk rule |
| `updateHighWaterMark(vault, newNAV)` | external (onlyVault) | Updates the high-water mark after a profitable period |
| `haltAgent(vault)` | external | Pauses all trade execution for the agent |
| `resumeAgent(vault)` | external (onlyTrader) | Re-enables trade execution after a halt |
| `isHalted(vault)` | external view | Returns whether the agent is currently halted |

---

## 5. PerformanceOracle.sol

| Function | Visibility | Description |
|---|---|---|
| `pushSnapshot(vault, navPerToken, totalAUM, cumulativeReturn, winRate, sharpeRatio)` | external (onlyReporter) | Records a new performance snapshot for a vault |
| `getLatest(vault)` | external view | Returns the most recent performance record |
| `getHistory(vault, from, to)` | external view | Returns a slice of historical performance records |
| `setReporter(address)` | external (onlyOwner) | Updates the whitelisted backend reporter address |

---

## 6. AgentMarketplace.sol

| Function | Visibility | Description |
|---|---|---|
| `listTokens(agentToken, amount, pricePerToken)` | external | Creates a listing to sell agent tokens at a fixed price |
| `buyTokens(agentToken, listingId, amount)` | external | Purchases agent tokens from an existing listing |
| `cancelListing(agentToken, listingId)` | external | Removes the caller's active listing and returns tokens |
| `setProtocolFee(bps)` | external (onlyOwner) | Updates the protocol fee taken on each trade |
| `setFeeRecipient(address)` | external (onlyOwner) | Updates the address that receives protocol fees |
