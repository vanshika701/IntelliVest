# IntelliVest — Project Status: Search, Instrument Detail & Invest Flow

_Last updated: 2026-11-21 — implementation complete on branch `feature-instrument-search-invest`
(see section 7 for what was built, what's mocked and what's left)._

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
- **Mutual funds & ETFs — mfapi.in** (free, no key; `/mf/{code}` returns metadata + full daily
  NAV history). _Changed during implementation:_ mfapi's `/mf/search` caps results at 15, and for
  "gold" those missed SBI Gold Fund and Edelweiss Gold entirely. Search therefore matches
  against mfapi's full scheme list (`/mf`, ~38k schemes, 5.7 MB, cached 24 h), keeping only the
  ~9.4k schemes that still have an ISIN (schemes without one are long-closed). Results show one
  entry per fund (best variant: Direct > Regular, Growth > IDCW). `/mf/search` is the fallback
  if the list can't be loaded. Scheme names containing "ETF"/"Exchange Traded" (but not "Fund
  of Fund"/"FoF") are tagged ETF, the rest MF. Caching: search 1 h, scheme data 6 h; calls
  have a 10 s timeout and retries; failures return 502 or a `partial` search result.
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
- [x] 2. Backend: TTL cache helper; mfapi.in client; `fundMetaProvider` (mock); instrument
      service (search, detail, daily history, intraday) + routes + tests
- [x] 3. Backend: instrument sentiment in `sentiment_service` (stored FinBERT scores for stocks,
      on-demand Google News + FinBERT for funds, lexicon fallback, 20-min cache) + route + tests
- [x] 4. Backend: investments (accounts mock, create one-time/SIP, payment result, list) +
      collection/index + tests
- [x] 5. Frontend: API wrappers, `useDebouncedValue`, `GlobalSearch` combobox in the navbar
      (desktop + mobile), tests
- [x] 6. Frontend: range/YTD logic + returns formulas (+ tests); instrument page with header,
      chart, stats strip, sentiment section, return calculator; skeletons/empty/error states
- [x] 7. Frontend: `paymentService` (interface + mock), invest panel (One-time / Start SIP),
      confirmation screen, "My Investments" page + sidebar link
- [x] 8. Lint, type-check, all tests; run the app and walk the full flow
- [x] 9. Update this document with what was built, what's mocked, what's left

## 6. Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-11-21 | **Return calculator uses the standard SIP/lumpsum formulas, not an ML model.** | Deterministic, explainable and sufficient; a model adds nothing for compounding maths. |
| 2026-11-21 | **Sentiment uses the pre-trained FinBERT already in the backend; no training.** A keyword lexicon is the fallback if FinBERT can't load. Both sit behind `sentiment_service`, so the engine can be swapped. | FinBERT is already running for news (option 2 in the brief); no LLM keys exist in the project yet. |
| 2026-11-21 | Overall label = average of headline scores (positive − negative probability), with ±0.15 as the neutral band; at least 3 headlines needed, otherwise "Not enough news to determine sentiment". | Same rule as the existing per-stock sentiment, and avoids a label from one or two headlines. |
| 2026-11-21 | Fund sentiment is computed on request (fresh Google News search + FinBERT) and cached for 20 minutes, unlike stocks, which read precomputed scores. | Funds are open-ended (any of ~thousands of schemes), so pre-ingesting news for all of them isn't practical. The cache keeps it within rate limits. |
| 2026-11-21 | Fund search matches against mfapi's full live-scheme list, not `/mf/search`. | `/mf/search` returns at most 15 results and missed obvious matches (SBI Gold for "gold"). |
| 2026-11-21 | Sidebar starts closed on screens under 640 px. | It overlays the page on phones and blocked the new detail page's controls. |

## 7. Outcome

### What was built

**Backend** (`/api/v1`, all behind login)
- `GET /instruments/search?q=` — stocks (20 tracked NSE names) + MFs/ETFs (mfapi.in), with type
  tags; a `partial` flag when the fund provider is down.
- `GET /instruments/{id}` (header + stats), `/history` (daily), `/intraday` (5-min bars, stocks
  only), `/sentiment` (overall label + scored headlines). Ids: `stock-<TICKER>`, `mf-<CODE>`.
- `GET /investments/accounts`, `GET /investments`, `POST /investments/one-time`,
  `POST /investments/sip`, `POST /investments/{id}/payment-result` — mock orders/SIPs in a new
  `investments` collection, validated against minimums and account type, one-shot status changes.
- New modules: `core/cache.py` (TTL cache), `services/mfapi_client.py`,
  `services/fund_meta_provider.py`, `services/instrument_service.py`,
  `services/investment_service.py`; `sentiment_service.py` gained `score_texts` (FinBERT →
  lexicon fallback) and `get_instrument_sentiment`; FinBERT warms up in the background at startup.

**Frontend**
- `GlobalSearch` in the navbar (debounced combobox, keyboard + ARIA, mobile icon mode).
- `/instrument/:id`: header, price chart with ranges, stats strip, news sentiment, return
  calculator, invest panel (One-time / Start SIP) with confirmation screens.
- `/investments` ("My Investments", new sidebar entry).
- `services/paymentService.ts` (interface + `MockPaymentService`), `hooks/useApi.ts`,
  `hooks/useDebouncedValue.ts`, `lib/ranges.ts`, `lib/returns.ts`, `lib/format.ts`.

**Tests**: backend 95 passing (+43 new: instruments, instrument sentiment, investments); frontend
43 passing (+40 new: SIP/lumpsum/CAGR formulas, range + YTD logic, search debounce/keyboard/
states, payment mock, amount validation). Lint and type-check clean except 4 warnings that
predate this work. Manually verified end to end in a browser at desktop and phone widths:
search "gold" → SBI Gold Fund → all ranges → stats, sentiment, calculator → One-time ₹5,000
(confirmation) → SIP ₹1,000 on the 15th (confirmation) → both listed under My Investments;
mobile search → Infosys → 1D intraday chart.

### What is mocked or placeholder (all marked `TODO(mock)` in code)

| What | Where | Status |
|---|---|---|
| Rating, fund size (AUM) | `fund_meta_provider.py` | Not available from free sources → `null`, shown as "—" |
| Minimum SIP ₹500 / one-time ₹1,000 for MFs | `fund_meta_provider.py` | Placeholder defaults, labelled "Placeholder" in the UI |
| ETF minimums | `fund_meta_provider.py` | One unit at NAV (approximate), labelled placeholder |
| Investment accounts / folios | `investment_service.DEMO_ACCOUNTS` | Demo list, labelled "(Demo)" |
| Payments and SIP mandates | `frontend/src/services/paymentService.ts` | `MockPaymentService`: ~1.5 s delay, declines amounts above ₹5,00,000 so failure can be demoed |
| Payment verification | `investment_service.record_payment_result` | Trusts the client's result — must verify Razorpay signatures server-side before going live |

### Known limitations
- Stock search covers only the 20 tracked NSE stocks (the only ones with stored prices and news).
- A stock's header price is the last stored daily close (refreshed daily at 18:00 IST), so it can
  be a session behind the 1D intraday chart.
- Fund sentiment is an exact-phrase Google News search on the fund name: popular funds get
  headlines, many niche schemes show "Not enough news to determine sentiment". Headlines are
  scored on overall tone, not specifically for the fund.
- Historical CAGR is shown as-is, including negative values (e.g. a stock that fell over 3 years);
  only values outside −50%…+60% fall back to 12%.
- In-memory caches are per API process (fine for one instance; use Redis if scaled out).

### What's left / next steps
1. Real fund metadata (rating, AUM, minimums) from a paid feed or AMC factsheets → implement a
   second `FundMetaProvider`.
2. Razorpay: backend order creation + signature verification/webhooks, a
   `RazorpayPaymentService` on the frontend, then `VITE_PAYMENT_PROVIDER=razorpay`.
3. Real accounts/folios linked to the user (KYC, folio creation).
4. Broader stock search (e.g. yfinance search for any NSE ticker) with on-demand price history.
5. Optionally use the latest intraday price in the stock header when it's newer than the daily close.

### Environment variables
- No new keys or secrets are needed: mfapi.in, yfinance and Google News RSS are keyless.
- New optional frontend variable `VITE_PAYMENT_PROVIDER` (default `mock`), added to
  `frontend/.env.example`.

---

## 8. Summarization (Phase 5 — news summaries)

_Status: in progress (planned 2026-11-21)._

### Goal
On the instrument detail page, show the top 5 most relevant recent articles, each with a summary
of at most 100 words (headline, source, date, link, summary), next to the sentiment headline. The
current summarizer is a classical **extractive baseline**; it will be replaced by our own trained
seq2seq model (BART/T5/Pegasus) for the final submission, and compared against this baseline.

### Architecture

```mermaid
flowchart LR
  UI[InstrumentPage<br/>NewsSummaries] -->|GET /api/v1/instruments/:id/news-summaries| R[instruments route<br/>+ rate limit]
  R --> S[news_summary_service]
  S --> C1[candidates: stored news (stocks),<br/>Google News + Bing News RSS search]
  S --> F[article_fetcher<br/>robots.txt + timeout]
  S --> CACHE[(TTL cache:<br/>sha256 url+algo+config)]
  S --> G[get_summarizer factory]
  G -->|SUMMARIZER_PROVIDER=extractive| E[ExtractiveSummarizer]
  G -->|SUMMARIZER_PROVIDER=ml| M[MlSummarizer → model server]
  S -->|LOG_SUMMARIES=true| L[(data/summarization_log.jsonl)]
```

All summarizer code lives in `backend/app/services/summarization/`. Only `factory.py` imports
the implementations; the rest of the app uses `get_summarizer()` and the `Summarizer` interface.

### Interface contract
```
summarize(SummaryInput{title, text, url?, max_words, instrument_name?})
  -> SummaryResult{summary, word_count, provider, method, latency_ms}
summarize_batch([SummaryInput]) -> [SummaryResult | SummaryFailure]   # per-item error isolation
```
Guarantee every implementation must keep: `word_count <= max_words`, plain text, no markup.

### Decisions
| Decision | Why |
|---|---|
| Extractive baseline first, trained model later, same interface | Assignment requires our own model; baseline gives a comparison point. |
| No LLM / API calls anywhere in summarization | Requirement; also keeps it free and offline. |
| Google News links are never fetched | `news.google.com/robots.txt` disallows all crawlers; those items fall back to the headline. 885 of 887 stored articles are Google News links. |
| Add **Bing News RSS** search as a candidate source (same RSS parsing code) | Its robots.txt allows `/news/search`; items carry the publisher's real URL (decoded from the link, no extra request) and a description snippet, so there is text to summarize. |
| Full text fetched only where the publisher's robots.txt allows, with a timeout and size cap | Respect robots/ToS; never block the page on fetch failures. |

### Plan (checklist)
- [x] S1. This section
- [x] S2. `summarization` package: interface, extractive algorithm + config, ML placeholder, factory, ROUGE helpers; unit tests
- [x] S3. Article fetcher (robots-aware) + Bing News search; candidate selection (relevance + recency, near-duplicate removal); summary service with cache, JSONL logging; endpoint + rate limit; tests
- [ ] S4. `scripts/eval_summarizer.py`
- [ ] S5. Frontend "Top stories · Auto-summary" cards with skeleton/empty/error states; tests
- [ ] S6. Lint, type-check, all tests, manual check in the browser; update this section with results
