const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("RiskManager", function () {
  let riskManager, trader, other;
  const VAULT = "0x0000000000000000000000000000000000000001";
  const AUM = 100_000_000n; // 100 USDC

  beforeEach(async () => {
    [, trader, other] = await ethers.getSigners();
    riskManager = await ethers.getContractFactory("RiskManager").then(f => f.deploy());
    await riskManager.connect(trader).setRiskProfile(VAULT, 20, 10, 5);
  });

  it("setRiskProfile stores params and sets trader to msg.sender", async () => {
    const p = await riskManager.profiles(VAULT);
    expect(p.maxDrawdownPct).to.equal(20n);
    expect(p.maxPositionPct).to.equal(10n);
    expect(p.trailingStopPct).to.equal(5n);
    expect(p.trader).to.equal(trader.address);
  });

  it("validateTrade passes when trade size is within position limit", async () => {
    // maxPositionPct = 10, AUM = 100 USDC → max = 10 USDC = 10_000_000
    await expect(riskManager.validateTrade(VAULT, 10_000_000n, AUM)).not.to.be.reverted;
  });

  it("validateTrade reverts when trade exceeds max position size", async () => {
    await expect(riskManager.validateTrade(VAULT, 10_000_001n, AUM))
      .to.be.revertedWith("RiskManager: trade exceeds max position size");
  });

  it("validateTrade reverts when agent is halted", async () => {
    await riskManager.haltAgent(VAULT);
    await expect(riskManager.validateTrade(VAULT, 1n, AUM))
      .to.be.revertedWith("RiskManager: agent is halted");
  });

  it("validateTrade skips position check when no profile is set", async () => {
    const OTHER = "0x0000000000000000000000000000000000000002";
    await expect(riskManager.validateTrade(OTHER, AUM * 99n, AUM)).not.to.be.reverted;
  });

  it("anyone can halt; only the trader can resume", async () => {
    await riskManager.connect(other).haltAgent(VAULT);
    expect(await riskManager.isHalted(VAULT)).to.be.true;

    await expect(riskManager.connect(other).resumeAgent(VAULT))
      .to.be.revertedWith("RiskManager: caller is not trader");

    await riskManager.connect(trader).resumeAgent(VAULT);
    expect(await riskManager.isHalted(VAULT)).to.be.false;
  });

  it("updateHighWaterMark only updates when new NAV is strictly higher", async () => {
    await riskManager.updateHighWaterMark(VAULT, 2_000_000n);
    await riskManager.updateHighWaterMark(VAULT, 1_000_000n); // lower — should not update
    expect(await riskManager.highWaterMark(VAULT)).to.equal(2_000_000n);
  });

  it("emits RiskProfileSet, AgentHalted, AgentResumed", async () => {
    await expect(riskManager.connect(trader).setRiskProfile(VAULT, 10, 5, 2))
      .to.emit(riskManager, "RiskProfileSet").withArgs(VAULT);
    await expect(riskManager.haltAgent(VAULT))
      .to.emit(riskManager, "AgentHalted").withArgs(VAULT);
    await expect(riskManager.connect(trader).resumeAgent(VAULT))
      .to.emit(riskManager, "AgentResumed").withArgs(VAULT);
  });
});
