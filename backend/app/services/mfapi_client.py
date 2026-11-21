"""Client for mfapi.in — free, keyless Indian mutual fund / ETF data
(scheme search and full daily NAV history, sourced from AMFI).

Every call has a timeout, retries transient failures, and is cached:
search results for an hour, scheme data for six hours (NAVs only change
once a day).
"""

import logging
from datetime import UTC, date, datetime

import httpx

from app.core.cache import MISSING, TTLCache
from app.core.retry import with_retry

logger = logging.getLogger(__name__)

MFAPI_BASE_URL = "https://api.mfapi.in"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IntelliVestBot/0.1)"}

_search_cache = TTLCache(ttl_seconds=60 * 60)
_scheme_list_cache = TTLCache(ttl_seconds=24 * 60 * 60, max_items=1)
_scheme_cache = TTLCache(ttl_seconds=6 * 60 * 60, max_items=256)


class MfApiError(Exception):
    """The provider is unreachable or returned something unusable."""


# Network/HTTP failures, timeouts, and malformed JSON or payload shapes.
_PROVIDER_ERRORS = (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError)


@with_retry
async def _get_json(path: str, params: dict | None = None):
    async with httpx.AsyncClient(base_url=MFAPI_BASE_URL, timeout=10.0, headers=_HEADERS) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()


def parse_navs(raw: list[dict]) -> list[tuple[date, float]]:
    """mfapi returns newest-first {"date": "dd-mm-yyyy", "nav": "123.45"};
    return oldest-first (date, nav) pairs, skipping malformed/zero rows."""
    navs = []
    for row in raw:
        try:
            nav = float(row["nav"])
            day = datetime.strptime(row["date"], "%d-%m-%Y").replace(tzinfo=UTC).date()
        except (KeyError, TypeError, ValueError):
            continue
        if nav > 0:
            navs.append((day, nav))
    navs.sort(key=lambda pair: pair[0])
    return navs


def _to_schemes(payload) -> list[dict]:
    return [
        {"scheme_code": int(item["schemeCode"]), "scheme_name": " ".join(str(item["schemeName"]).split())}
        for item in payload or []
        if item.get("schemeCode") and item.get("schemeName")
    ]


async def _live_scheme_list() -> list[dict]:
    """Every scheme that still has an ISIN (~9.4k of ~38k). Schemes without
    any ISIN are long-closed ones — keeping them buries real results."""
    cached = _scheme_list_cache.get("all")
    if cached is not MISSING:
        return cached
    payload = await _get_json("/mf")
    schemes = _to_schemes(
        [item for item in payload or [] if item.get("isinGrowth") or item.get("isinDivReinvestment")]
    )
    _scheme_list_cache.set("all", schemes)
    return schemes


def match_schemes(schemes: list[dict], query: str) -> list[dict]:
    """Schemes whose name contains every word of the query."""
    words = query.lower().split()
    return [s for s in schemes if all(w in s["scheme_name"].lower() for w in words)]


async def search_schemes(query: str, max_results: int = 60) -> list[dict]:
    """Match against the cached full scheme list (mfapi's /mf/search caps
    results at 15, which misses obvious matches such as SBI Gold for
    "gold"); fall back to /mf/search if the list can't be loaded."""
    key = query.strip().lower()
    cached = _search_cache.get(key)
    if cached is not MISSING:
        return cached
    try:
        results = match_schemes(await _live_scheme_list(), query)[:max_results]
    except _PROVIDER_ERRORS as exc:
        logger.warning("mfapi scheme list unavailable (%s); falling back to /mf/search", exc)
        try:
            results = _to_schemes(await _get_json("/mf/search", {"q": query}))
        except _PROVIDER_ERRORS as fallback_exc:
            logger.warning("mfapi search failed for %r: %s", query, fallback_exc)
            raise MfApiError("Mutual fund search is unavailable") from fallback_exc

    _search_cache.set(key, results)
    return results


async def get_scheme(scheme_code: int) -> dict | None:
    """{"meta": {...}, "navs": [(date, nav), ...]} or None if the scheme
    doesn't exist or has no NAV history."""
    cached = _scheme_cache.get(scheme_code)
    if cached is not MISSING:
        return cached
    try:
        payload = await _get_json(f"/mf/{scheme_code}")
    except _PROVIDER_ERRORS as exc:
        logger.warning("mfapi scheme fetch failed for %s: %s", scheme_code, exc)
        raise MfApiError("Mutual fund data is unavailable") from exc

    meta = (payload or {}).get("meta") or {}
    navs = parse_navs((payload or {}).get("data") or [])
    scheme = {"meta": meta, "navs": navs} if meta.get("scheme_name") and navs else None
    _scheme_cache.set(scheme_code, scheme)
    return scheme
