const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("MockUSDC", function () {
  let usdc, owner, user1, user2;

  beforeEach(async () => {
    [owner, user1, user2] = await ethers.getSigners();
    usdc = await ethers.getContractFactory("MockUSDC").then(f => f.deploy());
  });

  it("has 6 decimals, correct name and symbol", async () => {
    expect(await usdc.decimals()).to.equal(6);
    expect(await usdc.name()).to.equal("Mock USDC");
    expect(await usdc.symbol()).to.equal("USDC");
  });

  it("mint increases balance and total supply", async () => {
    await usdc.mint(user1.address, 1_000_000n);
    expect(await usdc.balanceOf(user1.address)).to.equal(1_000_000n);
    expect(await usdc.totalSupply()).to.equal(1_000_000n);
  });

  it("transfer moves tokens between accounts", async () => {
    await usdc.mint(user1.address, 1_000_000n);
    await usdc.connect(user1).transfer(user2.address, 400_000n);
    expect(await usdc.balanceOf(user1.address)).to.equal(600_000n);
    expect(await usdc.balanceOf(user2.address)).to.equal(400_000n);
  });

  it("approve and transferFrom work correctly", async () => {
    await usdc.mint(user1.address, 1_000_000n);
    await usdc.connect(user1).approve(user2.address, 500_000n);
    await usdc.connect(user2).transferFrom(user1.address, user2.address, 500_000n);
    expect(await usdc.balanceOf(user2.address)).to.equal(500_000n);
  });

  it("reverts transfer when balance is insufficient", async () => {
    await usdc.mint(user1.address, 100n);
    await expect(usdc.connect(user1).transfer(user2.address, 200n)).to.be.reverted;
  });
});
