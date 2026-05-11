// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract PerformanceOracle {
    struct Snapshot {
        uint256 navPerToken;       // NAV per token scaled by 1e6 (USDC decimals)
        uint256 totalAUM;          // Total AUM in USDC (6 decimals)
        int256  cumulativeReturn;  // Basis points, e.g. 1500 = +15%
        uint256 winRate;           // Basis points, e.g. 6000 = 60%
        int256  sharpeRatio;       // Scaled by 100, e.g. 150 = 1.50
        uint256 timestamp;
    }

    address public owner;
    address public reporter;

    mapping(address => Snapshot[]) private history;

    event SnapshotPushed(address indexed vault, uint256 timestamp);
    event ReporterUpdated(address indexed reporter);

    modifier onlyOwner() {
        require(msg.sender == owner, "PerformanceOracle: caller is not owner");
        _;
    }

    modifier onlyReporter() {
        require(msg.sender == reporter, "PerformanceOracle: caller is not reporter");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function setReporter(address reporter_) external onlyOwner {
        reporter = reporter_;
        emit ReporterUpdated(reporter_);
    }

    function pushSnapshot(
        address vault,
        uint256 navPerToken,
        uint256 totalAUM,
        int256  cumulativeReturn,
        uint256 winRate,
        int256  sharpeRatio
    ) external onlyReporter {
        history[vault].push(Snapshot({
            navPerToken: navPerToken,
            totalAUM: totalAUM,
            cumulativeReturn: cumulativeReturn,
            winRate: winRate,
            sharpeRatio: sharpeRatio,
            timestamp: block.timestamp
        }));
        emit SnapshotPushed(vault, block.timestamp);
    }

    function getLatest(address vault) external view returns (Snapshot memory) {
        Snapshot[] storage snaps = history[vault];
        require(snaps.length > 0, "PerformanceOracle: no snapshots");
        return snaps[snaps.length - 1];
    }

    function getHistory(address vault, uint256 from, uint256 to)
        external
        view
        returns (Snapshot[] memory)
    {
        Snapshot[] storage snaps = history[vault];
        require(to <= snaps.length, "PerformanceOracle: out of range");
        require(from <= to, "PerformanceOracle: invalid range");
        uint256 len = to - from;
        Snapshot[] memory result = new Snapshot[](len);
        for (uint256 i = 0; i < len; i++) {
            result[i] = snaps[from + i];
        }
        return result;
    }
}
