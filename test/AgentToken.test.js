const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentToken", function () {
  let token, usdc, vault, investor1, investor2, other;

  const INITIAL_SUPPLY = ethers.parseEther("1000000");
  const TOKENS = ethers.parseEther("100"); // 100 tokens to investor

  beforeEach(async () => {
    [vault, investor1, investor2, other] = await ethers.getSigners();

    usdc = await ethers.getContractFactory("MockUSDC").then(f => f.deploy());
    token = await ethers.getContractFactory("AgentToken").then(f =>
      f.deploy("Test Agent", "TAGT", INITIAL_SUPPLY, vault.address, usdc.getAddress())
    );
  });

  it("mints initial supply to vault at construction", async () => {
    expect(await token.balanceOf(vault.address)).to.equal(INITIAL_SUPPLY);
  });

  it("only vault can call pushProfitSnapshot", async () => {
    await expect(token.connect(other).pushProfitSnapshot(1_000_000n))
      .to.be.revertedWith("AgentToken: caller is not vault");
    await token.connect(vault).pushProfitSnapshot(500_000n);
    expect(await token.globalProfitPerToken()).to.equal(500_000n);
  });

  it("pendingProfits is proportional to token balance", async () => {
    await token.connect(vault).transfer(investor1.address, TOKENS);
    await token.connect(vault).transfer(investor2.address, TOKENS * 2n);

    // amountPerToken = 100_000 → pending = 100_000 * balance / 1e18
    await token.connect(vault).pushProfitSnapshot(100_000n);

    // investor1 (100 tokens): 100_000 * 100e18 / 1e18 = 10_000_000 (10 USDC)
    expect(await token.pendingProfits(investor1.address)).to.equal(10_000_000n);
    // investor2 (200 tokens): 20_000_000 (20 USDC)
    expect(await token.pendingProfits(investor2.address)).to.equal(20_000_000n);
  });

  it("claimProfits transfers USDC to claimant and resets accrued amount", async () => {
    await token.connect(vault).transfer(investor1.address, TOKENS);
    await token.connect(vault).pushProfitSnapshot(100_000n); // 10 USDC owed

    await usdc.mint(vault.address, 10_000_000n);
    await usdc.connect(vault).approve(await token.getAddress(), 10_000_000n);

    await token.connect(investor1).claimProfits();
    expect(await usdc.balanceOf(investor1.address)).to.equal(10_000_000n);
    expect(await token.accruedProfits(investor1.address)).to.equal(0n);
  });

  it("claimProfits reverts when there is nothing to claim", async () => {
    await expect(token.connect(other).claimProfits())
      .to.be.revertedWith("AgentToken: nothing to claim");
  });

  it("profit checkpoint prevents double-counting on transfer", async () => {
    await token.connect(vault).transfer(investor1.address, TOKENS);
    await token.connect(vault).pushProfitSnapshot(100_000n); // 10 USDC earned by investor1

    // Transfer triggers _settleHolder: locks in investor1's earned profits before balance changes
    await token.connect(investor1).transfer(investor2.address, TOKENS);

    expect(await token.accruedProfits(investor1.address)).to.equal(10_000_000n);
    // investor2 joined after the snapshot so earns nothing from it
    expect(await token.pendingProfits(investor2.address)).to.equal(0n);
  });

  it("holder joining after a snapshot earns only future profits", async () => {
    await token.connect(vault).pushProfitSnapshot(500_000n); // snapshot before investor holds any tokens
    await token.connect(vault).transfer(investor1.address, TOKENS);

    // No pending profits from the pre-join snapshot
    expect(await token.pendingProfits(investor1.address)).to.equal(0n);

    // New snapshot after joining → investor1 earns from delta only
    await token.connect(vault).pushProfitSnapshot(100_000n);
    expect(await token.pendingProfits(investor1.address)).to.equal(10_000_000n);
  });

  it("multiple profit snapshots accumulate correctly", async () => {
    await token.connect(vault).transfer(investor1.address, TOKENS);
    await token.connect(vault).pushProfitSnapshot(100_000n);
    await token.connect(vault).pushProfitSnapshot(50_000n);
    // total delta = 150_000 → 150_000 * 100e18 / 1e18 = 15_000_000
    expect(await token.pendingProfits(investor1.address)).to.equal(15_000_000n);
  });
});
