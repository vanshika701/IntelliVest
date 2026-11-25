import { expect } from "chai";
import { ethers, networkHelpers, deploy, run, Side, U } from "./helpers.js";

const load = () => networkHelpers.loadFixture(deploy);

describe("Withdrawals", () => {
  it("work when paused, revoked, expired, with stale prices and revoked models", async () => {
    const c = await load();
    await run(c);
    await c.vault.connect(c.user).setAiPaused(true);
    await c.mandates.connect(c.user).revokeMandate(c.vaultAddr);
    await c.registry.revoke(c.models[2]);
    await networkHelpers.time.increase(400 * 86400);
    await c.vault.connect(c.user).withdraw(await c.inr.getAddress(), 95_000n * U);
    await c.vault.connect(c.user).withdraw(c.eq, 50n * U);
    expect(await c.inr.balanceOf(c.user.address)).to.equal(95_000n * U);
    expect(await c.equity.balanceOf(c.user.address)).to.equal(50n * U);
  });

  it("are refused to everyone else, including the project admin and the advisor", async () => {
    const c = await load();
    for (const who of [c.admin, c.attacker, c.sAdvisor, c.runner]) {
      await expect(c.vault.connect(who).withdraw(await c.inr.getAddress(), 1n)).to.be.revertedWith("not owner");
      await expect(c.vault.connect(who).executeAi(ethers.ZeroHash, c.eq, 0, 1n, 0n)).to.be.revertedWith("not task manager");
      await expect(c.vault.connect(who).ownerTrade(c.eq, 0, 1n, 0n)).to.be.revertedWith("not owner");
      await expect(c.vault.connect(who).setAiPaused(false)).to.be.revertedWith("not owner");
      await expect(c.vault.connect(who).setSip(c.eq, 1n, 1, 100, 9999999999n)).to.be.revertedWith("not owner");
      await expect(c.mandates.connect(who).setMandate(c.vaultAddr, c.mandate, c.funds, c.models)).to.be.revertedWith("not vault owner");
      await expect(c.mandates.connect(who).revokeMandate(c.vaultAddr)).to.be.revertedWith("not vault owner");
    }
  });

  it("exposes no function that takes a destination for funds", async () => {
    const c = await load();
    const names = c.vault.interface.fragments.filter((f: any) => f.type === "function" && !["view", "pure"].includes(f.stateMutability)).map((f: any) => f.name).sort();
    expect(names).to.deep.equal(["cancelSip", "deposit", "executeAi", "ownerTrade", "runSip", "setAiPaused", "setSip", "withdraw"]);
  });
});

describe("Owner and factory", () => {
  it("lets the owner trade directly without the AI", async () => {
    const c = await load();
    await c.vault.connect(c.user).ownerTrade(c.gd, Side.BUY, 1_000n * U, 10n * U);
    expect(await c.gold.balanceOf(c.vaultAddr)).to.equal(10n * U);
  });
  it("allows one vault per wallet", async () => {
    const c = await load();
    await expect(c.factory.connect(c.user).createVault()).to.be.revertedWith("vault exists");
  });
  it("limits how fast test prices can move", async () => {
    const c = await load();
    await networkHelpers.time.increase(3601);
    await expect(c.feed.setPrice(c.eq, 79n * U)).to.be.revertedWith("move too large");
    await c.feed.setPrice(c.eq, 80n * U);
    await expect(c.feed.setPrice(c.eq, 81n * U)).to.be.revertedWith("too soon");
    await expect(c.feed.connect(c.attacker).setPrice(c.eq, 80n * U)).to.be.revertedWithCustomError(c.feed, "OwnableUnauthorizedAccount");
  });
});

describe("SIP", () => {
  for (const day of [1, 15, 28]) {
    it(`schedules day ${day} correctly across three years, including leap days`, async () => {
      const c = await load();
      let t = await networkHelpers.time.latest();
      for (let i = 0; i < 37; i++) {
        await c.vault.connect(c.user).setSip(c.db, 1_000n * U, day, 100, BigInt(t) + 10_000n * 86400n);
        const d = new Date((await networkHelpers.time.latest()) * 1000);
        let want = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), day);
        if (d.getUTCDate() >= day) want = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, day);
        expect((await c.vault.sip()).nextRun).to.equal(BigInt(want / 1000));
        await networkHelpers.time.increase(30 * 86400 + 7 * 3600);
        t = await networkHelpers.time.latest();
      }
    });
  }

  it("runs for anyone when due, once, with no choice of amount", async () => {
    const c = await load();
    const end = (await networkHelpers.time.latest()) + 400 * 86400;
    await c.vault.connect(c.user).setSip(c.db, 1_000n * U, 1, 100, end);
    await expect(c.vault.connect(c.runner).runSip()).to.be.revertedWith("sip not due");
    await networkHelpers.time.increaseTo((await c.vault.sip()).nextRun);
    await expect(c.vault.connect(c.runner).runSip()).to.be.revertedWith("stale price");
    await c.feed.setPrice(c.db, 100n * U);
    await c.vault.connect(c.runner).runSip();
    expect(await c.debt.balanceOf(c.vaultAddr)).to.equal(10n * U);
    await expect(c.vault.connect(c.runner).runSip()).to.be.revertedWith("sip not due");
    await c.vault.connect(c.user).cancelSip();
    await expect(c.vault.connect(c.runner).runSip()).to.be.revertedWith("sip not due");
  });
});
