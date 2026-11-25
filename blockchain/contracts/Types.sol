// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

// Shared formats. Documented in docs/PHASE_10_BLOCKCHAIN.md; changing a
// signed struct means updating the Python hashing and the test vectors too.

enum Step { NONE, SENTIMENT, STOCK_PREDICTION, ADVISOR }
enum EvidenceStatus { OK, NO_DATA, FALLBACK }
enum Side { BUY, SELL }
enum Outcome { NONE, OPEN, PENDING_USER, EXECUTED, REJECTED }

enum Reason {
    NONE,
    NO_MANDATE,
    OUTSIDE_DATES,
    AI_PAUSED,
    FUND_NOT_ALLOWED,
    BAD_AMOUNT,
    OVER_TRADE_CAP,
    OVER_DAILY_CAP,
    OVER_MONTHLY_CAP,
    TOO_MANY_TRADES,
    OVER_EQUITY_LIMIT,
    STALE_PRICE,
    LOSS_LIMIT,
    MODEL_INACTIVE,
    MODEL_NOT_ACCEPTED,
    MISSING_EVIDENCE,
    NO_DATA_NOT_ALLOWED,
    EVIDENCE_MISMATCH,
    EVIDENCE_STALE,
    EXPIRED,
    EXECUTION_FAILED,
    USER_DECLINED
}

/// Scores are integers: sentiment -10000..10000; stock prediction is the
/// probability of "up", 0..10000 (direction is up when it is >= 5000).
struct Evidence {
    bytes32 taskId;
    uint8 step;
    uint8 status;
    bytes32 modelId;
    bytes32 modelVersion;
    bytes32 inputHash;
    bytes32 outputHash;
    int32 score;
    uint32 count;
    uint32 horizonDays;
    uint64 asOf;
}

/// amount is tINR for a BUY and fund units for a SELL. minimumReceived is
/// in the other token. All test tokens have 6 decimals.
struct Proposal {
    bytes32 taskId;
    address vault;
    address fund;
    uint8 side;
    uint256 amount;
    uint256 minimumReceived;
    uint16 confidence;
    bytes32 modelId;
    bytes32 modelVersion;
    bytes32 inputHash;
    bytes32 evidenceHash;
    bytes32 explanationHash;
    uint256 nonce;
    uint64 deadline;
}

struct Mandate {
    uint64 start;
    uint64 end;
    uint128 perTradeCap;
    uint128 dailyCap;
    uint128 monthlyCap;
    uint128 userSignAbove; // trades worth more than this need the owner
    uint16 maxEquityBps;
    uint16 maxSlippageBps;
    uint16 maxLossBps;
    uint16 maxTradesPerDay;
    uint16 confidenceThreshold; // below this the owner must approve
    bool requireSentiment;
    bool requireStock;
    bool askUserOnNoData; // false: missing data rejects the trade
}
