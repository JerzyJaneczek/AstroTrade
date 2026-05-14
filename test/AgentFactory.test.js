const { expect } = require("chai");
const { ethers } = require("hardhat");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");

describe("AgentFactory", function () {
  let factory, usdc, riskManager, performanceOracle;
  let owner, trader;

  const SUPPLY = ethers.parseEther("1000000");
  const HASH = ethers.id("strategy");

  beforeEach(async () => {
    [owner, trader] = await ethers.getSigners();

    usdc = await ethers.getContractFactory("MockUSDC").then(f => f.deploy());
    riskManager = await ethers.getContractFactory("RiskManager").then(f => f.deploy());
    performanceOracle = await ethers.getContractFactory("PerformanceOracle").then(f => f.deploy());

    factory = await ethers.getContractFactory("AgentFactory").then(f =>
      f.deploy(riskManager.getAddress(), performanceOracle.getAddress(), usdc.getAddress())
    );
  });

  async function deploy(name = "AlphaBot") {
    return factory.connect(trader).deployAgent(name, HASH, SUPPLY, 100n, 1000n, 1_000_000n);
  }

  it("stores constructor addresses and starts with zero agents", async () => {
    expect(await factory.riskManager()).to.equal(await riskManager.getAddress());
    expect(await factory.usdc()).to.equal(await usdc.getAddress());
    expect(await factory.getAgentCount()).to.equal(0n);
  });

  it("deployAgent stores correct record (name, strategyHash, trader)", async () => {
    await deploy("AlphaBot");
    const r = await factory.getAgent(0);
    expect(r.name).to.equal("AlphaBot");
    expect(r.strategyHash).to.equal(HASH);
    expect(r.trader).to.equal(trader.address);
  });

  it("deployAgent produces non-zero, distinct token and vault addresses", async () => {
    await deploy();
    const r = await factory.getAgent(0);
    expect(r.tokenAddr).to.not.equal(ethers.ZeroAddress);
    expect(r.vaultAddr).to.not.equal(ethers.ZeroAddress);
    expect(r.tokenAddr).to.not.equal(r.vaultAddr);
  });

  it("vault is wired to its token after deployment", async () => {
    await deploy();
    const r = await factory.getAgent(0);
    const vault = (await ethers.getContractFactory("AgentVault")).attach(r.vaultAddr);
    expect(await vault.agentToken()).to.equal(r.tokenAddr);
  });

  it("initial supply is minted to the vault", async () => {
    await deploy();
    const r = await factory.getAgent(0);
    const token = (await ethers.getContractFactory("AgentToken")).attach(r.tokenAddr);
    expect(await token.balanceOf(r.vaultAddr)).to.equal(SUPPLY);
  });

  it("emits AgentDeployed and increments agent count", async () => {
    await expect(deploy("AlphaBot"))
      .to.emit(factory, "AgentDeployed")
      .withArgs(0n, trader.address, anyValue, anyValue, "AlphaBot");
    expect(await factory.getAgentCount()).to.equal(1n);
  });

  it("getAgent reverts for an out-of-range index", async () => {
    await expect(factory.getAgent(0)).to.be.revertedWith("AgentFactory: index out of range");
  });

  it("derives a 4-char uppercase symbol from agent name", async () => {
    await deploy("AlphaBot");       // → ALPH
    await deploy("123ABCTest");     // → ABCT
    await deploy("ab");             // → AB

    const AgentToken = await ethers.getContractFactory("AgentToken");
    const sym = async (idx) => AgentToken.attach((await factory.getAgent(idx)).tokenAddr).symbol();

    expect(await sym(0n)).to.equal("ALPH");
    expect(await sym(1n)).to.equal("ABCT");
    expect(await sym(2n)).to.equal("AB");
  });
});
