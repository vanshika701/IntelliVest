// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {TestToken} from "./TestToken.sol";
import {MockPriceFeed} from "./MockPriceFeed.sol";
import {Side} from "../Types.sol";

/// Mints and burns test tokens at the test price. Both legs happen in one
/// transaction, so either both move or neither does.
contract MockFundMarket is Ownable {
    using SafeERC20 for IERC20;

    uint256 public constant MAX_FUNDS = 20;
    TestToken public immutable inr;
    MockPriceFeed public immutable feed;

    address[] private _funds;
    mapping(address => bool) public isFund;
    mapping(address => bool) public isEquity;
    /// Simulates bad execution (slippage) in tests.
    uint16 public skewBps;

    constructor(TestToken inr_, MockPriceFeed feed_) Ownable(msg.sender) {
        inr = inr_;
        feed = feed_;
    }

    /// A fund's equity flag is fixed once added.
    function addFund(address fund, bool equity) external onlyOwner {
        require(!isFund[fund] && _funds.length < MAX_FUNDS, "fund");
        isFund[fund] = true;
        isEquity[fund] = equity;
        _funds.push(fund);
    }

    function setSkew(uint16 bps) external onlyOwner {
        require(bps <= 10_000, "skew");
        skewBps = bps;
    }

    function funds() external view returns (address[] memory) { return _funds; }

    function swap(address fund, Side side, uint256 amount) external returns (uint256 out) {
        require(isFund[fund], "unknown fund");
        (uint256 price,) = feed.price(fund);
        require(price > 0, "no price");
        out = side == Side.BUY ? amount * 1e6 / price : amount * price / 1e6;
        out = out * (10_000 - skewBps) / 10_000;
        TestToken tokenIn = side == Side.BUY ? inr : TestToken(fund);
        TestToken tokenOut = side == Side.BUY ? TestToken(fund) : inr;
        IERC20(address(tokenIn)).safeTransferFrom(msg.sender, address(this), amount);
        tokenIn.burn(amount);
        tokenOut.mint(msg.sender, out);
    }
}
