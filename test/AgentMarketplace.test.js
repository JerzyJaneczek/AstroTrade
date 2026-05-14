const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentMarketplace", function () {
  let marketplace, usdc, agentToken;
  let owner, seller, buyer, feeRecipient, other;

  const FEE_BPS = 50n;                         // 0.5%
  const LIST_AMOUNT = ethers.parseEther("100"); // 100 agent tokens (18 dec)
  const PRICE = 2_000_000n;                    // 2 USDC per token (6 dec / 18 dec token)
  // totalCost = 100e18 * 2e6 / 1e18 = 200_000_000 (200 USDC)
  const TOTAL_COST = LIST_AMOUNT * PRICE / ethers.parseEther("1");

  beforeEach(async () => {
    [owner, seller, buyer, feeRecipient, other] = await ethers.getSigners();

    usdc = await ethers.getContractFactory("MockUSDC").then(f => f.deploy());

    // seller acts as vault so it receives the full initial token supply
    agentToken = await ethers.getContractFactory("AgentToken").then(f =>
      f.deploy("Test Agent", "TAGT", ethers.parseEther("1000000"), seller.address, usdc.getAddress())
    );

    marketplace = await ethers.getContractFactory("AgentMarketplace").then(f =>
      f.deploy(usdc.getAddress(), FEE_BPS, feeRecipient.address)
    );

    await agentToken.connect(seller).approve(await marketplace.getAddress(), LIST_AMOUNT);
  });

  it("listTokens pulls tokens into marketplace and stores the listing", async () => {
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);

    const l = await marketplace.listings(0);
    expect(l.seller).to.equal(seller.address);
    expect(l.amount).to.equal(LIST_AMOUNT);
    expect(l.active).to.be.true;
    expect(await agentToken.balanceOf(await marketplace.getAddress())).to.equal(LIST_AMOUNT);
  });

  it("listTokens reverts on zero amount or zero price", async () => {
    await expect(
      marketplace.connect(seller).listTokens(await agentToken.getAddress(), 0n, PRICE)
    ).to.be.revertedWith("AgentMarketplace: amount must be > 0");
    await expect(
      marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, 0n)
    ).to.be.revertedWith("AgentMarketplace: price must be > 0");
  });

  it("buyTokens sends tokens to buyer, net USDC to seller, fee to feeRecipient", async () => {
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);
    await usdc.mint(buyer.address, TOTAL_COST);
    await usdc.connect(buyer).approve(await marketplace.getAddress(), TOTAL_COST);

    await marketplace.connect(buyer).buyTokens(0, LIST_AMOUNT);

    const fee = TOTAL_COST * FEE_BPS / 10000n;
    expect(await agentToken.balanceOf(buyer.address)).to.equal(LIST_AMOUNT);
    expect(await usdc.balanceOf(seller.address)).to.equal(TOTAL_COST - fee);
    expect(await usdc.balanceOf(feeRecipient.address)).to.equal(fee);
  });

  it("buyTokens marks listing inactive when fully purchased", async () => {
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);
    await usdc.mint(buyer.address, TOTAL_COST);
    await usdc.connect(buyer).approve(await marketplace.getAddress(), TOTAL_COST);
    await marketplace.connect(buyer).buyTokens(0, LIST_AMOUNT);
    expect((await marketplace.listings(0)).active).to.be.false;
  });

  it("buyTokens reverts on inactive listing or zero/excess amount", async () => {
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);
    await usdc.mint(buyer.address, TOTAL_COST);
    await usdc.connect(buyer).approve(await marketplace.getAddress(), TOTAL_COST);
    await marketplace.connect(buyer).buyTokens(0, LIST_AMOUNT);

    await expect(marketplace.connect(buyer).buyTokens(0, 1n))
      .to.be.revertedWith("AgentMarketplace: listing not active");
    await expect(marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE));
    await agentToken.connect(seller).approve(await marketplace.getAddress(), LIST_AMOUNT);
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);
    await expect(marketplace.connect(buyer).buyTokens(1, 0n))
      .to.be.revertedWith("AgentMarketplace: invalid amount");
  });

  it("cancelListing returns tokens to seller and deactivates listing", async () => {
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);
    const before = await agentToken.balanceOf(seller.address);
    await marketplace.connect(seller).cancelListing(0);
    expect(await agentToken.balanceOf(seller.address)).to.equal(before + LIST_AMOUNT);
    expect((await marketplace.listings(0)).active).to.be.false;
  });

  it("cancelListing is seller-only", async () => {
    await marketplace.connect(seller).listTokens(await agentToken.getAddress(), LIST_AMOUNT, PRICE);
    await expect(marketplace.connect(other).cancelListing(0))
      .to.be.revertedWith("AgentMarketplace: caller is not seller");
  });

  it("setProtocolFee is owner-only and capped at 1000 bps", async () => {
    await expect(marketplace.connect(other).setProtocolFee(100n))
      .to.be.revertedWith("AgentMarketplace: caller is not owner");
    await expect(marketplace.connect(owner).setProtocolFee(1001n))
      .to.be.revertedWith("AgentMarketplace: fee too high");
    await marketplace.connect(owner).setProtocolFee(100n);
    expect(await marketplace.feeBps()).to.equal(100n);
  });
});
