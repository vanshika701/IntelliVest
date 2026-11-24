# IntelliVest AI

An AI-powered investment advisor + budgeting/watchlist platform. See
[`PROJECT_PLAN.md`](./PROJECT_PLAN.md) for the full phased build roadmap.

## Repo structure

```
backend/     FastAPI service (layered: api / services / data / core)
frontend/    React + TypeScript + Tailwind app (Vite)
ml/          Model training notebooks/scripts and saved artifacts
blockchain/  Mode 2 AI + user-owned vault contracts (Phase 10 — not started yet)
docs/        Written docs/evaluation reports produced as phases complete
```

## Prerequisites

- Python 3.12 (pinned in `.python-version`)
- Node 24 (pinned in `.nvmrc`)
- Docker Desktop, for MongoDB: `docker compose up -d` from the repo root
  starts MongoDB 8.0 on `localhost:27017`, with data kept in a Docker
  volume across restarts (`docker compose down` stops it)

## Backend setup

```bash
python3 -m venv .venv          # once, from the repo root (Windows: py -3.12 -m venv .venv)
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd backend
cp .env.example .env           # JWT_SECRET_KEY works out of the box for local dev;
                                # fill in API keys as later phases need them
uvicorn app.main:app --reload --port 8000
```

Check it's alive: `curl http://localhost:8000/api/v1/health` should return
`{"status": "ok", "database": "connected"}` (MongoDB must be running for
`database` to say `connected`).

Run backend tests and lint:

```bash
cd backend
pytest
ruff check .
```

### Data ingestion (Phase 1)

Three pipelines pull real data into MongoDB — market data (yfinance, no
key needed), news (Indian financial RSS feeds, no key needed), and Reddit (asyncpraw). Each has a manual
entry point for one-off runs, and all three also run automatically on a
schedule (daily for prices, hourly for news/Reddit) whenever the backend
is running, via `app/core/scheduler.py` (which also runs price-alert
evaluation every 5 minutes, for Phase 2's watchlist alerts):

```bash
cd backend
python -m scripts.ingest_market_data   # works immediately, no API key
python -m scripts.ingest_news          # works immediately, no API key
python -m scripts.ingest_reddit        # needs REDDIT_CLIENT_ID/SECRET/USER_AGENT in .env
```

News comes from Economic Times and Livemint market feeds (headlines are
matched to tickers via `TICKER_ALIASES` in `app/core/constants.py`) plus
one Google News search per company. Moneycontrol and Business Standard
are not used: their feeds return 403 to automated requests. Reddit logs a
warning and exits cleanly if its credentials aren't set yet.

**Reddit is currently blocked on Reddit's own approval process**, not on
anything in this codebase. Since November 2025, new API apps require
manual approval under Reddit's
["Responsible Builder Policy"](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
before you get credentials — `/prefs/apps` no longer issues them
instantly. Submit that request whenever you get to it; the ingestion
code is already built and tested, so once Reddit approves you and hands
over `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/`REDDIT_USER_AGENT`,
nothing else needs to change.

### News sentiment (Phase 5)

Every news article is scored with [FinBERT](https://huggingface.co/ProsusAI/finbert)
(pretrained, inference only, runs on CPU). Scoring runs automatically
right after each hourly news ingestion, and stores a `sentiment` field
(`label`, `score` from -1 to 1, class `probabilities`, `model`,
`scored_at`) on the article itself. For a one-off run:

```bash
cd backend
python -m scripts.score_sentiment      # first run downloads FinBERT (~420 MB) into ml/models/hf_cache/
```

Read endpoints (login required): `GET /api/v1/sentiment` (every tracked
stock) and `GET /api/v1/sentiment/{ticker}` — label counts, average
score, overall label and the latest articles over the last `days`
(default 7). To use a fine-tuned model later, set `SENTIMENT_MODEL` in
`backend/.env` to its Hugging Face id or local path; the next run
re-scores every article with it.

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                    # http://localhost:5173
```

Other frontend commands: `npm run build`, `npm run lint`, `npm run test`.

## Environment variables & secrets

Every real secret lives in a `.env` (backend) / `.env.local` (frontend)
file — both are gitignored. Only the corresponding `.env.example` files
are committed, and they must be kept up to date whenever a new variable is
added, so the other person can `cp` it and know exactly what to fill in.
Never commit a real API key, even temporarily.

## Git workflow

Two people, one `main` branch — to avoid stepping on each other:

- `main` stays deployable; don't commit directly to it for anything beyond trivial docs fixes.
- Branch per phase/feature: `phase-<n>-<short-description>` (e.g. `phase-1-market-data-ingestion`) or `fix-<short-description>` for bugfixes.
- Open a PR into `main` even solo — it's a natural point for the other person to skim the diff, and gives you a review trail.
- Commit messages: short imperative summary line (`Add Mongo health check to backend`), body if the "why" isn't obvious from the diff.
- Pull `main` before starting a new branch so you're not building on stale code, especially once you're both touching overlapping phases (e.g. Phase 9 depends on Phases 3–8).

## Current status

Phase 2's exit criteria are met. Track remaining polish items in
[`PHASE_2_EXECUTION_PLAN.md`](./PHASE_2_EXECUTION_PLAN.md) (source of truth).

- **Phase 0** — done. Empty-but-running React app talking to an
  empty-but-running FastAPI backend, backend talking to local MongoDB.
- **Phase 1** — built and tested, partially verified live:
  - Market data (yfinance): fully live — 20-stock universe, ~10k real
    price records in MongoDB, confirmed idempotent on re-runs
  - News: switched from NewsAPI (free plan's ~100 requests/day and
    truncated article text didn't fit hourly ingestion) to Indian
    financial RSS feeds — Economic Times, Livemint, and Google News
    per-company search. No API key or daily quota
  - Reddit (asyncpraw): **paused, not dropped** — pipeline is fully
    built and tested against fabricated data, waiting on Reddit's own
    access approval (see "Data ingestion" above). News is the working
    sentiment source in the meantime; Reddit slots in later with zero
    code changes once approved
  - Scheduler wraps all three into a real background job, retries
    transient failures with backoff, fails fast on permanent ones
- **Phase 2** — exit criteria verified live: register/login, add an
  expense, upload a CSV statement, add a watchlist item with notes, and
  get a rule-based alert when a price crosses a threshold, all confirmed
  end-to-end against the real backend and MongoDB. 39/39 backend tests,
  7/7 frontend tests, `npm run build` green. Refresh tokens, a ticker
  marquee, and a shared modal component library are explicitly deferred
  polish — see `PHASE_2_EXECUTION_PLAN.md` Section 7.
- **Phase 3** — complete. Expense categorizer trained on the **full**
  `mitulshah/transaction-categorization` dataset (Hugging Face, all
  4,501,043 rows), benchmarked against the DFTSen paper (95.3% accuracy
  reported) — **98.7% accuracy / 98.7% macro-F1** on held-out
  template-style test data with a classical TF-IDF + Logistic Regression
  model (Random Forest scored marginally higher but took 47 minutes to
  train vs. 89 seconds, so it wasn't shipped). A stress test against 50
  hand-written realistic examples (real brand names, Indian UPI/NEFT-style
  text) initially measured only **50.0% accuracy** — this dataset's
  synthetic merchant names don't overlap with real ones, so the model had
  no learned signal for brands like Swiggy, Zerodha, or BESCOM. Fixed by
  mixing ~13,466 supplementary rows of real vocabulary (484 hand-curated
  brands + 12,982 real Indian business names from the BharatPOI dataset)
  into training, upweighted via `sample_weight`; a second bug (the fix
  silently failing at full-dataset scale because `TfidfVectorizer`'s
  vocabulary selection ignores sample weighting) was found and fixed
  before shipping. A second pass reviewed the remaining misses for
  patterns, found 3 confident token-collision errors (e.g. "auto" in
  "AUTO DEBIT" pulling toward Transportation instead of meaning
  "automatic payment"), fixed them with trigrams + 14 targeted
  disambiguation rows, and expanded the stress test from 50 to 150
  examples — see `ml/log.md` for the full investigation. **Final
  realistic-text results: 92.0% accuracy, 0.9200 macro-F1** (138/150,
  all originally-targeted token-collision errors fixed; the 12 remaining
  misses are genuine category-boundary confusions, not vocabulary gaps).
  This stress test now runs automatically on every training run and
  reports the full precision/recall/F1 breakdown, not just accuracy
  (`ml/evaluate_on_realistic_examples.py`, wired into
  `ml/train_expense_categorizer.py`) so `metrics.json` always reflects
  it — see `PROJECT_PLAN.md` Phase 3 for the complete writeup. Manual
  entry and CSV import both auto-categorize when no category is given;
  the Budgeting page shows the live accuracy metric and marks
  ML-categorized transactions.

- **Phase 8** — complete (redefined as Smart Budgeting & Goal Planner).
  Users pick expense categories from a fixed list of 13 (Needs / Wants /
  Savings), which replaced the Phase 3 auto-categorizer in the app. Old
  categories are migrated on startup. Budget setup, an Estimated/Actual
  spending pie, a deterministic overspend rules engine (50/30/20,
  per-category ranges, DTI, emergency fund) and a flat vs step-up SIP
  goal planner with an affordability check. An LLM is optional and only
  rewords results. See `docs/PHASE_8_BUDGETING.md`.

See `PHASE_2_EXECUTION_PLAN.md` for remaining Phase 2 polish, and
`PROJECT_PLAN.md` for later phases and ownership.

### Training the expense categorizer (Phase 3)

```bash
cd ml
cp .env.example .env   # needs a free Hugging Face token — see that file
python3 train_expense_categorizer.py
```

Needs a Hugging Face account + accepting the dataset's access conditions
once at [huggingface.co/datasets/mitulshah/transaction-categorization](https://huggingface.co/datasets/mitulshah/transaction-categorization)
(instant, no review), then a token from
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
Writes `vectorizer.joblib` + `model.joblib` (gitignored — regenerate
locally) and `metrics.json` (tracked — the real reported results) to
`ml/models/expense_categorizer/`. As of Phase 8 the app no longer uses
this model (categories are picked by the user); the script is kept as
the Phase 3 record and is not needed to run the app.
