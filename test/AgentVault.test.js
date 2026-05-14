const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

const SCALE = 1_000_000_000_000n; // 1e12: 1 USDC (6 dec) = 1 token (18 dec)

describe("AgentVault", function () {
  let usdc, riskManager, vault, token;
  let owner, trader, executor, investor, other;

  const DEPOSIT = 100_000_000n; // 100 USDC

  beforeEach(async () => {
    [owner, trader, executor, investor, other] = await ethers.getSigners();

    usdc = await ethers.getContractFactory("MockUSDC").then(f => f.deploy());
    riskManager = await ethers.getContractFactory("RiskManager").then(f => f.deploy());

    vault = await ethers.getContractFactory("AgentVault").then(f =>
      f.connect(owner).deploy(
        usdc.getAddress(), riskManager.getAddress(), trader.address,
        100n, 1000n, 1_000_000n // 1% mgmt, 10% perf, 1 USDC min
      )
    );

    token = await ethers.getContractFactory("AgentToken").then(f =>
      f.deploy("Test Agent", "TAGT", ethers.parseEther("1000000"), vault.getAddress(), usdc.getAddress())
    );

    await vault.connect(owner).setAgentToken(await token.getAddress());
    await vault.connect(owner).setExecutor(executor.address);

    // Fund investor for deposit tests
    await usdc.mint(investor.address, DEPOSIT);
    await usdc.connect(investor).approve(await vault.getAddress(), DEPOSIT);
  });

  it("deposit transfers USDC to vault and gives investor tokens at 1:1 rate (×1e12)", async () => {
    await vault.connect(investor).deposit(DEPOSIT);
    expect(await usdc.balanceOf(await vault.getAddress())).to.equal(DEPOSIT);
    expect(await token.balanceOf(investor.address)).to.equal(DEPOSIT * SCALE);
  });

  it("deposit reverts below minimum investment", async () => {
    await expect(vault.connect(investor).deposit(999_999n))
      .to.be.revertedWith("AgentVault: below minimum investment");
  });

  it("full withdrawal flow: request → wait cooldown → execute returns USDC", async () => {
    await vault.connect(investor).deposit(DEPOSIT);
    await vault.connect(investor).requestWithdrawal();

    await time.increase(86400); // advance 1 day

    const tokenBal = await token.balanceOf(investor.address);
    await token.connect(investor).approve(await vault.getAddress(), tokenBal);
    await vault.connect(investor).executeWithdrawal();

    expect(await usdc.balanceOf(investor.address)).to.equal(DEPOSIT);
    expect(await token.balanceOf(investor.address)).to.equal(0n);
  });

  it("executeWithdrawal reverts before cooldown has elapsed", async () => {
    await vault.connect(investor).deposit(DEPOSIT);
    await vault.connect(investor).requestWithdrawal();
    await expect(vault.connect(investor).executeWithdrawal())
      .to.be.revertedWith("AgentVault: cooldown not elapsed");
  });

  it("requestWithdrawal reverts when caller holds no tokens", async () => {
    await expect(vault.connect(other).requestWithdrawal())
      .to.be.revertedWith("AgentVault: no tokens held");
  });

  it("executeTrade is executor-only and fails when agent is halted", async () => {
    await riskManager.connect(trader).setRiskProfile(await vault.getAddress(), 20, 10, 5);
    await vault.connect(investor).deposit(DEPOSIT);

    await expect(vault.connect(other).executeTrade(other.address, "0x", 1n))
      .to.be.revertedWith("AgentVault: caller is not executor");

    await riskManager.haltAgent(await vault.getAddress());
    await expect(vault.connect(executor).executeTrade(other.address, "0x", 1n))
      .to.be.revertedWith("RiskManager: agent is halted");
  });

  it("settleProfits updates lastSettledAUM and increases globalProfitPerToken on profit", async () => {
    await vault.connect(investor).deposit(DEPOSIT);
    await vault.settleProfits(); // baseline

    await usdc.mint(await vault.getAddress(), 10_000_000n); // add 10 USDC profit
    const gppBefore = await token.globalProfitPerToken();
    await vault.settleProfits();

    expect(await token.globalProfitPerToken()).to.be.gt(gppBefore);
    expect(await vault.lastSettledAUM()).to.equal(DEPOSIT + 10_000_000n);
  });

  it("setAgentToken is owner-only and can only be called once", async () => {
    await expect(vault.connect(owner).setAgentToken(other.address))
      .to.be.revertedWith("AgentVault: token already set");
    await expect(vault.connect(other).setExecutor(other.address))
      .to.be.revertedWith("AgentVault: caller is not owner");
  });
});
