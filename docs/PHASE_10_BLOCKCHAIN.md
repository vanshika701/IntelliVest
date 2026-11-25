# Phase 10: Blockchain

Status 2026-11-25: contracts and signing formats are built (checklist B1-B8). Nothing is connected
to the app yet. Design and tasks: `checklist.md`. **Test tokens only. Not audited.**

## Run it

```bash
cd blockchain
npm install
npm test               # contract tests
npm run node           # local chain (keep open)
npm run deploy:local   # second terminal; writes deployments/local.json
```

If C: is full on Windows, point `npm_config_cache`, `TEMP`, `TMP` and `LOCALAPPDATA` at a folder on
another drive for these commands.

## Contracts

| File | Job |
|---|---|
| `Types.sol` | Shared structs, outcomes and rejection reasons |
| `ModelRegistry.sol` | Model versions and their signers. Admin can add or revoke, never edit |
| `MandateManager.sol` | The owner's terms. No admin |
| `AITaskManager.sol` | Tasks, signed evidence, proposals, approvals. No admin |
| `InvestmentVault.sol` | Holds one user's tokens; enforces every limit. No admin, not upgradeable |
| `VaultFactory.sol` | One vault per wallet |
| `mocks/` | Test tokens, test prices and the test market |

## Formats (frozen)

`Evidence` and `Proposal` are in `Types.sol`, signed with EIP-712 (name `IntelliVest`, version `1`,
verifying contract `AITaskManager`). Python copies are in
`backend/app/services/blockchain/hashing.py`. Both are checked against
`blockchain/test-vectors/signing.json`.

- Tokens have 6 decimals. Percentages and scores are integers out of 10000.
- Sentiment score is -10000..10000. A stock score is the probability of "up", 0..10000; direction
  is up at 5000 or more, so it isn't stored separately.
- Evidence hash: starts at zero; each step makes `keccak256(abi.encode(previous, structHash))`.
- Data hashes: canonical JSON (sorted keys, no spaces, no floats), keccak256. Private data is salted.
- The owner's transaction is their signature on a mandate or an approval.

## Behaviour to know

- A bad signature reverts and leaves the task open. A validly signed proposal that breaks a rule is
  stored as `REJECTED` with a reason.
- Approval replaces only the "ask the user" step; every limit is checked again.
- Daily and monthly caps use fixed UTC days and fixed 30-day periods, so two periods' worth can be
  spent around a boundary. They count buys and sells.
- Owner trades and SIPs don't count toward AI caps. Missed SIP months are skipped.
- The loss baseline resets on the next AI trade after the owner withdraws or resumes the AI.
- AI trades and SIPs stop when a price is over a day old, which includes weekends unless posted.
- Evidence older than 7 days is rejected.

## Trust limits

- We post the test prices. Moves are limited to 20% an hour, but a wrong price is still believed.
- We run every signer, and the registry admin chooses signers. Owners must accept each version.
- A signature doesn't prove that a model ran or is right.
- A stolen advisor key can still make bad trades inside the mandate. Requiring evidence means other
  keys are needed too.
- Balances, mandates and trades are public.
