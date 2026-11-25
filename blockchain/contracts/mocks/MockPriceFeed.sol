// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// Test prices posted by the project, so they must be trusted. Limiting each
/// move and how often it can happen slows a price attack; it can't stop one.
contract MockPriceFeed is Ownable {
    uint256 public constant MAX_MOVE_BPS = 2000;
    uint256 public constant MIN_INTERVAL = 1 hours;

    struct Price { uint192 value; uint64 updatedAt; }
    mapping(address fund => Price) private _prices;

    event PriceUpdated(address indexed fund, uint256 value);

    constructor() Ownable(msg.sender) {}

    /// value: tINR base units for one whole fund unit (1e6 base units).
    function setPrice(address fund, uint192 value) external onlyOwner {
        require(value > 0, "zero price");
        Price memory old = _prices[fund];
        if (old.value != 0) {
            require(block.timestamp >= old.updatedAt + MIN_INTERVAL, "too soon");
            uint256 diff = value > old.value ? value - old.value : old.value - value;
            require(diff * 10_000 <= uint256(old.value) * MAX_MOVE_BPS, "move too large");
        }
        _prices[fund] = Price(value, uint64(block.timestamp));
        emit PriceUpdated(fund, value);
    }

    function price(address fund) external view returns (uint256 value, uint256 updatedAt) {
        Price memory p = _prices[fund];
        return (p.value, p.updatedAt);
    }
}
