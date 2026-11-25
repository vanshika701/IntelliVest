// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Mandate} from "./Types.sol";

interface IOwned { function owner() external view returns (address); }

/// The terms each vault owner has agreed to. Only the owner can write them;
/// there is no admin. A new mandate replaces the old fund and model lists.
contract MandateManager {
    mapping(address vault => uint256) public versionOf;
    mapping(address vault => bool) public active;
    mapping(address vault => Mandate) private _mandates;
    mapping(address vault => mapping(uint256 version => mapping(address fund => bool))) private _funds;
    mapping(address vault => mapping(uint256 version => mapping(bytes32 key => bool))) private _models;

    event MandateSet(address indexed vault, uint256 version, Mandate mandate, address[] funds, bytes32[] models);
    event MandateRevoked(address indexed vault);
    event ModelAcceptance(address indexed vault, bytes32 indexed key, bool accepted);

    modifier onlyVaultOwner(address vault) {
        require(IOwned(vault).owner() == msg.sender, "not vault owner");
        _;
    }

    function setMandate(address vault, Mandate calldata m, address[] calldata funds, bytes32[] calldata models)
        external onlyVaultOwner(vault)
    {
        require(m.end > m.start && m.end > block.timestamp, "bad dates");
        require(m.maxEquityBps <= 10_000 && m.maxSlippageBps <= 10_000 && m.maxLossBps <= 10_000
            && m.confidenceThreshold <= 10_000, "bad bps");
        uint256 v = ++versionOf[vault];
        _mandates[vault] = m;
        active[vault] = true;
        for (uint256 i; i < funds.length; ++i) _funds[vault][v][funds[i]] = true;
        for (uint256 i; i < models.length; ++i) _models[vault][v][models[i]] = true;
        emit MandateSet(vault, v, m, funds, models);
    }

    function acceptModel(address vault, bytes32 key, bool accepted) external onlyVaultOwner(vault) {
        _models[vault][versionOf[vault]][key] = accepted;
        emit ModelAcceptance(vault, key, accepted);
    }

    /// Stops the AI at once.
    function revokeMandate(address vault) external onlyVaultOwner(vault) {
        active[vault] = false;
        emit MandateRevoked(vault);
    }

    function mandateOf(address vault) external view returns (Mandate memory) { return _mandates[vault]; }
    function fundAllowed(address vault, address fund) external view returns (bool) { return _funds[vault][versionOf[vault]][fund]; }
    function modelAccepted(address vault, bytes32 key) external view returns (bool) { return _models[vault][versionOf[vault]][key]; }
}
