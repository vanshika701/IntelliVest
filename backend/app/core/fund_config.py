"""Phase 7 debt and gold funds: the ONE place to edit which mutual funds
fill the non-equity parts of a recommendation.

How they were chosen (2026-11-26, from mfapi.in's full AMFI scheme list):
- Direct plan, Growth option (no distributor commission, no payouts).
- Large, long-running schemes from different fund houses, two per role,
  so one can stand in if the other is closed or its data goes stale.
- Only schemes whose AMFI category matches the role. Some live schemes
  still carry pre-2018 category names (e.g. "Income/Debt Oriented
  Schemes - Short Term Fund"); those were skipped.
- Gold uses funds of funds rather than gold ETFs, so investing needs no
  demat account and SIPs work like any other mutual fund.
- Long-horizon debt uses corporate bond funds: SEBI requires them to hold
  at least 80% in AA+ or higher rated bonds, so credit risk stays low.

Not considered: expense ratio and fund size, because our free data
sources don't provide them reliably. Both matter; check them before
investing. Names, not recommendations of these specific schemes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FundChoice:
    scheme_code: int
    name: str


@dataclass(frozen=True)
class FundRole:
    id: str  # matches allocation_config debt_style, or "gold"
    label: str
    category_keyword: str  # must appear in the scheme's AMFI category
    choices: tuple[FundChoice, ...]  # first usable one wins


FUND_ROLES: dict[str, FundRole] = {
    "liquid": FundRole(
        "liquid", "Liquid fund", "Liquid Fund",
        (FundChoice(119091, "HDFC Liquid Fund - Direct Plan - Growth Option"),
         FundChoice(119800, "SBI Liquid Fund - Direct Plan - Growth")),
    ),
    "short_duration": FundRole(
        "short_duration", "Short duration debt fund", "Short Duration Fund",
        (FundChoice(120754, "ICICI Prudential Short Term Fund - Direct Plan - Growth"),
         FundChoice(119498, "Aditya Birla Sun Life Short Term Fund - Direct Plan - Growth")),
    ),
    "medium_duration": FundRole(
        "medium_duration", "Corporate bond fund", "Corporate Bond Fund",
        (FundChoice(118987, "HDFC Corporate Bond Fund - Direct Plan - Growth Option"),
         FundChoice(120692, "ICICI Prudential Corporate Bond Fund - Direct Plan - Growth")),
    ),
    "gold": FundRole(
        "gold", "Gold fund of funds", "FoF Domestic",
        (FundChoice(119788, "SBI Gold Fund - Direct Plan - Growth"),
         FundChoice(118663, "Nippon India Gold Savings Fund - Direct Plan - Growth Option")),
    ),
}

# A fund whose latest NAV is older than this is treated as unavailable.
MAX_NAV_AGE_DAYS = 10
