"""Service layer for health checks.

Business logic (what "healthy" means) lives here, not in the route. Right
now that's just "is the database reachable," but this is the seam where
future checks (e.g. background job queue status) get added without the
route ever changing.
"""

from app.data.mongo import ping_database


async def get_health_status() -> dict[str, str]:
    db_ok = await ping_database()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
    }
