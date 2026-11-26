"""Phase 7 market statistics job: load stored closes, compute
(market_stats.py) and store. Runs after each price ingestion, so
recommendations only ever read precomputed numbers."""

import logging
from datetime import UTC, datetime

from app.core.constants import STOCK_UNIVERSE
from app.data import market_stats_repository as repo
from app.data.prices_repository import get_close_series
from app.services.market_stats import compute_market_stats

logger = logging.getLogger(__name__)


async def refresh_market_stats(now: datetime | None = None) -> dict | None:
    series = {ticker: await get_close_series(ticker) for ticker in STOCK_UNIVERSE}
    stats = compute_market_stats(series, now or datetime.now(UTC))
    if stats is None:
        logger.warning("Market stats not computed: fewer than two stocks with enough shared history")
        return None
    await repo.save_stats(stats)
    logger.info(
        "Market stats refreshed: %d stocks, %d daily returns to %s (shrinkage %.2f, %d excluded)",
        len(stats["tickers"]), stats["observations"], stats["as_of"].date(),
        stats["shrinkage"], len(stats["excluded"]),
    )
    return stats


async def get_latest_stats() -> dict | None:
    return await repo.get_latest_stats()
