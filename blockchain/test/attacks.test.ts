// B21: one test per attack in checklist.md, against the real contracts.
// Each records what the attacker managed; the results feed the B22 report
// (reports/attacks.json, written by the last test).
import { mkdirSync, writeFileSync } from "node:fs";
import { expect } from "chai";
import { networkHelpers, deploy, run, openTask, evidence, buildProposal, propose, result, setMandate,
  id, MODELS, Outcome, Reason, Side, Step, U } from "./helpers.js";

const load = () => networkHelpers.loadFixture(deploy);
// lossTinr is measured in the test unless `measured` is false (then it is the bound).
const results: { attack: string; blocked: boolean; how: string; lossTinr: number; measured: boolean }[] = [];
const record = (attack: string, blocked: boolean, how: string, lossTinr = 0, measured = true) =>
  results.push({ attack, blocked, how, lossTinr, measured });

/** Vault value in tINR at the feed price: cash plus fund units. */
async function value(c: any) {
  let total = await c.inr.balanceOf(c.vaultAddr);
  for (const t of [c.equity, c.debt, c.gold]) {
    const [price] = await c.feed.price(await t.getAddress());
    total += (await t.balanceOf(c.vaultAddr)) * price / U;
  }
  return total;
}
const tinr = (x: bigint) => Number(x) / 1e6;

describe("B21 attacks", () => {
  it("stolen advisor key: worst-case churn stays inside the caps and slippage", async () => {
    const c = await load();
    // The attacker also gets the worst execution the mandate allows (1%).
    await c.market.setSkew(100);
    await setMandate(c, { requireSentiment: false, requireStock: false, maxEquityBps: 10_000 });
    const start = await value(c);
    let executed = 0;
    for (let i = 0; i < 12; i++) {
      const held = await c.equity.balanceOf(c.vaultAddr);
      const sell = i % 2 === 1 && held > 0n;
      const r = await run(c, { side: sell ? Side.SELL : Side.BUY, amount: sell ? held : 8_000n * U, confidence: 10_000 });
      if (r.outcome === Outcome.EXECUTED) executed++;
    }
    const loss = start - (await value(c));
    // Daily cap 20,000 tINR of volume at 1% worst execution: at most 200 tINR a day.
    expect(loss).to.be.lessThanOrEqual(200n * U);
    expect(executed).to.be.lessThan(12);
    expect(await c.inr.balanceOf(c.sAdvisor.address)).to.equal(0n);
    record("Stolen advisor key", false, `Bounded: ${executed} trades, then daily cap and trade count stopped it`, tinr(loss));
  });

  it("hacked backend: every backend key together still can't withdraw or change terms", async () => {
    const c = await load();
    const backend = [c.sSentiment, c.sStock, c.sAdvisor, c.runner];
    for (const who of backend) {
      await expect(c.vault.connect(who).withdraw(await c.inr.getAddress(), 1n)).to.be.revertedWith("not owner");
      await expect(c.mandates.connect(who).setMandate(c.vaultAddr, { ...c.mandate, perTradeCap: 10n ** 30n }, c.funds, c.models))
        .to.be.revertedWith("not vault owner");
      await expect(c.mandates.connect(who).acceptModel(c.vaultAddr, id("x"), true)).to.be.revertedWith("not vault owner");
      await expect(c.vault.connect(who).setAiPaused(false)).to.be.revertedWith("not owner");
    }
    // With the evidence keys too, a proposal over the cap is still rejected.
    const r = await run(c, { amount: 50_000n * U, confidence: 10_000 });
    expect(r.reason).to.equal(Reason.OVER_TRADE_CAP);
    // Same bound as a stolen advisor key: at most 1% of the 20,000 tINR daily cap.
    record("Hacked backend (all its keys)", false, "Bounded like a stolen advisor key; no withdrawal or term change possible", 200, false);
  });

  it("replay: a sent proposal or its nonce can't be used again", async () => {
    const c = await load();
    const t1 = await openTask(c);
    await evidence(c, t1, "sentiment"); await evidence(c, t1, "stock");
    const p = await buildProposal(c, t1);
    await propose(c, p);
    await expect(propose(c, p)).to.be.revertedWith("task closed");
    const t2 = await openTask(c);
    await evidence(c, t2, "sentiment"); await evidence(c, t2, "stock");
    await expect(propose(c, await buildProposal(c, t2, { nonce: p.nonce }))).to.be.revertedWith("nonce used");
    record("Replay", true, "Reverted: task closed / nonce used");
  });

  it("over limit: per-trade cap rejects; above the sign limit waits for the owner", async () => {
    const c = await load();
    expect((await run(c, { amount: 10_001n * U })).reason).to.equal(Reason.OVER_TRADE_CAP);
    const big = await run(c, { amount: 9_000n * U });
    expect(big.outcome).to.equal(Outcome.PENDING);
    record("Over the limits", true, "Rejected OVER_TRADE_CAP; above the sign limit goes to the owner");
  });

  it("bad fund: a fund outside the mandate is rejected", async () => {
    const c = await load();
    const r = await run(c, {}, c.gd); // gold is not in the mandate's funds
    expect(r.reason).to.equal(Reason.FUND_NOT_ALLOWED);
    record("Fund not allowed", true, "Rejected FUND_NOT_ALLOWED");
  });

  it("old or changed model: revoked or unaccepted versions are refused; versions can't be edited", async () => {
    const c = await load();
    await c.registry.revoke(c.models[2]); // the advisor version
    expect((await run(c)).reason).to.equal(Reason.MODEL_INACTIVE);
    const v2 = { id: MODELS.advisor.id, version: id("v2") };
    await c.registry.register(v2.id, v2.version, Step.ADVISOR, c.sAdvisor.address, id("new weights"));
    expect((await run(c, { modelId: v2.id, modelVersion: v2.version })).reason).to.equal(Reason.MODEL_NOT_ACCEPTED);
    await expect(c.registry.register(v2.id, v2.version, Step.ADVISOR, c.attacker.address, id("swapped")))
      .to.be.revertedWith("already registered");
    record("Old or changed model", true, "Rejected MODEL_INACTIVE / MODEL_NOT_ACCEPTED; a version can't be re-registered");
  });

  it("stale price: AI trades stop once a price is over a day old", async () => {
    const c = await load();
    await networkHelpers.time.increase(86_401);
    expect((await run(c)).reason).to.equal(Reason.STALE_PRICE);
    record("Stale price", true, "Rejected STALE_PRICE");
  });

  it("price manipulation: moves are capped at 20% an hour, but a moved price is believed", async () => {
    const c = await load();
    await networkHelpers.time.increase(3601);
    await expect(c.feed.setPrice(c.eq, 50n * U)).to.be.revertedWith("move too large");
    await c.feed.setPrice(c.eq, 120n * U); // the most the feed admin can do in one hour
    await expect(c.feed.setPrice(c.eq, 144n * U)).to.be.revertedWith("too soon");
    await setMandate(c, { requireSentiment: false, requireStock: false });
    const r = await run(c, { amount: 5_000n * U, confidence: 10_000 });
    expect(r.outcome).to.equal(Outcome.EXECUTED);
    // Buying at a price 20% too high: the owner over-paid by 5,000 x (1 - 100/120).
    const loss = 5_000 * (1 - 100 / 120);
    record("Price manipulation (feed admin)", false, "Not blocked: moves capped at 20%/hour; a trusted-feed limit", Math.round(loss), false);
  });

  it("missing evidence: a required step that was never submitted rejects the trade", async () => {
    const c = await load();
    const taskId = await openTask(c);
    await evidence(c, taskId, "sentiment");
    await propose(c, await buildProposal(c, taskId));
    expect((await result(c, taskId)).reason).to.equal(Reason.MISSING_EVIDENCE);
    record("Missing evidence", true, "Rejected MISSING_EVIDENCE");
  });

  it("backend switched off: the owner can still withdraw, trade and run the SIP", async () => {
    const c = await load();
    await run(c);
    // Nothing below uses a backend key.
    await c.vault.connect(c.user).ownerTrade(c.db, Side.BUY, 1_000n * U, 9n * U);
    await c.vault.connect(c.user).setSip(c.db, 500n * U, 1, 100, (await networkHelpers.time.latest()) + 400 * 86400);
    await networkHelpers.time.increase(32 * 86400);
    await c.feed.setPrice(c.db, 100n * U);
    await c.vault.connect(c.user).runSip();
    await c.vault.connect(c.user).withdraw(await c.inr.getAddress(), await c.inr.balanceOf(c.vaultAddr));
    expect(await c.inr.balanceOf(c.vaultAddr)).to.equal(0n);
    record("Backend switched off", true, "Owner withdraws, trades and runs the SIP with no backend");
  });

  after(() => {
    mkdirSync("reports", { recursive: true });
    writeFileSync("reports/attacks.json", JSON.stringify(results, null, 2) + "\n");
  });
});
