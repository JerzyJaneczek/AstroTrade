// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./AgentToken.sol";
import "./RiskManager.sol";

contract AgentVault {
    IERC20 public immutable usdc;
    RiskManager public immutable riskManager;

    AgentToken public agentToken;
    bool private tokenSet;

    address public owner;
    address public executor;
    address public trader;

    uint256 public mgmtFeeBps;
    uint256 public perfFeeBps;
    uint256 public minInvestment;

    uint256 public lastSettledAUM;
    uint256 public constant COOLDOWN = 1 days;

    // 1 USDC (6 dec) = 1 token (18 dec): scale factor = 1e12
    uint256 private constant SCALE = 1e12;

    mapping(address => uint256) public withdrawalRequestTime;

    event Deposited(address indexed investor, uint256 usdcAmount, uint256 tokensMinted);
    event WithdrawalRequested(address indexed investor, uint256 readyAt);
    event WithdrawalExecuted(address indexed investor, uint256 usdcAmount, uint256 tokensBurned);
    event TradeExecuted(address indexed dexRouter, bytes callData, uint256 maxSlippage);
    event ProfitsSettled(uint256 profitAmount, uint256 amountPerToken);
    event ExecutorUpdated(address indexed executor);

    modifier onlyOwner() {
        require(msg.sender == owner, "AgentVault: caller is not owner");
        _;
    }

    modifier onlyExecutor() {
        require(msg.sender == executor, "AgentVault: caller is not executor");
        _;
    }

    constructor(
        address usdc_,
        address riskManager_,
        address trader_,
        uint256 mgmtFeeBps_,
        uint256 perfFeeBps_,
        uint256 minInvestment_
    ) {
        owner = msg.sender;
        usdc = IERC20(usdc_);
        riskManager = RiskManager(riskManager_);
        trader = trader_;
        mgmtFeeBps = mgmtFeeBps_;
        perfFeeBps = perfFeeBps_;
        minInvestment = minInvestment_;
    }

    // Called once by AgentFactory after token is deployed
    function setAgentToken(address token_) external onlyOwner {
        require(!tokenSet, "AgentVault: token already set");
        agentToken = AgentToken(token_);
        tokenSet = true;
    }

    // Investor deposits USDC; receives agent tokens at 1 USDC = 1 token rate
    function deposit(uint256 usdcAmount) external {
        require(tokenSet, "AgentVault: token not set");
        require(usdcAmount >= minInvestment, "AgentVault: below minimum investment");

        uint256 tokensToTransfer = usdcAmount * SCALE;
        require(
            agentToken.balanceOf(address(this)) >= tokensToTransfer,
            "AgentVault: insufficient token supply"
        );

        require(usdc.transferFrom(msg.sender, address(this), usdcAmount), "AgentVault: USDC transfer failed");
        agentToken.transfer(msg.sender, tokensToTransfer);
        emit Deposited(msg.sender, usdcAmount, tokensToTransfer);
    }

    function requestWithdrawal() external {
        require(agentToken.balanceOf(msg.sender) > 0, "AgentVault: no tokens held");
        withdrawalRequestTime[msg.sender] = block.timestamp;
        emit WithdrawalRequested(msg.sender, block.timestamp + COOLDOWN);
    }

    // Investor returns tokens; receives USDC at same 1:1 rate (profits claimed separately)
    function executeWithdrawal() external {
        uint256 requestTime = withdrawalRequestTime[msg.sender];
        require(requestTime != 0, "AgentVault: no withdrawal requested");
        require(block.timestamp >= requestTime + COOLDOWN, "AgentVault: cooldown not elapsed");

        uint256 tokenBalance = agentToken.balanceOf(msg.sender);
        require(tokenBalance > 0, "AgentVault: no tokens to redeem");

        uint256 usdcOut = tokenBalance / SCALE;
        require(usdcOut > 0, "AgentVault: redemption too small");
        require(getAUM() >= usdcOut, "AgentVault: insufficient AUM");

        withdrawalRequestTime[msg.sender] = 0;
        // Pull tokens back to vault (investor must have approved)
        agentToken.transferFrom(msg.sender, address(this), tokenBalance);
        require(usdc.transfer(msg.sender, usdcOut), "AgentVault: USDC transfer failed");
        emit WithdrawalExecuted(msg.sender, usdcOut, tokenBalance);
    }

    // Called by executor (backend AI agent) to record a trade
    function executeTrade(
        address dexRouter,
        bytes calldata callData,
        uint256 maxSlippage
    ) external onlyExecutor {
        riskManager.validateTrade(address(this), maxSlippage, getAUM());
        emit TradeExecuted(dexRouter, callData, maxSlippage);
    }

    // Backend calls this each period to distribute net profits to token holders
    function settleProfits() external {
        uint256 currentAUM = getAUM();
        if (currentAUM <= lastSettledAUM) {
            lastSettledAUM = currentAUM;
            return;
        }

        uint256 grossProfit = currentAUM - lastSettledAUM;
        uint256 mgmtFee = (currentAUM * mgmtFeeBps) / 10000;
        uint256 perfFee = (grossProfit * perfFeeBps) / 10000;
        uint256 totalFees = mgmtFee + perfFee;
        uint256 netProfit = grossProfit > totalFees ? grossProfit - totalFees : 0;

        lastSettledAUM = currentAUM;

        if (netProfit > 0) {
            // Circulating supply = tokens held by investors (not the vault)
            uint256 totalSupply = agentToken.totalSupply();
            uint256 vaultHolding = agentToken.balanceOf(address(this));
            uint256 circulating = totalSupply - vaultHolding;
            if (circulating > 0) {
                uint256 amountPerToken = (netProfit * 1e18) / circulating;
                agentToken.pushProfitSnapshot(amountPerToken);
                // Pre-approve AgentToken to pull USDC when investors claim
                usdc.approve(address(agentToken), netProfit);
                emit ProfitsSettled(netProfit, amountPerToken);
            }
        }

        riskManager.updateHighWaterMark(address(this), currentAUM);
    }

    function getAUM() public view returns (uint256) {
        return usdc.balanceOf(address(this));
    }

    function setExecutor(address executor_) external onlyOwner {
        executor = executor_;
        emit ExecutorUpdated(executor_);
    }
}
