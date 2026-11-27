"""/api/v1/blockchain: status, wallet linking, task queue (Phase 10, B11)."""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from app.core.config import settings

API = "/api/v1/blockchain"


@pytest.fixture
def enabled(client, monkeypatch):
    # After the client fixture, so startup didn't try to load keys.
    monkeypatch.setattr(settings, "blockchain_enabled", True)
    return client


def _sign(account, message: str) -> str:
    return "0x" + bytes(account.sign_message(encode_defunct(text=message)).signature).hex()


def _link(client, headers, account=None):
    account = account or Account.create()
    challenge = client.post(
        f"{API}/wallet/challenge", json={"address": account.address}, headers=headers
    )
    assert challenge.status_code == 200
    message = challenge.json()["message"]
    body = {"address": account.address, "signature": _sign(account, message)}
    return account, client.post(f"{API}/wallet/verify", json=body, headers=headers)


def _second_user(client) -> dict:
    user = {
        "email": "other@example.com",
        "password": "password123",
        "full_name": "Other",
        "date_of_birth": "1999-01-01",
    }
    client.post("/api/v1/auth/register", json=user)
    token = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_status_when_off(client):
    body = client.get(f"{API}/status").json()
    assert body["enabled"] is False and "seen by anyone" in body["privacy_notice"]


def test_routes_are_404_when_off(client, auth_headers):
    assert client.get(f"{API}/wallet", headers=auth_headers).status_code == 404
    assert (
        client.post(f"{API}/tasks", json={"fund": "tEquityFund"}, headers=auth_headers).status_code
        == 404
    )


def test_status_when_on(enabled):
    body = enabled.get(f"{API}/status").json()
    assert body["enabled"] is True and body["chain_id"] == settings.blockchain_chain_id


def test_link_wallet(enabled, auth_headers):
    account, response = _link(enabled, auth_headers)
    assert response.status_code == 200 and response.json()["address"] == account.address
    assert enabled.get(f"{API}/wallet", headers=auth_headers).json()["address"] == account.address


def test_challenge_message_names_address_and_chain(enabled, auth_headers):
    account = Account.create()
    message = enabled.post(
        f"{API}/wallet/challenge", json={"address": account.address.lower()}, headers=auth_headers
    ).json()["message"]
    assert account.address in message and f"Chain ID: {settings.blockchain_chain_id}" in message
    assert "does not move any funds" in message


def test_challenge_works_once(enabled, auth_headers):
    account = Account.create()
    message = enabled.post(
        f"{API}/wallet/challenge", json={"address": account.address}, headers=auth_headers
    ).json()["message"]
    body = {"address": account.address, "signature": _sign(account, message)}
    assert enabled.post(f"{API}/wallet/verify", json=body, headers=auth_headers).status_code == 200
    enabled.delete(f"{API}/wallet", headers=auth_headers)
    # Replaying the same signature after unlinking fails: the challenge is gone.
    assert enabled.post(f"{API}/wallet/verify", json=body, headers=auth_headers).status_code == 400


def test_signature_from_another_wallet_is_refused_and_uses_up_the_challenge(enabled, auth_headers):
    account, other = Account.create(), Account.create()
    message = enabled.post(
        f"{API}/wallet/challenge", json={"address": account.address}, headers=auth_headers
    ).json()["message"]
    bad = {"address": account.address, "signature": _sign(other, message)}
    assert enabled.post(f"{API}/wallet/verify", json=bad, headers=auth_headers).status_code == 400
    good = {"address": account.address, "signature": _sign(account, message)}
    assert enabled.post(f"{API}/wallet/verify", json=good, headers=auth_headers).status_code == 400


def test_only_newest_challenge_counts(enabled, auth_headers):
    account = Account.create()
    first = enabled.post(
        f"{API}/wallet/challenge", json={"address": account.address}, headers=auth_headers
    ).json()
    enabled.post(f"{API}/wallet/challenge", json={"address": account.address}, headers=auth_headers)
    body = {"address": account.address, "signature": _sign(account, first["message"])}
    assert enabled.post(f"{API}/wallet/verify", json=body, headers=auth_headers).status_code == 400


def test_wallet_belongs_to_one_account(enabled, auth_headers):
    account, _ = _link(enabled, auth_headers)
    _, response = _link(enabled, _second_user(enabled), account)
    assert response.status_code == 409


def test_cannot_link_two_wallets(enabled, auth_headers):
    _link(enabled, auth_headers)
    _, response = _link(enabled, auth_headers)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "body",
    [{"address": "0x123"}, {"address": "not-an-address"}],
)
def test_bad_address_is_422(enabled, auth_headers, body):
    assert (
        enabled.post(f"{API}/wallet/challenge", json=body, headers=auth_headers).status_code == 422
    )


def test_wallet_routes_need_login(enabled):
    assert enabled.get(f"{API}/wallet").status_code in (401, 403)


def test_task_needs_a_wallet(enabled, auth_headers):
    response = enabled.post(f"{API}/tasks", json={"fund": "tEquityFund"}, headers=auth_headers)
    assert response.status_code == 409


def test_task_is_queued_and_not_doubled(enabled, auth_headers):
    _link(enabled, auth_headers)
    body = {"fund": "tEquityFund", "ticker": "RELIANCE"}
    first = enabled.post(f"{API}/tasks", json=body, headers=auth_headers)
    assert first.status_code == 202
    task = first.json()
    assert task["state"] == "queued" and task["mock_advisor"] is True and task["task_id"] is None
    assert enabled.post(f"{API}/tasks", json=body, headers=auth_headers).status_code == 409
    # A different fund is a separate task.
    assert (
        enabled.post(f"{API}/tasks", json={"fund": "tGoldFund"}, headers=auth_headers).status_code
        == 202
    )
    listed = enabled.get(f"{API}/tasks", headers=auth_headers).json()
    assert [t["fund"] for t in listed] == ["tGoldFund", "tEquityFund"]
    assert enabled.get(f"{API}/tasks/{task['id']}", headers=auth_headers).json()["id"] == task["id"]


def test_tasks_are_private(enabled, auth_headers):
    _link(enabled, auth_headers)
    task = enabled.post(f"{API}/tasks", json={"fund": "tEquityFund"}, headers=auth_headers).json()
    other = _second_user(enabled)
    assert enabled.get(f"{API}/tasks/{task['id']}", headers=other).status_code == 404
    assert enabled.get(f"{API}/tasks", headers=other).json() == []
    assert enabled.get(f"{API}/tasks/not-an-id", headers=auth_headers).status_code == 404


@pytest.mark.parametrize(
    "body", [{"fund": "tStocks"}, {"fund": "tEquityFund", "ticker": "bad ticker"}]
)
def test_bad_task_is_422(enabled, auth_headers, body):
    _link(enabled, auth_headers)
    assert enabled.post(f"{API}/tasks", json=body, headers=auth_headers).status_code == 422


def test_unreadable_signature_is_400(enabled, auth_headers):
    account = Account.create()
    enabled.post(f"{API}/wallet/challenge", json={"address": account.address}, headers=auth_headers)
    body = {"address": account.address, "signature": "0x" + "00" * 65}
    assert enabled.post(f"{API}/wallet/verify", json=body, headers=auth_headers).status_code == 400
