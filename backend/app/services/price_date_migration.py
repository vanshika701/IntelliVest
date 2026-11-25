"""One-time repair of price dates stored before 2026-11-25.

They were converted from IST midnight to UTC before the time was dropped, so
each is one day early. Repaired rows carry `date_basis`, as does everything
ingested since, so this can run on every start and resume if interrupted.
"""

import logging
from datetime import timedelta

from app.data.prices_repository import get_rows_without_date_basis, replace_price_date

logger = logging.getLogger(__name__)


async def migrate_price_dates() -> int:
    # Newest first, so a row never moves onto one that hasn't moved yet.
    rows = await get_rows_without_date_basis()
    for row in rows:
        await replace_price_date(row, row["date"] + timedelta(days=1))
    if rows:
        logger.info("Moved %d price rows to their real trading date", len(rows))
    return len(rows)
