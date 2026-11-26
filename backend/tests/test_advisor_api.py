"""Phase 9 advice service and API: template summary, storage, login, rate
limit, and a user going from nothing to an invest action (real HTTP + test
DB; fund lookups faked so tests stay offline)."""

import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes import advisor as advisor_routes
from app.core.advisor_config import ADVICE_REQUESTS_PER_MINUTE, MODULES
from app.core.risk_config import QUESTIONS
from app.services.advisor.summary import template_summary
from tests.test_recommendations import _store_stats, offline_funds  # noqa: F401 — fixture

ANSWERS = {q.id: q.options[2].id for q in QUESTIONS}


@pytest.fixture(autouse=True)
def _fresh_limiter():
    advisor_routes._limiter.reset()
    yield
    advisor_routes._limiter.reset()


def _action(title: str) -> dict:
    return {"title": title}


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"actions": [], "setup": [{"title": "Set up your budget"}], "partial": False},
         "To get personalised advice, start with: set up your budget."),
        ({"actions": [], "setup": [], "partial": False}, "You're on track: nothing needs your attention right now."),
        ({"actions": [_action("Build your emergency fund: ₹65,000 to go")], "setup": [], "partial": False},
         "1 thing to look at, most important first. Start with: Build your emergency fund: ₹65,000 to go."),
        ({"actions": [_action("A"), _action("B"), _action("C")], "setup": [], "partial": True},
         ("3 things to look at, most important first. Start with: A. Then: B. "
          "Some information couldn't be loaded, so this advice may be incomplete.")),
    ],
)
def test_template_summary(result: dict, expected: str) -> None:
    assert template_summary(result) == expected


def test_requires_login(client: TestClient) -> None:
    assert client.post("/api/v1/advisor/advice").status_code == 401
    assert client.get("/api/v1/advisor/advice/latest").status_code == 401


def test_new_user_gets_setup_steps_and_every_module(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/advisor/advice/latest", headers=auth_headers).status_code == 404

    created = client.post("/api/v1/advisor/advice", headers=auth_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["id"] and "user_id" not in body
    assert body["actions"] == []
    assert [s["module"] for s in body["setup"]] == ["budget", "risk_profile", "portfolio_plan"]
    assert [m["module"] for m in body["modules"]] == list(MODULES)
    assert body["summary"] == {"text": "To get personalised advice, start with: set up your budget.",
                               "source": "template"}
    assert body["version"] == "advisor-v1" and "not investment advice" in body["disclaimer"]

    latest = client.get("/api/v1/advisor/advice/latest", headers=auth_headers).json()
    assert latest["id"] == body["id"]


def test_user_with_a_plan_is_told_to_invest(
    client: TestClient, auth_headers: dict[str, str], offline_funds: None  # noqa: F811
) -> None:
    client.put("/api/v1/risk-profile", headers=auth_headers, json={"answers": ANSWERS})
    _store_stats()
    plan = client.post("/api/v1/recommendations", headers=auth_headers,
                       json={"horizon_months": 84, "lump_sum": 50_000, "monthly_sip": 5_000})
    assert plan.status_code == 201

    body = client.post("/api/v1/advisor/advice", headers=auth_headers).json()
    invest = next(a for a in body["actions"] if a["id"] == "invest_per_plan")
    assert "₹50,000 now and ₹5,000 a month" in invest["title"]
    assert "couldn't check your emergency fund" in invest["detail"]  # no budget yet
    assert set(invest["contributors"]) >= {"risk_profile", "portfolio_plan"}
    assert {s["module"] for s in body["setup"]} == {"budget"}
    statuses = {m["module"]: m["status"] for m in body["modules"]}
    assert statuses["risk_profile"] == statuses["portfolio_plan"] == "ok"
    # No sector rollup or predictions in the test DB: reported, not fatal.
    assert statuses["predictions"] == "unavailable" and body["partial"] is True
    assert "predictions" in body["modules_unavailable"]


def test_rate_limited(client: TestClient, auth_headers: dict[str, str]) -> None:
    for _ in range(ADVICE_REQUESTS_PER_MINUTE):
        assert client.post("/api/v1/advisor/advice", headers=auth_headers).status_code == 201
    limited = client.post("/api/v1/advisor/advice", headers=auth_headers)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    # Reading saved advice isn't limited.
    assert client.get("/api/v1/advisor/advice/latest", headers=auth_headers).status_code == 200
