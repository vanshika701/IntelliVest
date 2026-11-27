# Phase 10 evaluation: attacks and design comparison (B21, B22)

Measured 2026-11-27 on Hardhat's local chain, with the **mock advisor** (fixed rules). These results
are about whether the contracts hold the user's limits, not about advice quality. Test tokens only.

Reproduce:

```bash
cd blockchain
npm test          # contract tests, including test/attacks.test.ts; writes reports/attacks.json
npm run compare   # gas, latency, valid trades; writes reports/comparison.json
```

Vault used in the tests: 100,000 tINR; mandate of 10,000 per trade, 20,000 a day, 50,000 per 30
days, owner signs above 8,000, at most 40% equity, 1% slippage, 10% loss limit, 5 AI trades a day.

## Designs compared

| Design | Who holds the tokens | Who checks the limits |
|---|---|---|
| **No limits** | IntelliVest's own wallet | Nobody: the AI's result is traded as is |
| **Backend-only limits** | IntelliVest's own wallet | The backend, with the same rules as the mandate |
| **Vault limits** (built) | The user's vault contract | The contracts, against terms the owner signed |

Only the vault design is deployed and measured. The other two columns are **modelled** from the same
attacks: what each design could stop, given who holds the keys and the tokens.

## Attacks (B21)

Loss is the most the attacker can cost the owner in tINR. "Measured" values come from the test run;
"bound" values follow from the mandate.

| Attack | No limits | Backend-only limits | Vault limits |
|---|---|---|---|
| Stolen advisor key | Not blocked; whole balance at risk | Bounded while the backend is intact | **Bounded**: 159 measured (bound 200 a day: 1% of the daily cap) |
| Hacked backend (all its keys) | Not blocked; 100,000 (can withdraw) | Not blocked; 100,000 (can withdraw) | **Bounded**: 200 a day; can't withdraw, change terms or accept models |
| Replay | Not blocked | Blocked if it tracks nonces | **Blocked** (task closed / nonce used) |
| Over the limits | Not blocked | Blocked | **Blocked** (`OVER_TRADE_CAP`; above 8,000 waits for the owner) |
| Fund not allowed | Not blocked | Blocked | **Blocked** (`FUND_NOT_ALLOWED`) |
| Old or changed model | Not blocked | Blocked, but the operator can swap a model silently | **Blocked** (`MODEL_INACTIVE`, `MODEL_NOT_ACCEPTED`; versions can't be re-registered) |
| Stale price | Not blocked | Blocked | **Blocked** (`STALE_PRICE`) |
| Price manipulation (feed admin) | Not blocked | Not blocked | **Not blocked**: moves are capped at 20% an hour; 833 bound on a 5,000 trade |
| Missing evidence | Not blocked | Blocked | **Blocked** (`MISSING_EVIDENCE`) |
| Backend switched off | Tokens unreachable | Tokens unreachable | **Owner keeps control**: withdraws, trades and runs the SIP |
| **Blocked or bounded** | 0 of 10 | 7 of 10 (6 blocked, 1 bounded) | 9 of 10 (7 blocked, 2 bounded) |

What the vault adds over backend-only limits is the two rows where the backend itself is the
attacker or is gone: a hacked backend can't take the tokens, and a stopped backend can't lock them.

## Valid trades, gas and latency (B22)

| Measure | Vault limits |
|---|---|
| Valid trades wrongly blocked | **0 of 40** (amounts 100-7,900 tINR, confidence 60-99%, equity and debt funds) |
| Gas: open task | 77,810 |
| Gas: sentiment evidence | 117,462 |
| Gas: stock evidence | 100,111 |
| Gas: proposal that executes | 591,298 |
| Gas per automatic trade (4 transactions) | **886,681** |
| Extra gas when the owner approves | 303,158 |
| Time per trade, local chain | 67 ms (blocks are mined instantly) |
| Time per trade, Sepolia (estimate) | About 50 s for 4 transactions at ~12 s a block, plus up to 15 s for the worker cycle and the confirmations the event reader waits for |

The relayer pays all gas except the owner's own actions (vault, mandate, approve, withdraw). Gas is
measured; cost in ETH depends on the network's gas price at the time.

## Limits of these results

- The advisor is a mock. Real advice (Phase 9, B20) will change what trades are proposed, not what
  the contracts allow.
- We post the test prices. A wrong price within the 20%-an-hour cap is believed; that is the
  largest remaining risk, and it is the same for every design.
- The modelled columns assume the other designs keep the tokens in IntelliVest's wallet, which is
  how they would have to work without a user-owned vault.
- Hardhat timing says nothing about a public network; the Sepolia time is an estimate until B23.
