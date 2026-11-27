# IntelliVest AI: Project Overview

IntelliVest AI is a personal-finance and investing assistant for Indian
retail investors. It brings budgeting, goal planning, market data, news
sentiment, stock forecasting and portfolio construction into one web app,
and ends in an advisor that turns all of them into one prioritised,
explained list of what the user should do next.

Every suggestion in the app is educational, not investment advice: the
app is not a SEBI-registered investment adviser, and it says so.

## 1. The problem

A retail investor's decisions depend on many separate questions: Am I
overspending? Do I have a safety net? Can I afford my goals? How much risk
can I take? What should I hold? What is the news saying? Existing apps
answer these one at a time, if at all, and rarely explain themselves.

IntelliVest's aim is one product that answers them together, explains
every recommendation, and is honest about how good each model really is.

## 2. What the user can do

| Feature | What it does |
|---|---|
| Budgeting and health score | Track income and expenses against a 50/30/20 rules engine, with a 0-100 financial health score |
| Goal planner | Flat and step-up SIP plans for a goal, with an affordability check against the user's surplus |
| Watchlist and alerts | Track stocks and get alerts when a price crosses a threshold |
| Stocks and funds | Search any NSE stock or Indian mutual fund, with charts, news, sentiment and return ranges |
| Sector view | How each market sector is moving, with its news sentiment |
| Portfolio plan | A risk questionnaire, then a stocks / debt / gold split and specific holdings, in rupees, with reasons |
| AI Advisor | One prioritised list of next steps drawn from every module above, each showing why |

## 3. Architecture

```
React + TypeScript frontend
        │  REST /api/v1  (JWT auth, validation, rate limits)
FastAPI backend:  routes  →  services  →  data access
        │                         │
   MongoDB (indexed)       background jobs (APScheduler):
                           prices daily, news hourly, sentiment,
                           sector rollups, market statistics, predictions
        │
Machine-learning artefacts (trained offline in ml/, loaded by services)
        │
Smart contracts (Solidity, local test chain) for AI-proposed vault trades
```

Design choices worth noting:

- **Layered backend.** Routes handle HTTP only, services hold the logic,
  repositories are the only code that touches MongoDB.
- **Precompute, don't recompute.** Sentiment, sector rollups, market
  statistics and predictions are calculated by background jobs and
  stored; a page load only reads them.
- **Pure functions for the logic.** Rules, scoring and optimisation are
  written without I/O, so they are unit-tested directly.
- **Graceful degradation.** If one data source or model fails, the rest of
  the page still works and the failure is named.
- **Configuration as reviewed code.** Thresholds and assumptions sit in
  one config file per module, each with its source or marked as our own
  choice.

## 4. Data

| Source | Used for |
|---|---|
| Yahoo Finance (yfinance) | Daily prices for 20 tracked NSE large caps, the Nifty 50 and India VIX; any NSE stock on demand |
| Economic Times, Livemint RSS, Google News | Company and sector news, ingested hourly |
| mfapi.in (AMFI data) | Mutual fund NAV history and categories |
| Hugging Face datasets | 4.5 million labelled transactions; financial-sentiment datasets |
| User's own entries | Budget, expenses, goals, risk answers, demo investments |

Data quality checks found and handled real problems, for example a 40%
one-day "fall" in Tata Motors that was really its 2025 demerger, and a
Nestlé share split Yahoo didn't adjust.

## 5. The AI and decision modules

### Expense categorisation (machine learning) — completed, later retired from the app

- TF-IDF features and logistic regression, trained on 4.5 million
  transactions; compared with random forest and benchmarked against the
  DFTSen paper (95.3% reported).
- 98.7% accuracy on held-out data, but only **50%** on 150 hand-written
  realistic Indian bank and UPI descriptions: the dataset's merchant names
  were synthetic. Adding real brand and business names raised this to
  **92.0%**.
- Later replaced in the app by user-picked categories, because a wrong
  guess distorts every budget figure after it. Kept as the record of the work.

### Stock forecasting (machine learning) — built

- One gradient-boosted tree model for 20 stocks and every horizon from 1
  day to 2 years, with 27 inputs (past returns, volatility, distance from
  averages, RSI, market and VIX features). It predicts a **range** of
  returns (10th / 50th / 90th percentile), not a single price.
- Walk-forward tested on 2020-2025: about **80% of real returns fall
  inside the 80% range**, at every horizon. But up/down calls are **no
  better than "always up"**, and ranking stocks is weak.
- So the app shows ranges and, honestly, never uses the forecast to say
  buy or sell.

### News sentiment (pretrained transformer) — built

- FinBERT scores every stored headline in a background job.
- On 30 hand-written Indian news headlines: pretrained FinBERT **83.3%**
  accuracy. A version we fine-tuned on financial tweets scored **73.3%**:
  tweets don't transfer to news. The app uses the pretrained model.
- A combined fine-tune on tweets plus Financial PhraseBank is prepared but
  needs a GPU machine to finish.
- News summaries use an extractive (sentence-selection) baseline, with a
  slot ready for a trained summarisation model.

### Sector intelligence — built

Nine sectors, each an equal-weight rollup of its stocks' 1-day to 3-month
change, trend and news sentiment, recomputed after every price and news job.

### Budgeting and goals (rules) — built

A deterministic rules engine (50/30/20 split, per-category ranges, debt-to-
income limits, emergency fund of 3-6 months) and a goal planner. An optional
LLM can reword its explanations, and is rejected if it changes any number.

### Portfolio recommendation (rules + optimisation) — built

1. **Risk profile.** Eight questions, four on *capacity* (horizon,
   emergency fund, income stability, EMIs) and four on *tolerance*. The
   profile follows the **lower** of the two, standard suitability practice.
2. **Asset split** by profile and goal horizon, from published fund-house
   model portfolios; no stocks for goals under 3 years.
3. **Stock weights** by minimum-variance optimisation on a Ledoit-Wolf
   shrunk covariance, with 15% per-stock and 35% per-sector caps. Past
   returns are deliberately not used, as they are mostly noise. A small,
   bounded tilt towards stocks with better news sentiment.
4. **Debt and gold** from real Direct-plan mutual funds, checked for the
   right category and recent data, with a fallback fund for each.

**Walk-forward backtest, 2013-2026** (163 monthly rebalances, 0.2% trading cost):

| Strategy | Annual return | Volatility | Worst fall | Sharpe |
|---|---|---|---|---|
| Our optimiser | 16.9% | **13.9%** | **-29.6%** | **0.78** |
| Equal weight, same 20 stocks | **17.7%** | 16.0% | -36.7% | 0.73 |
| Nifty 50 index | 11.2% | 16.1% | -38.4% | 0.33 |

The optimiser lowered risk on unseen data, as designed, for slightly less
return. Its predicted volatility (12.6%) matched what followed (12.4%).
The index comparison is flattered by hindsight (today's large caps) and
by the index excluding dividends; optimiser vs equal weight is the fair test.

### AI Advisor (orchestration) — built

- Reads eight modules through one common interface, each with its own
  timeout: budget, goals, risk profile, portfolio plan, holdings, sectors,
  sentiment and forecast ranges.
- Rules turn them into prioritised actions, following the financial-
  planning order: stop overspending, build an emergency fund, deal with
  heavy debt, fund goals, invest, then rebalance and review holdings.
- Every action lists the facts and modules behind it. A failing module is
  named and the advice marked partial.
- **Rules decide; an LLM may only reword.** No dataset of "correct advice"
  exists to train an advisor, and an LLM deciding could invent numbers and
  can't be tested or signed reproducibly.
- **Evaluation:** 18 hand-written user situations, 18/18 giving the
  expected advice; every module knocked out in turn (109 runs), 0
  problems; every rupee figure shown traced to its source (50/50).

### Blockchain vault (smart contracts) — contracts built, not yet connected to the app

AI-proposed trades in a user-owned vault on a local Ethereum test chain,
with test tokens only. The user signs a mandate (caps, allowed funds,
limits); the contract executes, asks the user, or rejects each proposal,
and the owner can always withdraw. The advisor already implements the
contracts' advisor interface.

## 6. How we tested

| Level | What |
|---|---|
| Unit | Every rule, formula and optimiser, as pure functions |
| Integration | API routes against a real, throwaway MongoDB database |
| Model evaluation | Held-out splits **and** hand-written realistic examples for every model |
| Backtests | Walk-forward, no look-ahead, for forecasting and portfolios |
| Frontend | Component and page tests with a faked backend |
| Totals | About 650 backend tests and 100 frontend tests; linters on both |

The most useful lesson: **held-out accuracy on the training data's own
distribution was misleading every time.** Realistic, hand-written tests
caught a 98.7% → 50% drop (expense categoriser), a fine-tune that made
sentiment worse, and forecasts whose direction was no better than a guess.

## 7. Honest limitations

- Not yet deployed, and no automated test pipeline on GitHub yet.
- No study with real users; the advisor's scenarios were written by us,
  not reviewed by a certified financial planner.
- The combined sentiment fine-tune and a trained news summariser need GPU time.
- Reddit sentiment is built but waiting on Reddit's API approval.
- The blockchain vault isn't connected to the app's pages yet.
- Investments in the app are simulated; no real money moves.

## 8. Technology

Python 3.12, FastAPI, Pydantic, Motor/MongoDB, APScheduler, scikit-learn,
SciPy, PyTorch and Hugging Face Transformers (FinBERT), yfinance; React 19,
TypeScript, Vite, Tailwind CSS, Recharts; Solidity and Hardhat; pytest,
Vitest, ruff, oxlint.
