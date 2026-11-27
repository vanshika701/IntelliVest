# Phase 8 Checklist: Smart Budgeting & Goal Planner

## What Phase 8 is

IntelliVest is an investment advisor combined with a budgeting and watchlist platform. Phase 8
is the part that looks at a user's own money: what they earn, what they spend, where they
overspend, and how much they can set aside each month for a goal such as a car.

The original plan called this phase "Financial Health Assessment": compute ratios such as savings
rate, debt-to-income and emergency-fund coverage, and combine them into one health score. It was
redefined as a smart budgeter and goal planner. The ratios are built; the combined score is not
(item 9; built 2026-11-25).

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

As of 2026-11-26. Only item 5 is open: it needs a free API key and one real call.

## Fix first (affects whether the numbers and page can be trusted)

- [x] **1. "Actual" runs low early in the month.** A partial current month counts as a full one.
  - Where: `actual_monthly_spend` in `backend/app/services/budget_service.py`
  - Done when: a partial month no longer lowers the average, with a test.
- [x] **2. Missing actual data reads as ₹0.** Once any expense is logged, categories with nothing
      logged count as zero, which can inflate the surplus.
  - Where: `_analysis` in `backend/app/services/budget_service.py`
  - Done when: unlogged categories are handled explicitly (e.g. fall back to the estimate and
    say so in the UI), with a test.
- [x] **3. An expense's category can't be changed.** Records in "Other" can only be deleted and
      re-added.
  - Where: `backend/app/api/v1/routes/expenses.py`, `frontend/src/pages/BudgetingPage.tsx`
  - Done when: there is an update endpoint and an edit control, with a test.
- [x] **4. The Budgeting page has no error state.** If the API fails it stays on "Loading metrics...".
  - Where: `loadData` in `frontend/src/pages/BudgetingPage.tsx`
  - Done when: a failure shows a message and a retry button.
- [ ] **5. LLM wording with a free API.** Claude has no lasting free tier, so this now uses Groq
      (default) or Gemini over HTTP, with no extra package. Both endpoints were reached and the
      fallback to template text works; no valid key has been used yet.
  - Where: `backend/app/core/config.py`, `backend/app/services/budget_explainer.py`
  - Done when: `GROQ_API_KEY` is set in `backend/.env` and one real reply has been checked.

## Fix next

- [x] **6. The LLM number check is limited.** It only checks that each number appears somewhere in
      the source, so swapped figures or numbers written as words would pass.
  - Where: `numbers_are_preserved` in `backend/app/services/budget_explainer.py`
- [x] **7. Goal affordability has gaps.** Only the flat SIP is checked, each goal is checked as if
      it were the only one, and the step-up plan is never offered as a way to fit.
  - Where: `_affordability` in `backend/app/services/goal_planner.py`
- [x] **8. Saved goals can't be edited,** only deleted.
  - Where: `backend/app/api/v1/routes/budget.py`, `frontend/src/components/budget/GoalsPanel.tsx`

## Not built

- [x] **9. Combined financial health score** on the dashboard (the plan's original Phase 8 goal).
- [x] **10. Tests for the new React components.** Only their helper functions are tested.

## Housekeeping

- [x] **11. Verify sources.** Pages opened 2026-11-25; results, including what could not be
      verified, are in `docs/PHASE_8_BUDGETING.md`. Return defaults lowered to 6% / 8% / 11%.
- [x] **12. Commit the Phase 8 work.** On branch `phase-8-and-6`.
- [x] **13. Restart the backend on port 8000.** Done 2026-11-26.

---

# Phase 10 Checklist: Blockchain (Mode 2 AI + user-owned vault)

Written 2026-11-25. B1-B10 (setup, contracts, settings, backend signing and chain client) are
built and tested. Paused 2026-11-25 for Phase 4; **resumed 2026-11-27** at B10 with the real stock
model instead of a mock. This is the detailed spec;
`PROJECT_PLAN.md` Phase 10 is the summary. If they disagree, fix both.

## What we are building and why

The AI works off-chain and proposes a trade. A smart contract checks it against terms the user
signed, and only then swaps test tokens held in a vault **the user owns**. This is **Mode 2
(schedule AI collaboration)** of the paper "Intelligent Contracts: Making Smart Contracts Smart
for Blockchain Intelligence", applied to investing.

**Justification:** IntelliVest can propose trades but cannot withdraw the user's assets or exceed
the mandate, even if its server is hacked. A database can store the limit but cannot hold the
asset outside its operator's control. The immutable trade history is a second benefit.

**Claims we must not make:** a signature shows who submitted a result, not that the model really
ran or is right. A trade inside the limits can still lose money. Test prices come from us.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Platform | **Ethereum-compatible (EVM)**, Solidity | Wallets, tokens, atomic swaps and user-owned vaults are standard here |
| Hyperledger Fabric | No | Built for a known group of organizations; we have one operator, so it would remove the user-control argument |
| Other chains (e.g. Solana) | No | Possible, but new tooling with no benefit for this prototype |
| Network | Local Hardhat first; Ethereum Sepolia for the final demo | Free and repeatable; Polygon Amoy is a fallback |
| Libraries | Hardhat, OpenZeppelin, `web3.py`, one frontend wallet library | Pin versions when installing |
| Assets | Test tokens only (`tINR`, `tEquityFund`, `tDebtFund`, `tGoldFund`) | No real money |
| SGX / TEE | Not used | Not needed for smart contracts |
| Default state | `BLOCKCHAIN_ENABLED=false` | The current app must work unchanged |

## Where blockchain goes

| Part of the app | Blockchain use | Can do now? |
|---|---|---|
| AI advisor (Phase 9) | Signed proposal; the contract accepts, waits for the user, or rejects | Interface and mock only |
| Sentiment (Phase 5) | Evidence step, only for an AI trade task | **Yes**, FinBERT exists |
| Stock prediction (Phase 4) | Evidence step, only for an AI trade task | **Yes**, reads stored predictions |
| Portfolio / risk profile (Phase 7) | Suggests mandate limits; the user signs the final ones | Manual entry only |
| Goal planner (Phase 8) | Suggests amount and end date for the mandate | Yes |
| Invest panel / SIP | Optional vault execution. A SIP is rule-based: a separate path with no AI evidence | Yes, test tokens |
| Budget, expenses, income, login, watchlist, search, charts, summaries, sector view | **None** | n/a |

Opening a page never creates a transaction.

## Flow

1. The user connects a wallet, proves ownership by signing a one-time message, creates a vault,
   deposits `tINR` and signs a mandate.
2. The backend opens a task in `AITaskManager` for one vault and one fund.
3. Workers submit signed evidence: sentiment, stock prediction, then the advisor proposal.
4. The contracts check signer, model version, deadline, required steps and mandate.
5. Result: **execute**, **wait for the user's signature**, or **reject with a reason**. Rejections
   must be stored as an outcome with an event; a reverted transaction leaves no event.
6. The backend follows events and updates MongoDB. The UI shows pending / executed / rejected.

## What gets recorded

**Every evidence step, on-chain:** task ID, step type, status (`OK` or `NO_DATA`), model ID hash,
version hash, input hash, output hash, submitter, time.

| Step | Extra on-chain values | Off-chain (MongoDB), covered by the hashes |
|---|---|---|
| Sentiment | score (-10000..10000), article count | Article IDs, URLs, text hashes, probabilities, engine, window |
| Stock prediction | direction, probability (0..10000), horizon, as-of date | Feature values, price window, model artifact hash |
| Advisor proposal | fund, side, amount, minimum received, confidence, nonce, deadline, explanation hash | Full explanation, contributions per module |
| Trade | amounts in and out, price and its time, result or rejection reason | Transaction hash, link to the `investments` record |

Rules: canonical JSON, then keccak256. Add a random salt to anything derived from private data.
Never put names, emails, income, expenses, goals or article text on-chain. Use integers, never
floats. On a public chain, vault balances and mandate limits **are visible**; the UI must say so.

## Proposal interface (freeze this first)

```
Proposal { taskId, vault, fund, side, amount, minimumReceived, confidence,
           modelId, modelVersion, inputHash, evidenceHash, explanationHash, nonce, deadline }
```

Signed with EIP-712. `confidence` is 0..10000. `evidenceHash` covers the task's submitted steps,
so evidence can't be swapped later. Any advisor (LLM, trained model, mock) returns this shape.

## Contracts

| Contract | Job |
|---|---|
| `ModelRegistry` | Model IDs, versions, artifact/config hash, allowed signer; can revoke |
| `MandateManager` | The user's signed terms and the model versions they accept |
| `AITaskManager` | Tasks, required steps, evidence, deadlines, proposals |
| `InvestmentVault` | One per user: deposit, execute, withdraw, revoke, pause |
| `MockFundMarket` + test tokens + test price feed | Atomic swaps at test prices |

### Mandate terms

- [x] Allowed funds; per-trade, daily and monthly caps; maximum equity %; maximum slippage
- [x] Start and end date; required evidence steps; accepted model versions
- [x] Confidence threshold and amount above which the user must sign
- [x] Maximum trades per day; loss limit that pauses the AI until the owner resumes

### Rules that must hold

- [x] Only the owner can withdraw, and only to the owner. Works when the AI is paused or revoked,
      a mandate has expired, prices are stale, or the backend is down.
- [x] IntelliVest has no admin function that moves vault assets or changes a mandate.
- [x] Confidence can only make a check stricter. It never bypasses a hard limit.
- [x] A new model version isn't usable by a vault until its owner accepts it.
- [x] Replayed, expired, duplicate or wrong-chain proposals are rejected.
- [x] Stale prices stop AI trades. Minimum received is always enforced.
- [x] A sentiment `NO_DATA` (too few articles) or the `lexicon` fallback is never treated as
      FinBERT. It goes to the user's signature, or is rejected, as the mandate says.
- [x] Vaults are not upgradeable. Use reentrancy protection and safe token transfers.

## Can't be done yet

| Blocked item | Waiting for |
|---|---|
| Automatic limits from a risk profile | Phase 7 (not built) |
| Real advisor proposals | Phase 9; LLM or trained model undecided |
| Final results with real models | Phases 4, 7 and 9 |
| Sepolia deployment | A team test wallet, RPC URL and test ETH. **Never paste a private key into chat** |
| Real money, stocks or mutual funds | Out of scope: regulation, KYC, tokenized assets, audit |
| Proof that a model really ran | Out of scope: TEE or zkML |

## Build order

### A. Set up
- [x] **B1.** Use Node 24 as pinned in `.nvmrc`. `blockchain/` carries its own Node 24.22.3 (dev
      dependency); the system Node is still 23.5.0.
- [x] **B2.** Create the Hardhat project in `blockchain/` and ignore its build output.
- [x] **B3.** Freeze the `Proposal` and evidence formats in `docs/PHASE_10_BLOCKCHAIN.md`, with
      shared test vectors so Solidity and Python produce the same hashes.

### B. Contracts
- [x] **B4.** Test tokens, price feed and `MockFundMarket`.
- [x] **B5.** `ModelRegistry` and `MandateManager`.
- [x] **B6.** `InvestmentVault`, with withdrawal tests written first.
- [x] **B7.** `AITaskManager`, including approve-by-user and reject paths.
- [x] **B8.** Tests for every rule above, plus a local deploy script. Done when all pass.

### C. Backend
- [x] **B9.** Settings in `backend/app/core/config.py` and `.env.example`; keys only in `.env`.
      Use a different key per role (sentiment, stock, advisor, relayer, SIP runner).
- [x] **B10.** `backend/app/services/blockchain/`: client, hashing, signing, advisor interface,
      mock advisor, and stock evidence from the **real** Phase 4 predictions (no mock predictor).
      `web3.py` imported only here. A mock-advisor trade with stock evidence runs end to end on
      Hardhat (`tests/test_blockchain_chain.py`).
- [x] **B11.** Wallet linking (one-time nonce), repositories, indexes and `/api/v1/blockchain/...`.
      Follow routes -> services -> data. Routes 404 while the flag is off (except `/status`);
      creating a task only queues it, one unfinished task per user and fund.
- [x] **B12.** Background worker and event reader: retry, timeout, no double submission, resume
      after restart, handle reorganized blocks. Requests never wait for the chain. Transactions are
      signed and saved before sending; the event reader alone records outcomes. Tested on Hardhat
      with crashes before and after sending and a simulated reorganization.
- [x] **B13.** Sentiment adapter. Add evidence details without changing existing responses.
      Stored articles hold their model name; keep the exact model revision too. Fixed 7-day
      window; under 3 articles is `NO_DATA`; any non-FinBERT score (e.g. `lexicon`) is `FALLBACK`.

### D. Frontend
- [x] **B14.** Connect wallet, vault, deposit/withdraw and mandate form (goal values prefilled).
      Withdrawal goes wallet-to-contract directly, with no backend call. `/vault` page, ethers 6.17.0
      (loaded only on that page).
- [x] **B15.** Pending trades with approve/reject, evidence view, "Revoke AI", privacy notice.
      Approve, decline and revoke go from the wallet to the contracts; the mock advisor is labelled.
- [x] **B16.** Vault SIP, triggered by any permitted runner; the vault enforces date and amount.
      The backend's SIP runner uses its own key and only calls `runSip()`.
- [x] **B17.** With the flag off, the existing invest flow and tests are unchanged. No sidebar link,
      routes 404, web3 not imported; all 563 backend and 111 frontend tests pass.

### E. Connect later
- [x] **B18.** Phase 4: evidence uses the real model, version and artifact hash (B10); the worker
      stores each evidence record in MongoDB (B12); `scripts/register_models.py` registers a
      retrained version (owners must still accept it).
- [x] **B19.** Phase 7: prefill mandate limits from the risk profile. Equity limit from the latest
      portfolio plan, loss limit by risk profile; only suggestions, the owner signs the final terms.
- [ ] **B20.** Phase 9: replace the mock advisor; include contributions per module.
      `Phase9Advisor` (`backend/app/services/advisor/chain_advisor.py`) implements `Advisor` and is
      tested with `build_proposal`; wiring it into the worker waits for B11-B12.

### F. Evaluate
- [x] **B21.** Attack tests: stolen advisor key, hacked backend, replay, over limit, bad fund, old
      or changed model, stale price, price manipulation, missing evidence, backend switched off.
      `blockchain/test/attacks.test.ts`, one test each; results in `blockchain/reports/attacks.json`.
- [x] **B22.** Compare no limits, backend-only limits and vault limits. Report blocked attacks,
      maximum loss, valid trades wrongly blocked, gas and latency. Label mock results as mock.
      `docs/PHASE_10_EVALUATION.md`: vault blocks or bounds 9 of 10 attacks (backend-only 7, none 0),
      0 of 40 valid trades blocked, 886,681 gas per automatic trade.
- [ ] **B23.** Deploy to Sepolia and verify the source. Prepared: `npm run deploy:sepolia` and the steps
      in `docs/PHASE_10_BLOCKCHAIN.md`. Blocked on a funded test wallet and an RPC URL.

**Infrastructure done (without Phases 4, 7, 9):** B1-B17 pass, B21 passes locally, and a
mock-advisor trade with real FinBERT evidence runs end to end.
**Phase 10 complete:** B18-B23 are also done.
