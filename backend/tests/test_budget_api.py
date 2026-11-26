"""Budget routes through the real HTTP layer + DB, and the explainer guard."""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.data.collections import get_expenses_collection
from app.services import budget_explainer, budget_service
from app.services.budget_rules import analyze_budget
from app.services.health_score import health_score

PROFILE = {
    "monthly_income": 100_000,
    "estimates": {"housing": 30_000, "groceries": 10_000, "food_dining": 5_000, "savings_investments": 20_000},
    "emergency_fund": 50_000,
}


def _expense(client, headers, amount, category):
    today = datetime.now(UTC).isoformat()
    r = client.post(
        "/api/v1/expenses",
        headers=headers,
        json={"amount": amount, "description": "x", "category": category, "date": today},
    )
    assert r.status_code == 201


def test_categories_meta_lists_13_with_buckets(client: TestClient) -> None:
    body = client.get("/api/v1/budget/categories").json()
    assert len(body["categories"]) == 13
    assert {c["bucket"] for c in body["categories"]} == {"needs", "wants", "savings"}
    assert body["llm_explanations"] is False


def test_profile_validation(client: TestClient, auth_headers) -> None:
    bad = [
        {"monthly_income": -1, "estimates": {}},
        {"monthly_income": 1000, "estimates": {"groceries": -5}},
        {"monthly_income": 1000, "estimates": {"not_a_category": 5}},
    ]
    for body in bad:
        assert client.put("/api/v1/budget/profile", headers=auth_headers, json=body).status_code == 422


def test_profile_warns_when_estimates_exceed_income(client: TestClient, auth_headers) -> None:
    body = client.put(
        "/api/v1/budget/profile",
        headers=auth_headers,
        json={"monthly_income": 10_000, "estimates": {"housing": 8_000, "groceries": 4_000}},
    ).json()
    assert "₹2,000 more than your income" in body["warnings"][0]


def test_overview_without_profile(client: TestClient, auth_headers) -> None:
    body = client.get("/api/v1/budget/overview", headers=auth_headers).json()
    assert body["has_profile"] is False and body["analysis"] is None
    assert client.get("/api/v1/budget/improve", headers=auth_headers).status_code == 404


def test_estimated_then_actual_basis(client: TestClient, auth_headers) -> None:
    client.put("/api/v1/budget/profile", headers=auth_headers, json=PROFILE)
    overview = client.get("/api/v1/budget/overview", headers=auth_headers).json()
    assert overview["has_profile"] and overview["analysis"]["basis"] == "estimated"
    assert overview["actual"]["has_data"] is False

    _expense(client, auth_headers, 9_000, "food_dining")
    overview = client.get("/api/v1/budget/overview", headers=auth_headers).json()
    assert overview["analysis"]["basis"] == "actual"
    food = next(r for r in overview["comparison"] if r["category"] == "food_dining")
    assert food == {**food, "estimated": 5_000, "actual": 9_000, "difference": 4_000}

    improve = client.get("/api/v1/budget/improve?focus=food_dining", headers=auth_headers).json()
    assert improve["focus_category"]["overspend_amount"] == 3_000
    assert "₹4,000 more than your own estimate" in improve["summary"]

    estimated = client.get("/api/v1/budget/analysis?basis=estimated", headers=auth_headers).json()
    assert estimated["basis"] == "estimated"
    assert client.get("/api/v1/budget/improve?focus=nope", headers=auth_headers).status_code == 422


def test_goals_crud_and_affordability(client: TestClient, auth_headers) -> None:
    client.put("/api/v1/budget/profile", headers=auth_headers, json=PROFILE)
    goal = {"name": "Car", "target_amount": 800_000, "horizon_months": 36}

    preview = client.post("/api/v1/budget/goals/preview", headers=auth_headers, json=goal).json()
    assert preview["assumption"]["annual_return_pct"] == 6
    # Surplus = income − needs − wants = 1,00,000 − 45,000 = 55,000; SIP ≈ 19.7k fits.
    assert preview["affordability"]["status"] == "affordable"

    created = client.post("/api/v1/budget/goals", headers=auth_headers, json=goal)
    assert created.status_code == 201
    goal_id = created.json()["id"]

    listed = client.get("/api/v1/budget/goals", headers=auth_headers).json()
    assert len(listed["items"]) == 1 and listed["combined"]["fits"] is True

    assert client.post(
        "/api/v1/budget/goals", headers=auth_headers, json={**goal, "horizon_months": 0}
    ).status_code == 422

    explained = client.post(
        "/api/v1/budget/explain", headers=auth_headers, json={"kind": "goal", "goal_id": goal_id}
    ).json()
    assert explained["source"] == "template" and "To reach ₹8,00,000" in explained["text"]

    assert client.delete(f"/api/v1/budget/goals/{goal_id}", headers=auth_headers).status_code == 204
    assert client.delete(f"/api/v1/budget/goals/{goal_id}", headers=auth_headers).status_code == 404


def test_explainer_number_guard() -> None:
    src = "You're overspending by ₹3,000/month. Suggested target: ₹6,000."
    assert budget_explainer.numbers_are_preserved(src, "Try trimming ₹3,000 to land near ₹6,000.")
    assert not budget_explainer.numbers_are_preserved(src, "Cut ₹3,500 a month.")


async def test_explainer_falls_back_when_llm_alters_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "budget_explainer_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("k"))

    async def fake_bad(_facts, **_kw):
        return "Save ₹9,999 now!"

    monkeypatch.setattr(budget_explainer, "_ask_llm", fake_bad)
    out = await budget_explainer.explain(["Spend ₹6,000."])
    assert out == {"text": "Spend ₹6,000.", "source": "template"}

    async def fake_good(_facts, **_kw):
        return "Aim to keep it around ₹6,000."

    monkeypatch.setattr(budget_explainer, "_ask_llm", fake_good)
    assert (await budget_explainer.explain(["Spend ₹6,000."]))["source"] == "llm"

    async def fake_error(_facts, **_kw):
        raise RuntimeError("no network")

    monkeypatch.setattr(budget_explainer, "_ask_llm", fake_error)
    assert (await budget_explainer.explain(["Spend ₹6,000."]))["source"] == "template"


def test_explainer_guard_rejects_swaps_words_and_unit_changes() -> None:
    src = "You're overspending by ₹3,000/month. Suggested target: ₹6,000 (9%)."
    ok = budget_explainer.numbers_are_preserved
    assert not ok(src, "Overspending by ₹6,000; aim for ₹3,000.")
    assert not ok(src, "You're over by three thousand rupees.")
    assert not ok(src, "Cut it in half from ₹3,000.")
    assert not ok(src, "That's ₹9.")
    assert ok(src, "No one enjoys cutting back, but ₹3,000 less gets you to ₹6,000.")


async def _log(user_id, amount, category, when):
    await get_expenses_collection().insert_one(
        {"user_id": user_id, "amount": amount, "category": category, "expense_type": "expense", "date": when}
    )


async def test_unfinished_month_does_not_lower_the_average(mongo_test_db) -> None:
    now = datetime(2026, 11, 3, tzinfo=UTC)
    await _log("u", 10_000, "groceries", datetime(2026, 9, 10, tzinfo=UTC))
    await _log("u", 12_000, "groceries", datetime(2026, 10, 10, tzinfo=UTC))
    await _log("u", 500, "groceries", datetime(2026, 11, 2, tzinfo=UTC))
    await _log("u", 99_000, "groceries", datetime(2026, 12, 2, tzinfo=UTC))  # future-dated
    actual = await budget_service.actual_monthly_spend("u", now)
    assert actual["by_category"] == {"groceries": 11_000} and actual["partial"] is False
    assert actual["months"] == ["2026-09", "2026-10"]

    await _log("new", 500, "groceries", datetime(2026, 11, 2, tzinfo=UTC))
    assert (await budget_service.actual_monthly_spend("new", now))["partial"] is True


def test_unlogged_categories_use_the_estimate() -> None:
    profile = {"monthly_income": 100_000, "estimates": {"housing": 30_000, "groceries": 10_000}}
    actual = {"by_category": {"groceries": 2_000}, "partial": False}
    result = budget_service._analysis(profile, actual, "actual")
    assert result["total_spend"] == 32_000
    assert result["filled_from_estimate"] == ["Housing & Rent"]
    # An unfinished month below the estimate isn't evidence of lower spending.
    result = budget_service._analysis(profile, {**actual, "partial": True}, "actual")
    assert result["total_spend"] == 40_000
    over = budget_service._analysis(profile, {"by_category": {"groceries": 15_000}, "partial": True}, "actual")
    assert over["total_spend"] == 45_000


def test_second_goal_only_gets_what_the_first_leaves(client: TestClient, auth_headers) -> None:
    # Surplus 55,000; each goal needs about 39,800/month.
    client.put("/api/v1/budget/profile", headers=auth_headers, json=PROFILE)
    url = "/api/v1/budget/goals"
    goal = {"name": "Car", "target_amount": 1_600_000, "horizon_months": 36}
    first = client.post(url, headers=auth_headers, json=goal).json()
    second = client.post(url, headers=auth_headers, json={**goal, "name": "Trip"}).json()
    assert first["plan"]["affordability"]["status"] == "affordable"
    assert second["plan"]["affordability"]["status"] == "not_affordable"
    assert "after your other goals" in second["plan"]["affordability"]["message"]

    # Previewing an edit of the first goal must not count it (or later goals) against itself.
    preview = client.post(f"{url}/preview?goal_id={first['id']}", headers=auth_headers, json=goal).json()
    assert preview["affordability"]["committed"] == 0

    smaller = {**goal, "name": "Small car", "target_amount": 400_000}
    edited = client.put(f"{url}/{first['id']}", headers=auth_headers, json=smaller).json()
    assert edited["name"] == "Small car"
    items = client.get(url, headers=auth_headers).json()["items"]
    assert [i["plan"]["affordability"]["status"] for i in items] == ["affordable", "affordable"]
    assert client.put(f"{url}/bad", headers=auth_headers, json=goal).status_code == 404


def test_health_score_known_cases() -> None:
    perfect = health_score(
        analyze_budget(100_000, {"housing": 30_000, "groceries": 10_000, "utilities": 5_000}, emergency_fund=270_000)
    )
    assert (perfect["score"], perfect["band"], perfect["complete"]) == (100, "Good", True)
    # EMIs at 40%: debt 50/100. Groceries, bills and emergency fund not entered.
    debt = health_score(analyze_budget(100_000, {"emi_debt": 40_000}))
    assert {c["id"]: c["score"] for c in debt["components"]} == {
        "savings": 100,
        "debt": 50,
        "emergency": None,
        "housing": 100,
        "groceries": None,
        "household": None,
        "lifestyle": 100,
    }
    assert debt["complete"] is False and debt["score"] == 89  # 5950 / 67
    # Rent at 1.5x its 35% maximum earns half.
    rent = health_score(analyze_budget(100_000, {"housing": 52_500}))
    assert {c["id"]: c["score"] for c in rent["components"]}["housing"] == 50
    assert health_score(analyze_budget(0, {}))["score"] is None


def test_health_score_endpoint(client: TestClient, auth_headers) -> None:
    url = "/api/v1/budget/health-score"
    assert client.get(url, headers=auth_headers).json()["score"] is None
    client.put("/api/v1/budget/profile", headers=auth_headers, json=PROFILE)
    assert 0 <= client.get(url, headers=auth_headers).json()["score"] <= 100


async def test_explainer_request_and_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = {}

    class FakeClient:
        def __init__(self, **_kw): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a): ...
        async def post(self, url, headers, json):
            sent.update(url=url, auth=headers["Authorization"], model=json["model"])
            body = {"choices": [{"finish_reason": "stop", "message": {"content": "Around ₹6,000."}}]}
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(budget_explainer.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "budget_explainer_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    assert not budget_explainer.llm_enabled()
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("k"))
    assert (await budget_explainer.explain(["Spend ₹6,000."])) == {"text": "Around ₹6,000.", "source": "llm"}
    assert sent["url"].endswith("/v1beta/openai/chat/completions") and sent["auth"] == "Bearer k"
