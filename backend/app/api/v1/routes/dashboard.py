"""Dashboard route — aggregated payload for the unified dashboard view.

Instead of the frontend making 4-5 separate API calls to populate the
dashboard, this endpoint gathers watchlist, budget summary, active alerts,
and recent news into one response.  Each sub-call is independent and
won't block if one source has no data yet.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id
from app.data.collections import get_news_collection
from app.services.alert_service import list_alerts
from app.services.expense_service import summarize_expenses
from app.services.watchlist_service import get_enriched_watchlist

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _recent_news(limit: int = 10) -> list[dict]:
    """Fetch the most recent news articles across all tickers."""
    cursor = (
        get_news_collection()
        .find({}, {"_id": 0, "url": 1, "title": 1, "source": 1, "published_at": 1, "tickers": 1})
        .sort("published_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


@router.get("")
async def get_dashboard(user_id: str = Depends(get_current_user_id)):
    watchlist = await get_enriched_watchlist(user_id)
    budget = await summarize_expenses(user_id)
    alerts = await list_alerts(user_id)
    news = await _recent_news()

    # Separate triggered (notification-worthy) alerts from active ones.
    triggered_alerts = [a for a in alerts if a.get("triggered")]
    active_alerts = [a for a in alerts if a.get("is_active") and not a.get("triggered")]

    return {
        "watchlist": watchlist,
        "budget_summary": budget,
        "active_alerts": active_alerts,
        "triggered_alerts": triggered_alerts,
        "recent_news": news,
    }
