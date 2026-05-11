// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract RiskManager {
    struct RiskProfile {
        uint256 maxDrawdownPct;   // e.g. 20 = 20% max drawdown
        uint256 maxPositionPct;   // e.g. 10 = max 10% of AUM per trade
        uint256 trailingStopPct;  // e.g. 5 = 5% trailing stop
        address trader;
    }

    mapping(address => RiskProfile) public profiles;
    mapping(address => bool) public halted;
    mapping(address => uint256) public highWaterMark;

    event RiskProfileSet(address indexed vault);
    event AgentHalted(address indexed vault);
    event AgentResumed(address indexed vault);

    modifier onlyTrader(address vault) {
        require(msg.sender == profiles[vault].trader, "RiskManager: caller is not trader");
        _;
    }

    function setRiskProfile(
        address vault,
        uint256 maxDrawdownPct,
        uint256 maxPositionPct,
        uint256 trailingStopPct
    ) external {
        profiles[vault] = RiskProfile({
            maxDrawdownPct: maxDrawdownPct,
            maxPositionPct: maxPositionPct,
            trailingStopPct: trailingStopPct,
            trader: msg.sender
        });
        emit RiskProfileSet(vault);
    }

    function validateTrade(address vault, uint256 tradeSize, uint256 currentAUM) external view {
        require(!halted[vault], "RiskManager: agent is halted");
        RiskProfile memory p = profiles[vault];
        if (currentAUM > 0 && p.maxPositionPct > 0) {
            uint256 maxAllowed = (currentAUM * p.maxPositionPct) / 100;
            require(tradeSize <= maxAllowed, "RiskManager: trade exceeds max position size");
        }
    }

    function updateHighWaterMark(address vault, uint256 newNAV) external {
        if (newNAV > highWaterMark[vault]) {
            highWaterMark[vault] = newNAV;
        }
    }

    function haltAgent(address vault) external {
        halted[vault] = true;
        emit AgentHalted(vault);
    }

    function resumeAgent(address vault) external onlyTrader(vault) {
        halted[vault] = false;
        emit AgentResumed(vault);
    }

    function isHalted(address vault) external view returns (bool) {
        return halted[vault];
    }
}
