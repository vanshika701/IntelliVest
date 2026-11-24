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
- [x] Optional LLM wording only: template text by default. A Claude rewrite is available if
      enabled, and it is rejected if any number changes.
- [x] Tests: SIP maths, rules engine, migration, API, explainer guard, and frontend
      validation and chart helpers.

The original plan's single "financial health score" was not built. The ratios it would
combine (savings rate, DTI, emergency-fund months) now exist in the rules engine.

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
- **Actual monthly spend** is the average over the calendar months, within the last 3
  (including the current month), that have at least one expense logged.
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
| 50/30/20 | Needs ≤ 50%, Wants ≤ 30%, Savings ≥ 20% of take-home | Warren & Tyagi, *All Your Worth*; widely restated (Experian, U.S. Bank) |
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
| EMI / Debt | ≤ 30%; **critical above 36%** | 28/36 rule caps total debt at 36% of *gross*; Indian advisers suggest ≤ 30–40% of take-home (bank FOIR allows 40–55% of gross). We use take-home, which is conservative |
| Savings & Investments | ≥ 20% | 50/30/20 |
| Other / Miscellaneous | no benchmark | — |
| Emergency fund | 3–6 months of essentials | standard guidance (American Express, Empower) |
| Return ≤ 3 years | 7% / yr | RD / short-duration debt yields ~6–8% |
| Return 3–5 years | 9% / yr | hybrid / balanced funds |
| Return > 5 years | 11% / yr | long-run diversified equity ~10–12% |
| Step-up | 10% / yr | common default |
| Bucket of "Other" | Wants | conservative (counts against discretionary) |
| Bucket of "Education", "EMI" | Needs | — |

The per-category ranges are not from one authority. They are starting points chosen to sit
inside the 50/30 split. Every figure is illustrative and is not financial advice. The UI
says so on the Improve and Goals tabs.

## Optional LLM explanations

These are off by default (`BUDGET_EXPLAINER_PROVIDER=template`). To enable them:

```bash
pip install anthropic
# backend/.env
BUDGET_EXPLAINER_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
BUDGET_EXPLAINER_MODEL=claude-opus-5-5   # any Claude model id
```

When enabled, an "Explain in plain words" button appears. The server recomputes everything
and sends only the engine's own sentences to the model. If the reply contains any number
that wasn't in those sentences, the template text is returned instead. The same happens if
the model refuses, errors, or the SDK is missing.

## Running and testing

```bash
docker compose up -d                       # MongoDB
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload   # migration runs on startup
cd frontend && npm run dev                 # open /budget

cd backend && ../.venv/Scripts/python -m pytest -q    # 218 tests
cd frontend && npm test && npx tsc -b && npm run lint
```

Phase 8 tests: `backend/tests/test_goal_planner.py`, `test_budget_rules.py`,
`test_category_migration.py`, `test_budget_api.py`, the updated `test_expenses.py`, and
`frontend/src/lib/budget.test.ts`.
