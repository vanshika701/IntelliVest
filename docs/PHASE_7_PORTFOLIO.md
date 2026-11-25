# Phase 7: Portfolio Recommendation Engine

Started 2026-11-26 on branch `phase-7-portfolio`.

## What Phase 7 is

Given a user's risk profile and goals, suggest how to split their money
across equity, debt and gold, and which of the tracked stocks to hold in
the equity part, with reasons. It reads stored prices, sentiment and
sector data. It never recomputes them.

No public dataset maps "user profile → correct portfolio", so this is not
a trained classifier. It is rules (risk profile, asset allocation) plus
optimization (portfolio weights) plus model signals (FinBERT sentiment,
later Phase 4 predictions), evaluated with a walk-forward backtest.

Educational suggestions only, not investment advice: IntelliVest is not a
SEBI-registered investment adviser.

## Data available

- Prices: 20 NSE stocks, 548 trading days each, up to 2026-11-22.
- Sentiment: 1,774 FinBERT-scored articles; sector snapshots from Phase 6.
- Budget profile and goals (Phase 8): income, emergency fund, horizons.
- Mutual funds via mfapi.in, for the debt and gold parts.
- Not yet: Phase 4 predictions. The engine has a slot for them.

## Decisions

- **Risk = the lower of capacity and tolerance.** Capacity comes from
  facts (horizon, emergency fund, income stability); tolerance from how
  the user says they would react to losses. Someone keen on risk but with
  no emergency fund still gets a cautious profile.
- **Two layers.** First the asset split (equity / debt / gold) from the
  profile and horizon; then the stock weights inside equity. Most of a
  portfolio's risk comes from the first layer.
- **Covariance is shrunk (Ledoit-Wolf).** 20 stocks and ~2 years of data
  give a noisy sample covariance; shrinkage makes the optimizer stable.
- **Expected returns are not trusted.** Two years of history says little
  about future returns, so the default optimizer minimises risk under
  limits instead of chasing past winners. Sentiment (and later
  predictions) may only tilt weights within small, stated bounds.
- **Hard limits.** Per stock and per sector caps, a minimum number of
  holdings, and no equity for goals under 3 years.
- **Every recommendation is stored** with its inputs and versions, so it
  can be explained later (and prefill Phase 10 mandates, checklist B19).

## Build steps

- [x] **1. Risk profile.** Questionnaire, capacity and tolerance scores,
      five profiles (Conservative to Aggressive). `risk_profiles`
      collection, `GET/PUT /api/v1/risk-profile`, tests.
- [ ] **2. Asset allocation.** Profile × horizon → equity / debt / gold %,
      as tested pure functions with documented sources.
- [ ] **3. Market statistics job.** From stored prices: daily returns,
      volatility, shrunk covariance, correlations. Stored nightly in
      `market_stats`; recomputed after the price job.
- [ ] **4. Equity optimizer.** Minimum-variance weights with stock and
      sector caps (scipy), compared with equal weight. Bounded sentiment
      tilt. Prediction slot left empty.
- [ ] **5. Debt and gold funds.** A short, configured list of index,
      debt and gold funds from mfapi.in.
- [ ] **6. Recommendation service and API.** Weights, rupee amounts,
      expected range of outcomes, reasons per holding, differences from
      current holdings. Stored in `recommendations`.
      `POST /api/v1/recommendations`, `GET /api/v1/recommendations/latest`.
- [ ] **7. Frontend.** Questionnaire page and recommendation page
      (allocation chart, holdings table, reasons, assumptions).
- [ ] **8. Evaluation.** Walk-forward backtest against equal weight and
      the Nifty 50, with trading costs: return, volatility, maximum
      drawdown, Sharpe ratio. Results in `ml/log.md`.
- [ ] **9. Documentation.** Methodology, limits, what is real and what is
      assumed.

**Done when:** a user who answers the questionnaire gets a stored,
explained portfolio built from real stored data, the backtest is
documented honestly, and all tests pass.
