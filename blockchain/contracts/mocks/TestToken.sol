// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// Worthless test token. Anyone can use the faucet if it is enabled.
contract TestToken is ERC20, Ownable {
    uint256 public constant FAUCET_LIMIT = 1_000_000e6;
    bool public immutable faucetEnabled;
    mapping(address => bool) public isMinter;

    constructor(string memory name_, string memory symbol_, bool faucet_)
        ERC20(name_, symbol_) Ownable(msg.sender)
    {
        faucetEnabled = faucet_;
    }

    function decimals() public pure override returns (uint8) { return 6; }

    function setMinter(address account, bool allowed) external onlyOwner { isMinter[account] = allowed; }

    function faucet(uint256 amount) external {
        require(faucetEnabled && amount <= FAUCET_LIMIT, "faucet");
        _mint(msg.sender, amount);
    }

    function mint(address to, uint256 amount) external {
        require(isMinter[msg.sender], "not minter");
        _mint(to, amount);
    }

    function burn(uint256 amount) external { _burn(msg.sender, amount); }
}
