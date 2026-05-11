// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./AgentToken.sol";
import "./AgentVault.sol";

contract AgentFactory {
    struct AgentRecord {
        string name;
        bytes32 strategyHash;
        address tokenAddr;
        address vaultAddr;
        address trader;
    }

    address public immutable riskManager;
    address public immutable performanceOracle;
    address public immutable usdc;

    AgentRecord[] public agents;

    event AgentDeployed(
        uint256 indexed index,
        address indexed trader,
        address tokenAddr,
        address vaultAddr,
        string name
    );

    constructor(address riskManager_, address performanceOracle_, address usdc_) {
        riskManager = riskManager_;
        performanceOracle = performanceOracle_;
        usdc = usdc_;
    }

    function deployAgent(
        string calldata name,
        bytes32 strategyHash,
        uint256 initialSupply,
        uint256 mgmtFeeBps,
        uint256 perfFeeBps,
        uint256 minInvestment
    ) external returns (address tokenAddr, address vaultAddr) {
        // 1. Deploy vault (token reference set after)
        AgentVault vault = new AgentVault(
            usdc,
            riskManager,
            msg.sender,
            mgmtFeeBps,
            perfFeeBps,
            minInvestment
        );
        vaultAddr = address(vault);

        // 2. Deploy token pointing to vault; initial supply minted to vault
        string memory symbol = _toSymbol(name);
        AgentToken token = new AgentToken(
            name,
            symbol,
            initialSupply,
            vaultAddr,
            usdc
        );
        tokenAddr = address(token);

        // 3. Wire the vault to its token (one-time setter)
        vault.setAgentToken(tokenAddr);

        agents.push(AgentRecord({
            name: name,
            strategyHash: strategyHash,
            tokenAddr: tokenAddr,
            vaultAddr: vaultAddr,
            trader: msg.sender
        }));

        emit AgentDeployed(agents.length - 1, msg.sender, tokenAddr, vaultAddr, name);
    }

    function getAgent(uint256 index) external view returns (AgentRecord memory) {
        require(index < agents.length, "AgentFactory: index out of range");
        return agents[index];
    }

    function getAgentCount() external view returns (uint256) {
        return agents.length;
    }

    // Derive a short uppercase symbol from the agent name (up to 4 chars)
    function _toSymbol(string memory name) internal pure returns (string memory) {
        bytes memory b = bytes(name);
        bytes memory sym = new bytes(4);
        uint256 count = 0;
        for (uint256 i = 0; i < b.length && count < 4; i++) {
            if (b[i] >= 0x41 && b[i] <= 0x5A) {
                sym[count++] = b[i];
            } else if (b[i] >= 0x61 && b[i] <= 0x7A) {
                sym[count++] = bytes1(uint8(b[i]) - 32);
            }
        }
        bytes memory result = new bytes(count);
        for (uint256 i = 0; i < count; i++) result[i] = sym[i];
        return string(result);
    }
}
