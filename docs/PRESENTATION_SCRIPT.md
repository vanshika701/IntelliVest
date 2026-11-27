# IntelliVest AI: Presentation Script

About 12 minutes plus questions. Lines in plain text are what to say;
*italic lines* are what to do or show. Numbers are from the project's
evaluation files (`ml/log.md`, `ml/models/*/metrics.json`).

Before you start: backend and frontend running, logged in as a demo user
with a budget, a goal and a portfolio plan already saved.

---

## 1. The problem (1 minute)

A retail investor has to answer many questions at once. Am I overspending?
Do I have an emergency fund? Can I afford my goals? How much risk can I
take, what should I hold, and what is the news saying about it?

Most apps answer one of these at a time and rarely explain themselves.
IntelliVest puts them in one product, explains every suggestion, and is
honest about how good each model really is.

## 2. What it does (1 minute)

It has seven parts that feed each other: budgeting with a health score, a
goal planner, a watchlist with alerts, stock and fund pages with news
sentiment and forecasts, a sector view, a portfolio planner, and an AI
advisor that brings all of them together into one list of next steps.

## 3. Architecture (1.5 minutes)

*Show the diagram in PROJECT_OVERVIEW.md, section 3.*

The frontend is React and TypeScript. The backend is FastAPI in three
layers: routes handle HTTP, services hold the logic, and repositories are
the only code that talks to MongoDB.

The key design decision is "precompute, don't recompute". Background jobs
fetch prices daily and news hourly, score sentiment, and compute sector
rollups, market statistics and forecasts. When a user opens a page, the
app only reads stored results, so pages are fast and a slow model never
blocks a request.

## 4. The models, and what testing taught us (4 minutes)

The theme here is that a good score on the training data was misleading
every time, so every model was also tested on realistic, hand-written examples.

**Expense categorisation.** Logistic regression on 4.5 million labelled
transactions scored 98.7% on held-out data. On 150 realistic Indian bank
and UPI descriptions it scored only 50%, because the dataset's merchant
names were synthetic. Adding real brand and business names raised that to
92%. We later chose to let users pick categories instead, because a wrong
guess distorts every budget figure after it.

**News sentiment.** We use FinBERT. On 30 hand-written Indian headlines
the pretrained model scored 83%. Our own fine-tune on financial tweets
scored 73%, worse, because tweets don't transfer to news. So we kept the
pretrained model and documented the negative result.

**Stock forecasting.** A gradient-boosted tree model predicts a range of
returns for 20 stocks at any horizon. In a walk-forward test over
2020-2025, about 80% of real returns landed inside the 80% range, so the
ranges are trustworthy. But up-or-down calls were no better than simply
guessing "up". So the app shows ranges, and never uses the forecast to
say buy or sell.

**Portfolio optimisation.** Minimum-variance weights on a shrunk covariance
matrix, with stock and sector caps. In a 13-year walk-forward backtest it
had 13.9% volatility against 16.0% for an equal split, and a worst fall of
30% against 37%, for slightly less return. Its predicted risk, 12.6%,
matched what actually happened, 12.4%.

## 5. The AI Advisor (2 minutes)

The advisor reads eight modules through one common interface: budget,
goals, risk profile, plan, holdings, sectors, sentiment and forecasts.
Each has a time limit, so if one fails the advice is still produced and
marked partial.

Rules turn these into actions in financial-planning order: stop
overspending, build an emergency fund, deal with heavy debt, fund goals,
invest, then rebalance. Every action shows the facts and modules behind it.

We deliberately didn't let an LLM decide. There's no dataset of correct
advice to train or test against, an LLM can invent numbers, and the
blockchain part needs decisions that are reproducible. An LLM can only
reword the summary, and its text is rejected if it changes a single number.

To evaluate it we wrote 18 realistic user situations with the advice a
careful planner would give first. All 18 pass. We also knocked out every
module in turn, 109 runs with no problems, and checked that every rupee
figure shown can be traced to its source.

## 6. Live demo (2 minutes)

*Open **Portfolio plan**.* This is the risk questionnaire result: capacity
and tolerance, and the profile follows the lower one.
*Build a plan for 7 years.* The split, specific stocks and funds in rupees,
and under "Why", the reason for each holding.

*Open **AI Advisor**.* The summary at the top, then actions in priority
order. *Open one "Why".* These are the exact facts behind it, and the chips
show which modules it came from. *Scroll to "What the advisor looked at".*
Each module's status and data date.

*Optional:* open a stock page and the Predict tab to show the return range
and its measured accuracy.

## 7. Limitations and next steps (30 seconds)

It isn't deployed yet and has no automated test pipeline on GitHub. We
haven't tested it with real users, and the advisor's scenarios were written
by us rather than a certified planner. The combined sentiment fine-tune
needs GPU time. The blockchain vault contracts are built and tested on a
local chain but not connected to the app's pages. All investments in the
app are simulated.

Thank you. I'm happy to take questions.

---

## Likely questions

**Why not just use an LLM as the advisor?**
There's no labelled data to train or measure it, it can invent figures,
and it gives different answers to the same input. Rules are testable and
reproducible; the models feed them signals; the LLM only rewords.

**Your forecast can't predict direction. Isn't that a failure?**
It's an honest result. Research on large, liquid stocks finds the same:
volatility is predictable, direction mostly isn't. Papers claiming 90%
direction accuracy usually leak future data. We use the forecast for what
it measurably does well, ranges.

**How do you know there's no look-ahead in the backtests?**
At every rebalance or test date the model is rebuilt from data before that
date only, using the same code the app runs, and trading costs are charged.

**Why minimum variance and not maximum return?**
Expected returns estimated from a few years of prices are mostly noise, and
optimisers that chase them pile into past winners. Minimum variance needs
only the covariance, which is estimated far more reliably.

**Why did the fine-tuned sentiment model do worse?**
It was trained on tweets, while the app scores news headlines. That's
domain shift. A combined run adding Financial PhraseBank, which is
news-style text, is prepared but needs a GPU.

**Is this investment advice?**
No. Every recommendation is labelled educational. In India, personalised
investment advice requires SEBI registration.

**How is it tested?**
About 650 backend and 100 frontend automated tests: unit tests on every
rule and formula, integration tests against a real throwaway database, and
evaluation scripts for every model.
