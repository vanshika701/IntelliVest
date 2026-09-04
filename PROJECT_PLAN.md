# IntelliVest AI — Project Plan

This is the build roadmap derived from `IntelliVest_AI_Proposal_updated.docx`. It sequences the project into phases ordered so that (a) you get a working, demoable product early, (b) each ML module is learned and built in isolation before being wired into the orchestrator, and (c) GPU-heavy work is clearly flagged so it doesn't block progress while you're on the M1.

No code lives in this document — that gets written phase by phase, in teaching mode, once you confirm you're ready for each one.

---

## Guiding principles for the build order

1. **Skeleton before intelligence.** The unified dashboard, budgeting, and watchlist (the "boring" CRUD app) get built before any ML, so you have a real app to plug models into instead of building models in a vacuum.
2. **One module at a time, fully understood, before the next.** Each AI module (expense categorization → price prediction → sentiment → summarization → portfolio engine → health score → advisor) is its own phase with its own concepts, dataset, and evaluation — matching the teaching-mode requirement that you understand before code gets written.
3. **Orchestration last.** The "AI Investment Advisor" that combines everything is built only after every module it depends on already works standalone.
4. **Blockchain audit layer is bolted on, not baked in.** It hashes and timestamps outputs of the other modules — it's built after there's something real to hash.
5. **Hardware-aware sequencing.** Phases are tagged CPU-OK (fine on the M1) or GPU-heavy (fine-tuning transformers, deep sequence models on full data) so you know in advance which ones you can start immediately and which ones you may want to batch for a GPU session (Colab/Kaggle/rented GPU) rather than wait on entirely.
6. **Engineering quality is not optional.** This is a system-design project as much as an ML project. Every phase below carries a "System design focus" note — those aren't polish to add at the end, they're built in at the phase where they're first relevant. A working demo with a sloppy backend is not the goal.
7. **Every major model is grounded in a published paper.** Before building any major ML component, we pick a specific paper whose methodology we're adapting, so we have a documented reference architecture *and* a reported benchmark number to compare our results against — not just an internal train/test split with no external anchor. See the "Reference Papers for Benchmarking" section below for the candidates per phase.

---

## System Design & Backend Engineering Standards

These apply across every phase from Phase 0 onward — not a separate late-stage cleanup pass.

- **Layered backend architecture.** API/route layer, service (business logic) layer, and data-access layer stay separate — a route handler should never contain raw DB queries *and* business rules *and* response formatting all in one function.
- **Real API design.** Consistent REST conventions, request/response schema validation (e.g. Pydantic models in FastAPI), sensible status codes and error payloads, pagination on list endpoints, versioned routes (`/api/v1/...`) from the start.
- **Deliberate database schema design.** Collections/documents modeled for the access patterns you'll actually query (not just "however the API happens to send it"), with indexes on the fields you filter/sort by — not an afterthought once things get slow.
- **ML inference as its own service boundary.** Predictions, sentiment scores, and summaries are computed on a schedule or cache-invalidation basis and read from storage on request — not recomputed synchronously inside an API call every time a user opens the dashboard.
- **Background jobs, not blocking calls.** Data ingestion (Phase 1) and model inference runs are scheduled/queued background work, so the API layer stays fast and responsive regardless of how long a model takes.
- **Observability.** Structured logging and basic error tracking from Phase 0 on, so a failure in, say, news ingestion or model inference is visible and debuggable rather than silently swallowed.
- **Testing strategy.** Unit tests for service-layer logic and integration tests for API endpoints, introduced alongside each phase rather than bolted on in Phase 11.
- **Security basics.** No hardcoded secrets (env vars + `.gitignore`d config from Phase 0), input validation at every boundary, properly implemented auth (hashed passwords, token expiry/refresh) — not just "it works if you don't try to break it."

---

## Phase 0 — Foundations & Environment

**Goal:** Have a working dev environment, repo structure, and shared vocabulary before writing a single feature.

**What gets set up:**
- Repo structure conventions (frontend / backend / ml / blockchain / docs as separate top-level concerns)
- Python environment and dependency management approach
- Node/React environment
- MongoDB — local instance for development
- Git workflow (branching, commit conventions) for a solo learning project
- API key management strategy (financial data API, news API, Reddit API) and how secrets are kept out of version control

**Concepts to learn first:** REST API basics, client-server architecture, what an ORM/ODM is (Mongo + Python), environment variables and why secrets don't get committed.

**System design focus:** this phase is where the layered architecture (API / service / data-access) and config/secrets management get decided — every later phase inherits whatever gets set up here, so it's worth doing deliberately rather than "just get it running."

**Hardware:** CPU-OK — nothing here needs a GPU.

**Exit criteria:** Empty-but-running React app talking to an empty-but-running FastAPI/Flask backend, backend talking to a local MongoDB instance.

---

## Phase 1 — Core Data Infrastructure

**Goal:** Get real market and news data flowing into the system before any feature is built on top of it. Every later ML phase depends on this.

**What gets built:**
- Market data ingestion (historical OHLCV — open/high/low/close/volume — for a starter list of stocks)
- News ingestion pipeline (headlines + article text for a starter set of tickers/sectors)
- Reddit ingestion pipeline (posts/comments from finance-relevant subreddits)
- Basic data storage schema in MongoDB for prices, news, and social posts
- A scheduled/refreshable pull mechanism (not necessarily real-time yet)

**Concepts to learn:** what OHLCV data is, API rate limits and pagination, the difference between batch ingestion and streaming, basic data cleaning (missing values, duplicate records, timezone handling for market data).

**System design focus:** ingestion runs as a scheduled/background job (not a script you remember to re-run), is idempotent (re-running it doesn't duplicate records), and handles API rate limits and transient failures with retry/backoff rather than crashing silently. This is the first real test of the "background jobs, not blocking calls" standard.

**Hardware:** CPU-OK.

**Exit criteria:** MongoDB collections populated with real historical price data, real news articles, and real Reddit posts for your initial stock universe (see Datasets section below).

---

## Phase 2 — Unified Dashboard, Budgeting & Watchlist (core product shell)

**Goal:** Build the actual product skeleton — the thing a user opens — before any AI is layered in. This is deliberately the biggest non-ML phase because it's the scaffolding everything else plugs into.

**What gets built:**
- User accounts/auth
- Budgeting: manual expense entry + CSV/statement upload
- Smart Watchlist: add/remove tickers, notes, priority labels, investment rationale fields
- Intelligent Price Proximity Alerts (rule-based first — "notify when price is within X% of target" — no ML needed yet)
- Unified dashboard layout that will later surface AI-module outputs

**Concepts to learn:** frontend state management, form handling and file upload, authentication basics (sessions/JWT), designing a schema that anticipates future AI fields without over-building.

**System design focus:** auth done properly (hashed passwords, token expiry — not a toy login), request validation on every endpoint (expense entry, file upload, watchlist), and a schema designed for the query patterns you'll need later (e.g. "get all expenses for a user in a date range," "get all watchlist items with an active alert") rather than one that only works for the exact screens you're building today.

**Hardware:** CPU-OK.

**Exit criteria:** You can log in, add expenses, upload a transaction file, add stocks to a watchlist with notes, and get a rule-based alert when a price crosses a threshold. No AI yet — that's the point.

---

## Phase 3 — Expense Categorization (first ML module)

**Goal:** First taste of supervised ML, on the simplest and most self-contained module.

**What gets built:**
- A classifier that labels transactions into categories (rent, groceries, entertainment, salary, etc.) from transaction descriptions/amounts
- Since the proposal explicitly defers real bank data to a future Account Aggregator integration, this phase trains on **synthetic/simulated transaction data**, not real bank feeds

**Concepts to learn:** supervised classification basics, text feature extraction from short strings (transaction descriptions), train/test split, precision/recall for multi-class problems, why synthetic data is an acceptable and even necessary substitute here (privacy/regulatory reasons, not just convenience).

**System design focus:** this is the template for every ML module that follows — training happens offline (its own script/notebook), the trained model is saved as an artifact and *loaded* by the backend service layer at inference time, and inference is exposed through a clean service interface the API layer calls. The API route never trains a model or does feature engineering inline.

**Hardware:** CPU-OK — this is a lightweight classical ML or small-model problem, not a deep learning problem.

**Exit criteria:** Uploaded/entered transactions get auto-categorized with a visible accuracy metric, and the budgeting UI from Phase 2 shows categorized spending.

---

## Phase 4 — Stock Price Prediction

**Goal:** First deep learning module — sequence models on time series.

**What gets built:**
- LSTM/GRU baseline for daily forecasting on your initial stock universe
- Extension to weekly/monthly horizons
- Optional Transformer-based variant once the LSTM/GRU baseline works and is understood
- Backtesting methodology so predictions are evaluated honestly (no lookahead bias)

**Concepts to learn:** what a recurrent network is and why it suits sequences, train/validation splits for time series (this is *not* random splitting — order matters), overfitting on noisy financial data, why stock prediction accuracy claims in most papers are overstated, backtesting vs. live evaluation.

**System design focus:** predictions are generated on a schedule (e.g. once daily after market close) and stored, not recomputed per dashboard load — a user opening the app reads a cached prediction, they don't trigger a model run. Model versioning matters here too (which model version produced which stored prediction), since Phase 10's audit layer will need to reference it.

**Hardware:** GPU-heavy for meaningful training (multiple tickers, longer sequences, Transformer variant). A small LSTM on 1–2 tickers is feasible on the M1 for learning the concept; scale up (full stock universe, longer lookback windows, Transformer) when GPU access is available. This phase can be *started* immediately in reduced form and *scaled* later — no need to wait.

**Exit criteria:** Working prediction pipeline for at least a handful of stocks with a documented, honestly-evaluated backtest (not just training-set accuracy), and a written comparison against the reference paper's reported metrics (see "Reference papers for benchmarking") — including an honest account of *why* results differ if they do (different stock universe, shorter data window, M1 vs. paper's compute, etc.), not just the numbers side by side.

---

## Phase 5 — Financial Sentiment Analysis + AI News Summarization

**Goal:** Bring in pretrained financial NLP rather than training from scratch, and understand fine-tuning vs. using models as-is.

**What gets built:**
- FinBERT-based sentiment scoring applied to the news pipeline from Phase 1
- Optional fine-tuning of FinBERT on a labeled financial sentiment dataset for closer alignment with your data
- LLM-based news summarization producing concise market updates from ingested articles
- Multi-source sentiment aggregation combining news sentiment with Reddit discussion sentiment (Novelty item from the proposal)

**Concepts to learn:** what a pretrained transformer is and why FinBERT beats general-purpose sentiment models on financial text, zero-shot/inference-only use vs. fine-tuning, prompt design for summarization, aggregating signals from heterogeneous sources (news vs. social) into one sentiment measure.

**System design focus:** sentiment scoring and summarization run as part of the same background ingestion pipeline as Phase 1 (score/summarize as new articles arrive, not on-demand per request), and results are stored alongside the source article/post so the dashboard is just reading precomputed data.

**Hardware:** Using FinBERT purely for inference (no fine-tuning) is CPU-OK, just slower per document than on GPU. Fine-tuning FinBERT, or running summarization with a larger local LLM, is GPU-heavy — plan to batch that for a GPU session; inference-only can proceed on the M1 in the meantime.

**Exit criteria:** News articles and Reddit posts in your database carry sentiment scores; the dashboard shows AI-generated news summaries and a combined sentiment view per stock/sector; if FinBERT was fine-tuned, its classification accuracy is reported against the reference paper's benchmark (see "Reference papers for benchmarking").

---

## Phase 6 — Sector-Level Market Intelligence

**Goal:** Aggregate the per-stock signals from Phases 4–5 into sector-wide views.

**What gets built:**
- Sector classification/mapping for your stock universe
- Sector-level rollups of price trends and sentiment
- Sector view in the dashboard

**Concepts to learn:** aggregation/groupby logic over the signals already built, basic sector taxonomy for the market you're covering.

**System design focus:** sector rollups are computed as part of the same background pipeline (recomputed when underlying prices/sentiment update), not aggregated live on every request — same "precompute, don't recompute" pattern as Phases 4–5.

**Hardware:** CPU-OK — this is aggregation on top of outputs already produced, not new model training.

**Exit criteria:** Dashboard shows sector-level intelligence, not just individual stocks.

---

## Phase 7 — Portfolio Recommendation Engine

**Goal:** Turn per-stock predictions and sentiment into a personalized recommendation, incorporating the user's goals and risk profile.

**What gets built:**
- Risk-tolerance and goal-capture flow in the UI (horizon, capacity, objectives)
- Recommendation logic combining: user risk profile, Phase 4 predictions, Phase 5 sentiment, and portfolio theory fundamentals (diversification, risk/return tradeoff)
- This is *not* purely a labeled supervised-learning problem — no public dataset maps "user profile → correct portfolio." Expect this to be an ML-assisted optimization/scoring system rather than a single trained classifier.

**Concepts to learn:** Modern Portfolio Theory basics (risk, return, diversification, correlation), how to combine multiple model outputs into one decision system, why some "AI" systems are really optimization + ML hybrids rather than one end-to-end model.

**System design focus:** this service reads already-stored outputs from Phases 4–5 (never recomputes predictions/sentiment itself) and defines a clean interface — given a user's profile + current stored signals, return a recommendation — so it can be called synchronously (recommendations are cheap to compute here; it's the inputs that are expensive) without becoming a bottleneck.

**Hardware:** CPU-OK — this phase is mostly optimization logic and score combination, not deep learning training.

**Exit criteria:** Given a user's stated goals/risk profile, the system produces a personalized, explainable portfolio suggestion pulling from real predictions and sentiment already computed, with the recommendation methodology documented as an adaptation of the phase's reference paper(s) (see "Reference papers for benchmarking").

---

## Phase 8 — Financial Health Assessment

**Goal:** Turn budgeting + investment data already in the system into a single interpretable health score.

**What gets built:**
- Financial ratio computation (savings rate, debt-to-income if available, emergency fund coverage, investment diversification)
- A scoring model/formula that converts these into a health score and explanation

**Concepts to learn:** standard personal-finance health indicators, why an interpretable scoring approach is often preferable to a black-box model for something a user needs to trust and act on.

**System design focus:** the scoring formula lives in its own service function with well-defined inputs/outputs, unit-tested against known cases (e.g. "a user with X savings rate and Y debt ratio should score Z") — this is the easiest phase to write real tests for, since it's pure logic with no external dependencies.

**Hardware:** CPU-OK.

**Exit criteria:** Dashboard shows a financial health score with a breakdown of what's driving it, computed from the user's own budgeting and portfolio data.

---

## Phase 9 — AI Investment Advisor (orchestration layer)

**Goal:** Combine every module built so far (Phases 3–8) into one coherent advisory output. This is the phase where "IntelliVest AI" stops being a collection of models and becomes one product.

**What gets built:**
- An orchestration layer that pulls: predictions, sentiment, sector intelligence, portfolio recommendation, and health score into a single, explainable piece of guidance per user
- Explanation/traceability of *why* a recommendation was made (which module contributed what) — this also sets up what gets hashed in Phase 10

**Concepts to learn:** system design for combining multiple model outputs, explainability in multi-model pipelines, avoiding a "black box of black boxes."

**System design focus:** this is the phase where service-boundary discipline pays off — the advisor calls the Phase 3–8 services through their defined interfaces, handles a module being unavailable or slow without the whole recommendation failing (graceful degradation, not a hard crash if, say, sentiment data hasn't refreshed yet), and returns a response that records *which module contributed what* — that traceability is what Phase 10 hashes, so its shape needs to be decided deliberately here, not reverse-engineered later.

**Hardware:** CPU-OK — this phase composes existing outputs rather than training new models.

**Exit criteria:** A user gets one unified, explainable recommendation that visibly draws on every module built so far.

---

## Phase 10 — Blockchain Governance / Audit Layer

> **⚠️ Status: NOT FINALIZED.** The blockchain audit layer's design (scope, chain choice, even whether it stays a smart contract vs. some lighter tamper-evident approach) is still open and deliberately left for last. Do not start building this phase, and do not let earlier phases assume its final shape — revisit and lock the design down only once Phases 0–9 are done.

**Goal:** Add the verifiable audit trail described in the proposal, now that there's real advisor output to audit.

**What gets built:**
- Minimal smart contract on a public testnet (Polygon Amoy / Ethereum Sepolia) that stores hashes + metadata only
- Hashing at the four lifecycle stages from the proposal: (1) Design & Data — training data sources/licensing/model params; (2) Verification & Validation — test results and validation criteria; (3) Deployment — authorized model version + intended use; (4) Operations & Monitoring — periodically sampled inputs/outputs post-deployment for drift detection
- A verification flow: given a past recommendation, prove it matches what was hashed on-chain
- Explicit non-goals honored: no real transactions on-chain, no full dataset storage on-chain, no custom consensus

**Concepts to learn:** what a smart contract actually is, on-chain vs. off-chain data (why only hashes go on-chain), testnets vs. mainnet, what "tamper-evident" means and doesn't mean, basic Web3 interaction from a backend.

**System design focus:** testnet wallet keys are treated with the same secrets discipline as any other credential (never committed, loaded from environment config), and chain-write calls happen from a dedicated service rather than scattered inline — since these are the slowest, least reliable calls in the whole system, they need explicit timeout/retry handling and shouldn't block the request that triggered them.

**Hardware:** CPU-OK — smart contract development and testnet interaction don't need a GPU at all.

**Exit criteria:** A recommendation produced in Phase 9 has a corresponding on-chain hash record, and you can independently verify that a given recommendation matches its on-chain fingerprint.

---

## Phase 11 — Integration, Evaluation & Deployment

**Goal:** Make sure the whole system works end-to-end, is evaluated honestly, and is actually deployable/demoable.

**What gets built:**
- End-to-end testing across all modules
- Consolidated evaluation report per ML module (accuracy/precision/recall/backtest results — not just training metrics)
- Deployment plan (hosting for frontend, backend, database; where the ML inference runs)
- Documentation of what's real vs. simulated (synthetic transaction data, testnet blockchain) so evaluators/users understand current scope vs. future scope

**System design focus:** this is where the standards from every earlier phase get verified, not introduced for the first time — containerizing the backend for consistent deployment, confirming logging/error tracking actually surfaces failures, running the test suite as a gate before deployment, and writing up the architecture (a diagram of services, data flow, and where background jobs sit) as part of the final documentation.

**Hardware:** CPU-OK for integration and deployment work; any final GPU-trained model artifacts are just loaded for inference, not retrained here.

**Exit criteria:** A fully working, demoable IntelliVest AI covering Phases 2–10, deployed somewhere reachable, with an honest evaluation writeup per module.

---

## Explicitly out of scope for this build (per the proposal's own Future Scope section)

These are named in the proposal itself as future work, not part of the current build:
- **Financial Learning Module** (in-app investing tutorials/education) — future scope
- **Bank-Linked Model Training via Account Aggregator** — real bank data integration is deferred; Phase 3 uses synthetic data by design, not as a shortcut
- **Blockchain Audit Trail Performance Optimization** (off-chain indexing, batched writes, caching, layer-2 scaling) — only relevant once there's real usage volume to optimize for

---

## Reference papers for benchmarking

Per guiding principle #7: each major model is built as an adaptation of a specific published paper, not from scratch with no external anchor. These candidates come largely from the proposal's own Related Work / References section (Section IV/XIII), verified with working links below. Final selection per phase happens when that phase starts — data availability and compute may narrow the choice — but these are the grounded starting points.

| Phase / model | Candidate paper(s) | What we'll benchmark against | Note |
|---|---|---|---|
| **Phase 4 — Stock Price Prediction** (and jointly, Phase 5's sentiment→prediction link) | [Jiang & Zeng, "Financial sentiment analysis using FinBERT with application in predicting stock movement" (arXiv, 2023)](https://arxiv.org/abs/2306.02136) | Their reported comparison of LSTM+FinBERT-sentiment vs. plain LSTM vs. ARIMA vs. plain BERT — this maps directly onto our own Phase 4→Phase 5 build order (does adding sentiment actually improve the price model, the way it did in their study) | Primary anchor — it's the paper already cited in the proposal, and its ablation structure matches our phase sequencing almost exactly |
| Alternate/supplement for Phase 4 | [Maqbool et al., "Stock Prediction by Integrating Sentiment Scores of Financial News and MLP-Regressor" (Procedia Computer Science, 2023)](https://www.sciencedirect.com/science/article/pii/S1877050923000868) | Their reported ~90% trend-prediction accuracy over a 10-day horizon | Also proposal-cited; simpler MLP-Regressor baseline if the LSTM/GRU route needs a lighter comparison point |
| Alternate/supplement for Phase 4 | [Sadu, Das & Rambhia, "FinBERT-LSTM: Deep Learning based stock price prediction using News Sentiment Analysis" (arXiv, 2022)](https://arxiv.org/abs/2211.07392) | Their FinBERT-LSTM architecture and reported error metrics | Not proposal-cited, found during research — closest architectural match to what Phase 4/5 actually builds (FinBERT sentiment feeding an LSTM), worth reading even if not the final benchmark target |
| **Phase 5 — Financial Sentiment Analysis** (FinBERT fine-tuning specifically) | Same Jiang & Zeng (2023) paper above | Their reported FinBERT classification accuracy on financial text | One paper, two benchmark uses — its sentiment-classification numbers anchor Phase 5, its downstream-prediction numbers anchor Phase 4 |
| **Phase 7 — Portfolio Recommendation Engine** | [Cai, Wu, Yu & Brusic, "Blockchain with Machine Learning for Financial Portfolio Management" (IEEE ICEIEC, 2023)](https://ieeexplore.ieee.org/document/10201043/) | Their ML-enabled recommendation subsystem design (account-role mechanism + automated asset management) | Proposal-cited; you already have this PDF saved locally, which is a good sign it's been read before |
| Alternate/supplement for Phase 7 | [Mankawade et al., "Blockchain-Integrated Predictive Analytics for Diversified Investment Portfolio Optimization" (Springer, 2026)](https://link.springer.com/chapter/10.1007/978-981-96-9716-8_6) | Their multi-asset-class prediction methodology (LSTM + ARIMA + moving averages across stocks/real estate/gold/crypto) feeding into portfolio optimization | Proposal-cited; more directly about the prediction→portfolio pipeline than the IEEE paper above, which leans more on the blockchain side |
| **Phase 10 — Blockchain Governance/Audit Layer** | [Ahmed, "Exploring blockchain technology as a governance layer for responsible artificial intelligence" (AI and Ethics, 2026), DOI 10.1007/s43681-026-01192-2](https://doi.org/10.1007/s43681-026-01192-2) | N/A — this isn't a model to benchmark; it's the lifecycle-staged governance framework Phase 10 already implements structurally (Design & Data → Verification & Validation → Deployment → Operations & Monitoring), per the proposal | Already the plan's basis for Phase 10 — listed here for completeness, not as a new decision |
| **Phase 3 — Expense Categorization** | *No proposal-cited paper* | Standard supervised-classification metrics (precision/recall/F1) against the synthetic dataset's own labels | Lower priority for paper-grounding — it's a straightforward applied classifier, not a novel-methodology component. Flag if you want one sourced anyway before we build Phase 3 |
| **Phase 8 — Financial Health Assessment** | *Not applicable* | N/A | Formula/indicator-based (CFPB framework), not a trained model — nothing to benchmark against a paper |

---

## Datasets and data sources needed initially

Grouped by what they feed. Start with a small, fixed stock universe (e.g., 15–25 liquid stocks across a few sectors) rather than the full market — every phase is easier to debug and evaluate on a small, well-understood universe first, and can be scaled up in Phase 11.

### Which dataset trains which model

This is the direct mapping: for each AI component in the project, what it's actually trained on — and, just as important, which components involve *no training at all* (pretrained, rule-based, or optimization-based), so it's clear where a "training dataset" doesn't apply.

| Model / component | Trained by us? | Trained on | What the data provides |
|---|---|---|---|
| **Expense Categorizer** (Phase 3) | Yes — supervised classifier, trained from scratch | [Synthetic Global Bank Transactions](https://www.kaggle.com/datasets/mckenziemakwela/synthetic-global-bank-transactions-dataset), [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1), or [Bank Transaction Dataset for Fraud Detection](https://www.kaggle.com/datasets/valakhorasani/bank-transaction-dataset-for-fraud-detection) (pick one, repurposed) | Transaction description/amount → category label (the label the classifier learns to predict) |
| **Stock Price Prediction** (LSTM/GRU/Transformer, Phase 4) | Yes — trained from scratch | [yfinance](https://pypi.org/project/yfinance/) pulls (production) or the [NIFTY-50, Kaggle](https://www.kaggle.com/datasets/rohanrao/nifty50-stock-market-data) / [Nifty50 2000–2025, Kaggle](https://www.kaggle.com/datasets/ashishjangra27/nifty-50-25-yrs-data) snapshots (prototyping) | Historical OHLCV sequences — the "label" is just the next day's price from the same series, so no separate labeled dataset is needed here, only a long, clean price history |
| **Financial Sentiment Analysis** (FinBERT, Phase 5) | Only if you choose to fine-tune — FinBERT itself is already pretrained | [Financial PhraseBank, Hugging Face](https://huggingface.co/datasets/takala/financial_phrasebank) and/or [SEntFiN 1.0, GitHub](https://github.com/pyRis/SEntFiN) | Headline/sentence → positive/negative/neutral label, used only to adapt FinBERT to your specific news style. If you skip fine-tuning, FinBERT is used purely for inference on [NewsAPI](https://newsapi.org/)/[Moneycontrol](https://www.moneycontrol.com/)/Reddit text — no training dataset needed at all |
| **AI News Summarization** (Phase 5) | No | — (pretrained LLM used as-is via inference/prompting) | Not applicable — no dataset trains this in the current project scope |
| **Portfolio Recommendation Engine** (Phase 7) | No — optimization/rules-based, not a trained classifier | Uses yfinance/Kaggle price history as a *computation input* (returns, volatility, correlation for portfolio theory math), not as a labeled training set | No public "user profile → correct portfolio" dataset exists to train on; the risk-profile capture design is informed by [FinaMetrica](https://www.riskprofiling.com/) as a reference, not a training set |
| **Financial Health Assessment** (Phase 8) | No — formula-based scoring | None | [CFPB Financial Well-Being Scale](https://www.consumerfinance.gov/data-research/research-reports/financial-well-being-scale/) is a *design reference* for which ratios/indicators to compute, not something to train a model on |
| **Sector-Level Market Intelligence** (Phase 6) | No | None | Aggregates outputs already produced by Phases 4–5; no new training |
| **AI Investment Advisor** (Phase 9) | No | None | Orchestrates the outputs of Phases 3–8; no separate training of its own |
| **Price Proximity Alerts** (Phase 2) | No | None | Rule-based threshold check on live price data, not ML |
| **Blockchain Audit Layer** (Phase 10) | No | None | No ML involved at all — smart contract logic only |

The [Reddit API](https://www.reddit.com/dev/api/)/[PRAW](https://praw.readthedocs.io/en/stable/) feed and the [NifSent50, Kaggle](https://www.kaggle.com/datasets/grounddominator/nifsent50-nifty-50-stocks-and-news-dataset) combined dataset don't train anything themselves either — they're *inference-time input* (Reddit/news text that gets scored by FinBERT) or a prototyping convenience (NifSent50, to test the price+news+sentiment pipeline end-to-end before live ingestion exists), not training data.

Each entry below now states explicitly which model it's used for and whether it trains that model or just feeds it at inference time.

### 1. Market price data (feeds Phases 1, 4, 6, 7)
- Historical OHLCV data for your chosen stock universe. Given the proposal's SEBI/Indian-market framing (comparisons to Zerodha, Groww), NSE/BSE-listed stocks are the natural target.
- Sources to evaluate:
  - [yfinance (PyPI)](https://pypi.org/project/yfinance/) — pulls Yahoo Finance data programmatically; covers NSE/BSE tickers with the `.NS`/`.BO` suffix. Best option for live/refreshable pulls in Phase 1.
    **→ Used to train:** the Stock Price Prediction model (LSTM/GRU/Transformer, Phase 4) — this is its primary training data, in production. Also feeds the Portfolio Recommendation Engine (Phase 7) as a computation input (returns/volatility), not as training data there.
  - [Alpha Vantage](https://www.alphavantage.co/) — API-based, free tier with rate limits; alternative/backup to Yahoo Finance.
    **→ Used to train:** same role as yfinance — backup price source for the Stock Price Prediction model if yfinance has gaps.
  - [NIFTY-50 Stock Market Data (2000–2021), Kaggle](https://www.kaggle.com/datasets/rohanrao/nifty50-stock-market-data) — static historical snapshot, good for prototyping the price-prediction pipeline before wiring up live pulls.
    **→ Used to train:** the Stock Price Prediction model, during early development/prototyping only (before live ingestion from Phase 1 is wired up).
  - [Nifty50 (2000–2025), Kaggle](https://www.kaggle.com/datasets/ashishjangra27/nifty-50-25-yrs-data) — more recent alternative snapshot if you want data closer to present day.
    **→ Used to train:** same role as the 2000–2021 snapshot — Stock Price Prediction model prototyping.
- Needed early because Phase 4 (price prediction) and the backtest methodology can't be designed without real historical series in hand.

### 2. Financial news data (feeds Phases 1, 5, 6)
- Headlines + article bodies for your stock universe and sectors.
- Sources to evaluate:
  - [NewsAPI](https://newsapi.org/) — general news API, filterable to finance-related sources/keywords.
    **→ Used for:** Financial Sentiment Analysis (FinBERT, Phase 5) and AI News Summarization (Phase 5) — as **inference-time input only**. It does not train either model; it's the live text those models score/summarize.
  - [Moneycontrol](https://www.moneycontrol.com/) and [Economic Times](https://economictimes.indiatimes.com/) — India-specific financial news, via RSS/scraping if no direct API access.
    **→ Used for:** same role as NewsAPI — inference-time input to FinBERT sentiment scoring and news summarization, not training data.
  - [NifSent50: NIFTY 50 Stocks and News Dataset, Kaggle](https://www.kaggle.com/datasets/grounddominator/nifsent50-nifty-50-stocks-and-news-dataset) — combined price + news dataset, useful for prototyping Phases 1/5/6 together before live ingestion is wired up.
    **→ Used for:** prototyping only — lets you test the Stock Price Prediction model and FinBERT sentiment scoring against the same linked price+news records before real ingestion pipelines exist. Not a training set for either model on its own.
- For *training/fine-tuning* the sentiment model specifically (not just running inference), a labeled sentiment dataset is needed separately from raw news — see item 4.

### 3. Social/Reddit data (feeds Phases 1, 5)
- Posts and comments from finance-relevant subreddits (e.g., r/IndianStreetBets, r/stocks, r/wallstreetbets).
- Sources:
  - [Reddit API (official dev docs)](https://www.reddit.com/dev/api/)
  - [PRAW — Python Reddit API Wrapper (docs)](https://praw.readthedocs.io/en/stable/) — the standard Python library for pulling Reddit data.
  - **→ Used for:** Financial Sentiment Analysis (FinBERT, Phase 5), specifically the "multi-source market sentiment" feature — **inference-time input only**, same as news. FinBERT scores Reddit text; Reddit data does not train FinBERT.
- Needed for the proposal's "multi-source market sentiment" feature — sentiment from social discussion, not just news.

### 4. Labeled sentiment data (feeds Phase 5, only if fine-tuning FinBERT rather than using it purely as-is)
- [Financial PhraseBank (Malo et al.), Hugging Face](https://huggingface.co/datasets/takala/financial_phrasebank) — the standard labeled financial-sentiment benchmark dataset, widely used to fine-tune FinBERT-style models.
  **→ Used to train:** Financial Sentiment Analysis (FinBERT, Phase 5) — this is the actual labeled training data if you choose to fine-tune FinBERT rather than use it zero-shot.
- [SEntFiN 1.0 (Sinha et al., 2022) — GitHub repo](https://github.com/pyRis/SEntFiN) — dataset + code for an Indian, entity-aware financial-news sentiment dataset; also see the [paper](https://arxiv.org/abs/2305.12257). Worth prioritizing given the Indian-market framing.
  **→ Used to train:** same role as Financial PhraseBank — fine-tuning data for the FinBERT sentiment model, better domain match for NSE/BSE-related news specifically.
- Twitter/StockTwits-style financial sentiment datasets (search Hugging Face/Kaggle for current listings) as a secondary option for social-text-style sentiment, closer in style to Reddit than news is.
  **→ Used to train:** FinBERT, specifically to better handle short, informal social-media-style text (closer to Reddit posts than news headlines).
- Not strictly required if you start with FinBERT purely for inference (zero-shot) — only needed once you decide to fine-tune.

### 5. Transaction/expense data (feeds Phase 3)
- **Synthetic, by design** — the proposal explicitly defers real bank data to a future Account Aggregator integration.
- A synthetic transaction dataset needs: a description string, amount, date, and a category label (rent, groceries, salary, entertainment, utilities, etc.).
- Sources to evaluate (repurposed for categorization, not their original fraud-detection labels):
  - [Synthetic Global Bank Transactions Dataset, Kaggle](https://www.kaggle.com/datasets/mckenziemakwela/synthetic-global-bank-transactions-dataset)
    **→ Used to train:** the Expense Categorization classifier (Phase 3) — description/amount fields → category label.
  - [PaySim — Synthetic Financial Datasets For Fraud Detection, Kaggle](https://www.kaggle.com/datasets/ealaxi/paysim1) — large simulated mobile-money transaction dataset; transaction-type field is useful as a categorization proxy.
    **→ Used to train:** same Expense Categorization classifier — its `type` field (cash-in, cash-out, debit, payment, transfer) stands in for a category label.
  - [Bank Transaction Dataset for Fraud Detection, Kaggle](https://www.kaggle.com/datasets/valakhorasani/bank-transaction-dataset-for-fraud-detection)
    **→ Used to train:** same Expense Categorization classifier — alternate source if the other two don't give you enough category variety.
  - Alternatively, generate your own synthetic set so the category taxonomy matches exactly what the budgeting UI (Phase 2) needs — gives more control and is a reasonable scope for a learning project.
    **→ Used to train:** same Expense Categorization classifier — a self-generated set trades dataset realism for exact control over the label set.

### 6. Risk-profile / financial-health reference data (feeds Phases 7, 8 — design reference only, not training data)
- No dataset to *train* on here — Phase 7's portfolio engine and Phase 8's health score are formula/optimization-driven, not supervised-learned from labeled examples.
- Useful as *design references* rather than datasets:
  - [FinaMetrica risk profiling (riskprofiling.com)](https://www.riskprofiling.com/) — standard risk-tolerance questionnaire structure, to inform how you capture user risk profile in Phase 2/7.
    **→ Used for:** the Portfolio Recommendation Engine (Phase 7) — informs questionnaire *design* only; nothing here is trained on it.
  - [CFPB Financial Well-Being Scale — guide](https://www.consumerfinance.gov/data-research/research-reports/financial-well-being-scale/) and [technical report](https://www.consumerfinance.gov/data-research/research-reports/financial-well-being-technical-report/) — standard financial-health indicator framework, to inform Phase 8's scoring formula.
    **→ Used for:** the Financial Health Assessment score (Phase 8) — informs which ratios/indicators the *formula* computes; nothing here is trained on it either.

---

## What to do next

Read through the phases and datasets above and flag anything that doesn't match how you pictured the build order or scope. Once you confirm the plan, we start at Phase 0 — in teaching mode, one concept and one confirmed step at a time, per how you asked to work.
