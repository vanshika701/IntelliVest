"""Fund metadata the free data sources don't provide: rating, fund size
(AUM), minimum SIP and minimum one-time investment.

`fund_meta_provider` is the single seam: swap MockFundMetaProvider for a
real implementation (e.g. a paid data feed or AMC factsheets) without
touching callers.
"""

import math
from typing import Protocol

# TODO(mock): replace with a real provider. Rating and AUM are unknown (None,
# shown as "—"); the MF minimums below are placeholder industry-typical
# defaults, flagged via `placeholder_fields`, not real per-scheme values.
PLACEHOLDER_MF_MIN_SIP = 500
PLACEHOLDER_MF_MIN_INVESTMENT = 1000


class FundMetaProvider(Protocol):
    async def get_meta(self, instrument_type: str, price: float | None) -> dict: ...


class MockFundMetaProvider:
    async def get_meta(self, instrument_type: str, price: float | None) -> dict:
        one_unit = math.ceil(price) if price else None
        if instrument_type == "STOCK":
            # Real, derived value: you can't buy less than one share.
            return _meta(min_sip=one_unit, min_investment=one_unit, placeholder_fields=[], source="derived")
        if instrument_type == "ETF":
            # One unit at NAV — approximate, since ETFs trade at exchange prices.
            return _meta(
                min_sip=one_unit,
                min_investment=one_unit,
                placeholder_fields=["min_sip", "min_investment"],
                source="placeholder",
            )
        return _meta(
            min_sip=PLACEHOLDER_MF_MIN_SIP,
            min_investment=PLACEHOLDER_MF_MIN_INVESTMENT,
            placeholder_fields=["min_sip", "min_investment"],
            source="placeholder",
        )


def _meta(min_sip, min_investment, placeholder_fields: list[str], source: str) -> dict:
    return {
        "rating": None,
        "aum_crore": None,
        "min_sip": min_sip,
        "min_investment": min_investment,
        "placeholder_fields": placeholder_fields,
        "source": source,
    }


fund_meta_provider: FundMetaProvider = MockFundMetaProvider()
