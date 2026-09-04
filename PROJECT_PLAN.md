# IntelliVest AI — Project Plan

This is the build roadmap derived from `IntelliVest_AI_Proposal_updated.docx`. It sequences the project into phases ordered so that (a) you get a working, demoable product early, (b) each ML module is learned and built in isolation before being wired into the orchestrator, and (c) GPU-heavy work is clearly flagged so it doesn't block progress while you're on the M1.

No code lives in this document — that gets written phase by phase, in teaching mode, once you confirm you're ready for each one.

---

## Team & ownership

This is a two-person project. Every phase below now carries an **Owner** field — leave it unassigned until you two decide who's taking it, then fill it in (a name, or "shared" for phases you're pairing on). Nothing here presumes a split in advance; assign phases as you go, however makes sense at the time (interest, existing strengths, or just alternating). Teaching mode (explain-first, you write the code) applies to whichever of you is hands-on for a given phase — it's not specific to one person.

---

## Guiding principles for the build order

1. **Skeleton before intelligence.** The unified dashboard, budgeting, and watchlist (the "boring" CRUD app) get built before any ML, so you have a real app to plug models into instead of building models in a vacuum.
2. **One module at a time, fully understood, before the next.** Each AI module (expense categorization → price prediction → sentiment → summarization → portfolio engine → health score → advisor) is its own phase with its own concepts, dataset, and evaluation — matching the teaching-mode requirement that you understand before code gets written.
3. **Orchestration last.** The "AI Investment Advisor" that combines everything is built only after every module it depends on already works standalone.
4. **Blockchain audit layer is bolted on, not baked in.** It hashes and timestamps outputs of the other modules — it's built after there's something real to hash.
5. **Hardware-aware sequencing.** Phases are tagged CPU-OK (fine on the M1) or GPU-heavy (fine-tuning transformers, deep sequence models on full data) so you know in advance which ones you can start immediately and which ones you may want to batch for a GPU session (Colab/Kaggle/rented GPU) rather than wait on entirely.
6. **Engineering quality is not optional.** This is a system-design project as much as an ML project. Every phase below carries a "System design focus" note — those aren't polish to add at the end, they're built in at the phase where they're first relevant. A working demo with a sloppy backend is not the goal.

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

**Owner:** _unassigned_

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

**Owner:** _unassigned_

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

**Exit criteria:** MongoDB collections populated with real historical price data, real news articles, and real Reddit posts for your initial stock universe (sources decided as this phase starts, not pre-selected here).

---

## Phase 2 — Unified Dashboard, Budgeting & Watchlist (core product shell)

**Owner:** _unassigned_

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

**Owner:** _unassigned_

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

**Owner:** _unassigned_

**Goal:** First deep learning module — sequence models on time series.

**What gets built:**
- LSTM/GRU baseline for daily forecasting on your initial stock universe
- Extension to weekly/monthly horizons
- Optional Transformer-based variant once the LSTM/GRU baseline works and is understood
- Backtesting methodology so predictions are evaluated honestly (no lookahead bias)

**Concepts to learn:** what a recurrent network is and why it suits sequences, train/validation splits for time series (this is *not* random splitting — order matters), overfitting on noisy financial data, why stock prediction accuracy claims in most papers are overstated, backtesting vs. live evaluation.

**System design focus:** predictions are generated on a schedule (e.g. once daily after market close) and stored, not recomputed per dashboard load — a user opening the app reads a cached prediction, they don't trigger a model run. Model versioning matters here too (which model version produced which stored prediction), since Phase 10's audit layer will need to reference it.

**Hardware:** GPU-heavy for meaningful training (multiple tickers, longer sequences, Transformer variant). A small LSTM on 1–2 tickers is feasible on the M1 for learning the concept; scale up (full stock universe, longer lookback windows, Transformer) when GPU access is available. This phase can be *started* immediately in reduced form and *scaled* later — no need to wait.

**Exit criteria:** Working prediction pipeline for at least a handful of stocks with a documented, honestly-evaluated backtest (not just training-set accuracy).

---

## Phase 5 — Financial Sentiment Analysis + AI News Summarization

**Owner:** _unassigned_

**Goal:** Bring in pretrained financial NLP rather than training from scratch, and understand fine-tuning vs. using models as-is.

**What gets built:**
- FinBERT-based sentiment scoring applied to the news pipeline from Phase 1
- Optional fine-tuning of FinBERT on a labeled financial sentiment dataset for closer alignment with your data
- LLM-based news summarization producing concise market updates from ingested articles
- Multi-source sentiment aggregation combining news sentiment with Reddit discussion sentiment (Novelty item from the proposal)

**Concepts to learn:** what a pretrained transformer is and why FinBERT beats general-purpose sentiment models on financial text, zero-shot/inference-only use vs. fine-tuning, prompt design for summarization, aggregating signals from heterogeneous sources (news vs. social) into one sentiment measure.

**System design focus:** sentiment scoring and summarization run as part of the same background ingestion pipeline as Phase 1 (score/summarize as new articles arrive, not on-demand per request), and results are stored alongside the source article/post so the dashboard is just reading precomputed data.

**Hardware:** Using FinBERT purely for inference (no fine-tuning) is CPU-OK, just slower per document than on GPU. Fine-tuning FinBERT, or running summarization with a larger local LLM, is GPU-heavy — plan to batch that for a GPU session; inference-only can proceed on the M1 in the meantime.

**Exit criteria:** News articles and Reddit posts in your database carry sentiment scores; the dashboard shows AI-generated news summaries and a combined sentiment view per stock/sector; if FinBERT was fine-tuned, its classification accuracy is reported and documented.

---

## Phase 6 — Sector-Level Market Intelligence

**Owner:** _unassigned_

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

**Owner:** _unassigned_

**Goal:** Turn per-stock predictions and sentiment into a personalized recommendation, incorporating the user's goals and risk profile.

**What gets built:**
- Risk-tolerance and goal-capture flow in the UI (horizon, capacity, objectives)
- Recommendation logic combining: user risk profile, Phase 4 predictions, Phase 5 sentiment, and portfolio theory fundamentals (diversification, risk/return tradeoff)
- This is *not* purely a labeled supervised-learning problem — no public dataset maps "user profile → correct portfolio." Expect this to be an ML-assisted optimization/scoring system rather than a single trained classifier.

**Concepts to learn:** Modern Portfolio Theory basics (risk, return, diversification, correlation), how to combine multiple model outputs into one decision system, why some "AI" systems are really optimization + ML hybrids rather than one end-to-end model.

**System design focus:** this service reads already-stored outputs from Phases 4–5 (never recomputes predictions/sentiment itself) and defines a clean interface — given a user's profile + current stored signals, return a recommendation — so it can be called synchronously (recommendations are cheap to compute here; it's the inputs that are expensive) without becoming a bottleneck.

**Hardware:** CPU-OK — this phase is mostly optimization logic and score combination, not deep learning training.

**Exit criteria:** Given a user's stated goals/risk profile, the system produces a personalized, explainable portfolio suggestion pulling from real predictions and sentiment already computed, with the recommendation methodology documented.

---

## Phase 8 — Financial Health Assessment

**Owner:** _unassigned_

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

**Owner:** _unassigned_

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

**Owner:** _unassigned_

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

**Owner:** _unassigned_

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

## What to do next

Read through the phases above and flag anything that doesn't match how you pictured the build order or scope. Papers and datasets aren't pre-selected here anymore — you and your teammate pick those when each phase actually starts. Once you confirm the plan, we start at Phase 0 — in teaching mode, one concept and one confirmed step at a time, per how you asked to work.
