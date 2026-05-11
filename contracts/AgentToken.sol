// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract AgentToken is ERC20 {
    address public immutable vault;
    IERC20 public immutable usdc;

    // Scaled by 1e18: total USDC profit accumulated per token since inception
    uint256 public globalProfitPerToken;

    // Per-holder checkpoint: the globalProfitPerToken value when they last settled
    mapping(address => uint256) public profitCheckpoint;
    // Accumulated unsettled profits per holder (before transfer)
    mapping(address => uint256) public accruedProfits;

    modifier onlyVault() {
        require(msg.sender == vault, "AgentToken: caller is not vault");
        _;
    }

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 initialSupply,
        address vault_,
        address usdc_
    ) ERC20(name_, symbol_) {
        vault = vault_;
        usdc = IERC20(usdc_);
        _mint(vault_, initialSupply);
    }

    // Called by the vault each time it distributes profits
    function pushProfitSnapshot(uint256 amountPerToken) external onlyVault {
        globalProfitPerToken += amountPerToken;
    }

    // Returns unclaimed USDC profits for a holder
    function pendingProfits(address holder) public view returns (uint256) {
        uint256 delta = globalProfitPerToken - profitCheckpoint[holder];
        return accruedProfits[holder] + (delta * balanceOf(holder)) / 1e18;
    }

    // Holder claims their USDC profit share; vault must have approved this contract or we pull directly
    function claimProfits() external {
        _settleHolder(msg.sender);
        uint256 owed = accruedProfits[msg.sender];
        require(owed > 0, "AgentToken: nothing to claim");
        accruedProfits[msg.sender] = 0;
        require(usdc.transferFrom(vault, msg.sender, owed), "AgentToken: USDC transfer failed");
    }

    // Settle profits before any balance change so the snapshot stays consistent
    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0)) _settleHolder(from);
        if (to != address(0)) _settleHolder(to);
        super._update(from, to, value);
    }

    function _settleHolder(address holder) internal {
        uint256 delta = globalProfitPerToken - profitCheckpoint[holder];
        if (delta > 0) {
            accruedProfits[holder] += (delta * balanceOf(holder)) / 1e18;
            profitCheckpoint[holder] = globalProfitPerToken;
        }
    }
}
