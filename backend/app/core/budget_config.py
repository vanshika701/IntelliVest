"""Phase 8 budgeting config: the ONE place to edit categories, benchmarks
and return assumptions. Everything here is a product decision, not a
secret, so it lives in code (reviewable, version-controlled) next to
`constants.py` rather than in `.env`.

Sources (pages opened and read 2026-11-25; details and what could not be
verified are in docs/PHASE_8_BUDGETING.md):
- 50/30/20 of after-tax income, Warren & Tyagi, "All Your Worth" (2005):
  https://www.experian.com/blogs/ask-experian/what-is-the-50-30-20-rule/
- Emergency fund of 3-6 months:
  https://www.empower.com/the-currency/play/50-30-20-budget-rule-explained
- 28% housing / 36% total debt, of GROSS income (we use take-home, which is
  stricter): https://www.bankrate.com/mortgages/what-is-the-28-36-rule/
- India: 25-35% of take-home is a safe EMI level, though banks lend up to 40-55%
  of gross: https://www.finnovate.in/learn/blog/home-loan-emi-affordability-india
- Returns: 3-year SBI FD 6.3% (https://scripbox.com/mf/sbi-fd-interest-rates);
  Nifty 50 TRI 20-year CAGR about 12.4% (Bajaj AMC quoting NSE,
  https://www.bajajamc.com/knowledge-centre/nifty-50-historical-returns). We
  assume less than both; the 3-5 year figure is our own value in between.
- The other category ranges are our own rules of thumb, not from a source.
"""

from dataclasses import dataclass
from typing import Literal

Bucket = Literal["needs", "wants", "savings"]


@dataclass(frozen=True)
class Category:
    id: str  # stable id stored on expenses — never rename
    name: str  # display label — safe to edit
    bucket: Bucket
    # Guideline as % of monthly take-home income. None = no bound.
    min_pct: float | None = None
    max_pct: float | None = None
    note: str | None = None


# Edit this list to change the categories offered in the app. Keep ids stable:
# they're what's stored on expense records and budget profiles.
CATEGORIES: list[Category] = [
    Category("housing", "Housing & Rent", "needs", 25, 35),
    Category("groceries", "Groceries", "needs", 8, 12),
    Category("food_dining", "Food & Dining Out", "wants", 3, 6),
    Category("transportation", "Transportation", "needs", 5, 10),
    Category("utilities", "Utilities & Bills", "needs", 5, 8),
    Category("health_insurance", "Health & Insurance", "needs", 5, 8),
    Category("shopping_personal", "Shopping & Personal Care", "wants", 3, 6),
    Category("entertainment", "Entertainment & Leisure", "wants", 3, 5),
    Category("travel", "Travel", "wants", 2, 5),
    Category("education", "Education", "needs", None, None, "As needed — no fixed benchmark"),
    Category("emi_debt", "EMI / Debt Repayment", "needs", 0, 30, "Flagged as critical above 36%"),
    Category("savings_investments", "Savings & Investments", "savings", 20, None, "Aim for at least 20%"),
    Category("other", "Other / Miscellaneous", "wants", None, None),
]

CATEGORY_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}
SPENDING_CATEGORY_IDS: list[str] = [c.id for c in CATEGORIES]
# Income records aren't spending; they get this fixed category.
INCOME_CATEGORY_ID = "income"
FALLBACK_CATEGORY_ID = "other"


# --- Income sources ---------------------------------------------------------

IncomeGroup = Literal["job", "investments", "other"]
INCOME_GROUPS: dict[IncomeGroup, str] = {"job": "Job", "investments": "Investments", "other": "Other"}


@dataclass(frozen=True)
class IncomeSource:
    id: str  # stored on income records, so never rename
    name: str
    group: IncomeGroup


INCOME_SOURCES: list[IncomeSource] = [
    IncomeSource("salary", "Salary", "job"),
    IncomeSource("bonus", "Bonus / incentive", "job"),
    IncomeSource("commission", "Commission / overtime", "job"),
    IncomeSource("part_time", "Part-time job", "job"),
    IncomeSource("stipend", "Internship stipend", "job"),
    IncomeSource("dividends", "Dividends", "investments"),
    IncomeSource("interest", "Interest (FD, RD, savings, bonds)", "investments"),
    IncomeSource("capital_gains", "Profit from selling investments", "investments"),
    IncomeSource("rental", "Rental income", "investments"),
    IncomeSource("business", "Business", "other"),
    IncomeSource("freelance", "Freelance / gig work", "other"),
    IncomeSource("content_royalties", "Content / royalties", "other"),
    IncomeSource("pension", "Pension", "other"),
    IncomeSource("scholarship_benefits", "Scholarship / government benefit", "other"),
    IncomeSource("gift_family", "Gift / family support", "other"),
    IncomeSource("refund_cashback", "Refund / cashback", "other"),
    IncomeSource("other_income", "Other income", "other"),
]
INCOME_SOURCE_BY_ID: dict[str, IncomeSource] = {s.id: s for s in INCOME_SOURCES}

# 50/30/20 targets as % of take-home income.
BUCKET_TARGETS_PCT: dict[Bucket, float] = {"needs": 50, "wants": 30, "savings": 20}

# Total EMIs above this % of take-home are flagged as critical.
DEBT_TO_INCOME_CRITICAL_PCT = 36.0

# Emergency fund target, in months of essential ("needs") spending.
EMERGENCY_FUND_MIN_MONTHS = 3
EMERGENCY_FUND_MAX_MONTHS = 6

# How many calendar months of logged expenses "actual" spending averages over.
ACTUAL_WINDOW_MONTHS = 3

# --- Financial health score (0-100). Weights and scales are our own product
# choices built on the thresholds above; they are not from a published index.
# A weight is how many of the 100 points a part is worth, not a share of income.
HEALTH_WEIGHTS: dict[str, float] = {
    "savings": 20,
    "emergency": 15,
    "debt": 15,
    "housing": 12,
    "groceries": 8,
    "household": 10,
    "lifestyle": 20,
}
# Spending parts of the score, and the categories each one covers. Full marks up
# to the sum of their guideline maximums, none at HEALTH_SPEND_ZERO_RATIO times it.
HEALTH_SPEND_GROUPS: dict[str, tuple[str, list[str]]] = {
    "housing": ("Rent / housing", ["housing"]),
    "groceries": ("Groceries", ["groceries"]),
    "household": ("Bills, transport and health", ["utilities", "transportation", "health_insurance"]),
    "lifestyle": ("Lifestyle spending", ["food_dining", "shopping_personal", "entertainment", "travel"]),
}
# Living rent-free or spending nothing on lifestyle is real; no groceries or
# bills at all means they weren't entered.
HEALTH_ZERO_IS_REAL = {"housing", "lifestyle"}
HEALTH_SPEND_ZERO_RATIO = 2.0
HEALTH_DEBT_FULL_PCT = 30.0  # EMI share of income that still earns full marks
HEALTH_DEBT_ZERO_PCT = 50.0  # EMI share that earns none
HEALTH_BANDS: list[tuple[float, str]] = [(75, "Good"), (50, "Fair"), (0, "Needs attention")]

# Top N other over-benchmark categories listed alongside a focus category.
TOP_OTHER_OVERSPENDS = 3


# --- Goal / SIP assumptions -------------------------------------------------

@dataclass(frozen=True)
class ReturnAssumption:
    max_months: int | None  # inclusive upper bound; None = no limit
    annual_return_pct: float
    label: str


# Default expected annual return by goal horizon (first match wins).
RETURN_ASSUMPTIONS: list[ReturnAssumption] = [
    ReturnAssumption(36, 6.0, "Up to 3 years: FDs, RDs, short-duration debt funds (~6%)"),
    ReturnAssumption(60, 8.0, "3-5 years: hybrid / balanced funds (between debt and equity)"),
    ReturnAssumption(None, 11.0, "5+ years: equity-oriented funds (~10-12%)"),
]

DEFAULT_STEP_UP_PCT = 10.0
SHORT_HORIZON_MONTHS = 36  # at or below this, show the volatility note
MAX_GOAL_HORIZON_MONTHS = 600  # 50 years
# When suggesting "extend the timeline", search up to this many months.
MAX_EXTENSION_SEARCH_MONTHS = 360

SAFER_INSTRUMENTS_NOTE = (
    "For goals 3 years or less away, equity can fall sharply right when you need the money. "
    "Lower-volatility options such as recurring deposits (RDs), short-duration debt funds or "
    "conservative hybrid funds are commonly used for this. General information only."
)

DISCLAIMER = (
    "Illustrative estimates only. Returns are assumed, not guaranteed, and actual results "
    "will vary. This is not professional financial advice."
)


def default_return_for(months: int) -> ReturnAssumption:
    for assumption in RETURN_ASSUMPTIONS:
        if assumption.max_months is None or months <= assumption.max_months:
            return assumption
    return RETURN_ASSUMPTIONS[-1]
