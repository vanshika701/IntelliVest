// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {InvestmentVault} from "./InvestmentVault.sol";
import {MandateManager} from "./MandateManager.sol";
import {MockFundMarket} from "./mocks/MockFundMarket.sol";

/// One vault per wallet.
contract VaultFactory {
    address public immutable taskManager;
    MandateManager public immutable mandates;
    MockFundMarket public immutable market;
    mapping(address owner => address) public vaultOf;

    event VaultCreated(address indexed owner, address vault);

    constructor(address taskManager_, MandateManager mandates_, MockFundMarket market_) {
        taskManager = taskManager_;
        mandates = mandates_;
        market = market_;
    }

    function createVault() external returns (address vault) {
        require(vaultOf[msg.sender] == address(0), "vault exists");
        vault = address(new InvestmentVault(msg.sender, taskManager, mandates, market));
        vaultOf[msg.sender] = vault;
        emit VaultCreated(msg.sender, vault);
    }
}
