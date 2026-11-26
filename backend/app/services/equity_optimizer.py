"""Pure Phase 7 equity optimizer: weights for the stocks in the equity part
of a portfolio. No I/O: it takes the stored market statistics (step 3)
and per-stock signals, and returns weights with the numbers behind them.

Method:
1. Minimum variance. Find the long-only weights with the lowest
   predicted volatility, using the shrunk covariance, with no stock above
   MAX_STOCK_WEIGHT and no sector above MAX_SECTOR_WEIGHT. Expected
   returns are deliberately NOT used: estimated from two years of prices
   they are mostly noise, and optimisers that chase them concentrate in
   past winners (the "error maximisation" problem, Michaud 1989, Financial
   Analysts Journal 45(1)). Minimum-variance portfolios need only the
   covariance, which is estimated far more reliably.
2. Sentiment tilt (optional). Move weight towards stocks with better
   recent FinBERT sentiment, within a small variance budget and a cap on
   how far any weight moves. A Phase 4 prediction signal can slot in the
   same way once it exists.
3. Compare with an equal-weight portfolio of the same stocks, the honest
   baseline any optimizer has to beat.
"""

import numpy as np
from scipy.optimize import minimize

from app.core.constants import TICKER_TO_SECTOR
from app.core.portfolio_config import (
    MAX_SECTOR_WEIGHT,
    MAX_STOCK_WEIGHT,
    MIN_HOLDING_WEIGHT,
    OPTIMIZER_VERSION,
    SENTIMENT_MAX_VARIANCE_INCREASE,
    SENTIMENT_MAX_WEIGHT_SHIFT,
    SENTIMENT_MIN_ARTICLES,
)


class OptimizationError(RuntimeError):
    """The limits can't be met with these stocks, or the solver failed."""


def _covariance(stats: dict, tickers: list[str]) -> np.ndarray:
    return np.array([[stats["covariance"][a][b] for b in tickers] for a in tickers])


def _sector_constraints(tickers: list[str], max_sector: float) -> list[dict]:
    constraints = []
    for sector in sorted({TICKER_TO_SECTOR.get(t, t) for t in tickers}):
        mask = np.array([TICKER_TO_SECTOR.get(t, t) == sector for t in tickers], dtype=float)
        constraints.append({"type": "ineq", "fun": lambda w, m=mask: max_sector - m @ w})
    return constraints


def _check_feasible(tickers: list[str], max_stock: float, max_sector: float) -> None:
    """The caps must leave room for 100%: each sector can hold at most
    min(sector cap, stocks in it x stock cap)."""
    capacity = sum(
        min(max_sector, max_stock * sum(TICKER_TO_SECTOR.get(t, t) == s for t in tickers))
        for s in {TICKER_TO_SECTOR.get(t, t) for t in tickers}
    )
    if capacity < 1 - 1e-9:
        raise OptimizationError(
            f"Limits allow at most {capacity:.0%} to be invested in these {len(tickers)} stocks"
        )


def _solve(objective, start: np.ndarray, bounds: list[tuple[float, float]], constraints: list[dict]):
    result = minimize(
        objective, start, method="SLSQP", bounds=bounds,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}, *constraints],
        options={"maxiter": 500, "ftol": 1e-12},
    )
    if not result.success:
        raise OptimizationError(f"Optimizer did not converge: {result.message}")
    return np.clip(result.x, 0, None)


def minimum_variance(
    cov: np.ndarray, tickers: list[str], max_stock: float, max_sector: float
) -> np.ndarray:
    """Lowest-variance weights within the caps; holdings under
    MIN_HOLDING_WEIGHT are dropped and the rest re-optimised."""
    _check_feasible(tickers, max_stock, max_sector)
    allowed = np.ones(len(tickers), dtype=bool)
    sectors = _sector_constraints(tickers, max_sector)
    for _ in range(len(tickers)):
        bounds = [(0.0, max_stock if ok else 0.0) for ok in allowed]
        start = np.where(allowed, 1 / allowed.sum(), 0.0)
        weights = _solve(lambda w: w @ cov @ w, start, bounds, sectors)
        tiny = allowed & (weights < MIN_HOLDING_WEIGHT)
        if not tiny.any():
            return weights / weights.sum()
        remaining = [t for t, ok in zip(tickers, allowed & ~tiny, strict=True) if ok]
        try:
            _check_feasible(remaining, max_stock, max_sector)
        except OptimizationError:
            return weights / weights.sum()  # dropping them would break the caps
        allowed &= ~tiny
    return weights / weights.sum()


def sentiment_scores(signals: dict[str, dict], tickers: list[str]) -> np.ndarray:
    """Average FinBERT score per stock (-1..1); 0 where there are too few articles."""
    scores = []
    for t in tickers:
        signal = signals.get(t) or {}
        enough = (signal.get("article_count") or 0) >= SENTIMENT_MIN_ARTICLES
        score = signal.get("sentiment_score")
        scores.append(float(score) if enough and score is not None else 0.0)
    return np.array(scores)


def sentiment_tilt(
    cov: np.ndarray, tickers: list[str], base: np.ndarray, scores: np.ndarray,
    max_stock: float, max_sector: float,
) -> np.ndarray:
    """Maximise sentiment exposure without raising variance by more than
    SENTIMENT_MAX_VARIANCE_INCREASE or moving any weight by more than
    SENTIMENT_MAX_WEIGHT_SHIFT. Stocks the base portfolio dropped stay out."""
    if not scores.any():
        return base
    budget = (base @ cov @ base) * (1 + SENTIMENT_MAX_VARIANCE_INCREASE)
    constraints = [
        *_sector_constraints(tickers, max_sector),
        {"type": "ineq", "fun": lambda w: budget - w @ cov @ w},
    ]
    allowed = base > 0
    for _ in range(len(tickers)):
        bounds = [
            (max(0.0, w - SENTIMENT_MAX_WEIGHT_SHIFT), min(max_stock, w + SENTIMENT_MAX_WEIGHT_SHIFT))
            if ok else (0.0, 0.0)
            for w, ok in zip(base, allowed, strict=True)
        ]
        start = np.clip(base, [lo for lo, _ in bounds], [hi for _, hi in bounds])
        try:
            tilted = _solve(lambda w: -(scores @ w), start, bounds, constraints)
        except OptimizationError:
            return base  # no tilt fits the budget once those holdings are dropped
        # Same rule as minimum_variance: no dust holdings.
        tiny = allowed & (tilted < MIN_HOLDING_WEIGHT)
        if not tiny.any():
            return tilted / tilted.sum()
        allowed &= ~tiny
    return base


def _volatility(cov: np.ndarray, w: np.ndarray) -> float:
    return float(np.sqrt(w @ cov @ w))


def _summary(cov: np.ndarray, tickers: list[str], w: np.ndarray) -> dict:
    sectors: dict[str, float] = {}
    for t, weight in zip(tickers, w, strict=True):
        sector = TICKER_TO_SECTOR.get(t, t)
        sectors[sector] = sectors.get(sector, 0.0) + float(weight)
    held = w[w > 1e-6]
    return {
        "annual_volatility": round(_volatility(cov, w), 6),
        "holdings": len(held),
        # 1 / sum(w^2): how many equal-sized holdings this behaves like.
        "effective_holdings": round(float(1 / (held**2).sum()), 2),
        "sector_weights": {s: round(v, 4) for s, v in sorted(sectors.items()) if v > 1e-6},
    }


def optimize_equity(
    stats: dict,
    signals: dict[str, dict] | None = None,
    use_sentiment: bool = True,
    max_stock: float = MAX_STOCK_WEIGHT,
    max_sector: float = MAX_SECTOR_WEIGHT,
) -> dict:
    """Weights for every stock in `stats`, plus how they compare with
    equal weights. `signals` maps ticker -> {"sentiment_score",
    "article_count"} (e.g. from Phase 6 sector snapshots)."""
    tickers = list(stats["tickers"])
    cov = _covariance(stats, tickers)

    base = minimum_variance(cov, tickers, max_stock, max_sector)
    scores = sentiment_scores(signals or {}, tickers)
    weights = sentiment_tilt(cov, tickers, base, scores, max_stock, max_sector) if use_sentiment else base
    equal = np.full(len(tickers), 1 / len(tickers))

    stocks = [
        {
            "ticker": t,
            "sector": TICKER_TO_SECTOR.get(t),
            "weight": round(float(w), 4),
            "min_variance_weight": round(float(b), 4),
            "sentiment_score": round(float(s), 4),
            "annual_volatility": stats["stocks"][t]["annual_volatility"],
        }
        for t, w, b, s in zip(tickers, weights, base, scores, strict=True)
    ]
    stocks.sort(key=lambda s: s["weight"], reverse=True)
    return {
        "stocks": stocks,
        "portfolio": _summary(cov, tickers, weights),
        "min_variance": _summary(cov, tickers, base),
        "equal_weight": _summary(cov, tickers, equal),
        "sentiment_used": bool(use_sentiment and scores.any()),
        "limits": {"max_stock_weight": max_stock, "max_sector_weight": max_sector},
        "market_stats_as_of": stats["as_of"],
        "version": OPTIMIZER_VERSION,
    }
