import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    """Set up structured, leveled logging for the whole app.

    Called once at process startup (see main.py). Without this, FastAPI/
    Uvicorn errors can get swallowed or printed with no timestamp/context —
    this is the minimum bar for "a failure is visible and debuggable."
    """
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
