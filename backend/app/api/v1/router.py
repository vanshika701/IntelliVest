from fastapi import APIRouter

from app.api.v1.routes import (
    advisor,
    alerts,
    auth,
    budget,
    dashboard,
    expenses,
    health,
    instruments,
    investments,
    market_stats,
    recommendations,
    risk_profile,
    sectors,
    sentiment,
    watchlist,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(expenses.router)
api_router.include_router(watchlist.router)
api_router.include_router(alerts.router)
api_router.include_router(dashboard.router)
api_router.include_router(sentiment.router)
api_router.include_router(instruments.router)
api_router.include_router(investments.router)
api_router.include_router(budget.router)
api_router.include_router(sectors.router)
api_router.include_router(risk_profile.router)
api_router.include_router(market_stats.router)
api_router.include_router(recommendations.router)
api_router.include_router(advisor.router)
