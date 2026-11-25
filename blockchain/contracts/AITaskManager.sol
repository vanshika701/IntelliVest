// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {InvestmentVault} from "./InvestmentVault.sol";
import {MandateManager} from "./MandateManager.sol";
import {ModelRegistry} from "./ModelRegistry.sol";
import "./Types.sol";

/// Mode 2: coordinates signed results from off-chain AI. A signature shows
/// who submitted a result, not that a model ran or is right.
///
/// Anyone may relay signed messages. Bad signatures revert, so outsiders
/// can't end a task. A validly signed proposal that breaks the rules is
/// stored as REJECTED with a reason. There is no admin.
contract AITaskManager is EIP712, ReentrancyGuard {
    bytes32 public constant EVIDENCE_TYPEHASH = keccak256(
        "Evidence(bytes32 taskId,uint8 step,uint8 status,bytes32 modelId,bytes32 modelVersion,bytes32 inputHash,bytes32 outputHash,int32 score,uint32 count,uint32 horizonDays,uint64 asOf)"
    );
    bytes32 public constant PROPOSAL_TYPEHASH = keccak256(
        "Proposal(bytes32 taskId,address vault,address fund,uint8 side,uint256 amount,uint256 minimumReceived,uint16 confidence,bytes32 modelId,bytes32 modelVersion,bytes32 inputHash,bytes32 evidenceHash,bytes32 explanationHash,uint256 nonce,uint64 deadline)"
    );
    uint256 public constant MAX_EVIDENCE_AGE = 7 days;
    uint256 public constant MAX_TASK_LENGTH = 7 days;
    uint256 public constant MIN_EXECUTION_GAS = 1_500_000;

    struct Task {
        address vault;
        address fund;
        uint64 deadline;
        Outcome outcome;
        Reason reason;
        bytes32 evidenceHash;
    }
    struct StoredEvidence { bytes32 modelKey; uint64 asOf; EvidenceStatus status; bool present; }

    ModelRegistry public immutable registry;
    MandateManager public immutable mandates;

    uint256 public taskCount;
    mapping(bytes32 taskId => Task) public tasks;
    mapping(bytes32 taskId => mapping(uint8 step => StoredEvidence)) public evidenceOf;
    mapping(bytes32 taskId => Proposal) private _proposals;
    mapping(address vault => mapping(uint256 nonce => bool)) public nonceUsed;

    event TaskOpened(bytes32 indexed taskId, address indexed vault, address indexed fund, uint64 deadline, address opener);
    event EvidenceSubmitted(bytes32 indexed taskId, uint8 indexed step, Evidence evidence, address signer, bytes32 evidenceHash);
    event ProposalSubmitted(bytes32 indexed taskId, Proposal proposal, address signer);
    event TaskResult(bytes32 indexed taskId, address indexed vault, Outcome outcome, Reason reason, uint256 amountOut);

    constructor(ModelRegistry registry_, MandateManager mandates_) EIP712("IntelliVest", "1") {
        registry = registry_;
        mandates = mandates_;
    }

    function openTask(address vault, address fund, uint64 deadline) external returns (bytes32 taskId) {
        require(deadline > block.timestamp && deadline <= block.timestamp + MAX_TASK_LENGTH, "bad deadline");
        taskId = keccak256(abi.encode(block.chainid, address(this), vault, fund, ++taskCount));
        tasks[taskId] = Task(vault, fund, deadline, Outcome.OPEN, Reason.NONE, bytes32(0));
        emit TaskOpened(taskId, vault, fund, deadline, msg.sender);
    }

    function submitEvidence(Evidence calldata e, bytes calldata signature) external {
        Task storage task = tasks[e.taskId];
        require(task.outcome == Outcome.OPEN && block.timestamp <= task.deadline, "task closed");
        require(e.step == uint8(Step.SENTIMENT) || e.step == uint8(Step.STOCK_PREDICTION), "bad step");
        require(e.status <= uint8(EvidenceStatus.FALLBACK) && e.asOf <= block.timestamp, "bad evidence");
        require(e.score <= 10_000 && e.score >= (e.step == uint8(Step.SENTIMENT) ? int32(-10_000) : int32(0)), "bad score");
        require(!evidenceOf[e.taskId][e.step].present, "duplicate step");

        bytes32 structHash = hashEvidence(e);
        bytes32 key = registry.keyOf(e.modelId, e.modelVersion);
        ModelRegistry.Version memory v = registry.get(key);
        require(v.signer != address(0) && !v.revoked && uint8(v.step) == e.step, "model not active");
        require(ECDSA.recover(_hashTypedDataV4(structHash), signature) == v.signer, "bad signature");

        evidenceOf[e.taskId][e.step] = StoredEvidence(key, e.asOf, EvidenceStatus(e.status), true);
        bytes32 chained = keccak256(abi.encode(task.evidenceHash, structHash));
        task.evidenceHash = chained;
        emit EvidenceSubmitted(e.taskId, e.step, e, v.signer, chained);
    }

    function submitProposal(Proposal calldata p, bytes calldata signature) external nonReentrant {
        Task storage task = tasks[p.taskId];
        require(task.outcome == Outcome.OPEN, "task closed");
        require(p.vault == task.vault && p.fund == task.fund && p.side <= uint8(Side.SELL), "wrong task");
        require(p.confidence <= 10_000, "bad confidence");
        require(!nonceUsed[p.vault][p.nonce], "nonce used");
        ModelRegistry.Version memory v = registry.get(registry.keyOf(p.modelId, p.modelVersion));
        require(v.signer != address(0) && v.step == Step.ADVISOR, "not an advisor");
        require(ECDSA.recover(_hashTypedDataV4(hashProposal(p)), signature) == v.signer, "bad signature");

        nonceUsed[p.vault][p.nonce] = true;
        _proposals[p.taskId] = p;
        emit ProposalSubmitted(p.taskId, p, v.signer);
        _decide(p.taskId, p, false);
    }

    /// The owner's approval replaces only the "ask the user" step. Hard
    /// limits, model status and deadlines are all checked again.
    function approve(bytes32 taskId) external nonReentrant {
        _requirePendingOwner(taskId);
        _decide(taskId, _proposals[taskId], true);
    }

    function decline(bytes32 taskId) external nonReentrant {
        _requirePendingOwner(taskId);
        _finish(taskId, Outcome.REJECTED, Reason.USER_DECLINED, 0);
    }

    /// Closes a task that ran out of time.
    function expire(bytes32 taskId) external nonReentrant {
        Task storage task = tasks[taskId];
        bool openLate = task.outcome == Outcome.OPEN && block.timestamp > task.deadline;
        bool pendingLate = task.outcome == Outcome.PENDING_USER && block.timestamp > _proposals[taskId].deadline;
        require(openLate || pendingLate, "not expired");
        _finish(taskId, Outcome.REJECTED, Reason.EXPIRED, 0);
    }

    function proposalOf(bytes32 taskId) external view returns (Proposal memory) { return _proposals[taskId]; }
    function domainSeparator() external view returns (bytes32) { return _domainSeparatorV4(); }

    function hashEvidence(Evidence calldata e) public pure returns (bytes32) {
        return keccak256(abi.encode(EVIDENCE_TYPEHASH, e));
    }

    function hashProposal(Proposal calldata p) public pure returns (bytes32) {
        return keccak256(abi.encode(PROPOSAL_TYPEHASH, p));
    }

    // --- Internal ---

    function _requirePendingOwner(bytes32 taskId) private view {
        Task storage task = tasks[taskId];
        require(task.outcome == Outcome.PENDING_USER, "not pending");
        require(InvestmentVault(task.vault).owner() == msg.sender, "not vault owner");
    }

    function _decide(bytes32 taskId, Proposal memory p, bool approved) private {
        (Reason reason, bool noData) = _checkAi(taskId, p);
        if (reason != Reason.NONE) return _finish(taskId, Outcome.REJECTED, reason, 0);

        InvestmentVault vault = InvestmentVault(p.vault);
        uint256 value;
        (reason, value) = vault.checkTrade(p.fund, Side(p.side), p.amount);
        // A loss-limit breach goes through executeAi so the vault pauses itself.
        if (reason != Reason.NONE && reason != Reason.LOSS_LIMIT) {
            return _finish(taskId, Outcome.REJECTED, reason, 0);
        }
        if (reason == Reason.NONE && !approved) {
            Mandate memory m = mandates.mandateOf(p.vault);
            if (noData || p.confidence < m.confidenceThreshold || value > m.userSignAbove) {
                return _finish(taskId, Outcome.PENDING_USER, Reason.NONE, 0);
            }
        }
        // Otherwise a relayer could starve the trade of gas to force a rejection.
        require(gasleft() >= MIN_EXECUTION_GAS, "not enough gas");
        try vault.executeAi(taskId, p.fund, Side(p.side), p.amount, p.minimumReceived) returns (Reason r, uint256 out) {
            _finish(taskId, r == Reason.NONE ? Outcome.EXECUTED : Outcome.REJECTED, r, out);
        } catch {
            _finish(taskId, Outcome.REJECTED, Reason.EXECUTION_FAILED, 0);
        }
    }

    function _checkAi(bytes32 taskId, Proposal memory p) private view returns (Reason reason, bool noData) {
        Task storage task = tasks[taskId];
        if (block.timestamp > p.deadline || (task.outcome == Outcome.OPEN && block.timestamp > task.deadline)) {
            return (Reason.EXPIRED, false);
        }
        if (!mandates.active(p.vault)) return (Reason.NO_MANDATE, false);
        bytes32 key = registry.keyOf(p.modelId, p.modelVersion);
        if (registry.get(key).revoked) return (Reason.MODEL_INACTIVE, false);
        if (!mandates.modelAccepted(p.vault, key)) return (Reason.MODEL_NOT_ACCEPTED, false);
        if (p.evidenceHash != task.evidenceHash) return (Reason.EVIDENCE_MISMATCH, false);

        Mandate memory m = mandates.mandateOf(p.vault);
        bool missing;
        (reason, missing) = _checkStep(taskId, p.vault, Step.SENTIMENT, m.requireSentiment);
        if (reason != Reason.NONE) return (reason, false);
        noData = missing;
        (reason, missing) = _checkStep(taskId, p.vault, Step.STOCK_PREDICTION, m.requireStock);
        if (reason != Reason.NONE) return (reason, false);
        noData = noData || missing;
        if (noData && !m.askUserOnNoData) return (Reason.NO_DATA_NOT_ALLOWED, true);
    }

    function _checkStep(bytes32 taskId, address vault, Step step, bool required)
        private view returns (Reason reason, bool noData)
    {
        StoredEvidence memory e = evidenceOf[taskId][uint8(step)];
        if (!e.present) return (required ? Reason.MISSING_EVIDENCE : Reason.NONE, false);
        if (registry.get(e.modelKey).revoked) return (Reason.MODEL_INACTIVE, false);
        if (block.timestamp > e.asOf + MAX_EVIDENCE_AGE) return (Reason.EVIDENCE_STALE, false);
        if (e.status != EvidenceStatus.OK) return (Reason.NONE, true);
        if (!mandates.modelAccepted(vault, e.modelKey)) return (Reason.MODEL_NOT_ACCEPTED, false);
    }

    function _finish(bytes32 taskId, Outcome outcome, Reason reason, uint256 amountOut) private {
        tasks[taskId].outcome = outcome;
        tasks[taskId].reason = reason;
        emit TaskResult(taskId, tasks[taskId].vault, outcome, reason, amountOut);
    }
}
