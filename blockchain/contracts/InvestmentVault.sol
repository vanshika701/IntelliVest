// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {MandateManager} from "./MandateManager.sol";
import {MockFundMarket} from "./mocks/MockFundMarket.sol";
import {MockPriceFeed} from "./mocks/MockPriceFeed.sol";
import {Mandate, Reason, Side} from "./Types.sol";

/// Holds one user's test tokens. Not upgradeable and has no admin.
/// Withdrawals go only to the owner and depend on no other project contract.
contract InvestmentVault is ReentrancyGuard {
    using SafeERC20 for IERC20;

    uint256 public constant MAX_PRICE_AGE = 1 days;

    struct Sip {
        address fund;
        uint128 amount;
        uint16 maxSlippageBps;
        uint8 dayOfMonth;
        uint64 nextRun;
        uint64 end;
    }

    address public immutable owner;
    address public immutable taskManager;
    MandateManager public immutable mandates;
    MockFundMarket public immutable market;
    MockPriceFeed public immutable feed;
    IERC20 public immutable inr;

    bool public aiPaused;
    /// Value the loss limit is measured against. Reset on the next AI trade
    /// after the owner withdraws or resumes.
    uint256 public baseline;
    bool public baselineStale;
    Sip public sip;

    mapping(uint256 day => uint256) public spentOnDay;
    mapping(uint256 day => uint256) public tradesOnDay;
    mapping(uint256 period => uint256) public spentInPeriod;

    event Deposited(address indexed from, uint256 amount);
    event Withdrawn(address indexed token, uint256 amount);
    event AiPaused(bool paused, Reason reason);
    event Traded(bytes32 indexed taskId, address indexed fund, Side side, uint256 amountIn, uint256 amountOut, uint256 price, uint256 priceTime);
    event SipSet(address indexed fund, uint256 amount, uint8 dayOfMonth, uint64 nextRun, uint64 end);
    event SipRun(address indexed fund, uint256 amountIn, uint256 amountOut, address runner);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(address owner_, address taskManager_, MandateManager mandates_, MockFundMarket market_) {
        owner = owner_;
        taskManager = taskManager_;
        mandates = mandates_;
        market = market_;
        feed = market_.feed();
        inr = IERC20(address(market_.inr()));
    }

    // --- Owner ---

    function deposit(uint256 amount) external nonReentrant {
        baseline += amount;
        inr.safeTransferFrom(msg.sender, address(this), amount);
        emit Deposited(msg.sender, amount);
    }

    /// Deliberately has no pause, price, mandate or backend dependency.
    function withdraw(address token, uint256 amount) external onlyOwner nonReentrant {
        baselineStale = true;
        IERC20(token).safeTransfer(owner, amount);
        emit Withdrawn(token, amount);
    }

    function setAiPaused(bool paused) external onlyOwner {
        aiPaused = paused;
        if (!paused) baselineStale = true;
        emit AiPaused(paused, Reason.NONE);
    }

    function ownerTrade(address fund, Side side, uint256 amount, uint256 minOut) external onlyOwner nonReentrant {
        _swap(bytes32(0), fund, side, amount, minOut);
    }

    // --- SIP: a fixed instruction from the owner, no AI involved ---

    function setSip(address fund, uint128 amount, uint8 dayOfMonth, uint16 maxSlippageBps, uint64 end) external onlyOwner {
        require(market.isFund(fund) && amount > 0 && dayOfMonth >= 1 && dayOfMonth <= 28, "bad sip");
        require(end > block.timestamp && maxSlippageBps <= 10_000, "bad sip");
        uint64 next = _nextMonthly(block.timestamp, dayOfMonth);
        sip = Sip(fund, amount, maxSlippageBps, dayOfMonth, next, end);
        emit SipSet(fund, amount, dayOfMonth, next, end);
    }

    function cancelSip() external onlyOwner {
        delete sip;
        emit SipSet(address(0), 0, 0, 0, 0);
    }

    /// Anyone may trigger this; they choose nothing. Missed months are skipped.
    function runSip() external nonReentrant {
        Sip memory s = sip;
        require(s.amount > 0 && block.timestamp >= s.nextRun && block.timestamp <= s.end, "sip not due");
        (uint256 price, bool fresh) = _price(s.fund);
        require(fresh, "stale price");
        sip.nextRun = _nextMonthly(block.timestamp, s.dayOfMonth);
        uint256 fair = uint256(s.amount) * 1e6 / price;
        uint256 out = _swap(bytes32(0), s.fund, Side.BUY, s.amount, fair * (10_000 - s.maxSlippageBps) / 10_000);
        emit SipRun(s.fund, s.amount, out, msg.sender);
    }

    // --- AI trades, through the task manager only ---

    /// Every hard limit. Returns a reason instead of reverting so the
    /// rejection can be recorded.
    function checkTrade(address fund, Side side, uint256 amount) public view returns (Reason reason, uint256 value) {
        Mandate memory m = mandates.mandateOf(address(this));
        if (!mandates.active(address(this))) return (Reason.NO_MANDATE, 0);
        if (block.timestamp < m.start || block.timestamp > m.end) return (Reason.OUTSIDE_DATES, 0);
        if (aiPaused) return (Reason.AI_PAUSED, 0);
        if (!mandates.fundAllowed(address(this), fund) || !market.isFund(fund)) return (Reason.FUND_NOT_ALLOWED, 0);
        (uint256 price, bool fresh) = _price(fund);
        if (!fresh) return (Reason.STALE_PRICE, 0);

        address tokenIn = side == Side.BUY ? address(inr) : fund;
        // Comparing with the balance first also rules out overflow below.
        if (amount == 0 || amount > IERC20(tokenIn).balanceOf(address(this))) return (Reason.BAD_AMOUNT, 0);
        value = side == Side.BUY ? amount : amount * price / 1e6;
        if (value == 0) return (Reason.BAD_AMOUNT, 0);
        if (value > m.perTradeCap) return (Reason.OVER_TRADE_CAP, value);
        if (spentOnDay[_day()] + value > m.dailyCap) return (Reason.OVER_DAILY_CAP, value);
        if (spentInPeriod[_period()] + value > m.monthlyCap) return (Reason.OVER_MONTHLY_CAP, value);
        if (tradesOnDay[_day()] >= m.maxTradesPerDay) return (Reason.TOO_MANY_TRADES, value);

        (uint256 total, uint256 equity, bool allFresh) = portfolio();
        if (!allFresh) return (Reason.STALE_PRICE, value);
        if (!baselineStale && total * 10_000 < baseline * (10_000 - m.maxLossBps)) return (Reason.LOSS_LIMIT, value);
        if (side == Side.BUY && market.isEquity(fund) && (equity + value) * 10_000 > total * m.maxEquityBps) {
            return (Reason.OVER_EQUITY_LIMIT, value);
        }
        return (Reason.NONE, value);
    }

    function executeAi(bytes32 taskId, address fund, Side side, uint256 amount, uint256 minOut)
        external nonReentrant returns (Reason reason, uint256 out)
    {
        require(msg.sender == taskManager, "not task manager");
        uint256 value;
        (reason, value) = checkTrade(fund, side, amount);
        if (reason == Reason.LOSS_LIMIT) {
            aiPaused = true;
            emit AiPaused(true, Reason.LOSS_LIMIT);
        }
        if (reason != Reason.NONE) return (reason, 0);

        if (baselineStale) {
            (baseline,,) = portfolio();
            baselineStale = false;
        }
        spentOnDay[_day()] += value;
        spentInPeriod[_period()] += value;
        tradesOnDay[_day()] += 1;

        (uint256 price,) = _price(fund);
        uint256 fair = side == Side.BUY ? amount * 1e6 / price : value;
        uint256 floor = fair * (10_000 - mandates.mandateOf(address(this)).maxSlippageBps) / 10_000;
        out = _swap(taskId, fund, side, amount, minOut > floor ? minOut : floor);
    }

    function portfolio() public view returns (uint256 total, uint256 equity, bool fresh) {
        total = inr.balanceOf(address(this));
        fresh = true;
        address[] memory list = market.funds();
        for (uint256 i; i < list.length; ++i) {
            uint256 balance = IERC20(list[i]).balanceOf(address(this));
            if (balance == 0) continue;
            (uint256 price, bool ok) = _price(list[i]);
            if (!ok) fresh = false;
            uint256 worth = balance * price / 1e6;
            total += worth;
            if (market.isEquity(list[i])) equity += worth;
        }
    }

    // --- Internal ---

    function _swap(bytes32 taskId, address fund, Side side, uint256 amount, uint256 minOut) private returns (uint256 out) {
        IERC20 tokenIn = side == Side.BUY ? inr : IERC20(fund);
        IERC20 tokenOut = side == Side.BUY ? IERC20(fund) : inr;
        uint256 beforeIn = tokenIn.balanceOf(address(this));
        uint256 beforeOut = tokenOut.balanceOf(address(this));
        tokenIn.forceApprove(address(market), amount);
        market.swap(fund, side, amount);
        tokenIn.forceApprove(address(market), 0);
        // Measure balances rather than trusting the market's return value.
        out = tokenOut.balanceOf(address(this)) - beforeOut;
        require(beforeIn - tokenIn.balanceOf(address(this)) == amount, "wrong input");
        require(out >= minOut && out > 0, "received too little");
        (uint256 price, uint256 time) = feed.price(fund);
        emit Traded(taskId, fund, side, amount, out, price, time);
    }

    function _price(address fund) private view returns (uint256 price, bool fresh) {
        uint256 updatedAt;
        (price, updatedAt) = feed.price(fund);
        fresh = price > 0 && block.timestamp <= updatedAt + MAX_PRICE_AGE;
    }

    /// Limits use fixed UTC days and fixed 30-day periods.
    function _day() private view returns (uint256) { return block.timestamp / 1 days; }
    function _period() private view returns (uint256) { return block.timestamp / 30 days; }

    /// First moment (UTC) of `dayOfMonth` strictly after today.
    function _nextMonthly(uint256 timestamp, uint8 dayOfMonth) private pure returns (uint64) {
        // Civil-date conversion (Howard Hinnant's algorithm).
        uint256 z = timestamp / 1 days + 719468;
        uint256 doe = z % 146097;
        uint256 yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        uint256 doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        uint256 mp = (5 * doy + 2) / 153;
        uint256 today = doy - (153 * mp + 2) / 5 + 1;
        // Months run from March here, so advancing is at most one year roll.
        uint256 year = yoe + (z / 146097) * 400;
        if (today >= dayOfMonth) {
            mp += 1;
            if (mp == 12) { mp = 0; year += 1; }
        }
        uint256 y = year % 400;
        uint256 dayOfEra = y * 365 + y / 4 - y / 100 + (153 * mp + 2) / 5 + dayOfMonth - 1;
        return uint64((year / 400 * 146097 + dayOfEra - 719468) * 1 days);
    }
}
