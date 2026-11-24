# Phase 8 Checklist: Smart Budgeting & Goal Planner

## What Phase 8 is

IntelliVest is an investment advisor combined with a budgeting and watchlist platform. Phase 8
is the part that looks at a user's own money: what they earn, what they spend, where they
overspend, and how much they can set aside each month for a goal such as a car.

The original plan called this phase "Financial Health Assessment": compute ratios such as savings
rate, debt-to-income and emergency-fund coverage, and combine them into one health score. It was
redefined as a smart budgeter and goal planner. The ratios are built; the combined score is not
(item 9).

**The main rule:** every number, flag and recommendation comes from fixed formulas and rules, not
from an AI model. Users need to be able to see why they got a piece of advice, the same inputs
should always give the same answer, and the results can be tested against known cases.

Phase 9 (the AI Investment Advisor) is planned to draw on this phase's output, so wrong numbers
here would carry into its advice.

## Components and why we want them

| Component | What it does | Why we want it |
|---|---|---|
| Fixed category list | 13 categories, each tagged Needs, Wants or Savings | Free text split the same spending across labels like "Food" and "food". Benchmarks need consistent categories |
| Manual category choice | The user picks the category; replaces the Phase 3 auto-categorizer | A wrong guess would distort every calculation that follows. The user knows what the expense was |
| Category migration | Maps old labels to the new list and keeps the original label | Existing records keep working after the change |
| Budget setup | Asks for income, emergency savings and an estimate per category | Benchmarks are a share of income, and estimates give a starting point before any expenses are logged |
| Pie chart and comparison table | Shows estimated and actual spending per category | Shows the gap between what users think they spend and what they spend |
| Rules engine | Checks 50/30/20, category ranges, debt and emergency fund | Turns spending data into a clear result: how much over, in rupees, and a target |
| Goal planner | Works out flat and step-up SIPs for a target and time frame | Links budgeting to investing. Step-up suits users whose income should grow |
| Affordability check | Compares the SIP with the monthly surplus and suggests options | A plan the user can't pay for isn't useful. Links goals back to overspending |
| Optional LLM wording | Rewrites the results in friendlier language; off by default | Easier to read, while the app still works fully without it |
| One config file | Holds categories, thresholds and return assumptions | These are assumptions, so they should be easy to find, question and change |

How each one works, and the assumptions behind it:
[docs/PHASE_8_BUDGETING.md](docs/PHASE_8_BUDGETING.md).

# Open items

As of 2026-11-24.

## Fix first (affects whether the numbers and page can be trusted)

- [ ] **1. "Actual" runs low early in the month.** A partial current month counts as a full one.
  - Where: `actual_monthly_spend` in `backend/app/services/budget_service.py`
  - Done when: a partial month no longer lowers the average, with a test.
- [ ] **2. Missing actual data reads as ₹0.** Once any expense is logged, categories with nothing
      logged count as zero, which can inflate the surplus.
  - Where: `_analysis` in `backend/app/services/budget_service.py`
  - Done when: unlogged categories are handled explicitly (e.g. fall back to the estimate and
    say so in the UI), with a test.
- [ ] **3. An expense's category can't be changed.** Records in "Other" can only be deleted and
      re-added.
  - Where: `backend/app/api/v1/routes/expenses.py`, `frontend/src/pages/BudgetingPage.tsx`
  - Done when: there is an update endpoint and an edit control, with a test.
- [ ] **4. The Budgeting page has no error state.** If the API fails it stays on "Loading metrics...".
  - Where: `loadData` in `frontend/src/pages/BudgetingPage.tsx`
  - Done when: a failure shows a message and a retry button.
- [ ] **5. The LLM API key isn't picked up.** `ANTHROPIC_API_KEY` in `backend/.env` never reaches
      the SDK, so the app always falls back to template text. `anthropic` is also not installed.
  - Where: `backend/app/core/config.py`, `backend/app/services/budget_explainer.py`
  - Done when: the key is a setting passed to the client, and one real API call has been checked.

## Fix next

- [ ] **6. The LLM number check is limited.** It only checks that each number appears somewhere in
      the source, so swapped figures or numbers written as words would pass.
  - Where: `numbers_are_preserved` in `backend/app/services/budget_explainer.py`
- [ ] **7. Goal affordability has gaps.** Only the flat SIP is checked, each goal is checked as if
      it were the only one, and the step-up plan is never offered as a way to fit.
  - Where: `_affordability` in `backend/app/services/goal_planner.py`
- [ ] **8. Saved goals can't be edited,** only deleted.
  - Where: `backend/app/api/v1/routes/budget.py`, `frontend/src/components/budget/GoalsPanel.tsx`

## Not built

- [ ] **9. Combined financial health score** on the dashboard (the plan's original Phase 8 goal).
- [ ] **10. Tests for the new React components.** Only their helper functions are tested.

## Housekeeping

- [ ] **11. Verify sources.** Thresholds were checked from search summaries; the pages were not
      opened. Confirm the Warren & Tyagi credit and find a source for the return rates, then
      update `budget_config.py` and `docs/PHASE_8_BUDGETING.md`.
- [ ] **12. Commit the Phase 8 work.** It is only in the working folder.
- [ ] **13. Restart the backend on port 8000.** It still runs the pre-Phase 8 code, so the page on
      port 5173 doesn't load budget data.
