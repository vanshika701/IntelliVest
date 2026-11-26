"""Phase 7 equity optimizer limits: the ONE place to edit them. Our own
choices (not from a source), picked to keep the equity part diversified
and the role of sentiment small and visible.
"""

OPTIMIZER_VERSION = "minvar-v1"

# No single stock above 15% and no sector above 35% of the equity part.
# Together they force at least 7 holdings across at least 3 sectors.
MAX_STOCK_WEIGHT = 0.15
MAX_SECTOR_WEIGHT = 0.35

# Weights below this are dropped and the rest re-optimised: a 0.3%
# holding adds paperwork, not diversification.
MIN_HOLDING_WEIGHT = 0.01

# Sentiment tilt. Starting from the minimum-variance weights, move towards
# stocks with better recent news, but:
# - the portfolio's variance may rise by at most this fraction, and
SENTIMENT_MAX_VARIANCE_INCREASE = 0.05
# - no stock's weight may move by more than this many percentage points.
SENTIMENT_MAX_WEIGHT_SHIFT = 0.03
# A stock needs this many scored articles for its sentiment to count;
# with fewer, it is treated as neutral (same rule as Phase 5 labels).
SENTIMENT_MIN_ARTICLES = 3
