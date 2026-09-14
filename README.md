# IntelliVest AI

An AI-powered investment advisor + budgeting/watchlist platform. See
[`PROJECT_PLAN.md`](./PROJECT_PLAN.md) for the full phased build roadmap.

## Repo structure

```
backend/     FastAPI service (layered: api / services / data / core)
frontend/    React + TypeScript + Tailwind app (Vite)
ml/          Model training notebooks/scripts and saved artifacts
blockchain/  Audit-layer smart contract work (Phase 10 — not started yet)
docs/        Written docs/evaluation reports produced as phases complete
```

## Prerequisites

- Python 3.12 (pinned in `.python-version`)
- Node 24 (pinned in `.nvmrc`)
- MongoDB running locally on the default port (`27017`) — `brew install mongodb-community` and `brew services start mongodb-community`, or run `mongod` yourself

## Backend setup

```bash
python3 -m venv .venv          # once, from the repo root
source .venv/bin/activate
pip install -r requirements.txt

cd backend
cp .env.example .env           # fill in API keys as later phases need them
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
key needed), news (NewsAPI), and Reddit (asyncpraw). Each has a manual
entry point for one-off runs, and all three also run automatically on a
schedule (daily for prices, hourly for news/Reddit) whenever the backend
is running, via `app/core/scheduler.py`:

```bash
cd backend
python -m scripts.ingest_market_data   # works immediately, no API key
python -m scripts.ingest_news          # needs NEWS_API_KEY in .env
python -m scripts.ingest_reddit        # needs REDDIT_CLIENT_ID/SECRET/USER_AGENT in .env
```

News and Reddit log a warning and exit cleanly if their credentials
aren't set yet, rather than failing — safe to leave unconfigured until
you're ready. Get a NewsAPI key at [newsapi.org](https://newsapi.org).

**Reddit is currently blocked on Reddit's own approval process**, not on
anything in this codebase. Since November 2025, new API apps require
manual approval under Reddit's
["Responsible Builder Policy"](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
before you get credentials — `/prefs/apps` no longer issues them
instantly. Submit that request whenever you get to it; the ingestion
code is already built and tested, so once Reddit approves you and hands
over `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/`REDDIT_USER_AGENT`,
nothing else needs to change.

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

Phase 2 is the active build. Track remaining work in
[`PHASE_2_EXECUTION_PLAN.md`](./PHASE_2_EXECUTION_PLAN.md) (source of truth).

- **Phase 0** — done. Empty-but-running React app talking to an
  empty-but-running FastAPI backend, backend talking to local MongoDB.
- **Phase 1** — built and tested, partially verified live:
  - Market data (yfinance): fully live — 20-stock universe, ~10k real
    price records in MongoDB, confirmed idempotent on re-runs
  - News (NewsAPI): fully live — 301 real articles across the 20-stock
    universe, tickers correctly merged on shared articles, confirmed
    idempotent across repeated runs
  - Reddit (asyncpraw): **paused, not dropped** — pipeline is fully
    built and tested against fabricated data, waiting on Reddit's own
    access approval (see "Data ingestion" above). News is the working
    sentiment source in the meantime; Reddit slots in later with zero
    code changes once approved
  - Scheduler wraps all three into a real background job, retries
    transient failures with backoff, fails fast on permanent ones

See `PHASE_2_EXECUTION_PLAN.md` for remaining Phase 2 work, and
`PROJECT_PLAN.md` for later phases and ownership.
