"""Phase 9 adapters: read each module through its own existing service and
summarise it (modules.py). Reads only stored or cached data; nothing here
recomputes prices, sentiment or predictions.

gather_modules() runs them in two rounds, each module concurrently with
its own timeout:
1. budget, goals, risk profile, portfolio plan, holdings, sectors
   (only need the user);
2. sentiment and predictions, for the stocks the user holds or plans to
   hold (known only after round 1).
"""

import asyncio
from datetime import UTC, datetime

from app.core.advisor_config import MODULES, PREDICTION_HORIZON_TRADING_DAYS
from app.data import prediction_repository
from app.data.sector_repository import list_snapshots
from app.services import (
    budget_service,
    portfolio_service,
    recommendation_service,
    risk_profile_service,
)
from app.services.advisor.modules import (
    is_usable,
    run_module,
    summarize_budget,
    summarize_goals,
    summarize_holdings,
    summarize_portfolio_plan,
    summarize_predictions,
    summarize_risk_profile,
    summarize_sectors,
    summarize_sentiment,
)
from app.services.health_score import health_score


async def budget(user_id: str) -> dict:
    analysis = await budget_service.analysis(user_id, "auto")
    # health_score() is pure; computing it here avoids a second analysis query.
    return summarize_budget(analysis, health_score(analysis) if analysis else None)


async def goals(user_id: str) -> dict:
    return summarize_goals(await budget_service.list_goals(user_id))


async def risk_profile(user_id: str) -> dict:
    return summarize_risk_profile(await risk_profile_service.get_risk_profile(user_id))


async def portfolio_plan(user_id: str, now: datetime) -> dict:
    return summarize_portfolio_plan(await recommendation_service.get_latest_recommendation(user_id), now)


async def holdings(user_id: str) -> dict:
    return summarize_holdings(await portfolio_service.get_portfolio(user_id))


async def sectors(tickers: list[str], now: datetime) -> dict:
    return summarize_sectors(await list_snapshots(), tickers, now)


async def sentiment(tickers: list[str], now: datetime) -> dict:
    return summarize_sentiment(await list_snapshots(), tickers, now)


async def predictions(tickers: list[str], now: datetime) -> dict:
    docs = await asyncio.gather(*(prediction_repository.get_latest_for_ticker(t) for t in tickers))
    return summarize_predictions(dict(zip(tickers, docs, strict=True)), PREDICTION_HORIZON_TRADING_DAYS, now)


def _tickers(*results: dict) -> list[str]:
    """Stocks the user holds or the plan includes, in a stable order."""
    seen: dict[str, None] = {}
    for r in results:
        if is_usable(r):
            for t in r["data"].get("stock_tickers", []):
                seen[t] = None
    return list(seen)


async def gather_modules(user_id: str, now: datetime | None = None) -> list[dict]:
    """Every module's result, in MODULES order. Never raises."""
    now = now or datetime.now(UTC)
    first = await asyncio.gather(
        run_module("budget", lambda: budget(user_id)),
        run_module("goals", lambda: goals(user_id)),
        run_module("risk_profile", lambda: risk_profile(user_id)),
        run_module("portfolio_plan", lambda: portfolio_plan(user_id, now)),
        run_module("holdings", lambda: holdings(user_id)),
    )
    by_id = {r["module"]: r for r in first}
    tickers = _tickers(by_id["holdings"], by_id["portfolio_plan"])
    second = await asyncio.gather(
        run_module("sectors", lambda: sectors(tickers, now)),
        run_module("sentiment", lambda: sentiment(tickers, now)),
        run_module("predictions", lambda: predictions(tickers, now)),
    )
    by_id |= {r["module"]: r for r in second}
    return [by_id[m] for m in MODULES]
