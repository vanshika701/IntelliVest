# Phase 8 — Smart Budgeting, Overspend Rules & Goal Planner

_Completed 2026-11-21 on branch `feature-instrument-search-invest`._

## Checklist

- [x] Remove AI auto-categorization. Expenses need a category picked from a fixed list. The
      Phase 3 ML service, its route (`/expenses/categorization-model-info`), its tests and the
      UI badges are gone. The offline training code in `ml/` is kept as the Phase 3 record.
- [x] 13 categories defined in one place (`backend/app/core/budget_config.py`), each tagged
      Needs / Wants / Savings.
- [x] Migration of old labels (free text and the Phase 3 ML labels) to the new ids. It runs
      on every startup, is idempotent, and keeps the old label in `legacy_category`. CSV
      import uses the same label mapping. It never guesses from the description.
- [x] Budget setup: monthly income, optional emergency savings, and a monthly estimate per
      category. Inputs are validated (non-negative, ≤ 2 dp). The app warns when estimates
      exceed income.
- [x] Pie chart with an Estimated / Actual toggle, plus an estimated-vs-actual table.
- [x] Deterministic rules engine: 50/30/20, per-category ranges, debt-to-income flag at
      36%, and the emergency fund (3–6 months of essentials). Results are compared against
      both the benchmark and the user's own estimate. "Improve my budget" works per category
      or for the whole budget, and lists the top 3 other overspends.
- [x] Goal planner with flat SIP and step-up SIP side by side. The expected return and
      step-up % can be edited and the plan updates live. Includes an affordability check
      against the monthly surplus, ₹-specific options (extend / reduce / cut), the
      short-horizon safer-instrument note, and a disclaimer.
- [x] Optional LLM wording only: template text by default. A Groq or Gemini rewrite is available if
      enabled, and it is rejected if any number changes.
- [x] Tests: SIP maths, rules engine, migration, API, explainer guard, and frontend
      validation and chart helpers.

Added 2026-11-25: income sources in three groups (Job / Investments / Other), editing of
transactions and goals, an error state, and a 0-100 health score (`services/health_score.py`):
savings 20 points, emergency fund 15, debt 15, rent / housing 12, groceries 8, bills + transport +
health 10, lifestyle spending 20. These are points out of 100, not shares of income. A spending
part earns full marks up to its guideline maximum and none at twice it; parts not entered are left
out. The weights and scales are our own choices, in `budget_config.py`.

## How it works

| Layer | File |
|---|---|
| Categories, thresholds, return assumptions, sources | `backend/app/core/budget_config.py` |
| Label mapping + startup migration | `backend/app/services/category_migration.py` |
| Rules engine (pure) | `backend/app/services/budget_rules.py` |
| SIP / goal maths (pure) | `backend/app/services/goal_planner.py` |
| Optional LLM wording | `backend/app/services/budget_explainer.py` |
| Orchestration + "actual" spend | `backend/app/services/budget_service.py` |
| Routes (`/api/v1/budget/...`) | `backend/app/api/v1/routes/budget.py` |
| UI | `frontend/src/pages/BudgetingPage.tsx`, `frontend/src/components/budget/*` |

**Definitions**
- **Actual monthly spend** is the average over the completed months, within the last 3, that
  have expenses. The current month is used only when there is nothing else. A category with
  nothing logged, or an unfinished month below the estimate, uses the estimate, and the UI says so.
- **Goals** claim the surplus in the order they were created.
- **Surplus** = income − (Needs + Wants). The Savings & Investments allocation counts as
  available for goal SIPs.
- **Savings rate** (50/30/20) = surplus ÷ income.
- **Emergency-fund essentials** = the user's Needs spending (housing, groceries, transport,
  utilities, health, education, EMIs).
- **SIP convention**: contributions are made at the start of each month and the monthly
  rate is annual ÷ 12, the same as the instrument return calculator. Step-up raises the
  amount once every 12 months, and the starting amount is solved exactly, including a
  partial final year.

## Assumptions to review (all in `budget_config.py`)

| Item | Default | Basis |
|---|---|---|
| 50/30/20 | Needs ≤ 50%, Wants ≤ 30%, Savings ≥ 20% of take-home | Warren & Tyagi, *All Your Worth*; confirmed on Experian; split also on U.S. Bank |
| Housing & Rent | 25–35% | ~30% rent-burden line / "28" of the 28/36 rule; widened for Indian metros |
| Groceries | 8–12% | rule of thumb |
| Food & Dining Out | 3–6% | rule of thumb |
| Transportation | 5–10% | rule of thumb |
| Utilities & Bills | 5–8% | rule of thumb |
| Health & Insurance | 5–8% | rule of thumb |
| Shopping & Personal Care | 3–6% | rule of thumb |
| Entertainment & Leisure | 3–5% | rule of thumb |
| Travel | 2–5% | rule of thumb |
| Education | no benchmark | "as needed" |
| EMI / Debt | ≤ 30%; **critical above 36%** | 28/36 rule caps total debt at 36% of *gross*; Finnovate calls 25–35% of take-home safe (bank FOIR allows 40–55% of gross). We use take-home, which is conservative |
| Savings & Investments | ≥ 20% | 50/30/20 |
| Other / Miscellaneous | no benchmark | — |
| Emergency fund | 3–6 months of essentials | Empower |
| Return ≤ 3 years | 6% / yr | just under a 3-year SBI FD (6.3%) |
| Return 3–5 years | 8% / yr | our own value between the other two; no source found |
| Return > 5 years | 11% / yr | below the Nifty 50 TRI 20-year CAGR of about 12.4% |
| Step-up | 10% / yr | common default |
| Bucket of "Other" | Wants | conservative (counts against discretionary) |
| Bucket of "Education", "EMI" | Needs | — |

The per-category ranges are not from one authority. They are starting points chosen to sit
inside the 50/30 split.

**Source check (2026-11-25).** Pages opened and read: Experian, U.S. Bank, Empower, Bankrate,
Finnovate, MoSPI's HCES 2023-24 press note, Scripbox (SBI FD) and Bajaj AMC (Nifty 50 TRI, quoting
NSE). Corrected: Finnovate says 25–35% of take-home, not 30–40%; the 7% and 9% return defaults were
not supported. Could not be opened: American Express, Investopedia, HUD, SBI and NSE's own pages.
MoSPI's urban averages (food about 40% of spending, conveyance 8.46%, rent 6.58%) are not used as
limits: they are shares of spending, not income, and the rent average includes home owners.

Every figure is illustrative and is not financial advice. The UI
says so on the Improve and Goals tabs.

## Optional LLM explanations

Off unless a key is set. With a key, an "Explain in plain words" button appears under
Budgeting > Improve and on each saved goal. In `backend/.env`:

```bash
BUDGET_EXPLAINER_PROVIDER=groq        # or gemini
GROQ_API_KEY=...                      # free: https://console.groq.com/keys
GEMINI_API_KEY=...                    # free: https://aistudio.google.com/apikey
```

| Provider | Free tier (checked 2026-11-25) | Use of our data |
|---|---|---|
| **Groq** (default), `openai/gpt-oss-120b` | Yes: 30 requests/min, 1,000/day | Not retained by default; up to 30 days for reliability or abuse checks |
| Gemini, `gemini-3.5-flash-lite` | Yes; limits shown only in AI Studio | Free-tier content is used to improve Google's products |
| Claude | Trial credits only | - |
| OpenAI (GPT) | Lists a free tier, but no free models or limits | - |
| xAI (Grok) | None listed on its models page | - |

Groq is the default because the text describes someone's finances and Groq has the better data
terms. Sources: console.groq.com/docs/rate-limits and /docs/your-data,
aistudio.google.com/docs/pricing, platform.claude.com pricing, developers.openai.com rate limits,
docs.x.ai/docs/models.

The server recomputes everything and sends only the engine's own sentences. If the reply contains a
number that wasn't in them, reorders numbers or writes them as words, or the call fails, the
template text is returned instead.

## Running and testing

```bash
docker compose up -d                       # MongoDB
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload   # migration runs on startup
cd frontend && npm run dev                 # open /budget

cd backend && ../.venv/Scripts/python -m pytest -q
cd frontend && npm test && npx tsc -b && npm run lint
```

Phase 8 tests: `backend/tests/test_goal_planner.py`, `test_budget_rules.py`,
`test_category_migration.py`, `test_budget_api.py`, the updated `test_expenses.py`, and
`frontend/src/lib/budget.test.ts`.
