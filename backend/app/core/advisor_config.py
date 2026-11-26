"""Phase 9 advisor settings: the ONE place to edit timeouts, freshness rules
and which modules the advisor reads. Our own choices, not from a source.
"""

ADVISOR_VERSION = "advisor-v1"

# Each module must answer within this many seconds or it is reported as
# unavailable and the advice is marked partial. Holdings can fetch fund NAVs
# over the network (cached), so it gets longer.
MODULE_TIMEOUT_SECONDS = 5.0
MODULE_TIMEOUTS_SECONDS: dict[str, float] = {"holdings": 10.0}

# Data older than this is still used, but reported as stale.
STALE_AFTER_DAYS: dict[str, int] = {
    "sectors": 7,
    "sentiment": 7,
    "predictions": 7,
    # A portfolio plan is rebuilt by the user; after a month prices, profile
    # or goals have likely moved on.
    "portfolio_plan": 30,
}

# The prediction horizon the advisor shows ranges for: one year.
PREDICTION_HORIZON_TRADING_DAYS = 252

# Fund names containing these words are classed as debt or gold when a
# holding isn't one of the configured Phase 7 funds. Anything else that
# isn't a stock is "unclassified" and left out of drift checks rather than
# guessed.
DEBT_FUND_WORDS = (
    "liquid", "debt", "bond", "gilt", "duration", "money market", "overnight", "income",
)
GOLD_FUND_WORDS = ("gold",)

# The modules the advisor reads, in the order they're shown.
MODULES: dict[str, tuple[str, int | None]] = {
    # id: (label, phase)
    "budget": ("Budget health", 8),
    "goals": ("Goals", 8),
    "risk_profile": ("Risk profile", 7),
    "portfolio_plan": ("Portfolio plan", 7),
    "holdings": ("Your holdings", 2),
    "sectors": ("Sector trends", 6),
    "sentiment": ("News sentiment", 5),
    "predictions": ("Stock return ranges", 4),
}
