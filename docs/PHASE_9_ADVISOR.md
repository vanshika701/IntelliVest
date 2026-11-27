# Phase 9: AI Investment Advisor (orchestration layer)

Built 2026-11-27 on branch `phase-9-advisor`.

One page, **AI Advisor** (`/ai`), that tells a user what to do next with
their money, in priority order, and shows which part of IntelliVest each
piece of advice came from. It reads what the other modules already
produce; it trains no model and computes no new market data.

Educational guidance only, not investment advice: IntelliVest is not a
SEBI-registered investment adviser. Every piece of advice says so.

- [x] 1. Module interface: every module reports in one shape, failures become a status
- [x] 2. Rules engine: prioritised, traceable actions
- [x] 3. Advice service, storage (`advice`) and API
- [x] 4. Optional LLM summary, rejected if it changes any number
- [x] 5. Phase 10: `Phase9Advisor` implements Phase 10's `Advisor` interface (B20)
- [x] 6. Frontend: AI Advisor page, enabled in the sidebar
- [x] 7. Evaluation: 18 scenarios, module knock-outs, ₹ traceability
- [x] 8. Documentation

## Decisions

- **Rules decide; an LLM may only reword.** No dataset maps "this user's
  situation → right advice", so a trained advisor couldn't be trained or
  evaluated honestly. An LLM deciding would be hard to test, could invent
  numbers, and can't give the reproducible decisions Phase 10 signs.
- **Priority follows the financial-planning sequence:** stop overspending,
  build a safety net, deal with heavy debt, fund goals, invest, then
  fine-tune (rebalance, concentration, single holdings).
- **Every module behind one interface,** each with its own timeout. A slow
  or failing module is reported and skipped; the advice is marked partial.
- **Every action is traceable:** its facts, contributing modules, their
  versions and data dates are stored with the advice.
- **Phase 4 predictions are used for ranges only.** Its own backtest found
  up/down calls no better than "always up" and ranking weak, so direction
  and rank never drive a buy or sell, here or in vault trades.

## How it works

```
 round 1 (concurrent)                         round 2 (concurrent, for held + planned stocks)
 budget · goals · risk profile ·   ──tickers──>  sectors · sentiment · predictions
 portfolio plan · holdings
                 └──────────────── 8 ModuleResults ───────────────┘
                                         │
              rules ──> actions + setup steps ──> summary (template, or LLM if enabled)
                                         │
                                 stored in `advice` ──> Phase9Advisor (Phase 10 vault trades)
```

**Module statuses:** `ok`, `stale` (used, flagged), `not_set_up` (the user
hasn't entered it), `unavailable` (failed or timed out), `not_built`.

| Module | Phase | Gives the advisor |
|---|---|---|
| Budget health | 8 | Surplus, emergency-fund gap, EMI load, overspent categories |
| Goals | 8 | Affordability of each goal, first option if it doesn't fit |
| Risk profile | 7 | Profile and scores |
| Portfolio plan | 7 | Target split and holdings; stale after 30 days |
| Holdings | 2 | What the user owns, by asset class; unclassifiable funds left out of drift checks |
| Sectors | 6 | 1-month trend and news for the sectors of held and planned stocks |
| News sentiment | 5 | Recent FinBERT sentiment per held and planned stock |
| Stock return ranges | 4 | 1-year 10th / 50th / 90th percentile returns |

### Rules

| Priority | Action | Trigger | Source of the threshold |
|---|---|---|---|
| 10 | Spending exceeds income | Monthly surplus below 0 | — |
| 20 | Build your emergency fund | Under 3 months of essential spending | Phase 8 config (3-6 months) |
| 30 / 35 | Loan EMIs | Above 36% critical / above 30% high | Phase 8 config |
| 40 | Goal out of reach | Goal planner: not affordable | Phase 8 goal planner |
| 50 | Invest per your plan | Risk profile and plan exist | — |
| 60 | Rebalance | An asset class 5+ points off the plan | Vanguard rebalancing research (2010) |
| 65 | Concentration | Stocks above 15% of all holdings (one card for all) | Same as the Phase 7 per-stock cap (ours) |
| 70 | Review a holding | Negative news **and** its sector down 5%+ in a month | Ours; never a sell signal |
| 80 | Holdings outside the plan | Owned but not in the plan | — |

When a high-severity safety action exists, the invest action is
downgraded and says to do it afterwards; without a budget, it says the
safety checks were skipped. Setup steps ("answer the risk questionnaire")
are listed separately: they unlock advice rather than being advice.

### LLM summary (optional)

Off by default. With `BUDGET_EXPLAINER_PROVIDER=groq` or `gemini` and a key,
the top 3 actions are reworded through Phase 8's explainer with
advisor-specific instructions. The reply is rejected (template used) if it
adds, changes or reorders a number, or the call fails.

### Phase 10 (checklist B20)

`app/services/advisor/chain_advisor.py` implements Phase 10's `Advisor`
interface (`app/services/blockchain/advisor.py`), replacing the mock.
Phase 10 asks about one vault and one fund; `Phase9Advisor`, built from the
owner's stored advice, answers:

- no trade while the advice has a high-severity safety action, or without
  a usable plan;
- otherwise buy or sell this fund towards the plan's share for its kind
  (stocks for an equity fund, debt plus gold otherwise), only outside the
  same 5-point band as the rebalance advice;
- sentiment and stock-prediction evidence recorded in the contributions,
  marked `used_to_decide: false`;
- confidence in the inputs: 10000 with a fresh plan and profile, 5000 if
  either is stale.

Phase 10's `build_proposal` then adds the hashes, minimum received, nonce
and deadline. Using it for live vault tasks needs B11 (vault → user) and
B12 (the worker); until then the mock stays wired in.

## API

| Method | Path | |
|---|---|---|
| POST | `/api/v1/advisor/advice` | Build, store and return fresh advice. Always 201; failed modules are listed. 10 per user per minute |
| GET | `/api/v1/advisor/advice/latest` | The user's latest advice, 404 if none |

Collection: `advice` (by user, newest first), with every module result,
the actions, setup steps, summary and versions.

## Evaluation

`ml/evaluate_advisor.py`, with the same checks in
`backend/tests/test_advisor_eval.py`; results in
`ml/models/advisor_eval/metrics.json` and `ml/log.md`.

| Check | Result |
|---|---|
| 18 hand-written situations: right first action, required and forbidden actions, setup steps | 18/18 |
| Rules triggered across the scenarios | 10/10 |
| Every usable module knocked out in turn (109 runs) | 0 problems |
| ₹ figures shown, traced to their source | 50/50 |

The checks themselves were tested: wrong priority order, an invented ₹
figure and citing a missing module each make them fail.

## Limits

- Scenarios were written by the developers, not reviewed by a certified
  financial planner, and they test decisions, not whether real users find
  the advice useful. That needs a user study.
- Rules are coarse by design: one threshold per situation, no tax, no
  income growth, no inflation beyond what Phase 8 assumes.
- The LLM wording wasn't measured live (no key configured).
- Holdings in funds the advisor can't classify are left out of rebalancing
  rather than guessed.
- Stocks outside the 20 tracked get no sector, sentiment or range.
- Vault decisions see only the vault's cash and the fund asked about.

## Files

Backend: `app/core/advisor_config.py`; `app/services/advisor/`
(`modules.py`, `adapters.py`, `rules.py`, `summary.py`, `service.py`,
`chain_advisor.py`); `app/data/advice_repository.py`;
`app/api/v1/routes/advisor.py`. Frontend: `src/pages/AdvisorPage.tsx`,
`src/components/advisor/AdviceViews.tsx`, `src/api/advisor.ts`. Tests:
`backend/tests/test_advisor_*.py`, `test_chain_advisor.py`,
`advisor_scenarios.py`; `frontend/src/pages/AdvisorPage.test.tsx`.

## Open items

- [ ] Agree the disclaimer wording and placement with the team.
- [ ] A short study with 5-10 real users on whether the advice is clear and useful.
- [ ] Phase 10 B11-B12: map vaults to users and use `Phase9Advisor` in the worker.
