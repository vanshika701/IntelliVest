"""Budget routes through the real HTTP layer + DB, and the explainer guard."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services import budget_explainer

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
    assert preview["assumption"]["annual_return_pct"] == 7
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
    monkeypatch.setattr(settings, "budget_explainer_provider", "anthropic")

    async def fake_bad(_facts):
        return "Save ₹9,999 now!"

    monkeypatch.setattr(budget_explainer, "_ask_claude", fake_bad)
    out = await budget_explainer.explain(["Spend ₹6,000."])
    assert out == {"text": "Spend ₹6,000.", "source": "template"}

    async def fake_good(_facts):
        return "Aim to keep it around ₹6,000."

    monkeypatch.setattr(budget_explainer, "_ask_claude", fake_good)
    assert (await budget_explainer.explain(["Spend ₹6,000."]))["source"] == "llm"

    async def fake_error(_facts):
        raise RuntimeError("no network")

    monkeypatch.setattr(budget_explainer, "_ask_claude", fake_error)
    assert (await budget_explainer.explain(["Spend ₹6,000."]))["source"] == "template"
