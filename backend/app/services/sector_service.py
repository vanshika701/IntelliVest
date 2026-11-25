"""Phase 6: sector rollups of price trend and news sentiment.

Recomputed by the background jobs after prices or sentiment update and stored
in `sector_snapshots`; requests only read. Every stock in a sector counts
equally, because market caps aren't stored.
"""

import logging
from datetime import UTC, datetime, timedelta

from app.core.constants import SECTORS, TICKER_TO_COMPANY_NAME
from app.data import sector_repository as repo
from app.data.news_repository import (
    get_headlines_for_tickers,
    get_scored_articles_for_ticker,
    get_sector_headlines,
)
from app.data.prices_repository import get_close_series
from app.services.sentiment_service import MIN_ARTICLES_FOR_LABEL, overall_label

logger = logging.getLogger(__name__)

# Trading days back for each change window.
WINDOWS = {"1d": 1, "1w": 5, "1m": 21, "3m": 63}
TREND_WINDOW = "1m"
TREND_THRESHOLD_PCT = 2.0
SENTIMENT_DAYS = 7
SERIES_DAYS = 63
# A stock whose prices stop this long before its sector's newest is left out.
MAX_STALE_DAYS = 7


def pct_change(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or not closes[-1 - days]:
        return None
    return round((closes[-1] / closes[-1 - days] - 1) * 100, 2)


def mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None


def trend_label(change_pct: float | None) -> str | None:
    if change_pct is None:
        return None
    if change_pct > TREND_THRESHOLD_PCT:
        return "up"
    return "down" if change_pct < -TREND_THRESHOLD_PCT else "flat"


def index_series(price_rows: list[list[dict]], days: int = SERIES_DAYS) -> list[dict]:
    """Equal-weighted index (starts at 100) over dates every stock has."""
    if not price_rows:
        return []
    by_stock = [{r["date"]: r["close"] for r in rows} for rows in price_rows]
    dates = sorted(set.intersection(*(set(s) for s in by_stock)))[-(days + 1) :]
    if len(dates) < 2:
        return []
    return [
        {
            "t": d.date().isoformat(),
            "v": round(sum(s[d] / s[dates[0]] for s in by_stock) / len(by_stock) * 100, 2),
        }
        for d in dates
    ]


def build_snapshot(
    sector: str, name: str, prices: dict[str, list[dict]], articles: dict[str, list[dict]], now: datetime
) -> dict:
    """Pure rollup for one sector from its stocks' stored prices and scored news."""
    newest = max((rows[-1]["date"] for rows in prices.values() if rows), default=None)
    stocks, used = [], []
    for ticker, rows in prices.items():
        fresh = bool(rows) and (newest - rows[-1]["date"]).days <= MAX_STALE_DAYS
        closes = [float(r["close"]) for r in rows]
        scores = [a["sentiment"]["score"] for a in articles.get(ticker, [])]
        average = mean(scores)
        stocks.append(
            {
                "ticker": ticker,
                "name": TICKER_TO_COMPANY_NAME.get(ticker, ticker),
                "price": closes[-1] if closes else None,
                "changes": {w: pct_change(closes, d) if fresh else None for w, d in WINDOWS.items()},
                "sentiment_score": average,
                "sentiment_label": overall_label(average) if len(scores) >= MIN_ARTICLES_FOR_LABEL else None,
                "article_count": len(scores),
            }
        )
        if fresh:
            used.append(rows)

    # A story tagged with two of the sector's stocks counts once.
    unique = {a["url"]: a for rows in articles.values() for a in rows}
    score = mean([a["sentiment"]["score"] for a in unique.values()])
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for a in unique.values():
        counts[a["sentiment"]["label"]] = counts.get(a["sentiment"]["label"], 0) + 1

    changes = {}
    for window in WINDOWS:
        value = mean([s["changes"][window] for s in stocks])
        changes[window] = None if value is None else round(value, 2)
    day_moves = [s["changes"]["1d"] for s in stocks if s["changes"]["1d"] is not None]
    return {
        "sector": sector,
        "name": name,
        "stock_count": len(stocks),
        "priced_count": len(used),
        "as_of": newest,
        "changes": changes,
        "trend": trend_label(changes[TREND_WINDOW]),
        "advancers": sum(m > 0 for m in day_moves),
        "decliners": sum(m < 0 for m in day_moves),
        "sentiment": {
            "score": score,
            "label": overall_label(score) if len(unique) >= MIN_ARTICLES_FOR_LABEL else None,
            "article_count": len(unique),
            "label_counts": counts,
            "window_days": SENTIMENT_DAYS,
        },
        "series": index_series(used),
        "stocks": stocks,
        "computed_at": now,
    }


async def refresh_sectors(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=SENTIMENT_DAYS)
    snapshots = []
    for sector, (name, tickers) in SECTORS.items():
        prices = {t: await get_close_series(t) for t in tickers}
        articles = {t: await get_scored_articles_for_ticker(t, since) for t in tickers}
        snapshots.append(build_snapshot(sector, name, prices, articles, now))
    await repo.replace_snapshots(snapshots)
    logger.info("Sector rollups refreshed: %d sectors", len(snapshots))
    return len(snapshots)


async def list_sectors() -> list[dict]:
    return await repo.list_snapshots()


async def get_sector(sector: str) -> dict | None:
    return await repo.get_snapshot(sector)


async def sector_news(sector: str, exclude_ticker: str | None = None, limit: int = 8) -> list[dict] | None:
    """Stored sector-wide headlines, topped up with news about its companies.
    `exclude_ticker` drops stories a stock's own page already covers."""
    if sector not in SECTORS:
        return None
    since = datetime.now(UTC) - timedelta(days=SENTIMENT_DAYS)
    tickers = [t for t in SECTORS[sector][1] if t != exclude_ticker]
    rows = await get_sector_headlines(sector, since, 100)
    rows += await get_headlines_for_tickers(tickers, since, 100)
    out, seen = [], set()
    for row in rows:
        title = row["title"].strip().lower()
        if title in seen or exclude_ticker in row.get("tickers", []):
            continue
        seen.add(title)
        sentiment = row.pop("sentiment", None) or {}
        out.append({**row, "label": sentiment.get("label")})
        if len(out) == limit:
            break
    return sorted(out, key=lambda r: r["published_at"], reverse=True)
