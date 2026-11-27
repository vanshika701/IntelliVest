# Phase 10: Blockchain

Status 2026-11-27: contracts, signing formats, backend settings, signing, chain client, advisor interface, mock
advisor and stock evidence are built (checklist B1-B10). Nothing is connected to the app's routes yet. Design and tasks: `checklist.md`. **Test tokens only. Not audited.**

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

## Settings

Listed in `backend/.env.example`; keys go only in `backend/.env`. With `BLOCKCHAIN_ENABLED=false`
(the default) nothing here is loaded. When it is on, the app won't start if a key is missing,
invalid or shared between roles, the network isn't an allowed test network, the deployment file
doesn't match it, or Hardhat's public keys are used outside the local chain.

The relayer is a fifth role: it pays gas to submit signed messages, so the signers need no ETH.

## Backend (`backend/app/services/blockchain/`)

| File | Job |
|---|---|
| `config.py` | Checks settings and keys at startup (B9) |
| `formats.py` | Enums and `Evidence` / `Proposal` shapes, same order as `Types.sol` |
| `hashing.py` | Canonical JSON, EIP-712, model IDs, the running evidence hash |
| `signing.py` | Signs evidence or a proposal with one role's key |
| `client.py` | The only `web3` user: contracts, relayer transactions, task and vault reads |
| `advisor.py` | `Advisor` interface: an advisor returns an `AdvisorDecision`; this builds the `Proposal` |
| `mock_advisor.py` | Fixed rules on the evidence. Results made with it are labelled mock |
| `sentiment_evidence.py` | Sentiment evidence from **stored** FinBERT scores: 7-day window, `NO_DATA` under 3 articles, `FALLBACK` for any other engine |
| `stock_evidence.py` | Stock evidence from **stored** Phase 4 predictions; never imports the model |

- **Advisor (Phase 9, B20):** implement `Advisor` (`model_name`, `model_version`, `async decide(request)`).
  Return the side, amount, confidence 0..10000, explanation and contributions per module, or `None`
  for no trade. Hashes, salt, minimum received, nonce and deadline are added here.
- **Stock predictor (Phase 4):** only these stored fields are read: `ticker`, `as_of`,
  `horizon_days`, `chance_beat`, `target`, `model_version`, `artifact_hash` (and `low`/`mid`/`high`
  if present). Since model 2.0.0 the score is the chance of beating the Nifty 50; rows from older
  models (`chance_up`) give `NO_DATA`.
  Renaming them breaks this adapter. A retrained model gives `NO_DATA` until its version is
  registered and each owner accepts it.
- **Sentiment (Phase 5):** newly scored articles also store `sentiment.revision`, the exact Hugging Face
  commit; evidence inputs list the revisions and article URLs and title hashes, never the text.
- The proposal nonce is the task ID, so a task can only ever get one proposal.

### API (`/api/v1/blockchain`, B11)

All routes but `/status` need a login and return 404 while `BLOCKCHAIN_ENABLED=false`.

| Route | Does |
|---|---|
| `GET /status` | On/off, chain, public contract addresses, privacy notice |
| `POST /wallet/challenge` | One-time message to sign (`personal_sign`); expires in 10 minutes, newest only |
| `POST /wallet/verify` | Checks the signature and links the wallet. One wallet per user, one user per wallet |
| `GET` / `DELETE /wallet` | Show or remove the link. Unlinking never touches the vault |
| `POST /tasks` | Queues an AI trade for a fund (202). The worker does the chain work |
| `GET /tasks`, `GET /tasks/{id}` | The user's tasks with evidence and proposal records (no salt) |

Collections: `wallet_links`, `wallet_challenges` (TTL), `chain_tasks`, `chain_events`, `chain_state`.

### Worker and event reader (B12)

Every 15 seconds while the flag is on (`runner.py`): the worker advances due tasks, then the event
reader copies `AITaskManager` events into `chain_events`.

- **States:** `queued` -> `opening` -> `evidence` -> `proposing` -> `submitted`; the event reader then
  sets `pending_user`, `executed` or `rejected` (also after approve or decline from the wallet).
  `no_trade` (advisor passed), `expired` and `failed` end a task early.
- **No double submission:** each transaction is signed and saved (`pending_tx`) before it is sent.
  After a restart the worker finds its receipt or resends the same bytes; a dropped one is rebuilt.
  Evidence and proposals are also checked on chain first.
- **Retries:** 15 s doubling to 10 min, 6 attempts, a 3-minute timeout per run, a 10-minute lease.
  Stored errors never contain the RPC URL. Run one worker per relayer key.
- **Reorganizations:** the reader saves the hash of the last block it read. If that block changed,
  it drops events from the last 64 blocks, resets those outcomes and reads them again. Deeper
  reorganizations are not handled. Use `BLOCKCHAIN_CONFIRMATIONS=3` or more on Sepolia.
- **Models:** `python -m scripts.register_models` registers FinBERT, the stock predictor (version
  from `metrics.json`, sha256 of the model file) and the mock advisor, and prints the
  `BLOCKCHAIN_*_MODEL_VERSION` settings. A step without a version setting is skipped.

### Frontend (`/vault`, B14-B16, B19)

Shown in the sidebar only when the server has the flag on; the page and ethers load only when opened.
Needs MetaMask (or any EIP-1193 wallet); on the local chain it offers to add Hardhat (chain 31337).

- **Wallet:** connect, then link by signing the one-time challenge. A warning shows if the connected
  account is not the linked one.
- **Vault:** create, get test tINR from the faucet, deposit, withdraw. All are wallet-to-contract.
- **Mandate:** prefilled from the first saved goal (monthly amount, end date) and the latest portfolio
  plan (equity limit; loss limit by risk profile). The model versions to accept come from `/status`.
- **AI trades:** ask the AI for a fund (optional stock for evidence), approve or decline pending
  trades, see evidence, and "Revoke AI" (pauses AI trading; withdrawals still work). Polls every 5 s.
- **Vault SIP:** amount, day 1-28, slippage and length. The backend SIP runner calls `runSip()` when due.

End-to-end test on a local chain (skipped otherwise):

```bash
cd blockchain && npm run node          # keep open
cd blockchain && npm run deploy:local  # second terminal
cd backend && BLOCKCHAIN_TEST_RPC=http://127.0.0.1:8545 pytest tests/test_blockchain_chain.py tests/test_blockchain_worker.py
```

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
