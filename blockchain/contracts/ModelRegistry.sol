// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Step} from "./Types.sol";

/// Which signer speaks for which model version. A version is fixed once
/// registered. Registering it does not let it act on a vault: each owner
/// must accept it in their mandate.
contract ModelRegistry is Ownable {
    struct Version { address signer; Step step; bool revoked; bytes32 artifactHash; }

    mapping(bytes32 key => Version) private _versions;

    event ModelRegistered(bytes32 indexed key, bytes32 indexed modelId, bytes32 version, Step step, address signer, bytes32 artifactHash);
    event ModelRevoked(bytes32 indexed key);

    constructor() Ownable(msg.sender) {}

    function keyOf(bytes32 modelId, bytes32 version) public pure returns (bytes32) {
        return keccak256(abi.encode(modelId, version));
    }

    function register(bytes32 modelId, bytes32 version, Step step, address signer, bytes32 artifactHash) external onlyOwner {
        bytes32 key = keyOf(modelId, version);
        require(_versions[key].signer == address(0), "already registered");
        require(signer != address(0) && step != Step.NONE, "bad version");
        _versions[key] = Version(signer, step, false, artifactHash);
        emit ModelRegistered(key, modelId, version, step, signer, artifactHash);
    }

    function revoke(bytes32 key) external onlyOwner {
        require(_versions[key].signer != address(0), "unknown model");
        _versions[key].revoked = true;
        emit ModelRevoked(key);
    }

    function get(bytes32 key) external view returns (Version memory) { return _versions[key]; }
}
