"""Phase 7 asset allocation: rules (pure) and the API (real HTTP + DB)."""

import pytest
from fastapi.testclient import TestClient

from app.core.allocation_config import BASE_SPLITS, HORIZON_LIMITS, Split
from app.core.risk_config import PROFILES, QUESTIONS
from app.services.asset_allocation import allocate

ORDER = [p.id for p in PROFILES]
HORIZONS = [1, 6, 12, 13, 24, 36, 37, 48, 60, 61, 120, 600]


def test_every_profile_has_a_split() -> None:
    assert set(BASE_SPLITS) == set(ORDER)


def test_sourced_splits_match_their_source() -> None:
    # Nippon India risk analyzers (see allocation_config.py).
    assert BASE_SPLITS["conservative"] == Split(15, 75, 10)
    assert BASE_SPLITS["moderate"] == Split(45, 45, 10)
    assert BASE_SPLITS["aggressive"] == Split(75, 15, 10)


def test_equity_rises_with_risk() -> None:
    equity = [BASE_SPLITS[p].equity for p in ORDER]
    assert equity == sorted(equity) and len(set(equity)) == len(equity)


def test_split_rejects_bad_totals() -> None:
    with pytest.raises(ValueError):
        Split(50, 40, 5)
    with pytest.raises(ValueError):
        Split(110, -10, 0)


@pytest.mark.parametrize("profile", ORDER)
@pytest.mark.parametrize("horizon", HORIZONS)
def test_every_result_is_valid(profile: str, horizon: int) -> None:
    result = allocate(profile, horizon)
    parts = (result["equity_pct"], result["debt_pct"], result["gold_pct"])
    assert sum(parts) == 100 and min(parts) >= 0
    limit = next((h for h in HORIZON_LIMITS if horizon <= h.max_months), None)
    if limit:
        assert result["equity_pct"] <= limit.max_equity
        assert result["gold_pct"] <= limit.max_gold


def test_long_horizon_uses_the_base_split() -> None:
    result = allocate("moderate", 120)
    assert (result["equity_pct"], result["debt_pct"], result["gold_pct"]) == (45, 45, 10)
    assert result["adjustments"] == []
    assert result["debt_style"] == "medium_duration"
    assert result["base_is_sourced"] is True


def test_short_horizons_remove_equity() -> None:
    within_year = allocate("aggressive", 12)
    assert (within_year["equity_pct"], within_year["debt_pct"], within_year["gold_pct"]) == (0, 100, 0)
    assert within_year["debt_style"] == "liquid"
    assert {a["asset"] for a in within_year["adjustments"]} == {"equity", "gold"}

    two_years = allocate("aggressive", 24)
    assert (two_years["equity_pct"], two_years["gold_pct"]) == (0, 5)
    assert two_years["debt_style"] == "short_duration"


def test_medium_horizon_caps_equity_only_when_needed() -> None:
    capped = allocate("aggressive", 48)
    assert (capped["equity_pct"], capped["debt_pct"], capped["gold_pct"]) == (40, 50, 10)
    assert capped["adjustments"][0]["from_pct"] == 75

    untouched = allocate("moderately_conservative", 48)
    assert untouched["equity_pct"] == 30 and untouched["adjustments"] == []
    assert untouched["base_is_sourced"] is False


def test_equity_never_rises_as_the_horizon_shortens() -> None:
    for profile in ORDER:
        equity = [allocate(profile, h)["equity_pct"] for h in sorted(HORIZONS)]
        assert equity == sorted(equity)


def test_invalid_inputs() -> None:
    with pytest.raises(KeyError):
        allocate("reckless", 60)
    with pytest.raises(ValueError):
        allocate("moderate", 0)


# --- API --------------------------------------------------------------------

HIGHEST = {q.id: q.options[-1].id for q in QUESTIONS}


def test_allocation_needs_a_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    url = "/api/v1/risk-profile/allocation?horizon_months=120"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_headers).status_code == 404

    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": HIGHEST})
    body = client.get(url, headers=auth_headers).json()
    assert (body["profile"], body["equity_pct"], body["gold_pct"]) == ("aggressive", 75, 10)


@pytest.mark.parametrize("horizon", ["0", "601", "ten"])
def test_allocation_validates_horizon(
    client: TestClient, auth_headers: dict[str, str], horizon: str
) -> None:
    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": HIGHEST})
    response = client.get(
        f"/api/v1/risk-profile/allocation?horizon_months={horizon}", headers=auth_headers
    )
    assert response.status_code == 422
