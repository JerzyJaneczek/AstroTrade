const { expect } = require("chai");
const { ethers } = require("hardhat");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");

describe("PerformanceOracle", function () {
  let oracle, owner, reporter, other;
  const VAULT = "0x0000000000000000000000000000000000000001";

  beforeEach(async () => {
    [owner, reporter, other] = await ethers.getSigners();
    oracle = await ethers.getContractFactory("PerformanceOracle").then(f => f.deploy());
    await oracle.setReporter(reporter.address);
  });

  it("deployer is owner; setReporter is owner-only", async () => {
    expect(await oracle.owner()).to.equal(owner.address);
    await expect(oracle.connect(other).setReporter(other.address))
      .to.be.revertedWith("PerformanceOracle: caller is not owner");
  });

  it("pushSnapshot stores all fields and only reporter can call it", async () => {
    await oracle.connect(reporter).pushSnapshot(VAULT, 1_000_000n, 100_000_000n, 1500n, 6000n, 150n);
    const snap = await oracle.getLatest(VAULT);
    expect(snap.navPerToken).to.equal(1_000_000n);
    expect(snap.totalAUM).to.equal(100_000_000n);
    expect(snap.cumulativeReturn).to.equal(1500n);
    expect(snap.winRate).to.equal(6000n);
    expect(snap.sharpeRatio).to.equal(150n);

    await expect(
      oracle.connect(other).pushSnapshot(VAULT, 0n, 0n, 0n, 0n, 0n)
    ).to.be.revertedWith("PerformanceOracle: caller is not reporter");
  });

  it("pushSnapshot supports negative return and Sharpe values", async () => {
    await oracle.connect(reporter).pushSnapshot(VAULT, 900_000n, 90_000_000n, -500n, 4000n, -50n);
    const snap = await oracle.getLatest(VAULT);
    expect(snap.cumulativeReturn).to.equal(-500n);
    expect(snap.sharpeRatio).to.equal(-50n);
  });

  it("pushSnapshot emits SnapshotPushed", async () => {
    await expect(oracle.connect(reporter).pushSnapshot(VAULT, 1n, 1n, 0n, 0n, 0n))
      .to.emit(oracle, "SnapshotPushed").withArgs(VAULT, anyValue);
  });

  it("getLatest reverts when no snapshots exist", async () => {
    await expect(oracle.getLatest(VAULT)).to.be.revertedWith("PerformanceOracle: no snapshots");
  });

  it("getLatest returns the most recent snapshot", async () => {
    await oracle.connect(reporter).pushSnapshot(VAULT, 1_000_000n, 100_000_000n, 0n, 0n, 0n);
    await oracle.connect(reporter).pushSnapshot(VAULT, 1_100_000n, 110_000_000n, 0n, 0n, 0n);
    expect((await oracle.getLatest(VAULT)).navPerToken).to.equal(1_100_000n);
  });

  it("getHistory returns a correct slice of snapshots", async () => {
    for (let i = 1; i <= 3; i++) {
      await oracle.connect(reporter).pushSnapshot(VAULT, BigInt(i) * 1_000_000n, 0n, 0n, 0n, 0n);
    }
    const slice = await oracle.getHistory(VAULT, 1, 3);
    expect(slice.length).to.equal(2);
    expect(slice[0].navPerToken).to.equal(2_000_000n);
  });

  it("getHistory reverts on out-of-range or inverted indices", async () => {
    await oracle.connect(reporter).pushSnapshot(VAULT, 1n, 0n, 0n, 0n, 0n);
    await expect(oracle.getHistory(VAULT, 0, 5)).to.be.revertedWith("PerformanceOracle: out of range");
    await expect(oracle.getHistory(VAULT, 1, 0)).to.be.revertedWith("PerformanceOracle: invalid range");
  });
});
