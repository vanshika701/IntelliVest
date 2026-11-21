"""Tiny in-process TTL cache for responses from external data providers.

One API process at this project's scale, so an in-memory cache is enough;
a shared cache (Redis) would only matter with several API instances.
"""

import time
from typing import Any

MISSING = object()


class TTLCache:
    def __init__(self, ttl_seconds: float, max_items: int = 512) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any:
        entry = self._items.get(key)
        if entry is None:
            return MISSING
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._items[key]
            return MISSING
        return value

    def set(self, key: Any, value: Any) -> None:
        self._items.pop(key, None)
        if len(self._items) >= self.max_items:
            # Dicts keep insertion order, so the first key is the oldest.
            del self._items[next(iter(self._items))]
        self._items[key] = (time.monotonic() + self.ttl_seconds, value)

    def clear(self) -> None:
        self._items.clear()
