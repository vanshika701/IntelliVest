"""Unit test — exercises the service layer alone, with the DB mocked out.

This is the pattern every later service should follow: the service is
tested against a fake/mocked data layer, so the test doesn't need a real
database and doesn't break because Mongo happened to be down.
"""

import pytest

from app.services import health_service


@pytest.mark.parametrize(
    ("db_reachable", "expected_status", "expected_database"),
    [
        (True, "ok", "connected"),
        (False, "degraded", "unavailable"),
    ],
)
async def test_get_health_status_reflects_database_reachability(
    monkeypatch: pytest.MonkeyPatch,
    db_reachable: bool,
    expected_status: str,
    expected_database: str,
) -> None:
    async def fake_ping_database() -> bool:
        return db_reachable

    monkeypatch.setattr(health_service, "ping_database", fake_ping_database)

    result = await health_service.get_health_status()

    assert result == {"status": expected_status, "database": expected_database}
