const { expect } = require("chai");
const { ethers } = require("hardhat");

// Thresholds are set ~15% above measured baseline to catch accidental regressions
// without being fragile to minor compiler changes.
//   deployAgent:   2,042,991 gas (measured)
//   deposit:          96,998 gas (measured)
//   settleProfits:   139,201 gas (measured)
const GAS_LIMITS = {
  deployAgent:   2_350_000n,
  deposit:         112_000n,
  settleProfits:   161_000n,
};

async function gasOf(tx) {
  return (await tx.wait()).gasUsed;
}

describe("Gas", function () {
  let usdc, riskManager, performanceOracle, factory, vault;
  let trader, investor;

  beforeEach(async () => {
    [, trader,, investor] = await ethers.getSigners();

    usdc = await ethers.getContractFactory("MockUSDC").then(f => f.deploy());
    riskManager = await ethers.getContractFactory("RiskManager").then(f => f.deploy());
    performanceOracle = await ethers.getContractFactory("PerformanceOracle").then(f => f.deploy());
    factory = await ethers.getContractFactory("AgentFactory").then(f =>
      f.deploy(riskManager.getAddress(), performanceOracle.getAddress(), usdc.getAddress())
    );
  });

  it("deployAgent stays within gas limit", async () => {
    const gas = await gasOf(
      await factory.connect(trader).deployAgent(
        "AlphaBot", ethers.id("strategy"), ethers.parseEther("1000000"),
        100n, 1000n, 1_000_000n
      )
    );
    console.log(`    deployAgent: ${gas.toLocaleString()} / ${GAS_LIMITS.deployAgent.toLocaleString()} gas`);
    expect(gas).to.be.lte(GAS_LIMITS.deployAgent);
  });

  it("deposit stays within gas limit", async () => {
    await factory.connect(trader).deployAgent(
      "AlphaBot", ethers.id("strategy"), ethers.parseEther("1000000"),
      100n, 1000n, 1_000_000n
    );
    const record = await factory.getAgent(0);
    vault = (await ethers.getContractFactory("AgentVault")).attach(record.vaultAddr);

    const DEPOSIT = 100_000_000n;
    await usdc.mint(investor.address, DEPOSIT);
    await usdc.connect(investor).approve(await vault.getAddress(), DEPOSIT);

    const gas = await gasOf(await vault.connect(investor).deposit(DEPOSIT));
    console.log(`    deposit: ${gas.toLocaleString()} / ${GAS_LIMITS.deposit.toLocaleString()} gas`);
    expect(gas).to.be.lte(GAS_LIMITS.deposit);
  });

  it("settleProfits stays within gas limit", async () => {
    await factory.connect(trader).deployAgent(
      "AlphaBot", ethers.id("strategy"), ethers.parseEther("1000000"),
      100n, 1000n, 1_000_000n
    );
    const record = await factory.getAgent(0);
    vault = (await ethers.getContractFactory("AgentVault")).attach(record.vaultAddr);

    const DEPOSIT = 100_000_000n;
    await usdc.mint(investor.address, DEPOSIT);
    await usdc.connect(investor).approve(await vault.getAddress(), DEPOSIT);
    await vault.connect(investor).deposit(DEPOSIT);

    await vault.settleProfits(); // baseline settlement
    await usdc.mint(await vault.getAddress(), 10_000_000n); // simulate 10 USDC profit

    const gas = await gasOf(await vault.settleProfits());
    console.log(`    settleProfits: ${gas.toLocaleString()} / ${GAS_LIMITS.settleProfits.toLocaleString()} gas`);
    expect(gas).to.be.lte(GAS_LIMITS.settleProfits);
  });
});
