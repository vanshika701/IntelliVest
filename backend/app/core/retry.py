"""Shared retry policy for ingestion's external API calls.

Not every failure deserves a retry. A rate limit (429) or a server error
(5xx) is transient — the same request will probably succeed a few
seconds later, so it's worth retrying with backoff. An auth failure
(401/403) or a bad request (400) will fail identically on every attempt;
retrying it just wastes calls and delays the real error being visible.
This module draws that line once, in one place, instead of every service
guessing at it separately.
"""

import asyncprawcore
import httpx
import requests
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

# Exception types where retrying is actually worth it: network-level
# failures (timeouts, dropped connections) and explicit "try again"
# signals from the APIs themselves (429 rate limit, 5xx server error).
_TRANSIENT_EXCEPTION_TYPES = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    httpx.TransportError,
    asyncprawcore.exceptions.RequestException,
    asyncprawcore.exceptions.ServerError,
    asyncprawcore.exceptions.TooManyRequests,
)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSIENT_EXCEPTION_TYPES):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    # Anything else — auth errors, 4xx client errors, malformed
    # responses — will fail the same way every time. Don't retry it.
    return False


def with_retry(func):
    """Decorator: up to 3 attempts, exponential backoff with jitter,
    only for transient failures. The final attempt's exception is
    re-raised as-is so callers' existing except blocks still work."""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    )(func)
