"""Phase 7 asset allocation: the ONE place to edit how a risk profile and
goal horizon become an equity / debt / gold split. Product decisions,
kept in code so they are reviewed and versioned.

Sources (pages opened and read 2026-11-26):
- Conservative 15/75/10, Moderate 45/45/10 and Aggressive 75/15/10
  (equity / fixed income / gold), described as "indicative", with "a
  standard allocation of 10% in gold". No horizon is attached:
  https://mf.nipponindiaim.com/LearnAndInvest/Pages/Conservative-Risk-Analyzer.aspx
  https://mf.nipponindiaim.com/LearnAndInvest/Pages/moderate-risk-analyzer.aspx
  https://mf.nipponindiaim.com/LearnAndInvest/Pages/Risk-Analyzer.aspx
- The same evenly stepped pattern (20 percentage points of equity per
  step) appears in Vanguard's LifeStrategy funds (20/40/60/80% stocks):
  https://investor.vanguard.com/mutual-funds/lifestrategy
- 10% gold sits inside the World Gold Council's 7.5-15% range for Indian
  portfolios, as reported in press coverage of its 2026 research (the
  report itself was not read):
  https://www.gold.org/goldhub/research/why-gold-2026-anchor-indian-portfolios

Our own choices, not from a source:
- The two in-between profiles (30/60/10 and 60/30/10) are interpolated.
- The horizon limits below. They follow Phase 8's horizon bands
  (budget_config.RETURN_ASSUMPTIONS): equity can fall sharply right when
  short-term money is needed.
"""

from dataclasses import dataclass

ALLOCATION_VERSION = "alloc-v1"


@dataclass(frozen=True)
class Split:
    equity: int
    debt: int
    gold: int

    def __post_init__(self) -> None:
        if min(self.equity, self.debt, self.gold) < 0 or self.equity + self.debt + self.gold != 100:
            raise ValueError(f"Split must be non-negative and sum to 100: {self}")


# Long-horizon split per risk profile (horizon above the last limit below).
BASE_SPLITS: dict[str, Split] = {
    "conservative": Split(15, 75, 10),
    "moderately_conservative": Split(30, 60, 10),
    "moderate": Split(45, 45, 10),
    "moderately_aggressive": Split(60, 30, 10),
    "aggressive": Split(75, 15, 10),
}

# Which profiles' numbers come straight from a source; the rest are ours.
SOURCED_PROFILES = frozenset({"conservative", "moderate", "aggressive"})


@dataclass(frozen=True)
class HorizonLimit:
    max_months: int  # applies to horizons up to and including this
    max_equity: int
    max_gold: int
    debt_style: str  # what kind of debt fund suits money needed this soon
    reason: str


# First match wins. Anything cut from equity or gold moves to debt.
HORIZON_LIMITS: tuple[HorizonLimit, ...] = (
    HorizonLimit(
        12, 0, 0, "liquid",
        "Money needed within a year should not be in anything that can fall in value.",
    ),
    HorizonLimit(
        36, 0, 5, "short_duration",
        "For goals 3 years or less away, equity can fall sharply right when you need the money.",
    ),
    HorizonLimit(
        60, 40, 10, "short_duration",
        "For goals 3 to 5 years away, equity is limited so a fall has time to recover.",
    ),
)

# Horizons beyond every limit above.
LONG_HORIZON_DEBT_STYLE = "medium_duration"
