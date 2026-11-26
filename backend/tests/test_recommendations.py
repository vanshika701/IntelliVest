"""Phase 7 recommendations: the pure builder and the API end to end
(real HTTP + test DB; fund lookups are faked so tests stay offline)."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pymongo
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.constants import STOCK_UNIVERSE
from app.core.risk_config import QUESTIONS
from app.services import recommendation_service
from app.services.asset_allocation import allocate
from app.services.equity_optimizer import optimize_equity
from app.services.market_stats import compute_market_stats
from app.services.recommendation import build_recommendation, split_amount

NOW = datetime(2026, 11, 26, tzinfo=UTC)
END = datetime(2026, 11, 25)  # noqa: DTZ001 — MongoDB returns price dates as naive UTC
PROFILE = {"profile": "moderate", "label": "Moderate", "capacity_score": 60.0,
           "tolerance_score": 50.0, "limited_by": "tolerance", "version": "risk-v1"}


def synthetic_stats() -> dict:
    rng = np.random.default_rng(7)
    market = rng.normal(0, 0.008, 400)
    series = {}
    for i, ticker in enumerate(STOCK_UNIVERSE):
        returns = market + rng.normal(0, 0.006 + 0.0005 * i, 400)
        closes = 100 * np.cumprod(np.concatenate([[1.0], 1 + returns]))
        series[ticker] = [{"date": END - timedelta(days=400 - d), "close": float(c)}
                          for d, c in enumerate(closes)]
    return compute_market_stats(series, NOW)


def fake_fund(role: str) -> dict:
    return {"role": role, "role_label": f"{role} fund", "instrument_id": f"mf-{len(role)}",
            "name": f"{role.title()} Fund - Direct Plan - Growth", "return_3y": 0.07,
            "annual_volatility": 0.02 if role != "gold" else 0.15, "max_drawdown_3y": -0.02,
            "skipped": []}


def build(lump: float = 100_000, monthly: float = 10_000, horizon: int = 84, **overrides) -> dict:
    stats = synthetic_stats()
    allocation = allocate("moderate", horizon)
    equity = optimize_equity(stats) if allocation["equity_pct"] else None
    args = {
        "profile": PROFILE, "allocation": allocation, "equity": equity,
        "stats": stats if equity else None, "signals": {},
        "funds": {allocation["debt_style"]: fake_fund(allocation["debt_style"]), "gold": fake_fund("gold")},
        "lump_sum": lump, "monthly_sip": monthly,
        "stock_prices": dict.fromkeys(STOCK_UNIVERSE, 500.0),
        "current_holdings": [], "goal": None, "created_at": NOW,
    }
    return build_recommendation(**{**args, **overrides})


# --- Pure builder -----------------------------------------------------------

@pytest.mark.parametrize("total", [0, 1, 999.6, 100_000, 12_345.67])
def test_split_amount_adds_up_exactly(total: float) -> None:
    weights = [0.3333, 0.3333, 0.3334]
    amounts = split_amount(total, weights)
    assert sum(amounts) == round(total)
    assert all(a >= 0 for a in amounts)


def test_amounts_follow_the_allocation() -> None:
    rec = build()
    holdings = rec["holdings"]
    assert sum(h["lump_sum_amount"] for h in holdings) == 100_000
    assert sum(h["monthly_amount"] for h in holdings) == 10_000
    by_class = {}
    for h in holdings:
        by_class[h["asset_class"]] = by_class.get(h["asset_class"], 0) + h["lump_sum_amount"]
    assert by_class == pytest.approx({"equity": 45_000, "debt": 45_000, "gold": 10_000}, abs=20)
    assert all(h["reasons"] for h in holdings)
    assert rec["disclaimer"] and rec["versions"]["allocation"] == "alloc-v1"


def test_short_horizon_needs_no_stocks() -> None:
    rec = build(horizon=12)
    assert [h["asset_class"] for h in rec["holdings"]] == ["debt"]
    assert rec["holdings"][0]["lump_sum_amount"] == 100_000
    assert rec["equity_comparison"] is None


def test_risk_upper_bound_combines_the_parts() -> None:
    rec = build()
    vol = rec["risk"]["class_volatility"]
    expected = 0.45 * vol["equity"] + 0.45 * 0.02 + 0.10 * 0.15
    assert rec["risk"]["volatility_upper_bound"] == pytest.approx(expected, abs=1e-5)
    assert rec["risk"]["bad_year_loss"] == pytest.approx(-1.65 * expected, abs=1e-3)


def test_missing_fund_volatility_is_reported_not_guessed() -> None:
    allocation = allocate("moderate", 84)
    funds = {allocation["debt_style"]: {**fake_fund("medium_duration"), "annual_volatility": None},
             "gold": fake_fund("gold")}
    rec = build(funds=funds)
    assert rec["risk"]["volatility_upper_bound"] is None
    assert rec["risk"]["missing"] == ["debt"]


def test_small_amounts_get_warnings_and_an_index_fund_note() -> None:
    rec = build(lump=0, monthly=2_000, stock_prices=dict.fromkeys(STOCK_UNIVERSE, 3_000.0))
    stocks = [h for h in rec["holdings"] if h["kind"] == "stock"]
    assert all("less than one share" in h["warnings"][0] for h in stocks)
    assert any("index fund" in n for n in rec["notes"])
    gold = next(h for h in rec["holdings"] if h["asset_class"] == "gold")
    assert "minimum SIP" in gold["warnings"][0]


def test_unavailable_fund_still_shows_its_share() -> None:
    allocation = allocate("moderate", 84)
    gone = {"role": "gold", "role_label": "Gold fund of funds", "instrument_id": None,
            "skipped": [{"scheme_code": 1, "name": "X", "reason": "scheme not found"}]}
    rec = build(funds={allocation["debt_style"]: fake_fund("medium_duration"), "gold": gone})
    gold = next(h for h in rec["holdings"] if h["asset_class"] == "gold")
    assert gold["instrument_id"] is None and gold["lump_sum_amount"] == 10_000
    assert "scheme not found" in gold["reasons"][0]


def test_compares_with_current_holdings() -> None:
    stats = synthetic_stats()
    held_stock = next(s["ticker"] for s in optimize_equity(stats)["stocks"] if s["weight"] > 0)
    current = [
        {"instrument_id": f"stock-{held_stock}", "instrument_name": "Held", "current_value": 5_000.0},
        {"instrument_id": "mf-999", "instrument_name": "Old Fund", "current_value": 2_000.0},
    ]
    rec = build(current_holdings=current)
    line = next(h for h in rec["holdings"] if h["instrument_id"] == f"stock-{held_stock}")
    assert line["already_held_value"] == 5_000.0
    assert rec["not_held"] == [{"instrument_id": "mf-999", "name": "Old Fund", "current_value": 2_000.0}]


# --- API --------------------------------------------------------------------

ANSWERS = {q.id: q.options[2].id for q in QUESTIONS}  # middle answers -> a moderate-ish profile


@pytest.fixture
def offline_funds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_select_funds(roles: list[str], _today: date) -> dict:
        return {r: fake_fund(r) for r in roles}

    monkeypatch.setattr(recommendation_service, "select_funds", fake_select_funds)


def _store_stats() -> None:
    with pymongo.MongoClient(settings.mongodb_uri) as sync:
        sync[settings.mongodb_db_name].market_stats.insert_one(synthetic_stats())


def test_requires_login_and_valid_input(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = {"horizon_months": 84, "lump_sum": 10_000}
    assert client.post("/api/v1/recommendations", json=body).status_code == 401
    for bad in ({"lump_sum": 10_000},  # no horizon or goal
                {"horizon_months": 84, "goal_id": "x", "lump_sum": 10_000},
                {"horizon_months": 84},  # no amount
                {"horizon_months": 84, "lump_sum": -5}):
        assert client.post("/api/v1/recommendations", headers=auth_headers, json=bad).status_code == 422


def test_needs_a_risk_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/recommendations", headers=auth_headers,
                           json={"horizon_months": 84, "lump_sum": 10_000})
    assert response.status_code == 409
    assert "risk questionnaire" in response.json()["detail"]


def test_needs_market_stats_for_equity(
    client: TestClient, auth_headers: dict[str, str], offline_funds: None
) -> None:
    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": ANSWERS})
    long_goal = client.post("/api/v1/recommendations", headers=auth_headers,
                            json={"horizon_months": 84, "lump_sum": 10_000})
    assert long_goal.status_code == 409
    # A short goal has no equity, so it works without market statistics.
    short_goal = client.post("/api/v1/recommendations", headers=auth_headers,
                             json={"horizon_months": 6, "lump_sum": 10_000})
    assert short_goal.status_code == 201


def test_create_store_and_read_latest(
    client: TestClient, auth_headers: dict[str, str], offline_funds: None
) -> None:
    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": ANSWERS})
    _store_stats()
    assert client.get("/api/v1/recommendations/latest", headers=auth_headers).status_code == 404

    created = client.post("/api/v1/recommendations", headers=auth_headers,
                          json={"horizon_months": 84, "lump_sum": 50_000, "monthly_sip": 5_000})
    assert created.status_code == 201
    body = created.json()
    assert body["id"] and "user_id" not in body
    assert sum(h["lump_sum_amount"] for h in body["holdings"]) == 50_000
    assert {h["asset_class"] for h in body["holdings"]} >= {"debt"}

    latest = client.get("/api/v1/recommendations/latest", headers=auth_headers).json()
    assert latest["id"] == body["id"]


def test_uses_a_saved_goal(client: TestClient, auth_headers: dict[str, str], offline_funds: None) -> None:
    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": ANSWERS})
    client.put("/api/v1/budget/profile", headers=auth_headers,
               json={"monthly_income": 100_000, "estimates": {}, "emergency_fund": 300_000})
    goal = client.post("/api/v1/budget/goals", headers=auth_headers,
                       json={"name": "Car", "target_amount": 500_000, "horizon_months": 24}).json()
    rec = client.post("/api/v1/recommendations", headers=auth_headers,
                      json={"goal_id": goal["id"], "monthly_sip": 10_000}).json()
    assert rec["inputs"]["horizon_months"] == 24
    assert rec["inputs"]["goal"]["name"] == "Car"
    assert rec["allocation"]["equity_pct"] == 0  # 2-year goal: no equity

    missing = client.post("/api/v1/recommendations", headers=auth_headers,
                          json={"goal_id": "000000000000000000000000", "monthly_sip": 10_000})
    assert missing.status_code == 404
