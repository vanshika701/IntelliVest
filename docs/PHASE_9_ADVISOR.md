# Phase 9: AI Investment Advisor (orchestration layer)

Planned 2026-11-26 on branch `phase-9-advisor` (built on `phase-7-portfolio`).

## What Phase 9 is

One page that tells a user what to do next with their money, in priority
order, and shows which part of IntelliVest each piece of advice came from.
It reads what the other modules already produce; it trains no model and
computes no new market data.

Example output:

1. **Build your emergency fund first** — ₹45,000 short of 3 months'
   expenses. *(Budget health)*
2. **Invest ₹10,000 a month for "House"** — 45% stocks, 45% debt, 10% gold.
   *(Risk profile, Portfolio plan, Goals)*
3. **Rebalance: stocks are 58% of your portfolio, the plan says 45%.**
   *(Holdings, Portfolio plan)*
4. **Review Wipro: negative news this week and the IT sector is down 6%
   this month.** Not a sell signal. *(Sentiment, Sectors)*

Educational illustration only, not investment advice.

## Decisions

- **The advisor is rules, not an LLM or a trained model.** No dataset maps
  "this user's situation → right advice", so a trained advisor can't be
  trained or evaluated honestly. An LLM deciding would be hard to test, could
  invent numbers, and can't produce the reproducible, signed proposals
  Phase 10 needs. Rules decide; every number comes from a module.
- **An LLM may only reword,** using Phase 8's explainer pattern: optional
  (Groq / Gemini free tier), rejected if it adds or changes any number,
  template text otherwise.
- **Priorities follow the standard financial-planning order:** safety net
  and debt before goals, goals before investing, investing before
  fine-tuning (rebalancing, single holdings).
- **Every module sits behind the same interface** and returns a status:
  `ok`, `stale`, `unavailable` or `not_built`. A slow or failing module
  is skipped with a timeout and named in the response; the advice is
  marked partial, never an error page.
- **Every action records its contributors:** which modules, which facts,
  which versions and data dates. This is the evidence Phase 10 hashes and
  signs (checklist B20).
- **Advice is stored** per user with its inputs, like Phase 7
  recommendations, so it can be explained later.

## Modules it draws on

| Module | Phase | Gives the advisor | Status today |
|---|---|---|---|
| Budget health score and rules | 8 | Emergency-fund gap, EMI load, monthly surplus | Built |
| Goals and SIP plans | 8 | Which goals are on track, affordable | Built |
| Risk profile, portfolio plan | 7 | Target split and holdings | Built (branch) |
| Current holdings | 2 | What the user owns, drift from the plan | Built |
| Sector intelligence | 6 | Sector trend and news for held stocks | Built |
| News sentiment | 5 | Negative news on held stocks | Built |
| Stock predictions | 4 | Return ranges (10th/50th/90th percentile) per stock and horizon | Built. Direction doesn't beat "always up", so ranges are used for risk context only, never to buy or sell |
| Expense categorizer | 3 | — | Retired from the app in Phase 8 |

The exit criterion asks for advice that "draws on every module built so
far". Phase 4's own backtest found its up/down calls no better than
"always up" and its ranking weak, so the advisor uses only its ranges (for
example, "a 10% chance this goal's stock part is down 18% or more in a
year") and says why it doesn't use direction.

## Build steps

- [x] **1. Module interface.** One `ModuleResult` shape (module, status,
      as_of, version, facts, data) and an adapter per module above, each
      reading through that module's existing service. Timeouts per module.
- [x] **2. Rules engine.** Pure functions that turn module results into
      prioritised actions: emergency fund, high EMIs, unaffordable goals,
      invest per plan, rebalance when a class drifts more than 5 points,
      review a holding with negative news and a falling sector. Each
      action lists its facts and contributors. Thresholds in one config
      file, sourced or marked as ours.
- [x] **3. Advice service, storage and API.** Gather modules concurrently,
      run the rules, store in `advice`.
      `POST /api/v1/advisor/advice`, `GET /api/v1/advisor/advice/latest`.
- [x] **4. Optional LLM summary.** A short plain-language summary of the
      actions, reusing the Phase 8 explainer's providers and number check.
- [ ] **5. Phase 10 bridge.** Turn an "invest" action into a
      `Proposal`-shaped draft (fund, side, amount, confidence 0-10000,
      model id and version, input / evidence / explanation hashes) using
      `blockchain/hashing.py`. Not sent on chain until B10-B12 exist.
- [ ] **6. Frontend.** Enable the disabled "AI Advisor" sidebar item
      (`/ai`): action cards with "why" and module chips, a module status
      panel, links to the pages each action came from.
- [ ] **7. Evaluation.** 15-20 hand-written user situations (no emergency
      fund, heavy EMIs, drifted portfolio, nothing invested, all modules
      down...) with the expected top actions, checked automatically. Plus:
      every action traceable to module facts; LLM wording fallback rate;
      advice still produced with each module failing in turn.
- [ ] **8. Documentation.** Method, rules and sources, limits, results in
      `ml/log.md`.

**Done when:** a user gets one stored, prioritised, explained piece of
advice that names every module it used (and the ones it couldn't), the
scenario tests pass, and it degrades cleanly when modules fail.

## Hardware

CPU only. The optional LLM summary calls a hosted API.
