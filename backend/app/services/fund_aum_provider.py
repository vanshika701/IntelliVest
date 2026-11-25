"""Fund size from AMFI (the mutual fund industry body): average AUM for the
latest published quarter. One ~2 MB response covers every scheme, so it is
fetched once and cached for a day.

AMFI's endpoint is the one behind its public page and is undocumented, so any
failure or change of format simply leaves the size blank.
"""

import asyncio
import logging
import re

import httpx

from app.core.cache import MISSING, TTLCache

logger = logging.getLogger(__name__)

URL = "https://www.amfiindia.com/api/average-aum-schemewise"
# The first period is the latest quarter; the response names it.
PARAMS = {"strType": "Categorywise", "fyId": 1, "periodId": 1, "MF_ID": 0}
LAKHS_PER_CRORE = 100

_cache = TTLCache(ttl_seconds=24 * 60 * 60, max_items=1)
_failures = TTLCache(ttl_seconds=10 * 60, max_items=1)
_lock = asyncio.Lock()

# Everything from the plan/option words on. "Dividend Yield", "Growth Sectors"
# and similar are part of the fund's name.
_PLAN_RE = re.compile(
    r"[\s\-(]*\b(?:direct|regular|retail|institutional|idcw|income distribution|plan|option|payout|"
    r"reinvest\w*|bonus|(?:growth|dividend)(?!\s+(?:sectors?|opportunit\w+|yield|leaders?)))\b.*$",
    re.IGNORECASE,
)


def fund_key(scheme_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _PLAN_RE.sub("", scheme_name).lower())


def parse(payload: dict) -> dict[int, float]:
    """AMFI code -> AUM in ₹ crore of the whole fund (all its plans)."""
    out: dict[int, float] = {}
    for group in payload["data"]:
        totals: dict[str, float] = {}
        codes: dict[str, list[int]] = {}
        for scheme in group["schemes"]:
            key = fund_key(scheme["SchemeNAVName"])
            # Split into two fields; a scheme uses one of them.
            aum = sum(v or 0 for v in scheme["AverageAumForTheMonth"].values())
            totals[key] = totals.get(key, 0) + aum
            codes.setdefault(key, []).append(int(scheme["AMFI_Code"]))
        for key, members in codes.items():
            if totals[key] > 0:
                out.update(dict.fromkeys(members, round(totals[key] / LAKHS_PER_CRORE, 2)))
    return out


async def _fetch() -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(URL, params=PARAMS)
        response.raise_for_status()
        return response.json()


async def get_aum(scheme_code: int) -> dict:
    """{"aum_crore", "aum_period"}, or {} if unknown."""
    async with _lock:
        data = _cache.get("all")
        if data is MISSING:
            if _failures.get("all") is not MISSING:
                return {}
            try:
                payload = await _fetch()
                data = {"period": payload.get("selectedPeriod"), "aum": parse(payload)}
            except Exception as exc:  # noqa: BLE001 - optional data must never break the page
                logger.warning("AMFI fund sizes unavailable: %s", exc)
                _failures.set("all", True)
                return {}
            _cache.set("all", data)
    aum = data["aum"].get(scheme_code)
    return {} if aum is None else {"aum_crore": aum, "aum_period": data["period"]}
