import { network } from "hardhat";

export const connection = await network.getOrCreate();
export const { ethers, networkHelpers } = connection;

export const U = 1_000_000n;
export const id = (s: string) => ethers.id(s);
export const Side = { BUY: 0, SELL: 1 };
export const Step = { SENTIMENT: 1, STOCK: 2, ADVISOR: 3 };
export const Status = { OK: 0, NO_DATA: 1, FALLBACK: 2 };
export const Outcome = { OPEN: 1n, PENDING: 2n, EXECUTED: 3n, REJECTED: 4n };
export const Reason = Object.fromEntries(
  ["NONE", "NO_MANDATE", "OUTSIDE_DATES", "AI_PAUSED", "FUND_NOT_ALLOWED", "BAD_AMOUNT", "OVER_TRADE_CAP",
    "OVER_DAILY_CAP", "OVER_MONTHLY_CAP", "TOO_MANY_TRADES", "OVER_EQUITY_LIMIT", "STALE_PRICE", "LOSS_LIMIT",
    "MODEL_INACTIVE", "MODEL_NOT_ACCEPTED", "MISSING_EVIDENCE", "NO_DATA_NOT_ALLOWED", "EVIDENCE_MISMATCH",
    "EVIDENCE_STALE", "EXPIRED", "EXECUTION_FAILED", "USER_DECLINED"].map((n, i) => [n, BigInt(i)]),
) as Record<string, bigint>;

const f = (type: string, name: string) => ({ type, name });
export const TYPES = {
  Evidence: [f("bytes32", "taskId"), f("uint8", "step"), f("uint8", "status"), f("bytes32", "modelId"),
    f("bytes32", "modelVersion"), f("bytes32", "inputHash"), f("bytes32", "outputHash"), f("int32", "score"),
    f("uint32", "count"), f("uint32", "horizonDays"), f("uint64", "asOf")],
  Proposal: [f("bytes32", "taskId"), f("address", "vault"), f("address", "fund"), f("uint8", "side"),
    f("uint256", "amount"), f("uint256", "minimumReceived"), f("uint16", "confidence"), f("bytes32", "modelId"),
    f("bytes32", "modelVersion"), f("bytes32", "inputHash"), f("bytes32", "evidenceHash"),
    f("bytes32", "explanationHash"), f("uint256", "nonce"), f("uint64", "deadline")],
};

export const MODELS = {
  sentiment: { id: id("ProsusAI/finbert"), version: id("v1") },
  stock: { id: id("mock-stock"), version: id("v1") },
  advisor: { id: id("mock-advisor"), version: id("v1") },
};
export const keyOf = (m: { id: string; version: string }) =>
  ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["bytes32", "bytes32"], [m.id, m.version]));

export async function deploy() {
  const [admin, user, attacker, sSentiment, sStock, sAdvisor, runner] = await ethers.getSigners();
  const inr = await ethers.deployContract("TestToken", ["Test INR", "tINR", true]);
  const equity = await ethers.deployContract("TestToken", ["Test Equity Fund", "tEquityFund", false]);
  const debt = await ethers.deployContract("TestToken", ["Test Debt Fund", "tDebtFund", false]);
  const gold = await ethers.deployContract("TestToken", ["Test Gold Fund", "tGoldFund", false]);
  const feed = await ethers.deployContract("MockPriceFeed");
  const market = await ethers.deployContract("MockFundMarket", [await inr.getAddress(), await feed.getAddress()]);
  for (const t of [inr, equity, debt, gold]) await t.setMinter(await market.getAddress(), true);
  await market.addFund(await equity.getAddress(), true);
  for (const t of [debt, gold]) await market.addFund(await t.getAddress(), false);
  for (const t of [equity, debt, gold]) await feed.setPrice(await t.getAddress(), 100n * U);

  const registry = await ethers.deployContract("ModelRegistry");
  const mandates = await ethers.deployContract("MandateManager");
  const manager = await ethers.deployContract("AITaskManager", [await registry.getAddress(), await mandates.getAddress()]);
  const factory = await ethers.deployContract("VaultFactory",
    [await manager.getAddress(), await mandates.getAddress(), await market.getAddress()]);
  await registry.register(MODELS.sentiment.id, MODELS.sentiment.version, Step.SENTIMENT, sSentiment.address, id("a"));
  await registry.register(MODELS.stock.id, MODELS.stock.version, Step.STOCK, sStock.address, id("b"));
  await registry.register(MODELS.advisor.id, MODELS.advisor.version, Step.ADVISOR, sAdvisor.address, id("c"));

  await factory.connect(user).createVault();
  const vault: any = await ethers.getContractAt("InvestmentVault", await factory.vaultOf(user.address));
  const vaultAddr = await vault.getAddress();
  await inr.connect(user).faucet(100_000n * U);
  await inr.connect(user).approve(vaultAddr, ethers.MaxUint256);
  await vault.connect(user).deposit(100_000n * U);

  const now = await networkHelpers.time.latest();
  const mandate = {
    start: now, end: now + 365 * 86400, perTradeCap: 10_000n * U, dailyCap: 20_000n * U, monthlyCap: 50_000n * U,
    userSignAbove: 8_000n * U, maxEquityBps: 4000, maxSlippageBps: 100, maxLossBps: 1000, maxTradesPerDay: 5,
    confidenceThreshold: 6000, requireSentiment: true, requireStock: true, askUserOnNoData: true,
  };
  const eq = await equity.getAddress(), db = await debt.getAddress(), gd = await gold.getAddress();
  const c: any = { admin, user, attacker, sSentiment, sStock, sAdvisor, runner, inr, equity, debt, gold, feed, market,
    registry, mandates, manager, factory, vault, vaultAddr, mandate, eq, db, gd, nonce: 0n };
  c.funds = [eq, db];
  c.models = [MODELS.sentiment, MODELS.stock, MODELS.advisor].map(keyOf);
  await setMandate(c);
  return c;
}

export async function setMandate(c: any, over: object = {}, models = c.models) {
  return c.mandates.connect(c.user).setMandate(c.vaultAddr, { ...c.mandate, ...over }, c.funds, models);
}

export async function domain(c: any) {
  return { name: "IntelliVest", version: "1", chainId: (await ethers.provider.getNetwork()).chainId,
    verifyingContract: await c.manager.getAddress() };
}

export async function openTask(c: any, fund = c.eq, vault = c.vaultAddr) {
  const deadline = (await networkHelpers.time.latest()) + 3600;
  const rc = await (await c.manager.openTask(vault, fund, deadline)).wait();
  const taskId = rc.logs.map((l: any) => c.manager.interface.parseLog(l)).find((l: any) => l?.name === "TaskOpened").args.taskId;
  return taskId as string;
}

export async function evidence(c: any, taskId: string, kind: "sentiment" | "stock", over: any = {}, signer?: any) {
  const e = { taskId, step: kind === "sentiment" ? Step.SENTIMENT : Step.STOCK, status: Status.OK,
    modelId: MODELS[kind].id, modelVersion: MODELS[kind].version, inputHash: id("in"), outputHash: id("out"),
    score: kind === "sentiment" ? -1500 : 6200, count: 5, horizonDays: kind === "stock" ? 1 : 0,
    asOf: await networkHelpers.time.latest(), ...over };
  const s = signer ?? (kind === "sentiment" ? c.sSentiment : c.sStock);
  const sig = await s.signTypedData(await domain(c), { Evidence: TYPES.Evidence }, e);
  return c.manager.connect(c.runner).submitEvidence(e, sig);
}

export async function buildProposal(c: any, taskId: string, over: any = {}) {
  const task = await c.manager.tasks(taskId);
  return { taskId, vault: task.vault, fund: task.fund, side: Side.BUY, amount: 5_000n * U, minimumReceived: 0n,
    confidence: 8000, modelId: MODELS.advisor.id, modelVersion: MODELS.advisor.version, inputHash: id("in"),
    evidenceHash: task.evidenceHash, explanationHash: id("why"), nonce: c.nonce++,
    deadline: (await networkHelpers.time.latest()) + 3600, ...over };
}

export async function propose(c: any, p: any, opts: any = {}) {
  const sig = await (opts.signer ?? c.sAdvisor).signTypedData(opts.domain ?? await domain(c), { Proposal: TYPES.Proposal }, p);
  return c.manager.connect(c.runner).submitProposal(opts.sent ?? p, sig);
}

/** Opens a task with both evidence steps and submits a proposal. */
export async function run(c: any, over: any = {}, fund = c.eq) {
  const taskId = await openTask(c, fund);
  await evidence(c, taskId, "sentiment");
  await evidence(c, taskId, "stock");
  await propose(c, await buildProposal(c, taskId, over));
  return { taskId, ...(await result(c, taskId)) };
}

export async function result(c: any, taskId: string) {
  const t = await c.manager.tasks(taskId);
  return { outcome: t.outcome as bigint, reason: t.reason as bigint };
}
