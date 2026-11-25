import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.scheduler import start_scheduler, stop_scheduler
from app.data.indexes import ensure_indexes
from app.data.mongo import close_mongo_connection, connect_to_mongo
from app.services.category_migration import migrate_expense_categories
from app.services.sector_service import refresh_sectors
from app.services.sentiment_service import warm_up_model

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown resources: DB connection + ingestion scheduler.

    This runs once per process (not per request), which is why both the
    DB connection and the scheduler live here instead of inside a route.
    """
    if settings.blockchain_enabled:
        # Imported here so web3's dependencies aren't needed while the feature is off.
        from app.services.blockchain.config import load_blockchain_config

        load_blockchain_config(settings)  # stop now rather than run misconfigured
    await connect_to_mongo()
    await ensure_indexes()
    # Phase 8: map old free-text / ML categories onto the fixed list (idempotent).
    await migrate_expense_categories()
    warm_up_task = None
    sector_task = None
    if settings.enable_scheduler:
        start_scheduler()
        # Off the event loop and not awaited: the API is usable immediately.
        warm_up_task = asyncio.create_task(asyncio.to_thread(warm_up_model))
        # Sector rollups from what's already stored, before the first job runs.
        sector_task = asyncio.create_task(refresh_sectors())
    logger.info("%s starting up (env=%s)", settings.app_name, settings.environment)
    yield
    if warm_up_task is not None and not warm_up_task.done():
        warm_up_task.cancel()
    if sector_task is not None and not sector_task.done():
        sector_task.cancel()
    if settings.enable_scheduler:
        stop_scheduler()
    await close_mongo_connection()
    logger.info("%s shutting down", settings.app_name)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
