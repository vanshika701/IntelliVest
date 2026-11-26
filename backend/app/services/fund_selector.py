"""Phase 7 debt and gold funds: pick the first usable fund for each role
(core/fund_config.py) and describe it from its NAV history.

The NAV figures are what the recommendation shows as "how this part has
behaved"; like the stock figures, they describe the past, not a promise.
"""

import asyncio
import logging
import math
from datetime import date, timedelta
from itertools import pairwise

from app.core.fund_config import FUND_ROLES, MAX_NAV_AGE_DAYS, FundChoice, FundRole
from app.services import mfapi_client

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252

Navs = list[tuple[date, float]]


def _nav_on_or_before(navs: Navs, day: date) -> float | None:
    earlier = [nav for d, nav in navs if d <= day]
    return earlier[-1] if earlier else None


def annualised_return(navs: Navs, years: int) -> float | None:
    """Compound annual growth over the last `years` years, if the history is long enough."""
    if not navs:
        return None
    end_day, end_nav = navs[-1]
    start_nav = _nav_on_or_before(navs, end_day - timedelta(days=round(365.25 * years)))
    if start_nav is None:
        return None
    return round((end_nav / start_nav) ** (1 / years) - 1, 6)


def annualised_volatility(navs: Navs, days: int = 365) -> float | None:
    """Volatility of daily NAV changes over the last `days` calendar days."""
    if not navs:
        return None
    since = navs[-1][0] - timedelta(days=days)
    window = [nav for d, nav in navs if d >= since]
    if len(window) < 30:
        return None
    returns = [b / a - 1 for a, b in pairwise(window)]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return round(math.sqrt(variance * TRADING_DAYS_PER_YEAR), 6)


def max_drawdown(navs: Navs, days: int = 3 * 365) -> float | None:
    if not navs:
        return None
    since = navs[-1][0] - timedelta(days=days)
    peak, worst = 0.0, 0.0
    for d, nav in navs:
        if d < since:
            continue
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1)
    return round(worst, 6)


def unusable_reason(role: FundRole, scheme: dict | None, today: date) -> str | None:
    """Why this scheme can't fill the role, or None if it can."""
    if scheme is None:
        return "scheme not found"
    category = scheme["meta"].get("scheme_category") or ""
    if role.category_keyword.lower() not in category.lower():
        return f"category is '{category}', expected '{role.category_keyword}'"
    age = (today - scheme["navs"][-1][0]).days
    if age > MAX_NAV_AGE_DAYS:
        return f"latest NAV is {age} days old"
    return None


def describe_fund(role: FundRole, choice: FundChoice, scheme: dict) -> dict:
    navs = scheme["navs"]
    return {
        "role": role.id,
        "role_label": role.label,
        "instrument_id": f"mf-{choice.scheme_code}",  # opens the existing fund page
        "scheme_code": choice.scheme_code,
        "name": scheme["meta"].get("scheme_name") or choice.name,
        "fund_house": scheme["meta"].get("fund_house"),
        "category": scheme["meta"].get("scheme_category"),
        "nav": navs[-1][1],
        "nav_date": navs[-1][0],
        "return_1y": annualised_return(navs, 1),
        "return_3y": annualised_return(navs, 3),
        "annual_volatility": annualised_volatility(navs),
        "max_drawdown_3y": max_drawdown(navs),
    }


async def _fetch(scheme_code: int) -> dict | None:
    try:
        return await mfapi_client.get_scheme(scheme_code)
    except mfapi_client.MfApiError as exc:
        logger.warning("Could not load fund %s: %s", scheme_code, exc)
        return None


async def select_fund(role_id: str, today: date) -> dict:
    """The first usable fund for a role, or a fund-less entry saying why
    none could be used (the role's share is still shown)."""
    role = FUND_ROLES[role_id]
    skipped = []
    for choice in role.choices:
        scheme = await _fetch(choice.scheme_code)
        reason = unusable_reason(role, scheme, today)
        if reason is None:
            return {**describe_fund(role, choice, scheme), "skipped": skipped}
        skipped.append({"scheme_code": choice.scheme_code, "name": choice.name, "reason": reason})
        logger.warning("Fund %s skipped for %s: %s", choice.scheme_code, role_id, reason)
    return {"role": role.id, "role_label": role.label, "instrument_id": None, "skipped": skipped}


async def select_funds(role_ids: list[str], today: date) -> dict[str, dict]:
    results = await asyncio.gather(*(select_fund(r, today) for r in role_ids))
    return dict(zip(role_ids, results, strict=True))
