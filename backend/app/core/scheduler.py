"""Background job scheduler for ingestion and price alert evaluation.

Runs inside the same process as the API, via FastAPI's lifespan, using
APScheduler's AsyncIOScheduler — which shares the app's existing asyncio
event loop. No separate worker process or task queue (Celery/Redis, etc.)
is needed at this project's current scale; that's a real upgrade to make
later if ingestion ever needs to run somewhere the API isn't.

This is what finally makes ingestion "a scheduled/background job, not a
script you remember to re-run" — the three scripts/ingest_*.py entry
points still exist for manual one-off runs, but the app now keeps itself
up to date on its own once it's running. It's also what makes Phase 2's
price alerts actually fire: evaluate_all_alerts() only ever does anything
useful if something calls it on a schedule.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.constants import FINANCE_SUBREDDITS, STOCK_UNIVERSE
from app.services.alert_service import evaluate_all_alerts
from app.services.market_data_service import ingest_stock_universe
from app.services.news_service import ingest_news_for_universe
from app.services.reddit_service import ingest_reddit_posts

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_market_data_ingestion() -> None:
    logger.info("Scheduled job starting: market data ingestion")
    await ingest_stock_universe(STOCK_UNIVERSE)


async def _run_news_ingestion() -> None:
    logger.info("Scheduled job starting: news ingestion")
    await ingest_news_for_universe(STOCK_UNIVERSE)


async def _run_reddit_ingestion() -> None:
    logger.info("Scheduled job starting: Reddit ingestion")
    await ingest_reddit_posts(FINANCE_SUBREDDITS)


async def _run_alert_evaluation() -> None:
    logger.info("Scheduled job starting: price alert evaluation")
    await evaluate_all_alerts()


def start_scheduler() -> None:
    # Prices move once per trading day — refresh daily, after Indian
    # market close (15:30 IST) with a buffer for the day's data to settle.
    scheduler.add_job(
        _run_market_data_ingestion,
        trigger=CronTrigger(hour=18, minute=0),
        id="market_data_ingestion",
        replace_existing=True,
    )
    # News and social sentiment move much faster than daily prices.
    scheduler.add_job(
        _run_news_ingestion,
        trigger=IntervalTrigger(hours=1),
        id="news_ingestion",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_reddit_ingestion,
        trigger=IntervalTrigger(hours=1),
        id="reddit_ingestion",
        replace_existing=True,
    )
    # Phase 2 exit criterion: "get a rule-based alert when a price crosses
    # a threshold" — that only actually happens if this runs. Every 5
    # minutes is frequent enough to feel responsive without hammering Mongo.
    scheduler.add_job(
        _run_alert_evaluation,
        trigger=IntervalTrigger(minutes=5),
        id="alert_evaluation",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Ingestion scheduler started (market data daily, news/Reddit hourly, alerts every 5min)"
    )


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Ingestion scheduler stopped")
