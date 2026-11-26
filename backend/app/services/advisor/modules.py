"""Phase 9 module interface: every module the advisor reads reports in the
same shape, and failures become a status instead of an error.

    ModuleResult = {
        "module": "budget",            # id from core/advisor_config.MODULES
        "label": "Budget health",
        "phase": 8,
        "status": "ok" | "stale" | "not_set_up" | "unavailable" | "not_built",
        "as_of": datetime | None,     # date of the data it's based on
        "version": str | None,        # model / rules version, for traceability
        "facts": [str],               # plain sentences, every number from the data
        "data": {...},                # structured values for the rules engine
        "reason": str | None,         # why it isn't "ok", for the user
        "elapsed_ms": int,
    }

`not_set_up` means the user hasn't given us this yet (no budget, no risk
profile); `unavailable` means it failed or timed out. Only `ok` and
`stale` results carry data the rules may use.

The summarise_* functions are pure (raw service output in, ModuleResult
out) so they are tested without a database; adapters.py does the I/O.
"""

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.core.advisor_config import (
    DEBT_FUND_WORDS,
    GOLD_FUND_WORDS,
    MODULE_TIMEOUT_SECONDS,
    MODULE_TIMEOUTS_SECONDS,
    MODULES,
    STALE_AFTER_DAYS,
)
from app.core.constants import TICKER_TO_COMPANY_NAME, TICKER_TO_SECTOR
from app.core.fund_config import FUND_ROLES
from app.services.budget_rules import inr

logger = logging.getLogger(__name__)

USABLE = ("ok", "stale")
_NO_STOCKS = "No stocks held or in your portfolio plan yet."


def module_result(
    module: str,
    status: str,
    *,
    facts: list[str] | None = None,
    data: dict | None = None,
    as_of: datetime | None = None,
    version: str | None = None,
    reason: str | None = None,
) -> dict:
    label, phase = MODULES[module]
    return {
        "module": module, "label": label, "phase": phase, "status": status,
        "as_of": as_of, "version": version, "facts": facts or [], "data": data or {},
        "reason": reason, "elapsed_ms": 0,
    }


def is_usable(result: dict) -> bool:
    return result["status"] in USABLE


def _aware(value: datetime | None) -> datetime | None:
    """MongoDB returns naive UTC datetimes; make them comparable."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def freshness(module: str, as_of: datetime | None, now: datetime) -> tuple[str, str | None]:
    """("ok", None) or ("stale", reason) from the module's age limit."""
    limit = STALE_AFTER_DAYS.get(module)
    as_of = _aware(as_of)
    if limit is None or as_of is None or now - as_of <= timedelta(days=limit):
        return "ok", None
    return "stale", f"Based on data from {as_of.date()}, more than {limit} days old."


async def run_module(module: str, fetch: Callable[[], Awaitable[dict]]) -> dict:
    """Run one adapter with its timeout. Never raises: a timeout or error
    becomes an `unavailable` result naming the module."""
    timeout = MODULE_TIMEOUTS_SECONDS.get(module, MODULE_TIMEOUT_SECONDS)
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(fetch(), timeout=timeout)
    except TimeoutError:
        logger.warning("Advisor module %s timed out after %.1fs", module, timeout)
        result = module_result(module, "unavailable", reason=f"Didn't respond within {timeout:g} seconds.")
    except Exception:
        logger.exception("Advisor module %s failed", module)
        result = module_result(module, "unavailable", reason="Failed to load; see the server log.")
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result


# --- Budget health and goals (Phase 8) ----------------------------------------

def summarize_budget(analysis: dict | None, health: dict | None) -> dict:
    if analysis is None:
        return module_result("budget", "not_set_up", reason="No budget set up yet (income and spending).")
    emergency = analysis["emergency_fund"]
    emi = next(c for c in analysis["categories"] if c["category"] == "emi_debt")
    overspent = [c for c in analysis["categories"] if c["category"] in analysis["overspent"]]
    facts = [
        (f"Monthly income {inr(analysis['income'])}, spending {inr(analysis['total_spend'])}, "
         f"surplus {inr(analysis['surplus'])}."),
        emergency["message"],
    ]
    if emi["amount"] > 0:
        facts.append(emi["message"])
    if health and health.get("score") is not None:
        facts.append(f"Financial health score {health['score']}/100 ({health['band']}).")
    return module_result(
        "budget", "ok", facts=facts,
        data={
            "income": analysis["income"],
            "surplus": analysis["surplus"],
            "savings_rate_pct": analysis["savings_rate_pct"],
            "basis": analysis["basis"],
            "emergency_fund": {k: emergency[k] for k in ("status", "current", "months_covered", "shortfall", "target_min")},
            "emi": {"amount": emi["amount"], "pct_of_income": emi["pct_of_income"], "status": emi["status"]},
            "overspent": [
                {"category": c["category"], "name": c["name"], "overspend_amount": c["overspend_amount"]}
                for c in overspent
            ],
            "health_score": (health or {}).get("score"),
            "health_band": (health or {}).get("band"),
        },
        version="budget-rules",
    )


def summarize_goals(goals: dict | None) -> dict:
    items = (goals or {}).get("items") or []
    if not items:
        return module_result("goals", "not_set_up", reason="No savings goals saved yet.")
    facts, data = [], []
    for g in items:
        plan = g["plan"]
        afford = plan["affordability"]
        facts.append(f"{g['name']}: {plan['summary']} {afford['message']}")
        data.append({
            "id": g["id"], "name": g["name"], "target_amount": g["target_amount"],
            "horizon_months": g["horizon_months"], "flat_monthly": plan["flat"]["monthly"],
            "affordability": afford["status"],
        })
    combined = goals.get("combined")
    if combined:
        facts.append(combined["message"])
    return module_result("goals", "ok", facts=facts, data={"goals": data, "combined": combined}, version="goal-planner")


# --- Risk profile and portfolio plan (Phase 7) ----------------------------------

def summarize_risk_profile(profile: dict | None) -> dict:
    if profile is None:
        return module_result("risk_profile", "not_set_up", reason="Risk questionnaire not answered yet.")
    facts = [
        (f"Risk profile: {profile['label']} (capacity {profile['capacity_score']:g}/100, "
         f"tolerance {profile['tolerance_score']:g}/100)."),
        *profile.get("notes", []),
    ]
    return module_result(
        "risk_profile", "ok", facts=facts,
        data={k: profile[k] for k in ("profile", "label", "capacity_score", "tolerance_score", "limited_by")},
        as_of=profile.get("updated_at"), version=profile.get("version"),
    )


def summarize_portfolio_plan(rec: dict | None, now: datetime) -> dict:
    if rec is None:
        return module_result("portfolio_plan", "not_set_up", reason="No portfolio plan built yet.")
    alloc = rec["allocation"]
    status, reason = freshness("portfolio_plan", rec["created_at"], now)
    goal = rec["inputs"].get("goal")
    target = f'for "{goal["name"]}"' if goal else f"for {rec['inputs']['horizon_months']} months"
    facts = [(f"Latest plan {target}: {alloc['equity_pct']}% stocks, {alloc['debt_pct']}% debt, "
              f"{alloc['gold_pct']}% gold ({rec['profile']['label']} profile).")]
    return module_result(
        "portfolio_plan", status, facts=facts, reason=reason,
        data={
            "id": rec["id"],
            "inputs": rec["inputs"],
            "split": {"equity": alloc["equity_pct"], "debt": alloc["debt_pct"], "gold": alloc["gold_pct"]},
            "holdings": [
                {"instrument_id": h["instrument_id"], "name": h["name"], "asset_class": h["asset_class"],
                 "weight": h["weight"], "lump_sum_amount": h["lump_sum_amount"], "monthly_amount": h["monthly_amount"]}
                for h in rec["holdings"]
            ],
            "stock_tickers": [h["instrument_id"].removeprefix("stock-") for h in rec["holdings"] if h["kind"] == "stock"],
        },
        as_of=rec["created_at"], version=rec["versions"].get("recommendation"),
    )


# --- Holdings (Phase 2 investments) ---------------------------------------------

_FUND_ROLE_BY_ID = {f"mf-{c.scheme_code}": role for role in FUND_ROLES.values() for c in role.choices}


def asset_class(holding: dict) -> str:
    """equity / debt / gold, or unclassified when we can't tell honestly."""
    if holding["instrument_type"] == "STOCK":
        return "equity"
    role = _FUND_ROLE_BY_ID.get(holding["instrument_id"])
    if role is not None:
        return "gold" if role.id == "gold" else "debt"
    name = holding["instrument_name"].lower()
    if any(w in name for w in GOLD_FUND_WORDS):
        return "gold"
    if any(w in name for w in DEBT_FUND_WORDS):
        return "debt"
    return "unclassified"


def summarize_holdings(portfolio: dict | None) -> dict:
    holdings = (portfolio or {}).get("holdings") or []
    if not holdings:
        return module_result("holdings", "not_set_up", reason="No investments recorded yet.")
    by_class: dict[str, float] = {}
    rows = []
    for h in holdings:
        cls = asset_class(h)
        value = h["current_value"]
        if value is not None:
            by_class[cls] = by_class.get(cls, 0.0) + value
        rows.append({"instrument_id": h["instrument_id"], "name": h["instrument_name"],
                     "asset_class": cls, "current_value": value, "gain_pct": h["gain_pct"]})
    valued = sum(by_class.values())
    split = {c: round(v / valued * 100, 1) for c, v in by_class.items()} if valued else {}
    facts = [f"You hold {len(holdings)} investments worth {inr(portfolio['current_value'])}."]
    if split:
        facts.append("By value: " + ", ".join(f"{c} {p:g}%" for c, p in sorted(split.items())) + ".")
    if portfolio.get("unvalued_count"):
        facts.append(f"{portfolio['unvalued_count']} holding(s) couldn't be valued right now.")
    return module_result(
        "holdings", "ok", facts=facts,
        data={"total_value": portfolio["current_value"], "split_pct": split, "holdings": rows,
              "unvalued_count": portfolio.get("unvalued_count", 0),
              "stock_tickers": [r["instrument_id"].removeprefix("stock-") for r in rows if r["asset_class"] == "equity"]},
    )


# --- Sectors and sentiment (Phases 6 and 5) --------------------------------------

def _latest(snapshots: list[dict]) -> datetime | None:
    dates = [_aware(s.get("as_of")) for s in snapshots if s.get("as_of")]
    return max(dates) if dates else None


def summarize_sectors(snapshots: list[dict], tickers: list[str], now: datetime) -> dict:
    """Sector trend for the sectors of the given stocks (held or planned)."""
    if not tickers:
        return module_result("sectors", "not_set_up", reason=_NO_STOCKS)
    if not snapshots:
        return module_result("sectors", "unavailable", reason="Sector figures haven't been computed yet.")
    wanted = {TICKER_TO_SECTOR.get(t) for t in tickers} - {None}
    as_of = _latest(snapshots)
    status, reason = freshness("sectors", as_of, now)
    rows = [
        {"sector": s["sector"], "name": s["name"], "change_1m": s["changes"].get("1m"), "trend": s["trend"],
         "sentiment_label": s["sentiment"]["label"], "article_count": s["sentiment"]["article_count"]}
        for s in snapshots if s["sector"] in wanted
    ]
    facts = [
        f"{r['name']} sector: {r['change_1m']:+.1f}% over 1 month ({r['trend'] or 'no trend'})"
        + (f", news {r['sentiment_label']}." if r["sentiment_label"] else ".")
        for r in rows if r["change_1m"] is not None
    ]
    return module_result("sectors", status, facts=facts, reason=reason, as_of=as_of, data={"sectors": rows})


def summarize_sentiment(snapshots: list[dict], tickers: list[str], now: datetime) -> dict:
    """Recent FinBERT sentiment for the given stocks, from the Phase 6 rollup."""
    if not tickers:
        return module_result("sentiment", "not_set_up", reason=_NO_STOCKS)
    if not snapshots:
        return module_result("sentiment", "unavailable", reason="News sentiment hasn't been computed yet.")
    stocks = {s["ticker"]: s for snap in snapshots for s in snap.get("stocks", [])}
    as_of = _latest(snapshots)
    status, reason = freshness("sentiment", as_of, now)
    rows, facts = [], []
    for t in tickers:
        s = stocks.get(t)
        if s is None:
            continue
        rows.append({"ticker": t, "name": s["name"], "score": s["sentiment_score"],
                     "label": s["sentiment_label"], "article_count": s["article_count"]})
        if s["sentiment_label"]:
            facts.append(f"{s['name']}: {s['sentiment_label']} news over the last week "
                         f"(score {s['sentiment_score']:+.2f}, {s['article_count']} articles).")
    return module_result("sentiment", status, facts=facts, reason=reason, as_of=as_of,
                         data={"stocks": rows}, version="FinBERT")


# --- Predictions (Phase 4) --------------------------------------------------------

def summarize_predictions(by_ticker: dict[str, list[dict]], horizon_days: int, now: datetime) -> dict:
    """One-year return ranges for the given stocks. Direction and rank are
    left out on purpose: Phase 4's backtest found up/down calls no better
    than "always up" and ranking weak (docs/PHASE_4_PREDICTION.md)."""
    if not by_ticker:
        return module_result("predictions", "not_set_up", reason=_NO_STOCKS)
    rows, facts, as_ofs, versions = [], [], [], set()
    for ticker, docs in by_ticker.items():
        doc = next((d for d in docs if d["horizon_days"] == horizon_days), None)
        if doc is None:
            continue
        # Stored as log returns, like the Phase 4 API converts them.
        low, mid, high = (round(math.expm1(doc[k]) * 100, 1) for k in ("low", "mid", "high"))
        name = TICKER_TO_COMPANY_NAME.get(ticker, ticker)
        rows.append({"ticker": ticker, "name": name, "low_pct": low, "mid_pct": mid, "high_pct": high,
                     "sector": TICKER_TO_SECTOR.get(ticker)})
        facts.append(f"{name}: over 1 year, 8 in 10 outcomes between {low:+.1f}% and {high:+.1f}% "
                     f"(middle case {mid:+.1f}%).")
        as_ofs.append(_aware(doc["as_of"]))
        versions.add(doc["model_version"])
    if not rows:
        return module_result("predictions", "unavailable", reason="No stored predictions for these stocks.")
    as_of = max(as_ofs)
    status, reason = freshness("predictions", as_of, now)
    return module_result(
        "predictions", status, facts=facts, reason=reason, as_of=as_of,
        data={"horizon_days": horizon_days, "stocks": rows,
              "used_for": "risk ranges only, not buy or sell direction"},
        version=", ".join(sorted(versions)),
    )
