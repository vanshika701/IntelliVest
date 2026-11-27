// B22: gas, latency and wrongly blocked valid trades for the vault design,
// measured on Hardhat's in-process chain with the mock advisor.
//   npm test          (writes reports/attacks.json)
//   npm run compare   (writes reports/comparison.json)
// The "no limits" and "backend-only limits" columns in the report are
// modelled from the same attacks, not deployed.
import { readFileSync, writeFileSync } from "node:fs";
import { ethers, deploy, openTask, evidence, buildProposal, propose, result, setMandate, Outcome, Side, U } from "../test/helpers.js";

const c: any = await deploy();
await setMandate(c, { maxEquityBps: 10_000, dailyCap: 10_000_000n * U, monthlyCap: 10_000_000n * U, maxTradesPerDay: 1000 });
// Enough cash that no valid trade fails for lack of tINR.
for (let i = 0; i < 4; i++) {
  await c.inr.connect(c.user).faucet(100_000n * U);
  await c.vault.connect(c.user).deposit(100_000n * U);
}

const gas: Record<string, bigint[]> = { openTask: [], sentimentEvidence: [], stockEvidence: [], proposalExecuted: [], approve: [] };
const used = async (tx: any) => (await tx.wait()).gasUsed as bigint;
const ms: number[] = [];
let valid = 0;
let wronglyBlocked = 0;

// 40 valid AI trades: amounts inside every limit, confidence above the threshold.
for (let i = 0; i < 40; i++) {
  const start = performance.now();
  const fund = i % 2 ? c.db : c.eq;
  const taskId = await openTask(c, fund);
  gas.sentimentEvidence.push(await used(await evidence(c, taskId, "sentiment")));
  gas.stockEvidence.push(await used(await evidence(c, taskId, "stock")));
  const amount = BigInt(100 + ((i * 937) % 7_800)) * U; // 100..7,900 tINR, under the 8,000 sign limit
  const p = await buildProposal(c, taskId, { side: Side.BUY, amount, confidence: 6_000 + (i % 40) * 100 });
  gas.proposalExecuted.push(await used(await propose(c, p)));
  ms.push(performance.now() - start);
  valid++;
  if ((await result(c, taskId)).outcome !== Outcome.EXECUTED) wronglyBlocked++;
}

// openTask gas, measured directly (the helper above doesn't return its receipt).
for (let i = 0; i < 5; i++) {
  const now = BigInt((await ethers.provider.getBlock("latest"))!.timestamp);
  gas.openTask.push(await used(await c.manager.openTask(c.vaultAddr, c.eq, now + 3600n)));
}

// Approval path: a trade above the sign limit, approved by the owner.
for (let i = 0; i < 5; i++) {
  const taskId = await openTask(c);
  await evidence(c, taskId, "sentiment");
  await evidence(c, taskId, "stock");
  await propose(c, await buildProposal(c, taskId, { amount: 9_000n * U }));
  gas.approve.push(await used(await c.manager.connect(c.user).approve(taskId)));
}

const avg = (xs: bigint[]) => Number(xs.reduce((a, b) => a + b, 0n) / BigInt(xs.length));
const gasAvg = Object.fromEntries(Object.entries(gas).map(([k, v]) => [k, avg(v)]));
const perTrade = gasAvg.openTask + gasAvg.sentimentEvidence + gasAvg.stockEvidence + gasAvg.proposalExecuted;
const attacks = JSON.parse(readFileSync("reports/attacks.json", "utf8"));

const report = {
  generatedAt: new Date().toISOString(),
  advisor: "mock (fixed rules); results are not about advice quality",
  network: "Hardhat in-process (automine); Sepolia latency is block-time bound",
  validTrades: valid,
  wronglyBlocked,
  gasAverage: gasAvg,
  gasPerAutoTrade: perTrade,
  localMsPerTrade: Math.round(ms.reduce((a, b) => a + b, 0) / ms.length),
  sepoliaEstimate: "4 transactions per trade, each ~12 s block: about 50 s from request to execution",
  attacks,
};
writeFileSync("reports/comparison.json", JSON.stringify(report, null, 2) + "\n");
console.log(report);
