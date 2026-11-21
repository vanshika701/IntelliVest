# IntelliVest — Project Status: Search, Instrument Detail & Invest Flow

_Last updated: 2026-11-21 (planning; updated as work progresses)_

## 1. What exists today

**Tech stack**
- Frontend: React 19 + TypeScript, Vite 8, Tailwind CSS v4 (dark theme only, colours as CSS
  variables in `frontend/src/index.css`), React Router 7, Recharts 3, lucide-react icons,
  date-fns. Tests: Vitest + Testing Library (jsdom). Lint: oxlint. Type-check: `tsc -b`.
- Backend: FastAPI (Python 3.12), layered `api/v1/routes` → `services` → `data` (Motor/MongoDB),
  Pydantic schemas, APScheduler background jobs, JWT auth. Tests: pytest (+ a real throwaway
  MongoDB database). Lint: ruff.
- Database: MongoDB 8 (via `docker compose up -d`).

**Pages** (`frontend/src/pages`): Auth (login/register), Dashboard (savings, alerts, watchlist
overview, market news), Watchlist, Budgeting (expenses, CSV upload, ML categorisation),
Alerts. Layout: `AppShell` = `Navbar` (page title, notifications bell, user chip) + `Sidebar`.

**Components**: `Button`, `Input`, layout components. No shared skeleton/badge components yet.

**APIs** (`/api/v1`, all except auth/health need a Bearer token): `auth`, `health`, `expenses`,
`watchlist`, `alerts`, `dashboard`, `sentiment` (FinBERT news sentiment per tracked stock).

**Data sources**
- Stock prices: yfinance, daily OHLCV for a fixed universe of 20 NSE large caps, stored in the
  `prices` collection (≈2 years) by a daily background job.
- News: Indian RSS feeds (Economic Times, Livemint, Google News per company), stored in
  `news_articles` hourly, each article scored by FinBERT (`sentiment` field).
- Reddit: built but paused (no API access yet).
- No mutual fund / ETF data, no instrument search, no investing/orders anywhere.

## 2. What's being asked for (restated)

- **A. Global search** in the top bar, next to the notifications bell: debounced (~300 ms)
  search over stocks, mutual funds and ETFs (e.g. "gold" → SBI Gold, Edelweiss Gold…), dropdown
  with name + type tag (Stock/MF/ETF), loading/empty/error states, keyboard navigation
  (↑/↓/Enter/Esc), collapses to an icon on mobile. A result opens `/instrument/:id`.
- **B. Instrument detail page**, top to bottom: header (name, type, price/NAV, day change abs +
  %, green/red) → price chart with 1D/1W/1M/3M/1Y/YTD (default 1M or whatever has data; ranges
  without data disabled with a tooltip) → key stats strip (price/NAV, rating, min SIP, fund size;
  "—" when unknown) → news sentiment (one-line overall label with coloured badge + the headlines
  used, each tagged with sentiment, source, date) → return calculator → invest panel.
- **C. Return calculator**: standard formulas only (no ML). SIP:
  `FV = P × [((1 + i)^n − 1) / i] × (1 + i)`, `i` = annual rate / 12, `n` = months. Lumpsum:
  `FV = P × (1 + r)^t`. Inputs: One-time/SIP toggle, amount, years, expected annual return
  (default: instrument's historical CAGR if computable, else 12%; editable). Outputs: invested,
  estimated returns, total value, small chart, and the note "Estimates are based on assumed
  returns and are not guaranteed."
- **D. Sentiment**: pre-trained only, behind one `sentimentService`, headline scores aggregated
  into Negative/Neutral/Positive, cached 15–30 min, "Not enough news to determine sentiment"
  when there's no news.
- **E. Invest panel** (UI only, no real money): "One-time" (amount + quick-pick chips ₹500 /
  ₹1000 / ₹5000, min-investment validation, account/folio selector, Invest button) and "Start
  SIP" (amount validated against min SIP, "Monthly on 1st" date row with a calendar icon,
  changeable to day 1–28, Start SIP button). A `paymentService` interface with a mock
  implementation (short delay, success/failure, confirmation screen), structured so Razorpay can
  replace it later. Mock orders/SIPs persisted so a "my investments" view can list them.
- **Quality**: responsive, accessible, consistent with the dark theme, loading skeletons,
  empty and error states, tests for formulas + range/YTD logic + search debounce, lint,
  type-check, existing tests green, manual end-to-end check, small commits per feature area.

## 3. Gap analysis

| Requirement | Exists today | Missing |
|---|---|---|
| A. Global search | Navbar with an empty slot ("Future: Global Stock Search") | Search API (stocks + MF/ETF), MF data source, debounced combobox component with ARIA + mobile mode |
| B. Header + chart | Daily stock prices in Mongo; Recharts installed | Instrument detail API, MF NAV history, intraday (1D) data, range filtering logic, chart component, detail page + route |
| B. Stats strip | Nothing | Rating / AUM / min SIP for funds (no free source → `fundMetaProvider`) |
| B/D. Sentiment | FinBERT scoring + per-stock summary for the 20 tracked stocks | Sentiment for funds/ETFs (no news ingested for them), a single swappable engine with a fallback, caching, "not enough news" state, UI section |
| C. Calculator | Nothing | Formula module, CAGR from history, calculator UI + chart, tests |
| E. Invest panel | Nothing | Investments collection/API, accounts/folios (none exist → mock), `paymentService` + mock, confirmation screen, "My investments" page |

## 4. Data source decisions & assumptions

- **Stocks — reuse yfinance + the existing `prices` collection.** Search covers the 20 tracked
  NSE stocks (matched on name, ticker and aliases). Daily history comes from Mongo; the 1D chart
  uses yfinance 5-minute bars for the last trading session, fetched on demand by the backend and
  cached for 5 minutes. _Assumption:_ stocks outside the 20-stock universe are out of scope for
  now (they have no stored prices or news sentiment).
- **Mutual funds & ETFs — mfapi.in** (free, no key; checked: `/mf/search?q=gold` returns 15
  schemes, `/mf/{code}` returns metadata + full daily NAV history). Scheme names containing "ETF"
  (but not "Fund of Fund"/"FoF") are tagged ETF, the rest MF. Results are cached (search 1 h,
  history 6 h), calls have a 10 s timeout and retries, and failures return a clean error.
  _Assumption:_ ETF prices shown are AMFI NAVs, not live exchange prices.
- **Mutual funds only have a daily NAV**, so 1D is disabled for MF/ETF with a tooltip.
- **Rating, fund size (AUM), minimum SIP / minimum investment: no free API.** They sit behind a
  `fundMetaProvider` (backend). The current implementation is a mock:
  rating and AUM are `null` (shown as "—", never invented); minimum SIP (₹500) and minimum
  one-time (₹1,000) are **placeholder defaults**, flagged `is_placeholder` and labelled
  "Placeholder" in the UI, so validation has something to check against. For stocks, the
  minimum is one share at the latest price (derived, not a placeholder).
- **Historical CAGR** for the calculator uses up to the last 3 years of the price/NAV series
  (needs ≥ 1 year of data). Results outside −50%…+60% a year are treated as data problems (e.g.
  the unit split visible in SBI Gold ETF's NAV history) and the calculator falls back to 12%.
- **Investment accounts/folios: none exist in the app**, so a mock list (clearly labelled "Demo")
  is returned by the backend.
- All external calls happen in the backend service layer; the frontend only calls our API. No
  new API keys are needed (mfapi.in, yfinance and Google News RSS are keyless).

## 5. Implementation plan (checklist)

- [x] 0. FinBERT sentiment work committed (`739cd86`); this work is on branch
      `feature-instrument-search-invest`
- [x] 1. This document
- [ ] 2. Backend: TTL cache helper; mfapi.in client; `fundMetaProvider` (mock); instrument
      service (search, detail, daily history, intraday) + routes + tests
- [ ] 3. Backend: instrument sentiment in `sentiment_service` (stored FinBERT scores for stocks,
      on-demand Google News + FinBERT for funds, lexicon fallback, 20-min cache) + route + tests
- [ ] 4. Backend: investments (accounts mock, create one-time/SIP, payment result, list) +
      collection/index + tests
- [ ] 5. Frontend: API wrappers, `useDebouncedValue`, `GlobalSearch` combobox in the navbar
      (desktop + mobile), tests
- [ ] 6. Frontend: range/YTD logic + returns formulas (+ tests); instrument page with header,
      chart, stats strip, sentiment section, return calculator; skeletons/empty/error states
- [ ] 7. Frontend: `paymentService` (interface + mock), invest panel (One-time / Start SIP),
      confirmation screen, "My Investments" page + sidebar link
- [ ] 8. Lint, type-check, all tests; run the app and walk the full flow
- [ ] 9. Update this document with what was built, what's mocked, what's left

## 6. Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-11-21 | **Return calculator uses the standard SIP/lumpsum formulas, not an ML model.** | Deterministic, explainable and sufficient; a model adds nothing for compounding maths. |
| 2026-11-21 | **Sentiment uses the pre-trained FinBERT already in the backend; no training.** A keyword lexicon is the fallback if FinBERT can't load. Both sit behind `sentiment_service`, so the engine can be swapped. | FinBERT is already running for news (option 2 in the brief); no LLM keys exist in the project yet. |
| 2026-11-21 | Overall label = average of headline scores (positive − negative probability), with ±0.15 as the neutral band; at least 3 headlines needed, otherwise "Not enough news to determine sentiment". | Same rule as the existing per-stock sentiment, and avoids a label from one or two headlines. |
| 2026-11-21 | Fund sentiment is computed on request (fresh Google News search + FinBERT) and cached for 20 minutes, unlike stocks, which read precomputed scores. | Funds are open-ended (any of ~thousands of schemes), so pre-ingesting news for all of them isn't practical. The cache keeps it within rate limits. |
