"""Minimal in-process sliding-window rate limiter for our own endpoints.

Per API process, which is all this app runs; behind several instances
this would move to Redis."""

import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> float | None:
        """Record a request. Returns None if allowed, else seconds until
        the next request would be allowed."""
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return self.window_seconds - (now - hits[0])
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()
