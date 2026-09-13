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

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown resources: DB connection + ingestion scheduler.

    This runs once per process (not per request), which is why both the
    DB connection and the scheduler live here instead of inside a route.
    """
    await connect_to_mongo()
    await ensure_indexes()
    if settings.enable_scheduler:
        start_scheduler()
    logger.info("%s starting up (env=%s)", settings.app_name, settings.environment)
    yield
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
