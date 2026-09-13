"""Unit test — verifies the retry policy actually retries transient
failures until they succeed, and fails immediately (no wasted retries)
on a permanent failure. No real network call needed for either case.
"""

import httpx
import pytest

from app.core.retry import with_retry


async def test_retries_transient_failure_then_succeeds() -> None:
    attempts = {"count": 0}

    @with_retry
    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise httpx.TransportError("connection reset")
        return "ok"

    result = await flaky()

    assert result == "ok"
    assert attempts["count"] == 2


async def test_does_not_retry_permanent_failure() -> None:
    attempts = {"count": 0}

    @with_retry
    async def always_unauthorized() -> None:
        attempts["count"] += 1
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        await always_unauthorized()

    # A 401 will fail identically every time — retrying it is pure waste,
    # so this should only ever be attempted once.
    assert attempts["count"] == 1
