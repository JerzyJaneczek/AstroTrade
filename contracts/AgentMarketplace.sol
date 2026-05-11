// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract AgentMarketplace {
    struct Listing {
        address seller;
        address agentToken;
        uint256 amount;
        uint256 pricePerToken; // USDC per token (6 decimals), token has 18 decimals
        bool active;
    }

    IERC20 public immutable usdc;
    address public owner;
    uint256 public feeBps;
    address public feeRecipient;

    Listing[] public listings;

    event TokensListed(uint256 indexed listingId, address indexed seller, address agentToken, uint256 amount, uint256 pricePerToken);
    event TokensBought(uint256 indexed listingId, address indexed buyer, uint256 amount, uint256 totalCost);
    event ListingCancelled(uint256 indexed listingId);
    event ProtocolFeeUpdated(uint256 feeBps);
    event FeeRecipientUpdated(address feeRecipient);

    modifier onlyOwner() {
        require(msg.sender == owner, "AgentMarketplace: caller is not owner");
        _;
    }

    constructor(address usdc_, uint256 feeBps_, address feeRecipient_) {
        usdc = IERC20(usdc_);
        owner = msg.sender;
        feeBps = feeBps_;
        feeRecipient = feeRecipient_;
    }

    function listTokens(
        address agentToken,
        uint256 amount,
        uint256 pricePerToken
    ) external returns (uint256 listingId) {
        require(amount > 0, "AgentMarketplace: amount must be > 0");
        require(pricePerToken > 0, "AgentMarketplace: price must be > 0");

        require(
            IERC20(agentToken).transferFrom(msg.sender, address(this), amount),
            "AgentMarketplace: token transfer failed"
        );

        listingId = listings.length;
        listings.push(Listing({
            seller: msg.sender,
            agentToken: agentToken,
            amount: amount,
            pricePerToken: pricePerToken,
            active: true
        }));

        emit TokensListed(listingId, msg.sender, agentToken, amount, pricePerToken);
    }

    function buyTokens(uint256 listingId, uint256 amount) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "AgentMarketplace: listing not active");
        require(amount > 0 && amount <= listing.amount, "AgentMarketplace: invalid amount");

        // totalCost = amount (18 dec) * pricePerToken (6 dec per 18 dec token) / 1e18
        uint256 totalCost = (amount * listing.pricePerToken) / 1e18;
        uint256 fee = (totalCost * feeBps) / 10000;
        uint256 sellerProceeds = totalCost - fee;

        listing.amount -= amount;
        if (listing.amount == 0) listing.active = false;

        require(usdc.transferFrom(msg.sender, listing.seller, sellerProceeds), "AgentMarketplace: USDC to seller failed");
        if (fee > 0) {
            require(usdc.transferFrom(msg.sender, feeRecipient, fee), "AgentMarketplace: fee transfer failed");
        }
        require(IERC20(listing.agentToken).transfer(msg.sender, amount), "AgentMarketplace: token transfer failed");

        emit TokensBought(listingId, msg.sender, amount, totalCost);
    }

    function cancelListing(uint256 listingId) external {
        Listing storage listing = listings[listingId];
        require(listing.active, "AgentMarketplace: listing not active");
        require(msg.sender == listing.seller, "AgentMarketplace: caller is not seller");

        listing.active = false;
        require(
            IERC20(listing.agentToken).transfer(listing.seller, listing.amount),
            "AgentMarketplace: token return failed"
        );
        listing.amount = 0;

        emit ListingCancelled(listingId);
    }

    function setProtocolFee(uint256 bps) external onlyOwner {
        require(bps <= 1000, "AgentMarketplace: fee too high");
        feeBps = bps;
        emit ProtocolFeeUpdated(bps);
    }

    function setFeeRecipient(address recipient) external onlyOwner {
        feeRecipient = recipient;
        emit FeeRecipientUpdated(recipient);
    }

    function getListingCount() external view returns (uint256) {
        return listings.length;
    }
}
