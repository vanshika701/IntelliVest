"""Mock invest flow tests through the real HTTP layer. The instrument
lookup is faked so tests don't depend on stored prices or mfapi.in."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.services import investment_service
from app.services.investment_service import next_installment_date

FUND = {
    "id": "mf-2",
    "name": "SBI Gold Fund - Direct Plan - Growth",
    "type": "MF",
    "price": 25.0,
    "stats": {"min_sip": 500, "min_investment": 1000},
}


@pytest.fixture(autouse=True)
def fake_instrument(monkeypatch: pytest.MonkeyPatch):
    async def fake_get_instrument(instrument_id: str) -> dict:
        return FUND

    monkeypatch.setattr(investment_service, "get_instrument", fake_get_instrument)


def _one_time(client: TestClient, headers: dict, amount: float = 5000, account_id: str = "demo-folio-1"):
    return client.post(
        "/api/v1/investments/one-time",
        json={"instrument_id": "mf-2", "amount": amount, "account_id": account_id},
        headers=headers,
    )


def test_next_installment_date_rolls_to_next_month_and_year() -> None:
    assert next_installment_date(15, date(2026, 11, 10)) == date(2026, 11, 15)
    assert next_installment_date(10, date(2026, 11, 10)) == date(2026, 12, 10)
    assert next_installment_date(1, date(2026, 12, 31)) == date(2027, 1, 1)
    assert next_installment_date(28, date(2027, 1, 31)) == date(2027, 2, 28)


def test_accounts_are_demo_and_filtered_by_instrument_type(client: TestClient, auth_headers: dict) -> None:
    accounts = client.get("/api/v1/investments/accounts?instrument_type=MF", headers=auth_headers).json()
    assert [a["id"] for a in accounts] == ["demo-folio-1", "demo-folio-new"]
    assert all(a["is_demo"] for a in accounts)


def test_one_time_order_then_successful_payment(client: TestClient, auth_headers: dict) -> None:
    created = _one_time(client, auth_headers)
    assert created.status_code == 201
    order = created.json()
    assert order["status"] == "pending_payment"
    assert order["estimated_units"] == 200.0
    assert order["is_mock"] is True

    paid = client.post(
        f"/api/v1/investments/{order['id']}/payment-result",
        json={"status": "success", "reference": "mock_pay_1"},
        headers=auth_headers,
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "completed"
    assert paid.json()["payment_reference"] == "mock_pay_1"

    # One-shot: a retried result can't flip a completed order.
    again = client.post(
        f"/api/v1/investments/{order['id']}/payment-result", json={"status": "failed"}, headers=auth_headers
    )
    assert again.status_code == 400

    listed = client.get("/api/v1/investments", headers=auth_headers).json()
    assert [i["id"] for i in listed] == [order["id"]]


def test_failed_payment_marks_order_failed(client: TestClient, auth_headers: dict) -> None:
    order = _one_time(client, auth_headers).json()
    failed = client.post(
        f"/api/v1/investments/{order['id']}/payment-result",
        json={"status": "failed", "failure_reason": "Declined by bank (mock)"},
        headers=auth_headers,
    ).json()
    assert failed["status"] == "failed"
    assert failed["failure_reason"] == "Declined by bank (mock)"


def test_one_time_below_minimum_is_rejected(client: TestClient, auth_headers: dict) -> None:
    response = _one_time(client, auth_headers, amount=999)
    assert response.status_code == 400
    assert "₹1,000" in response.json()["detail"]


def test_account_must_support_instrument_type(client: TestClient, auth_headers: dict) -> None:
    assert _one_time(client, auth_headers, account_id="demo-demat-1").status_code == 400


def test_sip_validates_min_and_day_then_activates(client: TestClient, auth_headers: dict) -> None:
    def sip(amount: float, day: int):
        return client.post(
            "/api/v1/investments/sip",
            json={"instrument_id": "mf-2", "amount": amount, "account_id": "demo-folio-1", "day_of_month": day},
            headers=auth_headers,
        )

    assert sip(499, 5).status_code == 400
    assert sip(500, 29).status_code == 422
    created = sip(500, 5)
    assert created.status_code == 201
    assert created.json()["status"] == "pending_mandate"

    active = client.post(
        f"/api/v1/investments/{created.json()['id']}/payment-result",
        json={"status": "success", "reference": "mock_mandate_1"},
        headers=auth_headers,
    ).json()
    assert active["status"] == "active"
    assert date.fromisoformat(active["next_installment_date"]).day == 5


def test_investments_are_private_to_each_user(client: TestClient, auth_headers: dict) -> None:
    order = _one_time(client, auth_headers).json()
    client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "password123", "full_name": "Other"},
    )
    token = client.post(
        "/api/v1/auth/login", json={"email": "other@example.com", "password": "password123"}
    ).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/investments", headers=other).json() == []
    response = client.post(
        f"/api/v1/investments/{order['id']}/payment-result", json={"status": "success"}, headers=other
    )
    assert response.status_code == 404


def test_unknown_investment_id_is_404(client: TestClient, auth_headers: dict) -> None:
    for bad_id in ("not-an-object-id", "0123456789abcdef01234567"):
        response = client.post(
            f"/api/v1/investments/{bad_id}/payment-result", json={"status": "success"}, headers=auth_headers
        )
        assert response.status_code == 404
