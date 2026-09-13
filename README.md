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

Run backend tests:

```bash
cd backend
pytest
```

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

Phase 0 (this setup) is done — empty-but-running React app talking to an
empty-but-running FastAPI backend, backend talking to local MongoDB. See
`PROJECT_PLAN.md` for what's next (Phase 1) and the phase-by-phase
ownership split as you two divide the work.
