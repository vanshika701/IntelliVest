# Phase 2 Execution Plan — Unified Dashboard, Budgeting & Watchlist

**Project**: IntelliVest AI  
**Phase**: Phase 2 (Core Product Shell)  
**Status**: In Progress — core shell implemented, not yet Phase-2-complete  
**Last audited**: 2026-09-14 (implementation vs this plan; source code is authoritative)  
**Reference Document**: `PROJECT_PLAN.md`  

This document is the **single source of truth** for Phase 2 remaining work. After any coding task, update checkboxes and notes here immediately.

**Status legend**: `[x]` done · `[ ]` pending · items marked **IN PROGRESS** or **NEEDS REWORK** in notes are not fully done.

---

## 1. Understanding Phase 2 Scope & Requirements

The primary goal of Phase 2 is to build the core non-AI application shell for IntelliVest AI — a modern financial platform modeled after **Groww** and **Zerodha (Kite)**. It serves as the foundation and UI/data scaffolding into which all future ML modules (Expense Categorization, Stock Price Prediction, FinBERT Sentiment Analysis, Portfolio Recommendation Engine, Financial Health Score, and AI Advisor) will seamlessly plug.

### Core Deliverables for Phase 2:

1. **User Management & Authentication**:
   - [x] Secure user registration
   - [x] Login
   - [ ] Token refresh
   - [x] Client-side logout (clears `localStorage` token; no server revoke)
   - [ ] Server-side logout / token invalidation
   - [x] Password hashing (`bcrypt` directly — not `passlib`/`pwdlib`)
   - [x] JWT bearer access tokens (`PyJWT`, HS256, 24h expiry)
   - [x] User profile endpoint `GET /api/v1/auth/me` and MongoDB `users` persistence

2. **Budgeting & Expense Management Module**:
   - [x] Manual expense and income entry (amount, category, description, date)
   - [x] CSV statement parser with header auto-detect (date / description / amount / debit-credit)
   - [ ] Sample CSV download
   - [ ] Treat a dedicated `Type` column as income vs expense (today `"type"` is treated as **category**; amount-only files default all rows to `expense`)
   - [x] Financial summaries (total income, total expense, net, category breakdowns)

3. **Smart Watchlist Module**:
   - [x] Add/remove tickers (backend accepts any ticker string)
   - [x] Frontend add/remove against the 20-stock universe dropdown
   - [ ] Custom ticker entry in the UI
   - [x] Notes field (backend + inline edit on Watchlist page)
   - [x] Priority enum on backend (`high` / `medium` / `low`); stored as `medium` on add
   - [ ] Priority picker in the UI
   - [x] Investment rationale field on backend
   - [ ] Investment rationale UI
   - [x] Live enrichment from ingested OHLCV in MongoDB (`latest_price`, `previous_close`, `change_pct`)

4. **Intelligent Price Proximity Alerts (Rule-Based)**:
   - [x] Custom rules: `above`, `below`, `within_pct` of a target price
   - [x] Rule evaluation logic (`alert_service._check_trigger` / `evaluate_all_alerts`)
   - [ ] Wire `evaluate_all_alerts` into `app/core/scheduler.py` (function exists; **not scheduled**)
   - [x] Persist `triggered` / `triggered_at` and dashboard split of triggered vs active
   - [ ] In-app notification bell + badge in the navbar

5. **Unified Dashboard & UX (Groww / Zerodha Inspired)**:
   - [x] Dark theme design tokens (slate-950, mint `#10B981`, coral `#F43F5E`, indigo `#6366F1`)
   - [x] Dashboard payload: watchlist slice, budget summary, alerts, recent news
   - [ ] Ticker marquee in the navbar
   - [ ] Dedicated reusable modal / dropzone component library (pages use inline overlays)
   - [x] Sidebar slots for future AI (AI Advisor nav item present, disabled)
   - [ ] Dashboard compile-clean (unused Recharts imports; empty-state uses undeclared `LineChart`)

---

## 2. Infrastructure Inventory (Phase 0 & Phase 1 Foundations)

### What is Already Built & Available:

- **Directory & Repo Conventions**: `frontend/` and `backend/` are the live trees. README still describes `ml/`, `blockchain/`, `docs/` as top-level concerns; those directories are **not present** yet (Phase 3+ / 10 / 11). Keep the convention; do not treat them as existing.
- **Backend Architecture**:
  - FastAPI app with CORS, structured logging, async lifespan management (`app/main.py`).
  - Motor async MongoDB connection pool (`app/data/mongo.py`).
  - Centralized configuration (`app/core/config.py`) using Pydantic Settings.
  - Data ingestion scheduler (`app/core/scheduler.py`) — **ingestion jobs only** (market daily, news/Reddit hourly).
  - Exponential backoff retry handler (`app/core/retry.py`).
- **Data Collections & Indexes**:
  - `prices`: unique `(ticker, date)`.
  - `news_articles`: unique sparse `url`, `(tickers, published_at)`.
  - `reddit_posts`: unique `post_id`, `(subreddit, created_utc)`.
  - **Phase 2**: `users` unique `email`; `expenses` `(user_id, date)`; `watchlist` unique `(user_id, ticker)`; `alerts` `(user_id, is_active)` and `(ticker, is_active)`.
- **Data Ingestion Pipelines (Phase 1)**:
  - `market_data_service.py`: 20 NSE stocks via yfinance.
  - `news_service.py`: NewsAPI.
  - CLI scripts (`ingest_market_data.py`, `ingest_news.py`, `ingest_reddit.py`).
  - Reddit pipeline paused on Reddit API approval (unchanged).
- **Frontend Stack**:
  - Vite + React 19 + TypeScript + Tailwind CSS v4.
  - React Router 7, Auth/Layout context, lucide-react, recharts, date-fns, clsx/tailwind-merge.
  - API client (`src/api/client.ts`) attaches JWT from `localStorage` (`intellivest_token`).
- **Auth config (Phase 2)**: `jwt_secret_key`, `jwt_algorithm`, `jwt_access_token_expire_minutes` in `Settings`. **Not listed in `backend/.env.example`.** Default secret is a hardcoded placeholder.

---

## 3. What Needs to Be Built in Phase 2

### Backend (`/backend/app`):

- **Models & Schemas (`app/schemas/`)**:
  - [x] `auth.py`: Login, Register, Token, `UserResponse`
  - [ ] `user.py`: dedicated user-profile schemas *(profile shape lives in `auth.py` today — optional file split, do not drop the intent)*
  - [x] `expense.py`: Expense entry, CSV import result, budget summary
  - [x] `watchlist.py`: item, notes, priority, rationale
  - [x] `alert.py`: rule creation + response (includes unused `latest_price` on read)

- **Data Repositories (`app/data/`)**:
  - [x] `user_repository.py`
  - [x] `expense_repository.py`
  - [x] `watchlist_repository.py`
  - [x] `alert_repository.py`

- **Service Layer (`app/services/`)**:
  - [x] `auth_service.py`: bcrypt hashing, access-token create/decode, register/login/`me`
  - [ ] Refresh-token issuance and rotation
  - [x] `expense_service.py`: summaries + CSV parser
  - [x] `watchlist_service.py`: enrichment from `prices`
  - [x] `alert_service.py`: rule evaluation engine
  - [ ] Scheduler job calling `evaluate_all_alerts`

- **API Endpoints (`app/api/v1/routes/`)**:
  - [x] `/api/v1/auth` — `register`, `login`, `me`
  - [ ] `/api/v1/auth` — `refresh`, `logout`
  - [x] `/api/v1/expenses` — `GET` (paginated), `POST`, `POST /upload-csv`, `DELETE /{id}`, `GET /summary`
  - [x] `/api/v1/watchlist` — `GET`, `POST`, `DELETE /{id}`, `PATCH /{id}` *(plan said `PATCH /notes`; implementation is REST `PATCH /{item_id}` — keep this)*
  - [x] `/api/v1/alerts` — `GET`, `POST`, `DELETE /{id}`, `PATCH /{id}/toggle`
  - [x] `/api/v1/dashboard` — aggregated payload

**Implementation notes (backend):**

- `POST /expenses` declares `response_model=ExpenseResponse` but the handler does not return `created_at` (and may omit a concrete `date`). This is a **response-validation bug** (likely 500 on create).
- `GET /expenses` returns `{ items, total, skip, limit }` with a loose `response_model=dict`; list items are raw Mongo docs (may include `created_at`, uses string `id`).
- Alert `latest_price` is on `AlertResponse` but `list_alerts` does not enrich prices.
- `bcrypt`, `PyJWT`, `email-validator` (for `EmailStr`), and `python-multipart` (for CSV `UploadFile`) are **imported/required at runtime but not pinned in `requirements.txt`**. A clean `pip install -r requirements.txt` will not boot auth or uploads until those deps are added.
- JWT secret default in `config.py` is not production-safe and is missing from `.env.example`.

### Frontend (`/frontend/src`):

- **Design System & Components (`src/components/`)**:
  - [x] Navbar with user name/email
  - [ ] Ticker marquee
  - [ ] Notification bell
  - [x] Sidebar / tab navigation (Dashboard, Watchlist, Budgeting, Alerts, AI Insights disabled)
  - [x] Page-level modal overlays for add expense / add watchlist / add alert
  - [ ] Shared modal + CSV drag-and-drop dropzone components
  - [x] Dark-theme cards, badges, tables (Groww/Zerodha-inspired tokens)
  - [ ] `Button` `size` prop (pages pass `size="sm"`; component does not accept it)
  - [ ] Fix import paths: `Button`/`Input` → `../../lib/utils`; `ProtectedRoute` → `../../AuthContext`

- **Pages / Views (`src/pages/`)**:
  - [x] `AuthPage.tsx`: Login & Sign Up
  - [x] `DashboardPage.tsx`: metric cards, watchlist table, news feed, AI placeholder
  - [ ] Dashboard: remove unused Recharts imports; import or replace `LineChart` empty-state icon
  - [x] `WatchlistPage.tsx`: universe picker, prices, notes edit, remove
  - [x] `BudgetingPage.tsx`: manual form, file-input CSV, pie chart, transaction list
  - [ ] Budgeting: drag-and-drop CSV + sample CSV download
  - [x] `AlertsPage.tsx`: create / list / toggle / delete rules
  - [ ] Frontend tests for Phase 2 pages (only Phase 0 `App.test.tsx` exists; `App.tsx` is unused by `main.tsx`)

**Implementation notes (frontend):**

- Routing lives in `main.tsx` (`/auth`, `/dashboard`, `/watchlist`, `/budget`, `/alerts`). `App.tsx` is the old Phase 0 health screen and is **not mounted**.
- CSV upload bypasses `api/client.ts` (raw `fetch` + FormData) so JSON `Content-Type` is not forced — correct for multipart.
- Auth bootstrap also uses raw `fetch` for `/auth/me` instead of `apiGet`.
- TypeScript currently fails (`frontend/tsc_errors.log`): unused imports, wrong relative modules, `Button` `size`, Recharts tooltip typing, `LineChart` undefined. `npm run build` (`tsc -b && vite build`) is **not green**.

---

## 4. Open Questions & Key Design Choices for User Confirmation

Recorded decisions from the implemented code (do not reopen unless changing architecture):

1. **Authentication Mechanism**: **JWT Bearer** in `Authorization` header; token stored in **`localStorage`** (`intellivest_token`). Refresh tokens were proposed in the original plan and are **still pending**.
2. **Database Collections & Schema**: `users`, `expenses`, `watchlist`, `alerts` in MongoDB `intellivest` — **implemented**, with indexes in `app/data/indexes.py`.
3. **CSV Parser Format**: Auto-detect synonyms for date/description/amount/debit/credit/category. Standard `Type` column and sample CSV download remain **pending**.
4. **Price Alert Evaluation Engine**: Intended as a scheduled job vs latest OHLCV close. **Logic is written; scheduler wiring is pending.**
5. **Frontend Aesthetics & UI Layout**: Groww/Zerodha-inspired dark theme **implemented** via Tailwind `@theme` tokens. Marquee + notification bell still pending.

---

## 5. Execution Steps & Sequencing Order

1. **Step 1: Auth & User Backend**:
   - [x] `user_repository.py`, `auth_service.py` (bcrypt + PyJWT), `/api/v1/auth` register/login/me
   - [ ] Pin `bcrypt`, `PyJWT`, `email-validator` in `requirements.txt`; document `JWT_SECRET_KEY` in `.env.example`
   - [ ] Write backend tests in `tests/test_auth.py`
   - [ ] Refresh tokens (if keeping original Phase 2 auth bar)

2. **Step 2: Budgeting & CSV Upload Backend**:
   - [x] `expense_repository.py`, `expense_service.py` (CSV engine), `/api/v1/expenses` routes
   - [ ] Pin `python-multipart` in `requirements.txt`
   - [ ] Fix `POST /expenses` response (`created_at` / `date`) so `ExpenseResponse` validates
   - [ ] CSV `Type` column + sample CSV
   - [ ] Tests for manual entry & CSV parsing

3. **Step 3: Watchlist & Market Integration Backend**:
   - [x] `watchlist_repository.py`, `watchlist_service.py`, `/api/v1/watchlist` routes
   - [ ] Backend tests for add/duplicate/enrich/delete

4. **Step 4: Price Proximity Alerts Backend**:
   - [x] `alert_repository.py`, `alert_service.py` (rule evaluation), `/api/v1/alerts` routes
   - [ ] Register `evaluate_all_alerts` on the APScheduler (interval or after price ingest)
   - [ ] Tests for `_check_trigger` and evaluation
   - [ ] Optional: enrich alert list with `latest_price`

5. **Step 5: Frontend Design System & Auth Flow**:
   - [x] Tailwind design tokens, dark AppShell, Auth context, Login & Register
   - [ ] Fix TypeScript/module-path errors so the app typechecks
   - [ ] Notification bell + ticker marquee (or explicitly defer marquee)

6. **Step 6: Frontend Watchlist & Budgeting Views**:
   - [x] Watchlist table with search, price badges, notes, default priority
   - [x] Budgeting manual entry, CSV file picker, spending pie + list
   - [ ] Priority + rationale on add/edit
   - [ ] Custom ticker input
   - [ ] Drag-and-drop CSV + sample download

7. **Step 7: Frontend Alerts & Unified Dashboard View**:
   - [x] Alerts management page and dashboard aggregation
   - [ ] Navbar notification popup for triggered alerts
   - [ ] Dashboard empty-state / unused-import cleanup
   - [x] AI placeholder card + disabled AI Advisor nav

8. **Step 8: End-to-End Verification & Documentation Update**:
   - [ ] Backend pytest covering Phase 2 modules
   - [ ] Frontend tests beyond Phase 0 `App.test.tsx`
   - [ ] Manual E2E: register → login → expenses/CSV → watchlist → alerts → dashboard
   - [ ] Confirm Groww/Zerodha UX polish
   - [x] This document updated to match implementation (this audit)

---

## 6. Progress Audit (2026-09-14)

Every planned item classified. Trust the code, not older README wording.

| Area | Item | Status | Reasoning |
| --- | --- | --- | --- |
| Auth | Register / login / me | Completed | Routes + service + `users` collection + unique email index |
| Auth | JWT access tokens + bcrypt | Completed | `auth_service.py`; 24h HS256 tokens |
| Auth | Token in localStorage + Bearer client | Completed | `AuthContext` + `api/client.ts` |
| Auth | Refresh tokens | Pending | No refresh route, no refresh collection |
| Auth | Server logout / revoke | Pending | Sidebar logout is client-only |
| Auth | `tests/test_auth.py` | Pending | File does not exist |
| Auth | Deps in `requirements.txt` + `.env.example` JWT | Needs rework | Runtime imports `bcrypt`/`jwt`; not pinned; JWT secret not in example env |
| Budget | Manual CRUD + summary | Completed | Routes, repo aggregation, Budgeting UI |
| Budget | CSV upload API + UI picker | In Progress | Parser + `upload-csv` + hidden file input exist |
| Budget | CSV `Type` + sample download + dropzone | Pending | `"type"` maps to category; no sample file; no DnD |
| Budget | `POST /expenses` response_model | Needs rework | Missing `created_at` vs `ExpenseResponse` |
| Budget | Tests | Pending | No `test_expense*.py` |
| Watchlist | Backend CRUD + price enrich | Completed | Unique `(user_id, ticker)`; aggregation on `prices` |
| Watchlist | UI add/remove/search/notes | In Progress | Universe dropdown only; notes editable; no rationale/priority picker |
| Watchlist | Custom tickers + rationale/priority UI | Pending | Backend fields exist; UI does not expose them |
| Watchlist | Tests | Pending | No watchlist tests |
| Alerts | CRUD + toggle + rule functions | Completed | `above`/`below`/`within_pct`; toggle resets trigger |
| Alerts | Background evaluation job | In Progress | `evaluate_all_alerts` exists; **not** in `start_scheduler` |
| Alerts | Notification bell | Pending | Dashboard shows triggered count only |
| Alerts | Tests | Pending | No alert tests |
| Dashboard | Aggregated API + page | In Progress | Endpoint + UI; TS error on `LineChart`; Recharts unused |
| UX | AppShell / Sidebar / tokens | In Progress | Layout works; `ProtectedRoute`/`Button`/`Input` import paths wrong per `tsc` |
| UX | Marquee, shared modals, dropzone | Pending | Navbar comment explicitly defers marquee |
| Step 8 | E2E + Phase 2 tests + polish | Pending | Phase 1 tests only; frontend test still targets unused `App.tsx` |

---

## 7. Remaining Work Backlog

### Completed

- Layered Phase 2 backend: schemas, repositories, services, versioned routes, Mongo indexes.
- JWT access-token auth with hashed passwords and `get_current_user_id` dependency.
- Expenses (list/create/delete/summary) and CSV import engine.
- Watchlist CRUD + OHLCV enrichment.
- Alerts CRUD/toggle + pure rule evaluator + `evaluate_all_alerts`.
- Dashboard aggregate endpoint.
- Auth page, AppShell, protected routing, Watchlist/Budget/Alerts/Dashboard pages, design tokens.

### In Progress

- CSV import UX/semantics (picker yes; Type column, sample file, dropzone no).
- Watchlist metadata UI (notes yes; priority/rationale/custom ticker no).
- Alert evaluation (code yes; scheduler no).
- Dashboard/Alerts UX (pages yes; bell/marquee/TS-clean no).
- Frontend design-system completeness (`Button` sizes, shared modals).

### Pending

- Refresh tokens and server-side logout.
- Phase 2 backend tests (`test_auth.py`, expenses, CSV, watchlist, alerts, dashboard).
- Phase 2 frontend tests; replace or drop unused `App.tsx` health test.
- Sample CSV download.
- Notification bell + ticker marquee.
- Pin missing Python dependencies; document JWT env vars.
- Extend `test_indexes.py` for Phase 2 index names.
- Step 8 E2E verification.

### Blocked

- **None on product scope.** Reddit ingestion remains Phase 1 paused (external API approval) and does **not** block Phase 2 CRUD/dashboard (news is the live feed).
- **Local-setup risk (not a product blocker):** a fresh venv from `requirements.txt` cannot import `bcrypt` / `jwt` until those packages are added.

---

## 8. Remaining-Work Roadmap (dependency order)

Do this sequence; do not start Phase 3 until Step 8 can be honestly checked.

1. **Pin runtime deps + env docs** (`bcrypt`, `PyJWT`, `email-validator`, `python-multipart`, `JWT_SECRET_KEY`).  
   *Why first:* nothing else is verifiable on a clean install. **Critical path.**
2. **Fix backend contract bugs** (`POST /expenses` body vs `ExpenseResponse`; optionally typed expense list).  
   *Why next:* Budgeting UI create-flow depends on a valid 201.
3. **Schedule `evaluate_all_alerts`** (e.g. every 5 minutes and/or immediately after market ingest).  
   *Why next:* Phase 2 exit criterion is “get a rule-based alert when a price crosses a threshold.” Without the job, alerts never flip to triggered in production. **Critical path.**
4. **Auth/expense/alert/watchlist unit + API tests.**  
   *Why next:* locks the contracts before more UI work. Critical for Step 8.
5. **Frontend typecheck/build green** (import paths, `Button` `size`, Dashboard `LineChart`, unused imports).  
   *Why next:* `tsc -b` currently fails; the shell is not shippable. **Critical path.**
6. **CSV Type column + sample CSV + dropzone.**  
   *Why after expense tests/fix:* parser changes need tests first.
7. **Watchlist priority, rationale, optional custom ticker.**  
   *Why after TS-green:* UI-only on a working client.
8. **Notification bell + (optional) marquee.**  
   *Why after alert job:* otherwise the bell has nothing truthful to show.
9. **Refresh tokens** (access + refresh, rotate, logout revoke) if still required for Phase 2 exit.  
   *Why late:* current 24h access token unblocks demo; PROJECT_PLAN still requires expiry/refresh. Do before calling Phase 2 done.
10. **Step 8 E2E + README status pointer** (this file stays SoT).

**Critical path:** deps → expense POST fix → alert scheduler → frontend typecheck → E2E.

**Risks:** JWT secret left as default; XSS/token theft via localStorage (accepted for this phase); alert job never running (silent product miss); CSV `"type"` mis-parse; frontend `tsc` failures hiding runtime import errors; `App.test.tsx` still testing a dead page.

**Technical debt (keep architecture; pay inside Phase 2):** missing deps in requirements; duplicate `STOCK_UNIVERSE` hardcoded in frontend pages; dashboard news query in the route instead of a news service; unused `App.tsx`; AuthContext raw `fetch`; Sidebar invalid CSS `hover:bg-[var(--color-[var(--color-losses-light)])]`.

---

## 9. Development Rules Going Forward

For every future coding task in this phase:

1. Update **this file** immediately after completing work.
2. Mark completed tasks `[x]`; split partial tasks into done vs pending checkboxes.
3. Add newly discovered subtasks here rather than in ad-hoc notes.
4. Never leave this plan behind the code.
5. If implementation and this document disagree, **change the document to match the code**, then decide whether the code still meets Phase 2 exit criteria.
6. Do not remove planned work because it is unfinished.
7. Do not start Phase 3 ML until Section 5 Step 8 is complete.

---

## 10. Phase 2 Exit Criteria (from `PROJECT_PLAN.md` — unchanged)

You can log in, add expenses, upload a transaction file, add stocks to a watchlist with notes, and get a rule-based alert when a price crosses a threshold. No AI yet.

**Honest current gap vs exit criteria:** login/expenses/upload/watchlist-notes are largely present; **automatic alert triggering is not live** (evaluator unscheduled); CSV/watchlist metadata/UX polish and tests are incomplete; frontend production build is not green.
