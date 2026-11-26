"""Every equity listed on NSE, for search and stock pages.

The 20 stocks in STOCK_UNIVERSE are "tracked": prices stored daily, news,
sentiment, sectors and scheduled predictions. Any other NSE stock can
still be searched and opened; its prices come from Yahoo on demand.

The list is a committed snapshot of NSE's EQUITY_L.csv (about 2,600
companies), refreshed with `python -m scripts.update_nse_listing`.
"""

import csv
import re
from functools import cache
from pathlib import Path

from app.core.constants import STOCK_UNIVERSE, TICKER_TO_COMPANY_NAME

LISTING_PATH = Path(__file__).resolve().parents[1] / "data" / "nse_equities.csv"
SUFFIX = ".NS"
_TRACKED = set(STOCK_UNIVERSE)
_COMPANY_ENDINGS = re.compile(r"\s+(limited|ltd\.?)$", re.IGNORECASE)


def clean_name(name: str) -> str:
    """ "Coal India Limited" -> "Coal India"."""
    return _COMPANY_ENDINGS.sub("", name.strip())


@cache
def _listing() -> dict[str, str]:
    """Yahoo ticker (SYMBOL.NS) -> company name. Tracked names win."""
    names: dict[str, str] = {}
    if LISTING_PATH.exists():
        with LISTING_PATH.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                names[row["symbol"] + SUFFIX] = clean_name(row["name"])
    for ticker in STOCK_UNIVERSE:
        names[ticker] = TICKER_TO_COMPANY_NAME.get(ticker, names.get(ticker, ticker))
    return names


def is_listed(ticker: str) -> bool:
    return ticker in _listing()


def is_tracked(ticker: str) -> bool:
    return ticker in _TRACKED


def company_name(ticker: str) -> str:
    return _listing().get(ticker, ticker.removesuffix(SUFFIX))


def search(query: str, limit: int) -> list[tuple[str, str]]:
    """(ticker, name) pairs matching the symbol or name, best first:
    exact symbol, then symbol or name starting with the query, then a word
    in the name starting with it. A match inside a word ("old" in "Gold")
    doesn't count. Tracked stocks first on ties."""
    q = query.strip().lower()
    if not q:
        return []
    scored = []
    for ticker, name in _listing().items():
        symbol, lower = ticker.removesuffix(SUFFIX).lower(), name.lower()
        if symbol == q:
            score = 0
        elif symbol.startswith(q) or lower.startswith(q):
            score = 1
        elif re.search(rf"\b{re.escape(q)}", lower):
            score = 2
        else:
            continue
        scored.append((score, ticker not in _TRACKED, len(name), ticker, name))
    scored.sort()
    return [(ticker, name) for *_, ticker, name in scored[:limit]]
