# Phase 7: Portfolio Recommendation Engine

Built 2026-11-26 on branch `phase-7-portfolio`.

Given a user's risk profile and a goal, IntelliVest suggests how to split
their money across stocks, debt and gold, which stocks and funds to use,
how many rupees go where, and why. Page: **Portfolio plan**
(`/portfolio-plan`).

This is not a trained classifier: no public dataset maps "user profile →
correct portfolio". It is rules (risk profile, asset split), optimization
(stock weights) and model signals (FinBERT sentiment; Phase 4 predictions
later), checked with a walk-forward backtest.

Educational illustration only, not investment advice: IntelliVest is not
a SEBI-registered investment adviser. Every recommendation says so.

## How it works

```
Risk questionnaire ──> profile ──┐
Goal horizon ────────────────────┴─> asset split ──┬─> stock weights (stored market stats + sentiment)
                                                   └─> debt and gold funds (mfapi.in)
                                   ──> rupee amounts, reasons, risk, differences ──> stored recommendation
```

| Step | What | Where |
|---|---|---|
| Risk profile | 8 questions: 4 capacity (horizon, emergency fund, income, EMIs), 4 tolerance (reaction to a fall, objective, experience, acceptable loss). Each dimension scored 0-100; the **lower** one sets one of 5 profiles. Needing the money within a year caps it at Conservative, no emergency fund at Moderately conservative. | `core/risk_config.py`, `services/risk_profile.py` |
| Asset split | Profile → stocks / debt / gold for long horizons, then capped by horizon: no stocks within 3 years, at most 40% at 3-5 years. Cut amounts move to debt. | `core/allocation_config.py`, `services/asset_allocation.py` |
| Market statistics | After each price update: daily returns over up to 504 days, volatility, max drawdown, Ledoit-Wolf shrunk covariance and correlations, one document per price date. | `services/market_stats.py`, `market_stats_service.py` |
| Stock weights | Minimum variance, long only, ≤15% per stock, ≤35% per sector, no holding under 1%. Past returns are deliberately not used. Optional sentiment tilt: each weight moves ≤3 points, variance rises ≤5%, needs ≥3 articles. | `core/portfolio_config.py`, `services/equity_optimizer.py` |
| Debt and gold funds | Two Direct-Growth funds per role (liquid, short duration, corporate bond, gold fund of funds). The first that exists, is in the right AMFI category and has a NAV under 10 days old is used. | `core/fund_config.py`, `services/fund_selector.py` |
| Recommendation | Rupee amounts that add up exactly, reasons per holding, minimum-amount warnings, a risk summary, differences from current holdings, versions of every input. Stored per user. | `services/recommendation.py`, `recommendation_service.py` |

### Sources and our own choices

- **From sources:** Conservative 15/75/10, Moderate 45/45/10 and Aggressive
  75/15/10 (Nippon India risk analyzers, "indicative"); 10% gold within the
  World Gold Council's 7.5-15% range for Indian portfolios (press coverage
  of its 2026 research); Ledoit & Wolf (2004) shrinkage; corporate bond
  funds hold ≥80% AA+ (SEBI categorisation, 2017).
- **Our own:** questionnaire scores and band edges, the two in-between
  splits (30/60/10, 60/30/10), the 3- and 5-year horizon caps, all
  optimizer limits, the 0.2% trading cost and 6% risk-free rate in the
  backtest. Each is in one config file and easy to change.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/v1/risk-profile/questions` | Questionnaire (no login) |
| GET / PUT | `/api/v1/risk-profile` | Read / answer (`{"answers": {question: option}}`) |
| GET | `/api/v1/risk-profile/allocation?horizon_months=` | Asset split for the user's profile |
| GET | `/api/v1/market-stats/latest` | Latest stored statistics |
| POST | `/api/v1/recommendations` | `{horizon_months or goal_id, lump_sum, monthly_sip, use_sentiment}`; 409 if a profile or market data is missing |
| GET | `/api/v1/recommendations/latest` | The user's latest recommendation |

New collections: `risk_profiles` (unique per user), `market_stats` (unique
per price date), `recommendations` (by user, newest first).

## Evaluation

Walk-forward backtest, `ml/backtest_portfolio.py`: every 21 trading days
from 2013 to 2026, build the stock portfolio from past prices only with
the app's own code, hold it, charge 0.2% per rupee traded. 163 rebalances,
13.6 years. Full results: `ml/models/portfolio_backtest/metrics.json` and
`ml/log.md`.

| Strategy | CAGR | Volatility | Max drawdown | Sharpe |
|---|---|---|---|---|
| Minimum variance (ours) | 16.9% | 13.9% | -29.6% | 0.78 |
| Equal weight, same 20 stocks | 17.7% | 16.0% | -36.7% | 0.73 |
| Nifty 50 price index | 11.2% | 16.1% | -38.4% | 0.33 |

- The optimizer lowers risk out of sample (calmer than equal weight in 80%
  of months) for slightly less return. It is not a return-beating model.
- Its risk predictions held up: 12.6% predicted vs 12.4% realised volatility.
- The index comparison is flattered by hindsight (today's large caps) and
  by the index excluding dividends; optimizer vs equal weight is the fair one.
- The sentiment tilt is not backtested: there are no historical FinBERT scores.

## Limits

- **Risk figure is an upper bound:** stocks, debt and gold are combined as
  if they always moved together; cross-asset correlations aren't estimated.
- **"Bad year" assumes normal returns;** real crashes can be worse.
- **Minimum variance favours recently calm stocks** (currently FMCG and
  pharma) and can lag for a year or more (2025: 5.5% vs 11.5%).
- **Expense ratio and fund size aren't checked** for the funds; the free
  data sources don't provide them reliably.
- **Small amounts:** many stocks cost more than their share of a small SIP;
  the plan warns and suggests an index fund for the stock part.
- **Data breaks:** daily moves over 35% are treated as corporate-action
  errors and dropped (only the 2025 Tata Motors demerger in 15 years).
- **Phase 6 shares that demerger break** in its Auto sector figures; it
  isn't filtered there.

## Open items

- [ ] Add Phase 4 predictions as a second bounded tilt, and backtest it.
- [ ] Estimate cross-asset correlations (stocks, debt, gold) for a tighter risk figure.
- [ ] Prefill Phase 10 mandate limits from the risk profile (checklist B19).
- [ ] Agree with the team on the disclaimer wording and placement.
- [ ] Test the questionnaire with a few real people, as Phase 3 did with real text.

Tests: `backend/tests/test_risk_profile.py`, `test_asset_allocation.py`,
`test_market_stats.py`, `test_equity_optimizer.py`, `test_fund_selector.py`,
`test_recommendations.py`; `frontend/src/pages/PortfolioPlanPage.test.tsx`.
