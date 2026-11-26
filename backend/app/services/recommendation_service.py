"""Phase 7 recommendation service: gather stored inputs, build the
recommendation (recommendation.py) and store it.

Everything expensive is precomputed elsewhere: market statistics and
sector sentiment by background jobs, fund NAVs cached for hours by the
mfapi client. This call only reads them, optimizes 20 weights (~0.1 s)
and writes one document, so it is safe to run inside a request.
"""

import logging
from datetime import UTC, datetime

from app.data import budget_repository, recommendation_repository
from app.data.sector_repository import list_snapshots
from app.services.asset_allocation import allocate
from app.services.equity_optimizer import optimize_equity
from app.services.fund_selector import select_funds
from app.services.investment_service import IST
from app.services.market_stats_service import get_latest_stats
from app.services.portfolio_service import get_portfolio
from app.services.recommendation import build_recommendation
from app.services.risk_profile_service import get_risk_profile

logger = logging.getLogger(__name__)


class RecommendationUnavailable(Exception):
    """A required input is missing; the message says which and how to fix it."""


class GoalNotFound(Exception):
    pass


async def _signals_and_prices() -> tuple[dict[str, dict], dict[str, float | None]]:
    """Per-stock sentiment and latest price from the Phase 6 sector snapshots."""
    signals, prices = {}, {}
    for snapshot in await list_snapshots():
        for stock in snapshot.get("stocks", []):
            signals[stock["ticker"]] = {
                "sentiment_score": stock.get("sentiment_score"),
                "article_count": stock.get("article_count", 0),
            }
            prices[stock["ticker"]] = stock.get("price")
    return signals, prices


async def _current_holdings(user_id: str) -> list[dict]:
    try:
        return (await get_portfolio(user_id))["holdings"]
    except Exception:  # holdings only add context; never block a recommendation
        logger.exception("Could not load holdings for recommendation")
        return []


async def create_recommendation(
    user_id: str,
    *,
    lump_sum: float,
    monthly_sip: float,
    horizon_months: int | None = None,
    goal_id: str | None = None,
    use_sentiment: bool = True,
) -> dict:
    profile = await get_risk_profile(user_id)
    if profile is None:
        raise RecommendationUnavailable("Answer the risk questionnaire first.")

    goal = None
    if goal_id is not None:
        goal = await budget_repository.get_goal(user_id, goal_id)
        if goal is None:
            raise GoalNotFound(goal_id)
        horizon_months = goal["horizon_months"]

    allocation = allocate(profile["profile"], horizon_months)

    stats = equity = None
    signals: dict[str, dict] = {}
    prices: dict[str, float | None] = {}
    if allocation["equity_pct"] > 0:
        stats = await get_latest_stats()
        if stats is None:
            raise RecommendationUnavailable(
                "Market statistics haven't been computed yet; they refresh after the daily price update."
            )
        signals, prices = await _signals_and_prices()
        equity = optimize_equity(stats, signals, use_sentiment=use_sentiment)

    roles = [r for r, pct in ((allocation["debt_style"], allocation["debt_pct"]),
                              ("gold", allocation["gold_pct"])) if pct > 0]
    funds = await select_funds(roles, datetime.now(IST).date())

    recommendation = build_recommendation(
        profile=profile,
        allocation=allocation,
        equity=equity,
        stats=stats,
        signals=signals,
        funds=funds,
        lump_sum=lump_sum,
        monthly_sip=monthly_sip,
        stock_prices=prices,
        current_holdings=await _current_holdings(user_id),
        goal=goal,
        created_at=datetime.now(UTC),
    )
    return await recommendation_repository.insert_recommendation(user_id, recommendation)


async def get_latest_recommendation(user_id: str) -> dict | None:
    return await recommendation_repository.get_latest_recommendation(user_id)
