# Phase 4: Stock Price Prediction

Built 2026-11-27.

- [x] One model for all 20 tracked stocks and every horizon from 1 trading day to 2 years
- [x] Walk-forward backtest over 2020–2025 against a volatility-only baseline (no lookahead)
- [x] Daily job stores predictions after prices update; requests only read `stock_predictions`
- [x] Each stored prediction has its model version, artifact hash, as-of date, horizon and chance up
- [x] `GET /api/v1/instruments/{id}/prediction?amount=7&unit=days` (days 1–730, months 1–24, years 1–2)
- [x] **Predict** tab in the stock page's invest panel, next to One-time and Start SIP
- [ ] Add predictions to the Phase 6 sector rollup
- [ ] Phase 7: use the stored rank as a second tilt (see results first: it is weak)
- [ ] Phase 10 B18: replace the mock stock predictor with these stored rows

## What it predicts

For a stock and a horizon, the stock's return as a **range**: a low case (10th percentile), a middle
case (50th) and a high case (90th). From the same output it also gives the **chance of going up** and
the stock's **rank** among the 20 by middle case.

It does not predict a single price. A model that predicts tomorrow's price learns to copy today's,
which scores well on error and tells the user nothing.

## How

- **Model:** scikit-learn's `HistGradientBoostingClassifier`, the same algorithm as LightGBM. It is
  already installed, so no new package.
- **Target:** the return over the horizon divided by the stock's recent volatility
  (63-day daily volatility × √horizon). The model sorts this into 15 buckets and gives a probability
  for each. Bucket edges are training percentiles, with 0 always an edge, so the chance up is exact.
  `backend/app/services/prediction/distribution.py` turns the buckets into percentiles.
- **One model, every horizon:** the horizon is an input. The daily job predicts 17 horizons (1, 2, 3,
  5, 7, 10, 15, 21, 31, 42, 63, 94, 126, 189, 252, 378 and 504 trading days). A request for any other
  horizon interpolates between the two nearest, on a log scale.
- **Inputs (27):** the stock's past returns (1 day to 1 year), volatility and its trend, distance
  from its 50 and 200-day averages and 52-week high and low, RSI, volume trend; the Nifty 50's
  returns, volatility and trend; India VIX and its 5-day change; return against the Nifty; rank of
  1 and 3-month returns among the 20; sector; horizon.
- **Shared code:** training and the daily job compute inputs with the same function
  (`backend/app/services/prediction/features.py`), so they can't drift apart.
- **Units:** days are calendar days (× 252/365 trading days), a month is 21 trading days, a year 252.

## Data

Yahoo Finance daily adjusted closes for the 20 stocks, the Nifty 50 (`^NSEI`) and India VIX
(`^INDIAVIX`), from March 2008, when India VIX starts. 90,591 stock-days. No Kaggle dataset needed;
the common one ("NIFTY-50 Stock Market Data") stops in 2021.

**Data breaks:** a one-day move over 35% is a data break, not a market move (same threshold as
Phase 7). Inputs and labels never span one. Two were found: TMPV at the Tata Motors demerger, and
Nestlé's 2024 1:10 split, which Yahoo doesn't adjust.

Sentiment isn't an input: stored news only goes back a few weeks, so there is nothing to train on.

## Testing

Walk-forward by calendar year, 2020 to 2025. For each test year the model trains only on rows whose
whole label window ends before that year starts. Two comparisons:

- **Volatility only:** the same range from recent volatility alone, with no other inputs. If the
  model can't beat this, its other inputs add nothing.
- **Always up:** for the chance of going up.

## Results (all six test years pooled)

| Horizon | Range hit (aim 80%) | Range width | Up/down right | Always up | Rank correlation |
|---|---|---|---|---|---|
| Up to 1 week | 81.4% (baseline 80.5%) | 6.6% (6.4%) | 51.9% | 52.7% | 0.024 (−0.011) |
| 1 week to 1 month | 80.6% (79.9%) | 15.1% (15.0%) | 54.8% | 56.2% | 0.025 (−0.008) |
| 1 to 6 months | 79.8% (79.7%) | 35.3% (36.6%) | 61.6% | 63.0% | 0.039 (0.023) |
| 6 months to 2 years | 81.8% (82.1%) | 87.0% (99.2%) | 76.6% | 76.9% | 0.020 (0.131) |

What this means:

- **The ranges are trustworthy.** About 80% of real returns land inside the range, in every year.
  But most of that comes from recent volatility: the baseline is calibrated too. The model's clear
  gain is at 6 months to 2 years, with ranges 12 points narrower at the same hit rate.
- **Up or down is not predictable here.** At every horizon, "always up" is slightly more often right.
  The chance shown is calibrated (Brier score within 0.003 of the baseline), not a signal.
- **Ranking is weak.** Up to 1 month the model ranks slightly better than the baseline, positive in
  5 of 6 years up to 1 week. Past 6 months the baseline ranks better. Phase 7 should not tilt on
  long-horizon ranks.
- This matches the literature on large, liquid stocks: volatility is predictable, direction mostly
  isn't. Papers reporting 90% accuracy usually leak future data.

The Predict tab shows the range hit rate and the up/down accuracy next to "always up" for the
chosen horizon, from `metrics.json`.

## Limits

- **Hindsight in the stock list:** the 20 stocks are today's large caps, so their past was good.
  Long horizons lean optimistic (e.g. 80% chance up over 2 years).
- **It almost never predicts a fall, and expects fallers to bounce.** On 48 random NSE stocks
  (2026-11-27), chance up was under 50% for 3 at 1 month and none at 1 year. Past 3-month return
  and 1-month chance up correlated at −0.43: stocks down 25–40% got 55–67% chance up (Sterlite
  Technologies, −36% in a month, ranked 1st of 21). The 20 large caps recovered from their dips,
  so the model learned "dips recover". Smaller companies often keep falling.
- **Daily closes only.** No fundamentals, results dates, news or flows.
- Test years 2020–2025 include the COVID crash and recovery, so results swing by year (2020 range
  hit at 1–6 months was 68.5%).

## Any NSE stock (added 2026-11-27)

Search covers every NSE equity (about 2,600, from NSE's `EQUITY_L.csv`, stored in
`backend/app/data/nse_equities.csv`; refresh with `python -m scripts.update_nse_listing`). The 20
tracked stocks keep stored prices, news, sentiment, sectors and scheduled predictions. Any other
stock reads 2 years of prices from Yahoo on demand (cached for an hour). Its first prediction
request runs the model, ranks it against the 20 on the same day (`rank_of` 21) and stores the
result with `tracked: false`. Later requests read it until a newer close arrives. The Predict tab
says when a stock isn't one of the 20 the model was tested on. Watchlist and alerts still price
only the 20 tracked stocks.

## Running it

```
.venv/Scripts/python ml/train_stock_predictor.py            # about 22 minutes on a laptop CPU
.venv/Scripts/python ml/train_stock_predictor.py --refresh  # re-download prices first
.venv/Scripts/python ml/train_stock_predictor.py --quick    # 2 test years, 5 minutes
```

The model file (`ml/models/stock_predictor/model.joblib`, 6 MB) is committed, unlike the other
model binaries, so a fresh clone works without training. After retraining, the backend sees the new
file on its next 30-minute check and stores fresh predictions. Without it the app still runs and the Predict tab says no
prediction exists yet. `metrics.json` is tracked.

Code: `ml/train_stock_predictor.py`, `backend/app/services/prediction/`,
`backend/app/services/prediction_service.py`, `frontend/src/components/instrument/PredictionPanel.tsx`.
Tests: `backend/tests/test_predictions.py`, `frontend/src/components/instrument/PredictionPanel.test.tsx`,
`frontend/src/lib/predictionHorizon.test.ts`.
