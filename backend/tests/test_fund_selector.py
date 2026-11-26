"""Phase 7 debt and gold funds: config, NAV maths and fallback (offline)."""

from datetime import date, timedelta

import pytest

from app.core.allocation_config import HORIZON_LIMITS, LONG_HORIZON_DEBT_STYLE
from app.core.fund_config import FUND_ROLES, MAX_NAV_AGE_DAYS
from app.services import fund_selector, mfapi_client
from app.services.fund_selector import (
    annualised_return,
    annualised_volatility,
    max_drawdown,
    select_fund,
    select_funds,
    unusable_reason,
)

TODAY = date(2026, 11, 26)


def steady_navs(annual_growth: float, years: int = 4, end: date = TODAY) -> list[tuple[date, float]]:
    days = years * 365
    daily = (1 + annual_growth) ** (1 / 365)
    return [(end - timedelta(days=days - i), 100 * daily**i) for i in range(days + 1)]


def scheme(category: str, navs=None) -> dict:
    return {"meta": {"scheme_name": "Some Fund", "fund_house": "AMC", "scheme_category": category},
            "navs": navs or steady_navs(0.07)}


def test_every_debt_style_and_gold_has_funds() -> None:
    needed = {h.debt_style for h in HORIZON_LIMITS} | {LONG_HORIZON_DEBT_STYLE, "gold"}
    assert needed <= set(FUND_ROLES)
    for role in FUND_ROLES.values():
        assert len(role.choices) >= 2  # a fallback for every role
        assert len({c.scheme_code for c in role.choices}) == len(role.choices)
        assert all("direct" in c.name.lower() and "growth" in c.name.lower() for c in role.choices)


def test_nav_maths() -> None:
    navs = steady_navs(0.07)
    assert annualised_return(navs, 1) == pytest.approx(0.07, abs=0.002)
    assert annualised_return(navs, 3) == pytest.approx(0.07, abs=0.002)
    assert annualised_return(navs, 10) is None  # not enough history
    assert annualised_volatility(navs) == pytest.approx(0, abs=1e-6)
    assert max_drawdown(navs) == 0
    falling = navs[:-30] + [(d, nav * 0.8) for d, nav in navs[-30:]]
    assert max_drawdown(falling) == pytest.approx(-0.2, abs=0.001)
    assert annualised_volatility(falling) > 0
    assert annualised_return([], 1) is None


def test_unusable_reasons() -> None:
    role = FUND_ROLES["liquid"]
    assert unusable_reason(role, scheme("Debt Scheme - Liquid Fund"), TODAY) is None
    assert unusable_reason(role, None, TODAY) == "scheme not found"
    assert "expected 'Liquid Fund'" in unusable_reason(role, scheme("Equity Scheme - Large Cap Fund"), TODAY)
    stale = steady_navs(0.07, end=TODAY - timedelta(days=MAX_NAV_AGE_DAYS + 1))
    assert "days old" in unusable_reason(role, scheme("Debt Scheme - Liquid Fund", stale), TODAY)


async def test_falls_back_to_the_second_fund(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = FUND_ROLES["gold"].choices

    async def fake_get_scheme(code: int):
        if code == first.scheme_code:
            raise mfapi_client.MfApiError("down")
        return scheme("Other Scheme - FoF Domestic")

    monkeypatch.setattr(mfapi_client, "get_scheme", fake_get_scheme)
    fund = await select_fund("gold", TODAY)
    assert fund["instrument_id"] == f"mf-{second.scheme_code}"
    assert fund["skipped"][0]["scheme_code"] == first.scheme_code
    assert fund["return_1y"] == pytest.approx(0.07, abs=0.002)


async def test_no_usable_fund_still_returns_the_role(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing(_code: int):
        return None

    monkeypatch.setattr(mfapi_client, "get_scheme", nothing)
    funds = await select_funds(["liquid", "gold"], TODAY)
    assert set(funds) == {"liquid", "gold"}
    assert funds["liquid"]["instrument_id"] is None
    assert len(funds["liquid"]["skipped"]) == len(FUND_ROLES["liquid"].choices)
    assert fund_selector.FUND_ROLES is FUND_ROLES
