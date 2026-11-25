import { expect } from "chai";
import { ethers, networkHelpers, deploy, run, openTask, evidence, buildProposal, propose, result, setMandate, keyOf,
  domain, id, MODELS, Outcome, Reason, Side, Status, Step, U } from "./helpers.js";

const load = () => networkHelpers.loadFixture(deploy);
const rejected = (r: any, name: string) => {
  expect(r.outcome).to.equal(Outcome.REJECTED);
  expect(r.reason).to.equal(Reason[name]);
};

describe("AI trades", () => {
  it("executes a valid buy and a valid sell", async () => {
    const c = await load();
    expect((await run(c)).outcome).to.equal(Outcome.EXECUTED);
    expect(await c.equity.balanceOf(c.vaultAddr)).to.equal(50n * U);
    expect(await c.inr.balanceOf(c.vaultAddr)).to.equal(95_000n * U);
    expect((await run(c, { side: Side.SELL, amount: 20n * U })).outcome).to.equal(Outcome.EXECUTED);
    expect(await c.inr.balanceOf(c.vaultAddr)).to.equal(97_000n * U);
  });

  it("emits evidence and the trade", async () => {
    const c = await load();
    const taskId = await openTask(c);
    await expect(evidence(c, taskId, "sentiment")).to.emit(c.manager, "EvidenceSubmitted");
    await evidence(c, taskId, "stock");
    await expect(propose(c, await buildProposal(c, taskId))).to.emit(c.vault, "Traded").and.to.emit(c.manager, "TaskResult");
  });

  for (const [name, over, fund] of [
    ["OVER_TRADE_CAP", { amount: 10_001n * U }, "eq"],
    ["BAD_AMOUNT", { amount: 0n }, "eq"],
    ["BAD_AMOUNT", { amount: 100_001n * U }, "eq"],
    ["BAD_AMOUNT", { amount: ethers.MaxUint256, side: Side.SELL }, "eq"],
    ["FUND_NOT_ALLOWED", {}, "gd"],
    ["EXECUTION_FAILED", { minimumReceived: 51n * U }, "eq"],
    ["EVIDENCE_MISMATCH", { evidenceHash: id("other") }, "eq"],
    ["EXPIRED", { deadline: 1 }, "eq"],
  ] as [string, any, string][]) {
    it(`rejects and records ${name} ${JSON.stringify(Object.keys(over))}`, async () => {
      const c = await load();
      rejected(await run(c, over, c[fund]), name);
      expect(await c.inr.balanceOf(c.vaultAddr)).to.equal(100_000n * U);
    });
  }

  it("enforces daily, monthly and trade-count caps, and resets the daily one", async () => {
    const c = await load();
    await setMandate(c, { maxEquityBps: 10_000, dailyCap: 10_000n * U, monthlyCap: 12_000n * U });
    await run(c); await run(c);
    rejected(await run(c), "OVER_DAILY_CAP");
    await networkHelpers.time.increaseTo((Math.floor((await networkHelpers.time.latest()) / 86400) + 1) * 86400);
    await c.feed.setPrice(c.eq, 100n * U); await c.feed.setPrice(c.db, 100n * U);
    const r = await run(c);
    // A new 30-day period may start on the same boundary; either way only one result is valid.
    const now = await networkHelpers.time.latest();
    if (Math.floor(now / (30 * 86400)) === Math.floor((now - 86400) / (30 * 86400))) rejected(r, "OVER_MONTHLY_CAP");
    else expect(r.outcome).to.equal(Outcome.EXECUTED);
    await setMandate(c, { maxTradesPerDay: 0 });
    rejected(await run(c), "TOO_MANY_TRADES");
  });

  it("enforces the equity limit on equity only", async () => {
    const c = await load();
    await setMandate(c, { maxEquityBps: 800 });
    expect((await run(c)).outcome).to.equal(Outcome.EXECUTED);
    rejected(await run(c), "OVER_EQUITY_LIMIT");
    expect((await run(c, {}, c.db)).outcome).to.equal(Outcome.EXECUTED);
  });

  it("enforces dates, revocation and pause", async () => {
    const c = await load();
    const now = await networkHelpers.time.latest();
    await setMandate(c, { start: now + 10_000 });
    rejected(await run(c), "OUTSIDE_DATES");
    await setMandate(c);
    await c.vault.connect(c.user).setAiPaused(true);
    rejected(await run(c), "AI_PAUSED");
    await c.vault.connect(c.user).setAiPaused(false);
    await c.mandates.connect(c.user).revokeMandate(c.vaultAddr);
    rejected(await run(c), "NO_MANDATE");
  });

  it("enforces maximum slippage even when the AI asks for no minimum", async () => {
    const c = await load();
    await c.market.setSkew(200);
    rejected(await run(c), "EXECUTION_FAILED");
    await c.market.setSkew(50);
    expect((await run(c)).outcome).to.equal(Outcome.EXECUTED);
  });

  it("rejects a stale price", async () => {
    const c = await load();
    await networkHelpers.time.increase(86401);
    rejected(await run(c), "STALE_PRICE");
  });

  it("rejects when another held fund has a stale price", async () => {
    const c = await load();
    await run(c);
    await networkHelpers.time.increase(86401);
    await c.feed.setPrice(c.db, 100n * U);
    rejected(await run(c, {}, c.db), "STALE_PRICE");
  });

  it("pauses itself at the loss limit until the owner resumes", async () => {
    const c = await load();
    await setMandate(c, { maxEquityBps: 10_000, maxLossBps: 100, userSignAbove: 10_000n * U });
    await run(c, { amount: 10_000n * U });
    await networkHelpers.time.increase(3601);
    await c.feed.setPrice(c.eq, 80n * U);
    rejected(await run(c), "LOSS_LIMIT");
    expect(await c.vault.aiPaused()).to.equal(true);
    rejected(await run(c), "AI_PAUSED");
    await c.vault.connect(c.user).setAiPaused(false);
    expect((await run(c)).outcome).to.equal(Outcome.EXECUTED);
  });
});

describe("Asking the user", () => {
  it("waits on low confidence or a large trade; confidence never lifts a limit", async () => {
    const c = await load();
    expect((await run(c, { confidence: 5999 })).outcome).to.equal(Outcome.PENDING);
    expect((await run(c, { amount: 9_000n * U })).outcome).to.equal(Outcome.PENDING);
    rejected(await run(c, { amount: 10_001n * U, confidence: 10_000 }), "OVER_TRADE_CAP");
  });

  it("lets only the owner approve or decline, once", async () => {
    const c = await load();
    const { taskId } = await run(c, { confidence: 0 });
    await expect(c.manager.connect(c.attacker).approve(taskId)).to.be.revertedWith("not vault owner");
    await expect(c.manager.connect(c.admin).approve(taskId)).to.be.revertedWith("not vault owner");
    await c.manager.connect(c.user).approve(taskId);
    expect((await result(c, taskId)).outcome).to.equal(Outcome.EXECUTED);
    await expect(c.manager.connect(c.user).approve(taskId)).to.be.revertedWith("not pending");
    const second = await run(c, { confidence: 0 });
    await c.manager.connect(c.user).decline(second.taskId);
    rejected(await result(c, second.taskId), "USER_DECLINED");
  });

  it("checks limits, models and deadline again on approval", async () => {
    const c = await load();
    const a = await run(c, { confidence: 0 });
    await setMandate(c, { perTradeCap: 1n });
    await c.manager.connect(c.user).approve(a.taskId);
    rejected(await result(c, a.taskId), "OVER_TRADE_CAP");
    await setMandate(c);
    const b = await run(c, { confidence: 0 });
    await c.registry.revoke(keyOf(MODELS.sentiment));
    await c.manager.connect(c.user).approve(b.taskId);
    rejected(await result(c, b.taskId), "MODEL_INACTIVE");
  });

  it("expires pending and open tasks", async () => {
    const c = await load();
    const p = await run(c, { confidence: 0 });
    const open = await openTask(c);
    await expect(c.manager.expire(open)).to.be.revertedWith("not expired");
    await networkHelpers.time.increase(3700);
    await c.manager.expire(open); await c.manager.expire(p.taskId);
    rejected(await result(c, open), "EXPIRED"); rejected(await result(c, p.taskId), "EXPIRED");
  });
});

describe("Evidence and models", () => {
  it("rejects missing evidence when the mandate requires it", async () => {
    const c = await load();
    const taskId = await openTask(c);
    await evidence(c, taskId, "sentiment");
    await propose(c, await buildProposal(c, taskId));
    rejected(await result(c, taskId), "MISSING_EVIDENCE");
  });

  for (const status of [Status.NO_DATA, Status.FALLBACK]) {
    it(`status ${status} asks the user or is rejected, as the mandate says`, async () => {
      const c = await load();
      for (const ask of [true, false]) {
        await setMandate(c, { askUserOnNoData: ask });
        const taskId = await openTask(c);
        await evidence(c, taskId, "sentiment", { status });
        await evidence(c, taskId, "stock");
        await propose(c, await buildProposal(c, taskId));
        if (ask) expect((await result(c, taskId)).outcome).to.equal(Outcome.PENDING);
        else rejected(await result(c, taskId), "NO_DATA_NOT_ALLOWED");
      }
    });
  }

  it("needs the owner to accept a new model version", async () => {
    const c = await load();
    const v2 = { id: MODELS.advisor.id, version: id("v2") };
    await c.registry.register(v2.id, v2.version, Step.ADVISOR, c.sAdvisor.address, id("x"));
    rejected(await run(c, { modelVersion: v2.version }), "MODEL_NOT_ACCEPTED");
    await expect(c.mandates.connect(c.admin).acceptModel(c.vaultAddr, keyOf(v2), true)).to.be.revertedWith("not vault owner");
    await c.mandates.connect(c.user).acceptModel(c.vaultAddr, keyOf(v2), true);
    expect((await run(c, { modelVersion: v2.version })).outcome).to.equal(Outcome.EXECUTED);
  });

  it("rejects evidence from a model the owner did not accept", async () => {
    const c = await load();
    await setMandate(c, {}, [keyOf(MODELS.stock), keyOf(MODELS.advisor)]);
    rejected(await run(c), "MODEL_NOT_ACCEPTED");
  });

  it("rejects old evidence", async () => {
    const c = await load();
    const taskId = await openTask(c);
    await evidence(c, taskId, "sentiment", { asOf: (await networkHelpers.time.latest()) - 8 * 86400 });
    await evidence(c, taskId, "stock");
    await propose(c, await buildProposal(c, taskId));
    rejected(await result(c, taskId), "EVIDENCE_STALE");
  });

  it("refuses bad evidence submissions", async () => {
    const c = await load();
    const taskId = await openTask(c);
    await expect(evidence(c, taskId, "sentiment", {}, c.attacker)).to.be.revertedWith("bad signature");
    await expect(evidence(c, taskId, "sentiment", {}, c.sStock)).to.be.revertedWith("bad signature");
    await expect(evidence(c, taskId, "sentiment", { score: 10_001 })).to.be.revertedWith("bad score");
    await expect(evidence(c, taskId, "stock", { score: -1 })).to.be.revertedWith("bad score");
    await expect(evidence(c, taskId, "sentiment", { modelVersion: id("zz") })).to.be.revertedWith("model not active");
    await expect(evidence(c, taskId, "sentiment", { asOf: 9999999999 })).to.be.revertedWith("bad evidence");
    await evidence(c, taskId, "sentiment");
    await expect(evidence(c, taskId, "sentiment")).to.be.revertedWith("duplicate step");
    await networkHelpers.time.increase(3700);
    await expect(evidence(c, taskId, "stock")).to.be.revertedWith("task closed");
  });

  it("fixes a model version once registered, and only the admin registers", async () => {
    const c = await load();
    await expect(c.registry.register(MODELS.advisor.id, MODELS.advisor.version, 3, c.attacker.address, id("x")))
      .to.be.revertedWith("already registered");
    await expect(c.registry.connect(c.attacker).register(id("m"), id("v"), 3, c.attacker.address, id("x")))
      .to.be.revertedWithCustomError(c.registry, "OwnableUnauthorizedAccount");
  });
});

describe("Attacks on proposals", () => {
  async function ready(c: any) {
    const taskId = await openTask(c);
    await evidence(c, taskId, "sentiment"); await evidence(c, taskId, "stock");
    return taskId;
  }

  it("refuses forged, altered, wrong-chain and wrong-contract proposals without ending the task", async () => {
    const c = await load();
    const taskId = await ready(c);
    const p = await buildProposal(c, taskId);
    const d = await domain(c);
    await expect(propose(c, p, { signer: c.attacker })).to.be.revertedWith("bad signature");
    await expect(propose(c, p, { sent: { ...p, amount: 9_000n * U } })).to.be.revertedWith("bad signature");
    await expect(propose(c, p, { domain: { ...d, chainId: 1n } })).to.be.revertedWith("bad signature");
    await expect(propose(c, p, { domain: { ...d, verifyingContract: c.eq } })).to.be.revertedWith("bad signature");
    await expect(propose(c, { ...p, fund: c.db })).to.be.revertedWith("wrong task");
    await expect(propose(c, { ...p, modelId: MODELS.stock.id, modelVersion: MODELS.stock.version })).to.be.revertedWith("not an advisor");
    await propose(c, p);
    expect((await result(c, taskId)).outcome).to.equal(Outcome.EXECUTED);
  });

  it("refuses replays and reused nonces", async () => {
    const c = await load();
    const t1 = await ready(c);
    const p = await buildProposal(c, t1);
    await propose(c, p);
    await expect(propose(c, p)).to.be.revertedWith("task closed");
    const t2 = await ready(c);
    await expect(propose(c, await buildProposal(c, t2, { nonce: p.nonce }))).to.be.revertedWith("nonce used");
  });

  it("refuses too little gas instead of recording a false rejection", async () => {
    const c = await load();
    const taskId = await ready(c);
    const p = await buildProposal(c, taskId);
    const { TYPES } = await import("./helpers.js");
    const sig = await c.sAdvisor.signTypedData(await domain(c), { Proposal: TYPES.Proposal }, p);
    await expect(c.manager.submitProposal(p, sig, { gasLimit: 1_500_000 })).to.revert(ethers);
    expect((await result(c, taskId)).outcome).to.equal(Outcome.OPEN);
  });

  it("caps what a stolen advisor key can do in a day", async () => {
    const c = await load();
    await setMandate(c, { requireSentiment: false, requireStock: false, maxEquityBps: 10_000 });
    for (let i = 0; i < 8; i++) await run(c, { amount: 8_000n * U, confidence: 10_000 });
    expect(await c.inr.balanceOf(c.vaultAddr)).to.equal(84_000n * U);
    expect(await c.equity.balanceOf(c.vaultAddr)).to.equal(160n * U);
    expect(await c.inr.balanceOf(c.sAdvisor.address)).to.equal(0n);
  });
});
